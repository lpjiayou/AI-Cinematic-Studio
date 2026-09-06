"""Server-owned backend selection. No transport, credentials or production facts."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

BACKEND_REGISTRY_SCHEMA = "v4.video-execution-backend-registry.v1"
BACKEND_ROUTE_DECISION_SCHEMA = "v4.video-execution-backend-route-decision.v1"
ATTEMPT_BACKEND_BINDING_SCHEMA = "v4.execution-attempt-backend-binding.v1"
BACKEND_TYPES = frozenset({"SELF_HOSTED_SINGLE_GPU", "SELF_HOSTED_MULTI_GPU_WORKER_POOL",
    "CLOUD_GPU_WORKER", "EXTERNAL_PROVIDER_API", "CPU_DETERMINISTIC"})
METHOD_PAIRS = (("MICRO_MOTION", "SINGLE_ANCHOR_I2V"),
    ("CONTACT_ACTION", "CONTACT_CONDITIONED_VIDEO"),
    ("GAIT_LOCOMOTION", "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO"))

# Immutable v1 read/display compatibility, never execution authorization.
LEGACY_VIDEO_CAPABILITY = "self-hosted-wan22-image-to-video-v1"
LEGACY_VIDEO_ADAPTER_IDENTITY = "v4.comfyui-wan22-image-to-video.v1"
LEGACY_REGISTRY_VERSION = "v5.video-method-capability-registry.v1"
LEGACY_METHOD_CAPABILITIES = {pair: LEGACY_VIDEO_CAPABILITY if index == 0 else None
                            for index, pair in enumerate(METHOD_PAIRS)}
LEGACY_METHOD_IDENTITIES = {pair: LEGACY_VIDEO_ADAPTER_IDENTITY if index == 0 else None
                          for index, pair in enumerate(METHOD_PAIRS)}


class BackendUnavailableError(ValueError):
    code = "worker_unavailable"


class BackendValidationError(ValueError):
    code = "backend_binding_invalid"


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise BackendValidationError("non-canonical backend value") from exc


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


def exact(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BackendValidationError(f"{label} fields are invalid")
    canonical(value)
    return value


def ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", value):
        raise BackendValidationError(f"{label} is invalid")
    return value


def hex_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BackendValidationError(f"{label} is invalid")
    return value


def integer(value: Any, label: str, *, minimum: int = 1, maximum: int = 10**12) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise BackendValidationError(f"{label} is invalid")
    return value


def strict_load(raw: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BackendValidationError("duplicate backend field")
            result[key] = value
        return result
    try:
        if not 0 < len(raw) <= 2_000_000:
            raise BackendValidationError("backend manifest size is invalid")
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               BackendValidationError("non-finite backend number")))
        if not isinstance(value, dict):
            raise BackendValidationError("backend manifest root is invalid")
        canonical(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BackendValidationError("backend manifest is invalid") from exc


LEGACY_REGISTRY_DIGEST = digest({"schemaVersion": LEGACY_REGISTRY_VERSION,
    "routes": [{"executionClass": pair[0], "executionMethod": pair[1],
                "adapterCapability": LEGACY_METHOD_CAPABILITIES[pair],
                "adapterIdentity": LEGACY_METHOD_IDENTITIES[pair]}
               for pair in sorted(METHOD_PAIRS)]})

IDENTITY_FIELDS = {"backendRef", "backendType", "adapterIdentity", "adapterCapability",
    "providerId", "modelId", "region", "endpointClass", "backendProfileRef",
    "backendProfileDigest", "credentialSourceRef", "runtimeAttestationRef",
    "runtimeAttestationDigest", "costCurrency", "maxCostMinor", "resourceShape"}
DECISION_FIELDS = IDENTITY_FIELDS | {"schemaVersion", "registryVersion", "registryDigest",
    "policyRef", "policyDigest", "fallbackAllowed"}


def validate_resource_shape(value: Any) -> None:
    exact(value, {"gpuCount", "minimumVramPerGpu", "minimumTotalVram", "distributionMode"}, "resource shape")
    for name in ("gpuCount", "minimumVramPerGpu", "minimumTotalVram"):
        integer(value[name], name, minimum=0)
    if value["distributionMode"] not in {"NONE", "HORIZONTAL_INDEPENDENT_WORKERS", "ONE_JOB_MULTI_DEVICE_DISTRIBUTED_INFERENCE"}:
        raise BackendValidationError("distributionMode is invalid")


def validate_identity(value: Mapping[str, Any]) -> None:
    for name in IDENTITY_FIELDS - {"resourceShape", "maxCostMinor"}:
        if name.endswith("Digest"):
            hex_digest(value[name], name)
        else:
            ref(value[name], name)
    if value["backendType"] not in BACKEND_TYPES:
        raise BackendValidationError("backendType is invalid")
    if not re.fullmatch(r"[A-Z]{3}", value["costCurrency"]):
        raise BackendValidationError("costCurrency is invalid")
    integer(value["maxCostMinor"], "maxCostMinor", minimum=0)
    validate_resource_shape(value["resourceShape"])


def validate_decision(value: Any) -> dict[str, Any]:
    exact(value, DECISION_FIELDS, "backend decision")
    if value["schemaVersion"] != BACKEND_ROUTE_DECISION_SCHEMA or value["fallbackAllowed"] is not False:
        raise BackendValidationError("backend decision is unsafe")
    validate_identity(value)
    for name in ("registryVersion", "policyRef"):
        ref(value[name], name)
    for name in ("registryDigest", "policyDigest"):
        hex_digest(value[name], name)
    return deepcopy(dict(value))


def attempt_binding(decision: Mapping[str, Any], worker_ref: str) -> dict[str, Any]:
    result = validate_decision(decision)
    result["schemaVersion"] = ATTEMPT_BACKEND_BINDING_SCHEMA
    result["workerRef"] = ref(worker_ref, "workerRef")
    return result


def validate_attempt_binding(value: Any, decision: Mapping[str, Any]) -> None:
    exact(value, DECISION_FIELDS | {"workerRef"}, "attempt backend binding")
    if value != attempt_binding(decision, value["workerRef"]):
        raise BackendValidationError("attempt backend binding changed")


def execution_classification(decision: Mapping[str, Any]) -> tuple[str, str]:
    if decision["backendType"] == "EXTERNAL_PROVIDER_API":
        return "EXTERNAL_PROVIDER_API", "LIVE_PROVIDER"
    if decision["backendType"] == "CPU_DETERMINISTIC":
        return "CPU_DETERMINISTIC", "LOCAL_EVIDENCE"
    return "INTERNAL_SELF_HOSTED", "SELF_HOSTED_AI_GENERATED"


class VideoExecutionBackendResolver(Protocol):
    registry_version: str
    registry_digest: str
    def resolve(self, execution_class: str, execution_method: str,
                input_roles: list[str], output_constraints: Mapping[str, Any]) -> dict[str, Any]: ...
    def profile(self, decision: Mapping[str, Any]) -> dict[str, Any]: ...


class BackendRegistry:
    """One operator-pinned route; no auto-routing, failover or secret storage."""
    def __init__(self, manifest: Mapping[str, Any]):
        exact(manifest, {"schemaVersion", "registryVersion", "policy", "backends"}, "backend registry")
        if manifest["schemaVersion"] != BACKEND_REGISTRY_SCHEMA:
            raise BackendValidationError("backend registry schema is invalid")
        self._manifest = deepcopy(dict(manifest))
        self.registry_version = ref(manifest["registryVersion"], "registryVersion")
        self.registry_digest = digest(manifest)
        policy = exact(manifest["policy"], {"policyRef", "pinnedBackendRef", "maxAttempts", "fallbackAllowed"}, "backend policy")
        ref(policy["policyRef"], "policyRef")
        ref(policy["pinnedBackendRef"], "pinnedBackendRef")
        if type(policy["maxAttempts"]) is not int or policy["maxAttempts"] != 1 or policy["fallbackAllowed"] is not False:
            raise BackendValidationError("retry/failover policy is unsafe")
        if not isinstance(manifest["backends"], list) or not manifest["backends"]:
            raise BackendValidationError("backend entries are missing")
        seen = set()
        for entry in manifest["backends"]:
            exact(entry, IDENTITY_FIELDS | {"supportedExecutionClasses", "supportedExecutionMethods",
                "acceptedInputRoles", "supportedOutputFormats", "profile"}, "backend entry")
            validate_identity(entry)
            if entry["backendRef"] in seen:
                raise BackendValidationError("backend identity is duplicated")
            seen.add(entry["backendRef"])
            for name in ("supportedExecutionClasses", "supportedExecutionMethods", "acceptedInputRoles", "supportedOutputFormats"):
                items = entry[name]
                if not isinstance(items, list) or not items or any(not isinstance(i, str) or not i for i in items) or len(set(items)) != len(items):
                    raise BackendValidationError(f"{name} is invalid")
            profile = exact(entry["profile"], {"schemaVersion", "parameters", "modelFiles"}, "backend profile")
            ref(profile["schemaVersion"], "profile schema")
            if not isinstance(profile["parameters"], Mapping) or not isinstance(profile["modelFiles"], list):
                raise BackendValidationError("backend profile content is invalid")
            if digest(profile) != entry["backendProfileDigest"]:
                raise BackendValidationError("backend profile digest mismatch")
        if policy["pinnedBackendRef"] not in seen:
            raise BackendValidationError("pinned backend is missing")

    @classmethod
    def from_file(cls, path: Path | str, expected_sha256: str):
        raw = Path(path).read_bytes()
        if sha256(raw).hexdigest() != hex_digest(expected_sha256, "registry file digest"):
            raise BackendValidationError("backend registry file changed")
        return cls(strict_load(raw))

    def resolve(self, execution_class, execution_method, input_roles, output_constraints):
        # E1 deliberately leaves Contact/Gait unavailable, even if misconfigured.
        if (execution_class, execution_method) != METHOD_PAIRS[0]:
            raise BackendUnavailableError("execution method is unavailable")
        entry = next(item for item in self._manifest["backends"]
                     if item["backendRef"] == self._manifest["policy"]["pinnedBackendRef"])
        if (execution_class not in entry["supportedExecutionClasses"]
                or execution_method not in entry["supportedExecutionMethods"]
                or not set(input_roles) <= set(entry["acceptedInputRoles"])
                or output_constraints.get("mediaType", "video/mp4") not in entry["supportedOutputFormats"]):
            raise BackendUnavailableError("backend is incompatible with the requested method")
        policy = self._manifest["policy"]
        return validate_decision({**{k: deepcopy(entry[k]) for k in IDENTITY_FIELDS},
            "schemaVersion": BACKEND_ROUTE_DECISION_SCHEMA, "registryVersion": self.registry_version,
            "registryDigest": self.registry_digest, "policyRef": policy["policyRef"],
            "policyDigest": digest(policy), "fallbackAllowed": False})

    def profile(self, decision: Mapping[str, Any]) -> dict[str, Any]:
        validate_decision(decision)
        if decision != self.resolve("MICRO_MOTION", "SINGLE_ANCHOR_I2V", ["ACTION_READY_ANCHOR"], {"mediaType": "video/mp4"}):
            raise BackendValidationError("backend registry or policy changed")
        entry = next(e for e in self._manifest["backends"] if e["backendRef"] == decision["backendRef"])
        return deepcopy(entry["profile"])


class UnavailableBackendResolver:
    registry_version = LEGACY_REGISTRY_VERSION
    registry_digest = LEGACY_REGISTRY_DIGEST

    def resolve(self, execution_class, execution_method, input_roles, output_constraints):
        raise BackendUnavailableError("no compatible backend is configured")
