"""ADR-0022 v1.2 data contracts. Pure validation; no runtime composition.

Canonical V4 values retain their original canonical encoder and validators.
These functions validate evidence, never the trustworthiness of its issuer.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from services.v4_platform import backend_registry as backend
from services.v4_platform.method_aware_execution import validate_output, validate_source

PREFIX = "v5.generation-dispatch-"
GRANT_SCHEMA = PREFIX + "grant.v1"
TERMINAL_SCHEMA = PREFIX + "grant-terminal.v1"
APPROVAL_SCHEMA = PREFIX + "approval-bundle.v1"
REVOCATION_SCHEMA = PREFIX + "revocation-bundle.v1"
MAX_JSON_BYTES = 2_000_000
SCOPE_FIELDS = frozenset({"workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef"})
TOKEN_FIELDS = frozenset({"recordJournalHead", "workspaceRecordJournalHead", "evidenceRevisionToken"})
PERMISSIONS = {"dispatchAllowed": True,
    "shotPlanScopeApproval": "APPROVED_FOR_EXACT_TECHNICAL_SUBJECT",
    "cameraScopeApproval": "APPROVED_FOR_EXACT_TECHNICAL_SUBJECT",
    "inputAssetProcessingAuthorized": True, "inputSubjectProcessingAuthorized": True}
ELIGIBILITIES = frozenset({"ELIGIBLE_FOR_CONSUMPTION", "NOT_YET_VALID", "EXPIRED", "CONSUMED",
    "REVOKED", "SOURCE_CHANGED", "APPROVAL_UNAVAILABLE", "CONFIG_CHANGED", "FENCE_UNAVAILABLE"})
ERROR_CODES = frozenset({"INVALID_CLOSED_SCHEMA", "APPROVAL_UNAVAILABLE", "APPROVAL_PLAN_MISMATCH",
    "SOURCE_CHANGED", "CONFIG_CHANGED", "RUNTIME_CHANGED", "COST_BOUND_UNVERIFIED",
    "OUTSIDE_VALIDITY_WINDOW", "CURRENTNESS_FENCE_UNAVAILABLE", "SNAPSHOT_CHANGED",
    "IDEMPOTENCY_CONFLICT", "GRANT_SUBJECT_ALREADY_RECORDED", "TERMINAL_ALREADY_RECORDED",
    "ALREADY_CONSUMED", "ALREADY_REVOKED", "ATTEMPT_OR_LEASE_CHANGED", "SCOPE_MISMATCH",
    "PERSISTENCE_UNAVAILABLE"})
SELECTORS = {
    "CURRENT_PROJECT": ("V5_PROJECT_CONTEXT", "projectRef"),
    "CURRENT_SERIES": ("V5_SERIES_EPISODE", "seriesRef"),
    "CURRENT_EPISODE": ("V5_SERIES_EPISODE", "episodeRef"),
    "CURRENT_CONFIRMED_SERIES_PLAN": ("V5_SERIES_PLANNING", "seriesRef"),
    "CURRENT_EPISODE_PLAN_BINDING": ("V5_SERIES_PLANNING", "episodeRef"),
    "CURRENT_CONFIRMED_SCRIPT": ("V5_SCRIPT", "episodeRef"),
    "ACTIVE_M6_BINDING": ("V5_M6", "episodeRef"),
    "CURRENT_M7_PASS": ("V5_EPISODE_PRODUCTION", "productionRunRef"),
    "CURRENT_METHOD_PLAN": ("V5_EPISODE_PRODUCTION", "productionRunRef"),
    "CURRENT_INPUT_PLAN": ("V5_EPISODE_PRODUCTION", "productionRunRef"),
    "CURRENT_IDENTITY_REFERENCE": ("V5_IDENTITY", "episodeRef"),
    "CURRENT_RIGHTS_EVALUATION": ("V5_RIGHTS", "productionRunRef"),
    "CURRENT_PROVIDER_POLICY": ("V5_PROVIDER_POLICY", "productionRunRef"),
    "CURRENT_BACKEND_CONFIG": ("V4_BACKEND_CONFIG", "productionRunRef"),
    "CURRENT_OWNER_APPROVAL": ("OWNER_APPROVAL", "productionRunRef"),
    "CURRENT_RUNTIME_PROCESS": ("RUNTIME_PROCESS", "productionRunRef"),
}
OWNERS = frozenset(owner for owner, _ in SELECTORS.values())
PREREQUISITES = frozenset({"scriptOwnerAcceptance", "identityReferenceEvaluation", "rightsEvaluation",
    "providerPolicyEvaluation", "costReview"})
APPROVAL_FIELDS = frozenset({"approvalRef", "authorityRef", "authorityDecisionRef", "actorRef",
    "authorityDecisionDigest", "actorKind", "actorRole", "approvalKind", "decision",
    "approvedPlanDigest", "approvalEvidenceRef", "approvalEvidenceDigest", "decidedAt"})
REVOCATION_FIELDS = (APPROVAL_FIELDS - {"approvedPlanDigest"}) | {"grantDigest"}


class DispatchError(ValueError):
    """Safe closed code; diagnostic paths/exception strings are never serialized."""
    def __init__(self, code: str = "INVALID_CLOSED_SCHEMA"):
        if code not in ERROR_CODES:
            raise ValueError("unknown dispatch error code")
        self.code = code
        super().__init__(code)


class CommitOutcomeUnknown(Exception):
    """The caller must inspect history, not assume rollback or retry a write."""


def require(condition: bool, code: str = "INVALID_CLOSED_SCHEMA") -> None:
    if not condition:
        raise DispatchError(code)


def canonical(value: Any) -> bytes:
    def walk(item: Any, depth: int = 0) -> None:
        require(depth <= 64)
        if type(item) is dict:
            require(all(type(key) is str for key in item))
            for child in item.values():
                walk(child, depth + 1)
        elif type(item) is list:
            for child in item:
                walk(child, depth + 1)
        else:
            require(item is None or type(item) in (str, int, float, bool))
    try:
        walk(value)
        return backend.canonical(value)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise DispatchError() from exc


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


def strict_json(raw: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    def invalid(_):
        raise DispatchError()
    try:
        require(type(raw) is bytes and 0 < len(raw) <= MAX_JSON_BYTES)
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
        require(type(value) is dict)
        canonical(value)  # Also rejects exponent overflow, surrogates and deep nesting.
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise DispatchError() from exc


def exact(value: Any, fields) -> dict:
    require(type(value) is dict and set(value) == set(fields))
    canonical(value)
    return value


def ref(value: Any) -> str:
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", value) is not None)
    return value


def sha(value: Any) -> str:
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)
    return value


def git_id(value: Any) -> str:
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None)
    return value


def integer(value: Any, minimum: int = 1) -> int:
    require(type(value) is int and value >= minimum)
    return value


def utc(value: Any) -> datetime:
    require(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value) is not None)
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DispatchError() from exc


def pinned(value: Any) -> None:
    exact(value, {"ref", "digest"})
    ref(value["ref"])
    sha(value["digest"])


def scope(value: Any) -> dict:
    exact(value, SCOPE_FIELDS)
    for item in value.values():
        ref(item)
    return value


def tokens(value: Any) -> dict:
    exact(value, TOKEN_FIELDS)
    for item in value.values():
        sha(item)
    return value


def sealed(value: Mapping[str, Any], field: str = "payloadDigest") -> dict:
    result = deepcopy(dict(value))
    result.pop(field, None)
    result[field] = digest(result)
    return result


def verify_seal(value: dict, field: str = "payloadDigest") -> None:
    sha(value[field])
    require(value[field] == digest({k: v for k, v in value.items() if k != field}))


def validate_limits(value: Any) -> dict:
    exact(value, {"maxAttempts", "maxPromptSubmissions", "retryAllowed", "fallbackAllowed", "costCurrency",
        "maxCostMinor", "executionTimeoutSeconds", "notBefore", "expiresAt", "stopPolicy"})
    for key in ("maxAttempts", "maxPromptSubmissions"):
        require(type(value[key]) is int and value[key] == 1)
    require(value["retryAllowed"] is False and value["fallbackAllowed"] is False)
    require(value["costCurrency"] == "CNY" and value["stopPolicy"] == "FAIL_CLOSED_NO_RESUBMISSION")
    integer(value["maxCostMinor"])
    integer(value["executionTimeoutSeconds"])
    require(utc(value["notBefore"]) < utc(value["expiresAt"]))
    return deepcopy(value)


def validate_subject(value: Any) -> dict:
    pins = {"scriptVersion", "consistencyValidationVersion", "executionMethodPlanVersion",
        "methodAwareInputPlanVersion", "creativeShotVersion", "actionExecutionBeat", "visualExecutionRequirement"}
    exact(value, pins | {"technicalTargetId", "productionRunPayloadDigest", "manifestDigest", "m6Binding", "inputAsset",
        "inputAppendAuthority", "sourceAction", "cameraInstruction", "frameRange", "outputConstraints", "executionClass", "executionMethod"})
    ref(value["technicalTargetId"])
    for key in ("productionRunPayloadDigest", "manifestDigest"):
        sha(value[key])
    for key in pins:
        pinned(value[key])
    m6 = exact(value["m6Binding"], {"m6BaselineSnapshotRef", "m6BaselineCanonicalDigest", "activationRevision", "m6ConsumerBindingDigest"})
    ref(m6["m6BaselineSnapshotRef"])
    sha(m6["m6BaselineCanonicalDigest"])
    sha(m6["m6ConsumerBindingDigest"])
    integer(m6["activationRevision"])
    asset = exact(value["inputAsset"], {"assetRef", "assetVersionRef", "assetVersionDigest", "inputRole",
        "contentDigest", "mediaType", "byteSize", "width", "height"})
    require(asset["inputRole"] == "ACTION_READY_ANCHOR" and asset["mediaType"] == "image/png")
    try:
        validate_source({k: v for k, v in asset.items() if k != "inputRole"})
        validate_output(value["outputConstraints"])
    except ValueError as exc:
        raise DispatchError() from exc
    authority = exact(value["inputAppendAuthority"], {"ref", "digest", "subjectDigest"})
    ref(authority["ref"])
    sha(authority["digest"])
    sha(authority["subjectDigest"])
    action = exact(value["sourceAction"], {"sourceSpan", "sourceTextDigest"})
    sha(action["sourceTextDigest"])
    span = exact(action["sourceSpan"], {"scriptSceneRef", "sourceField", "sourceIndex", "startOffsetInclusive", "endOffsetExclusive"})
    ref(span["scriptSceneRef"])
    require(span["sourceField"] == "ACTION")
    for key in ("sourceIndex", "startOffsetInclusive", "endOffsetExclusive"):
        integer(span[key], 0)
    require(span["sourceIndex"] == 0 and span["endOffsetExclusive"] > span["startOffsetInclusive"])
    exact(value["cameraInstruction"], {"framing", "movement"})
    require(value["cameraInstruction"] == {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"})
    frames = exact(value["frameRange"], {"startFrameInclusive", "endFrameExclusive"})
    integer(frames["startFrameInclusive"], 0)
    integer(frames["endFrameExclusive"])
    output = value["outputConstraints"]
    require(output["durationFrames"] == frames["endFrameExclusive"] - frames["startFrameInclusive"])
    require(output["durationFrames"] % 4 == 0 and output["width"] % 16 == output["height"] % 16 == 0)
    require(value["executionClass"] == "MICRO_MOTION" and value["executionMethod"] == "SINGLE_ANCHOR_I2V")
    return deepcopy(value)


def validate_binding(value: Any) -> dict:
    exact(value, {"backendDecision", "backendDecisionDigest", "executionProfile", "executionConfigDigest",
        "executionCode", "runtimeBinding", "workflowDigest", "costBasis", "prerequisiteEvidenceDigest"})
    try:
        backend.validate_decision(value["backendDecision"])
    except (ValueError, TypeError, KeyError) as exc:
        raise DispatchError() from exc
    decision = value["backendDecision"]
    require(decision["backendType"] == "SELF_HOSTED_SINGLE_GPU" and decision["costCurrency"] == "CNY")
    require(decision["resourceShape"]["gpuCount"] == 1 and decision["resourceShape"]["distributionMode"] == "NONE")
    require(value["backendDecisionDigest"] == backend.digest(decision))
    for key in ("backendDecisionDigest", "executionConfigDigest", "workflowDigest", "prerequisiteEvidenceDigest"):
        sha(value[key])
    for key in ("executionProfile", "costBasis"):
        pinned(value[key])
    require(value["executionProfile"] == {"ref": decision["backendProfileRef"], "digest": decision["backendProfileDigest"]})
    for item in exact(value["executionCode"], {"coreCommit", "coreTree", "comfyuiCommit"}).values():
        git_id(item)
    runtime = exact(value["runtimeBinding"], {"instanceRef", "processIdentityDigest", "attestationFileSha256"})
    ref(runtime["instanceRef"])
    sha(runtime["processIdentityDigest"])
    sha(runtime["attestationFileSha256"])
    return deepcopy(value)


def validate_plan(value: Any) -> dict:
    exact(value, {"scope", "subject", "executionBinding", "permissions", "limits"})
    scope(value["scope"])
    validate_subject(value["subject"])
    validate_binding(value["executionBinding"])
    exact(value["permissions"], PERMISSIONS)
    require(canonical(value["permissions"]) == canonical(PERMISSIONS))
    validate_limits(value["limits"])
    return deepcopy(value)


def subject_digest(plan: dict) -> str:
    return digest({**plan["scope"], "subject": plan["subject"]})


def grant_ref(plan: dict) -> str:
    return "generation-dispatch-grant-" + digest({"workspaceRef": plan["scope"]["workspaceRef"],
        "productionRunRef": plan["scope"]["productionRunRef"],
        "creativeShotVersionRef": plan["subject"]["creativeShotVersion"]["ref"],
        "beatRef": plan["subject"]["actionExecutionBeat"]["ref"]})


def validate_approval(value: Any, *, plan: dict | None = None, revocation: bool = False) -> dict:
    exact(value, REVOCATION_FIELDS if revocation else APPROVAL_FIELDS)
    for key in ("approvalRef", "authorityRef", "authorityDecisionRef", "actorRef", "approvalEvidenceRef"):
        ref(value[key])
    for key in ("approvalEvidenceDigest", "grantDigest" if revocation else "approvedPlanDigest"):
        sha(value[key])
    require(value["actorKind"] == "HUMAN" and value["actorRole"] == "PROJECT_LEAD" and value["decision"] == "APPROVED")
    require(value["approvalKind"] == ("REVOKE_EXACT_GENERATION_GRANT" if revocation else "EXACT_SUBJECT_GENERATION_EXECUTION"))
    utc(value["decidedAt"])
    verify_seal(value, "authorityDecisionDigest")
    if plan is not None:
        require(value["approvedPlanDigest"] == digest(plan), "APPROVAL_PLAN_MISMATCH")
    return deepcopy(value)


def validate_execution_config(value: Any) -> dict:
    roots = {"sourceRoot", "inputRoot", "modelRoot", "artifactRoot"}
    timeouts = {"connectionTimeoutMs", "requestTimeoutMs", "historyTimeoutMs", "postprocessTimeoutMs"}
    exact(value, roots | timeouts | {"schemaVersion", "configRef", "configRevision", "backendRef", "baseUrlDigest",
        "credentialSourceRef", "credentialBindingRevision", "launchConfiguration", "launchConfigDigest", "coordinationMode", "transportPolicy"})
    require(value["schemaVersion"] == PREFIX + "execution-config.v1")
    for key in ("configRef", "backendRef", "credentialSourceRef"):
        ref(value[key])
    for key in {"configRevision", "credentialBindingRevision"} | timeouts:
        integer(value[key])
    sha(value["baseUrlDigest"])
    for key in roots:
        for item_key, item in exact(value[key], {"locatorRef", "absolutePathDigest"}).items():
            (ref if item_key == "locatorRef" else sha)(item)
    launch = exact(value["launchConfiguration"], {"argv", "environmentProjection"})
    require(type(launch["argv"]) is list and len(launch["argv"]) > 0)
    for arg in launch["argv"]:
        require(type(arg) is str and "\x00" not in arg)
    env = launch["environmentProjection"]
    require(type(env) is list)
    names = []
    for entry in env:
        exact(entry, {"name", "value"})
        require(type(entry["name"]) is str and re.fullmatch(r"[A-Z_][A-Z0-9_]*", entry["name"]) is not None)
        require(type(entry["value"]) is str and "\x00" not in entry["value"])
        names.append(entry["name"])
    require(names == sorted(set(names)))
    require(value["launchConfigDigest"] == digest(launch))
    require(value["coordinationMode"] == "SINGLE_HOST_SINGLE_CONTROL_PROCESS")
    expected = {"maxPromptSubmissions": 1, "postRetryAllowed": False, "redirectAllowed": False, "fallbackAllowed": False}
    require(canonical(value["transportPolicy"]) == canonical(expected))
    require(value["connectionTimeoutMs"] <= value["requestTimeoutMs"])
    return deepcopy(value)


def validate_process(value: Any) -> dict:
    exact(value, {"schemaVersion", "instanceRef", "hostBootIdDigest", "pidNamespaceIdDigest",
        "comfyuiPid", "processStartTicks", "comfyuiCommit", "launchConfigDigest"})
    require(value["schemaVersion"] == PREFIX + "runtime-process.v1")
    ref(value["instanceRef"])
    for key in ("hostBootIdDigest", "pidNamespaceIdDigest", "launchConfigDigest"):
        sha(value[key])
    integer(value["comfyuiPid"])
    require(type(value["processStartTicks"]) is str and re.fullmatch(r"0|[1-9][0-9]*", value["processStartTicks"]) is not None)
    git_id(value["comfyuiCommit"])
    return deepcopy(value)


def validate_cost(value: Any) -> dict:
    nonnegative = {"fixedCostMinor", "computeUnitCostMinor", "computeMinimumUnits", "storageBoundMinor", "transferBoundMinor", "otherBoundMinor"}
    exact(value, nonnegative | {"schemaVersion", "costBasisRef", "currency", "sourceEvidence", "reviewedByAuthorityRef",
        "reviewDecision", "validFrom", "validUntil", "costScope", "computeUnitSeconds", "roundingMode", "billingResponsibility", "payloadDigest"})
    require(value["schemaVersion"] == PREFIX + "cost-basis.v1" and value["currency"] == "CNY")
    require(value["costScope"] == "APPROVED_OPERATION_WINDOW_ONLY" and value["roundingMode"] == "CEILING_EACH_COMPONENT")
    ref(value["costBasisRef"])
    ref(value["reviewedByAuthorityRef"])
    pinned(value["reviewDecision"])
    require(type(value["sourceEvidence"]) is list and len(value["sourceEvidence"]) > 0)
    for evidence in value["sourceEvidence"]:
        pinned(evidence)
    refs = [item["ref"] for item in value["sourceEvidence"]]
    require(refs == sorted(set(refs)))
    require(utc(value["validFrom"]) < utc(value["validUntil"]))
    integer(value["computeUnitSeconds"])
    for key in nonnegative:
        integer(value[key], 0)
    billing = exact(value["billingResponsibility"], {"powerStopOwnerRef", "dataRetentionOwnerRef", "continuingChargesEvidence"})
    ref(billing["powerStopOwnerRef"])
    ref(billing["dataRetentionOwnerRef"])
    pinned(billing["continuingChargesEvidence"])
    verify_seal(value)
    return deepcopy(value)


def cost_bound(cost: dict, limits: dict) -> int:
    units = (limits["executionTimeoutSeconds"] + cost["computeUnitSeconds"] - 1) // cost["computeUnitSeconds"]
    return (cost["fixedCostMinor"] + max(cost["computeMinimumUnits"], units) * cost["computeUnitCostMinor"]
        + cost["storageBoundMinor"] + cost["transferBoundMinor"] + cost["otherBoundMinor"])


def validate_read_set(value: Any, *, expected_scope: dict | None = None, phase: str | None = None) -> dict:
    exact(value, {"schemaVersion", "scope", "phase", "coordinationEpoch", "objects", "selectors"})
    require(value["schemaVersion"] == PREFIX + "read-set.v1")
    scope(value["scope"])
    require(expected_scope is None or value["scope"] == expected_scope, "SCOPE_MISMATCH")
    require(value["phase"] in ("PREPARE", "ISSUE", "CONSUME", "SEND") and (phase is None or phase == value["phase"]))
    sha(value["coordinationEpoch"])
    require(type(value["objects"]) is list and len(value["objects"]) > 0 and type(value["selectors"]) is list)
    object_keys = []
    for item in value["objects"]:
        exact(item, {"owner", "objectKind", "objectRef", "objectDigest"})
        require(type(item["owner"]) is str and item["owner"] in OWNERS)
        ref(item["objectKind"])
        ref(item["objectRef"])
        sha(item["objectDigest"])
        object_keys.append((item["owner"], item["objectKind"], item["objectRef"]))
    require(object_keys == sorted(set(object_keys)))
    keys, kinds = [], []
    objects = {(o["owner"], o["objectRef"], o["objectDigest"]) for o in value["objects"]}
    for item in value["selectors"]:
        exact(item, {"owner", "selectorKind", "scopeRef", "selectedRef", "selectedDigest", "coordinationRevision"})
        require(type(item["selectorKind"]) is str and item["selectorKind"] in SELECTORS)
        owner, scope_key = SELECTORS[item["selectorKind"]]
        require(item["owner"] == owner and item["scopeRef"] == value["scope"][scope_key], "SCOPE_MISMATCH")
        ref(item["selectedRef"])
        sha(item["selectedDigest"])
        integer(item["coordinationRevision"], 0)
        require((owner, item["selectedRef"], item["selectedDigest"]) in objects)
        keys.append((owner, item["selectorKind"], item["scopeRef"]))
        kinds.append(item["selectorKind"])
    expected = set(SELECTORS) - ({"CURRENT_OWNER_APPROVAL"} if value["phase"] == "PREPARE" else set())
    require(keys == sorted(set(keys)) and len(kinds) == len(expected) and set(kinds) == expected)
    return deepcopy(value)


def validate_read_set_bindings(read_set: dict, plan: dict, approval: dict) -> None:
    """Check the audit references we can derive; original Owner semantics stay in ports."""
    s, b = plan["subject"], plan["executionBinding"]
    selected = {item["selectorKind"]: item for item in read_set["selectors"]}
    for kind, key in (("CURRENT_PROJECT", "projectRef"), ("CURRENT_SERIES", "seriesRef"), ("CURRENT_EPISODE", "episodeRef")):
        require(selected[kind]["selectedRef"] == plan["scope"][key], "SCOPE_MISMATCH")
    for kind, key in (("CURRENT_CONFIRMED_SCRIPT", "scriptVersion"), ("CURRENT_M7_PASS", "consistencyValidationVersion"),
        ("CURRENT_METHOD_PLAN", "executionMethodPlanVersion"), ("CURRENT_INPUT_PLAN", "methodAwareInputPlanVersion")):
        require((selected[kind]["selectedRef"], selected[kind]["selectedDigest"]) == (s[key]["ref"], s[key]["digest"]), "SOURCE_CHANGED")
    require((selected["ACTIVE_M6_BINDING"]["selectedRef"], selected["ACTIVE_M6_BINDING"]["selectedDigest"]) ==
        (s["m6Binding"]["m6BaselineSnapshotRef"], s["m6Binding"]["m6BaselineCanonicalDigest"]), "SOURCE_CHANGED")
    if read_set["phase"] != "PREPARE":
        require((selected["CURRENT_OWNER_APPROVAL"]["selectedRef"], selected["CURRENT_OWNER_APPROVAL"]["selectedDigest"]) ==
            (approval["authorityDecisionRef"], approval["authorityDecisionDigest"]), "APPROVAL_UNAVAILABLE")
    objects = {(o["owner"], o["objectRef"], o["objectDigest"]) for o in read_set["objects"]}
    expected = [("V5_EPISODE_PRODUCTION", plan["scope"]["productionRunRef"], s["productionRunPayloadDigest"]),
        ("V5_EPISODE_PRODUCTION", s["inputAsset"]["assetVersionRef"], s["inputAsset"]["assetVersionDigest"]),
        ("V5_EPISODE_PRODUCTION", s["inputAppendAuthority"]["ref"], s["inputAppendAuthority"]["digest"]),
        ("V4_BACKEND_CONFIG", b["executionProfile"]["ref"], b["executionProfile"]["digest"]),
        ("V4_BACKEND_CONFIG", b["costBasis"]["ref"], b["costBasis"]["digest"])]
    if read_set["phase"] != "PREPARE":
        expected.append(("OWNER_APPROVAL", approval["approvalEvidenceRef"], approval["approvalEvidenceDigest"]))
    expected.extend(("V5_EPISODE_PRODUCTION", s[k]["ref"], s[k]["digest"]) for k in ("creativeShotVersion", "actionExecutionBeat", "visualExecutionRequirement"))
    require(all(item in objects for item in expected), "SOURCE_CHANGED")


def required_read_set_proofs(plan_package: dict) -> list[dict]:
    """Known proof dependencies at a complete, current material boundary.

    These are requirements, not observations or proof of an original read.
    The plan-only historical validator deliberately cannot make this check.
    """
    package = validate_plan_package(plan_package)
    decision = package["plan"]["executionBinding"]["backendDecision"]
    cost = package["materials"]["costBasis"]
    required = {}

    def add(owner, kind, reference, digest_value):
        key = (owner, kind, reference)
        value = {"owner": owner, "objectKind": kind,
                 "objectRef": reference, "objectDigest": digest_value}
        require(key not in required or required[key] == value, "SOURCE_CHANGED")
        required[key] = value

    add("RUNTIME_PROCESS", "RuntimeAttestation", decision["runtimeAttestationRef"],
        decision["runtimeAttestationDigest"])
    for proof in [*cost["sourceEvidence"], cost["billingResponsibility"]["continuingChargesEvidence"]]:
        add("V4_BACKEND_CONFIG", "CostEvidence", proof["ref"], proof["digest"])
    return [required[key] for key in sorted(required)]


def validate_read_set_proof_bindings(read_set: dict, plan_package: dict) -> None:
    """Require all known proofs without changing historical record schemas."""
    validate_read_set(read_set, expected_scope=plan_package["plan"]["scope"])
    required = required_read_set_proofs(plan_package)
    actual = {(o["owner"], o["objectKind"], o["objectRef"]): o["objectDigest"]
              for o in read_set["objects"]}
    for proof in required:
        key = (proof["owner"], proof["objectKind"], proof["objectRef"])
        require(actual.get(key) == proof["objectDigest"], "SOURCE_CHANGED")
        # A second representation of the same original must not conceal drift.
        require(all(o["objectDigest"] == proof["objectDigest"]
                    for o in read_set["objects"]
                    if (o["owner"], o["objectRef"]) == (proof["owner"], proof["objectRef"])),
                "SOURCE_CHANGED")


def request_identity(plan: dict) -> dict:
    binding = plan["executionBinding"]
    return {"schemaVersion": PREFIX + "request-identity.v1", "scope": deepcopy(plan["scope"]),
        "subjectDigest": subject_digest(plan), "backendProfileRef": binding["executionProfile"]["ref"],
        "backendProfileDigest": binding["executionProfile"]["digest"], "executionConfigDigest": binding["executionConfigDigest"],
        "executionCode": deepcopy(binding["executionCode"]), "outputConstraints": deepcopy(plan["subject"]["outputConstraints"]),
        "workflowCompilerRef": "comfyui-i2v-api-graph-v1"}


def _profile(value: Any) -> None:
    # The original BackendRegistry profile closed shape and canonical primitives.
    # I2V parameter bounds are those of ComfyUI.validate_method_aware_envelope;
    # that transport adapter's instance method also probes files and is not called.
    try:
        backend.exact(value, {"schemaVersion", "parameters", "modelFiles"}, "backend profile")
        require(value["schemaVersion"] == "v4.comfyui-i2v-backend-profile.v1")
        p = backend.exact(value["parameters"], {"seed", "steps", "cfg", "samplerName", "scheduler", "modelShift", "negativePrompt"}, "I2V parameters")
        backend.integer(p["steps"], "steps", maximum=100)
        backend.integer(p["seed"], "seed", minimum=0, maximum=2**64 - 1)
        for key in ("cfg", "modelShift"):
            require(type(p[key]) in (int, float) and 0 < p[key] <= 100)
        require(p["samplerName"] == "uni_pc" and p["scheduler"] == "simple")
        text = p["negativePrompt"]
        require(type(text) is str and 0 < len(text) <= 4000 and text == text.strip() and all(ord(c) >= 32 for c in text))
        files = value["modelFiles"]
        require(type(files) is list and len(files) == 3)
        for model in files:
            backend.exact(model, {"role", "name", "sha256"}, "model file")
            require(type(model["name"]) is str and 0 < len(model["name"]) <= 200 and "/" not in model["name"] and "\\" not in model["name"] and ".." not in model["name"] and all(ord(c) >= 32 for c in model["name"]))
            sha(model["sha256"])
        require({model["role"] for model in files} == {"UNET", "TEXT_ENCODER", "VAE"})
        require(len({model["name"] for model in files}) == 3)
    except (ValueError, TypeError) as exc:
        raise DispatchError() from exc


def _workflow(plan: dict, materials: dict) -> None:
    """Exact data comparison with the fixed existing I2V graph, no staging/adapter."""
    graph = materials["workflow"]
    require(type(graph) is dict)
    try:
        text = graph["5"]["inputs"]["text"]
        suffix = "; framing: MEDIUM_CLOSE_UP; movement: LOCKED"
        require(type(text) is str and text.endswith(suffix))
        source = text[:-len(suffix)]
        span = plan["subject"]["sourceAction"]["sourceSpan"]
        require(0 < len(source) <= 4000 and bool(source.strip()) and len(source) == span["endOffsetExclusive"] - span["startOffsetInclusive"])
        require(sha256(source.encode("utf-8")).hexdigest() == plan["subject"]["sourceAction"]["sourceTextDigest"])
        p, o = materials["backendProfile"]["parameters"], plan["subject"]["outputConstraints"]
        models = {m["role"]: m["name"] for m in materials["backendProfile"]["modelFiles"]}
        request_ref = "generation-request-" + digest(request_identity(plan))
        prefix = "acs-k2/" + sha256(request_ref.encode("utf-8")).hexdigest()[:24]
        def node(kind, **inputs):
            return {"class_type": kind, "inputs": inputs}
        expected = {
            "1": node("UNETLoader", unet_name=models["UNET"], weight_dtype="default"),
            "2": node("CLIPLoader", clip_name=models["TEXT_ENCODER"], type="wan", device="default"),
            "3": node("VAELoader", vae_name=models["VAE"]),
            "4": node("ModelSamplingSD3", model=["1", 0], shift=p["modelShift"]),
            "5": node("CLIPTextEncode", text=text, clip=["2", 0]),
            "6": node("CLIPTextEncode", text=p["negativePrompt"], clip=["2", 0]),
            "7": node("Wan22ImageToVideoLatent", vae=["3", 0], width=o["width"], height=o["height"], length=o["durationFrames"] + 1, batch_size=1, start_image=["12", 0]),
            "8": node("KSampler", model=["4", 0], seed=p["seed"], steps=p["steps"], cfg=p["cfg"], sampler_name=p["samplerName"], scheduler=p["scheduler"], positive=["5", 0], negative=["6", 0], latent_image=["7", 0], denoise=1.0),
            "9": node("VAEDecode", samples=["8", 0], vae=["3", 0]),
            "10": node("CreateVideo", images=["9", 0], fps=o["frameRate"], bit_depth=8),
            "11": node("SaveVideo", video=["10", 0], filename_prefix=prefix, format="mp4", codec="h264"),
            "12": node("LoadImage", image="acs-k2-m11/" + plan["subject"]["inputAsset"]["contentDigest"] + ".png"),
        }
        require(canonical(graph) == canonical(expected), "APPROVAL_PLAN_MISMATCH")
    except (KeyError, TypeError, UnicodeError) as exc:
        raise DispatchError() from exc


def validate_plan_package(value: Any) -> dict:
    exact(value, {"plan", "materials"})
    plan = validate_plan(value["plan"])
    m = exact(value["materials"], {"backendProfile", "executionConfig", "processIdentity", "workflow", "costBasis", "prerequisiteEvidence"})
    _profile(m["backendProfile"])
    config = validate_execution_config(m["executionConfig"])
    process = validate_process(m["processIdentity"])
    cost = validate_cost(m["costBasis"])
    for item in exact(m["prerequisiteEvidence"], PREREQUISITES).values():
        pinned(item)
    binding, limits = plan["executionBinding"], plan["limits"]
    require(backend.digest(m["backendProfile"]) == binding["executionProfile"]["digest"], "APPROVAL_PLAN_MISMATCH")
    require(config["backendRef"] == binding["backendDecision"]["backendRef"] and config["credentialSourceRef"] == binding["backendDecision"]["credentialSourceRef"])
    require(digest(config) == binding["executionConfigDigest"] and digest(process) == binding["runtimeBinding"]["processIdentityDigest"])
    require(process["instanceRef"] == binding["runtimeBinding"]["instanceRef"] and process["comfyuiCommit"] == binding["executionCode"]["comfyuiCommit"])
    require(process["launchConfigDigest"] == config["launchConfigDigest"])
    require(sum(config[k] for k in ("requestTimeoutMs", "historyTimeoutMs", "postprocessTimeoutMs")) <= limits["executionTimeoutSeconds"] * 1000)
    require(binding["costBasis"] == {"ref": cost["costBasisRef"], "digest": cost["payloadDigest"]})
    require(m["prerequisiteEvidence"]["costReview"] == cost["reviewDecision"])
    require(digest(m["prerequisiteEvidence"]) == binding["prerequisiteEvidenceDigest"])
    require(utc(cost["validFrom"]) <= utc(limits["notBefore"]) < utc(limits["expiresAt"]) <= utc(cost["validUntil"]), "COST_BOUND_UNVERIFIED")
    require(cost_bound(cost, limits) <= min(limits["maxCostMinor"], binding["backendDecision"]["maxCostMinor"]), "COST_BOUND_UNVERIFIED")
    _workflow(plan, m)
    require(digest(m["workflow"]) == binding["workflowDigest"], "APPROVAL_PLAN_MISMATCH")
    return deepcopy(value)


def validate_bundle(value: Any, *, revocation: bool = False) -> dict:
    collection = "revocations" if revocation else "approvals"
    exact(value, {"schemaVersion", "authorityRef", collection})
    require(value["schemaVersion"] == (REVOCATION_SCHEMA if revocation else APPROVAL_SCHEMA))
    ref(value["authorityRef"])
    entries = value[collection]
    require(type(entries) is list and len(entries) == 1)
    if revocation:
        approval = validate_approval(entries[0], revocation=True)
    else:
        exact(entries[0], {"planPackage", "approval"})
        package = validate_plan_package(entries[0]["planPackage"])
        approval = validate_approval(entries[0]["approval"], plan=package["plan"])
    require(value["authorityRef"] == approval["authorityRef"], "APPROVAL_UNAVAILABLE")
    return deepcopy(value)


def plan_from_grant(grant: dict) -> dict:
    return {"scope": {k: grant[k] for k in SCOPE_FIELDS},
        **{k: deepcopy(grant[k]) for k in ("subject", "executionBinding", "permissions", "limits")}}


def validate_grant(value: Any) -> dict:
    exact(value, SCOPE_FIELDS | {"schemaVersion", "generationDispatchGrantRef", "version", "subject", "subjectDigest",
        "executionBinding", "permissions", "limits", "approval", "issuanceEvidence", "publicationAllowed", "createdAt", "payloadDigest"})
    require(value["schemaVersion"] == GRANT_SCHEMA and type(value["version"]) is int and value["version"] == 1 and value["publicationAllowed"] is False)
    plan = validate_plan(plan_from_grant(value))
    require(value["subjectDigest"] == subject_digest(plan) and value["generationDispatchGrantRef"] == grant_ref(plan))
    validate_approval(value["approval"], plan=plan)
    created = utc(value["createdAt"])
    require(utc(value["approval"]["decidedAt"]) <= created)
    require(utc(value["limits"]["notBefore"]) <= created < utc(value["limits"]["expiresAt"]))
    evidence = exact(value["issuanceEvidence"], {"issuerServiceRef", "requestDigest", "approvalBundleSha256", "snapshotTokens", "currentSubjectReadSet", "currentSubjectReadSetDigest"})
    ref(evidence["issuerServiceRef"])
    for key in ("requestDigest", "approvalBundleSha256", "currentSubjectReadSetDigest"):
        sha(evidence[key])
    tokens(evidence["snapshotTokens"])
    validate_read_set(evidence["currentSubjectReadSet"], expected_scope=plan["scope"], phase="ISSUE")
    validate_read_set_bindings(evidence["currentSubjectReadSet"], plan, value["approval"])
    require(digest(evidence["currentSubjectReadSet"]) == evidence["currentSubjectReadSetDigest"])
    command = {"workspaceRef": value["workspaceRef"], "productionRunRef": value["productionRunRef"],
        "methodAwareInputPlanVersionRef": value["subject"]["methodAwareInputPlanVersion"]["ref"],
        "creativeShotVersionRef": value["subject"]["creativeShotVersion"]["ref"], "beatRef": value["subject"]["actionExecutionBeat"]["ref"],
        "inputAssetVersionRef": value["subject"]["inputAsset"]["assetVersionRef"], "backendRef": value["executionBinding"]["backendDecision"]["backendRef"],
        "expectedSubjectDigest": value["subjectDigest"], "expectedApprovedPlanDigest": value["approval"]["approvedPlanDigest"],
        "authorityDecisionRef": value["approval"]["authorityDecisionRef"]}
    require(evidence["requestDigest"] == issue_request_digest(command, value["approval"]))
    verify_seal(value)
    return deepcopy(value)


def validate_terminal(value: Any) -> dict:
    exact(value, {"schemaVersion", "grantTerminalRef", "generationDispatchGrantRef", "generationDispatchGrantDigest",
        "workspaceRef", "productionRunRef", "kind", "attemptBinding", "revocationApproval", "requestDigest", "snapshotTokens", "createdAt", "payloadDigest"})
    require(value["schemaVersion"] == TERMINAL_SCHEMA)
    for key in ("grantTerminalRef", "generationDispatchGrantRef", "workspaceRef", "productionRunRef"):
        ref(value[key])
    for key in ("generationDispatchGrantDigest", "requestDigest"):
        sha(value[key])
    require(value["grantTerminalRef"] == value["generationDispatchGrantRef"] + ":terminal")
    require(re.fullmatch(r"generation-dispatch-grant-[0-9a-f]{64}", value["generationDispatchGrantRef"]) is not None)
    tokens(value["snapshotTokens"])
    created = utc(value["createdAt"])
    if value["kind"] == "REVOKED":
        require(value["attemptBinding"] is None)
        approval = validate_approval(value["revocationApproval"], revocation=True)
        require(approval["grantDigest"] == value["generationDispatchGrantDigest"] and utc(approval["decidedAt"]) <= created)
        command = {k: value[k] for k in ("workspaceRef", "productionRunRef", "generationDispatchGrantRef", "generationDispatchGrantDigest")}
        command["authorityDecisionRef"] = approval["authorityDecisionRef"]
        require(value["requestDigest"] == revoke_request_digest(command, approval))
    elif value["kind"] == "CONSUMPTION_COMMITTED":
        require(value["revocationApproval"] is None)
        attempt = exact(value["attemptBinding"], {"mediaJobRef", "attemptRef", "workerRef", "workerProcessIdentityDigest", "jobRevision",
            "leaseTokenDigest", "executionEnvelopeDigest", "workflowDigest", "currentSubjectReadSet", "currentSubjectReadSetDigest"})
        for key in ("mediaJobRef", "attemptRef", "workerRef"):
            ref(attempt[key])
        for key in ("workerProcessIdentityDigest", "leaseTokenDigest", "executionEnvelopeDigest", "workflowDigest", "currentSubjectReadSetDigest"):
            sha(attempt[key])
        integer(attempt["jobRevision"])
        read_set = validate_read_set(attempt["currentSubjectReadSet"], phase="CONSUME")
        require(all(read_set["scope"][k] == value[k] for k in ("workspaceRef", "productionRunRef")), "SCOPE_MISMATCH")
        require(digest(read_set) == attempt["currentSubjectReadSetDigest"])
        command = {k: value[k] for k in ("workspaceRef", "productionRunRef", "generationDispatchGrantRef", "generationDispatchGrantDigest")}
        command.update({k: attempt[k] for k in ("mediaJobRef", "attemptRef", "workerRef")})
        command["expectedLeaseTokenDigest"] = attempt["leaseTokenDigest"]
        require(value["requestDigest"] == consumption_request_digest(command, value["generationDispatchGrantDigest"], attempt))
    else:
        raise DispatchError()
    verify_seal(value)
    return deepcopy(value)


def validate_record_envelope(record) -> None:
    """Duck-typed to keep the original journal -> contracts dependency acyclic."""
    grant = record.recordKind == "GenerationDispatchGrant"
    value = validate_grant(dict(record.payload)) if grant else validate_terminal(dict(record.payload))
    require(type(record.recordVersion) is int and record.recordVersion == 1)
    require(record.workspaceRef == value["workspaceRef"] and record.productionRunRef == value["productionRunRef"], "SCOPE_MISMATCH")
    require(record.recordRef == value["generationDispatchGrantRef" if grant else "grantTerminalRef"])
    require(record.payloadDigest == value["payloadDigest"] and record.createdAt == value["createdAt"])
    require(record.requestDigest == (value["issuanceEvidence"]["requestDigest"] if grant else value["requestDigest"]))
    ref(record.idempotencyKey)


def validate_command(operation: str, value: Any) -> dict:
    common = {"workspaceRef", "productionRunRef"}
    if operation == "PREPARE":
        fields = common | {"methodAwareInputPlanVersionRef", "creativeShotVersionRef", "beatRef",
            "inputAssetVersionRef", "backendRef", "executionConfigRef", "costBasisRef", "limits"}
    elif operation == "ISSUE":
        fields = common | {"methodAwareInputPlanVersionRef", "creativeShotVersionRef", "beatRef", "inputAssetVersionRef", "backendRef",
            "expectedSubjectDigest", "expectedApprovedPlanDigest", "authorityDecisionRef", "idempotencyKey", "snapshotTokens"}
    elif operation == "INSPECT":
        fields = common | {"generationDispatchGrantRef"}
    elif operation == "CONSUME":
        fields = common | {"generationDispatchGrantRef", "generationDispatchGrantDigest",
            "mediaJobRef", "attemptRef", "workerRef", "expectedJobRevision",
            "expectedLeaseTokenDigest", "idempotencyKey", "snapshotTokens"}
    elif operation == "REVOKE":
        fields = common | {"generationDispatchGrantRef", "generationDispatchGrantDigest", "authorityDecisionRef", "idempotencyKey", "snapshotTokens"}
    else:
        raise DispatchError()
    exact(value, fields)
    for key, item in value.items():
        if key == "limits":
            validate_limits(item)
        elif key == "snapshotTokens":
            tokens(item)
        elif key == "expectedJobRevision":
            integer(item)
        elif key.endswith("Digest"):
            sha(item)
        else:
            ref(item)
    return deepcopy(value)


def validate_consume_receipt(value: Any) -> dict:
    exact(value, {"schemaVersion", "operation", "terminal", "recordReplay",
        "eligibility", "sendPermission"})
    require(value["schemaVersion"] == PREFIX + "consume-result.v1"
        and value["operation"] == "CONSUME"
        and type(value["recordReplay"]) is bool
        and value["eligibility"] == "CONSUMED"
        and value["sendPermission"] == "NONE")
    terminal = validate_terminal(value["terminal"])
    require(terminal["kind"] == "CONSUMPTION_COMMITTED")
    return deepcopy(value)


def issue_request_digest(command: dict, approval: dict) -> str:
    return digest({"command": {k: v for k, v in command.items() if k not in {"idempotencyKey", "snapshotTokens"}},
        "resolvedApprovalDecisionDigest": approval["authorityDecisionDigest"], "approvedPlanDigest": approval["approvedPlanDigest"]})


def revoke_request_digest(command: dict, approval: dict) -> str:
    return digest({"command": {k: v for k, v in command.items() if k not in {"idempotencyKey", "snapshotTokens"}},
        "resolvedRevocationDecisionDigest": approval["authorityDecisionDigest"]})


def consumption_request_digest(command: dict, grant_digest: str, attempt: dict) -> str:
    """Pure Terminal integrity algorithm; this does not expose a consume operation."""
    return digest({"command": {k: v for k, v in command.items() if k not in {"idempotencyKey", "snapshotTokens", "expectedJobRevision"}},
        "resolvedGrantDigest": grant_digest, **{k: attempt[k] for k in ("attemptRef", "workerRef", "workerProcessIdentityDigest",
            "leaseTokenDigest", "executionEnvelopeDigest", "workflowDigest")}})
