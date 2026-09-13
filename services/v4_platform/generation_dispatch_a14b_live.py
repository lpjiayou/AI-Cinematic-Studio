"""D1's explicit live configuration type; validation never grants execution.

The v2 structural compiler is reused through a private projection. Neither a
v1 test profile nor a v2 offline candidate is accepted by this entry point.
Independent Owner originals, current runtime and the original Grant remain
mandatory at prepare/issue/consume/send.
"""
from copy import deepcopy

from .backend_registry import canonical, exact
from .generation_dispatch_a14b_profile import _require
from .generation_dispatch_a14b_exact import (
    EXACT_PROFILE_SCHEMA, EXACT_COMPILER_IDENTITY, EXACT_TEMPLATE_REF,
    EXACT_REQUEST_SCHEMA, validate_exact_profile, compile_exact_workflow,
    validate_exact_request_binding,
)

LIVE_PROFILE_SCHEMA = "v4.comfyui-a14b-i2v-backend-profile.v3"
LIVE_ADAPTER_IDENTITY = "v4.comfyui-wan22-a14b-image-to-video.v3"
LIVE_CAPABILITY = "self-hosted-wan22-a14b-image-to-video-v3"
LIVE_COMPILER_IDENTITY = "v4.generation-dispatch-a14b-compiler.v3"
LIVE_TEMPLATE_REF = "comfyui-a14b-original-topology-png49-v3"
LIVE_RUNTIME_SCHEMA = "v4.comfyui-a14b-runtime-attestation.v3"
LIVE_REQUEST_SCHEMA = "v4.generation-dispatch-live-transport-request.v3"
LIVE_ENDPOINT_CLASS = "CONTROLLED_SELF_HOSTED"


def _structural_projection(profile):
    projected = deepcopy(profile)
    projected["schemaVersion"] = EXACT_PROFILE_SCHEMA
    projected["parameters"].update(compilerIdentity=EXACT_COMPILER_IDENTITY,
        templateRef=EXACT_TEMPLATE_REF, evidenceClass="OFFLINE_SOURCE_CANDIDATE",
        cameraDisposition="PROPOSED_PENDING_OWNER_ACCEPTANCE")
    return projected


def validate_live_profile(value):
    exact(value, {"schemaVersion", "parameters", "modelFiles"}, "D1 live profile")
    _require(value["schemaVersion"] == LIVE_PROFILE_SCHEMA, "not a D1 live profile")
    p = value["parameters"]
    _require(p["compilerIdentity"] == LIVE_COMPILER_IDENTITY
        and p["templateRef"] == LIVE_TEMPLATE_REF
        and p["evidenceClass"] == "LIVE_CONFIGURATION"
        and p["cameraDisposition"] == "INDEPENDENT_OWNER_DECISION_REQUIRED",
        "live configuration is not approval or synthetic evidence")
    validate_exact_profile(_structural_projection(value))
    return deepcopy(value)


def compile_live_workflow(**inputs):
    profile = validate_live_profile(inputs["backend_profile"])
    return compile_exact_workflow(**{**inputs,
        "backend_profile": _structural_projection(profile)})


def validate_live_workflow(graph, **inputs):
    expected = compile_live_workflow(**inputs)
    _require(canonical(graph) == canonical(expected), "live topology or inputs changed")
    return expected


def validate_live_request_binding(request):
    _require(request["schemaVersion"] == LIVE_REQUEST_SCHEMA, "live request version changed")
    # This helper checks only topology/encoding, not permission or evidence class.
    return validate_exact_request_binding({**request, "schemaVersion": EXACT_REQUEST_SCHEMA})


def request_for_original_job(package, job):
    """Pure reconstruction for GET recovery, never a SendCapability factory."""
    from .generation_dispatch_live_contracts import make_live_transport_request
    from .backend_registry import digest
    profile = validate_live_profile(package["materials"]["backendProfile"])
    config = package["materials"]["executionConfig"]
    binding = package["plan"]["executionBinding"]
    native = profile["parameters"]["nativeOutput"]
    folder, _, prefix = native["filenamePrefix"].rpartition("/")
    grant = job["dispatchGrantBinding"]
    return make_live_transport_request(
        workspace_ref=job["workspaceRef"], production_run_ref=job["productionRunRef"],
        worker_ref=job["attempts"][0]["workerRef"],
        generation_dispatch_grant_ref=grant["generationDispatchGrantRef"],
        generation_dispatch_grant_digest=grant["generationDispatchGrantDigest"],
        media_job_ref=job["jobRef"], attempt_ref=job["attempts"][0]["attemptRef"],
        generation_request_ref=job["request"]["generationRequestRef"], generation_request_digest=job["requestDigest"],
        execution_envelope_digest=job["executionEnvelope"]["envelopeDigest"], workflow_digest=binding["workflowDigest"],
        output_constraints=job["executionEnvelope"]["outputConstraints"], workflow=package["materials"]["workflow"],
        connection_timeout_ms=config["connectionTimeoutMs"], request_timeout_ms=config["requestTimeoutMs"],
        history_timeout_ms=config["historyTimeoutMs"], postprocess_timeout_ms=config["postprocessTimeoutMs"],
        transport_policy=config["transportPolicy"], endpoint_digest=config["baseUrlDigest"],
        execution_config_digest=binding["executionConfigDigest"], runtime_binding_digest=digest(binding["runtimeBinding"]),
        backend_decision_digest=binding["backendDecisionDigest"], output_binding={"nodeId": native["nodeId"],
            "outputKey": "images", "mediaType": native["mediaType"], "frameCount": native["frameCount"],
            "filenamePrefix": prefix, "subfolder": folder},
        postprocess_binding=profile["parameters"]["postprocess"], live_profile_schema=LIVE_PROFILE_SCHEMA)
