"""Closed technical user-input branch of ADR-0022; no production fact claims.

The original scope is an existing access context. No Script, M6, Shot, Beat,
InputPlan, Admission or AssetVersion is manufactured or inherited here.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from . import generation_dispatch_contracts as c

SUBJECT_SCHEMA = "v5.user-image-video-subject.v1"
GRANT_SCHEMA = "v5.generation-dispatch-grant.v3"
READ_SET_SCHEMA = "v5.generation-dispatch-read-set.v2"
PERMISSIONS = {"dispatchAllowed": True, "inputSubjectProcessingAuthorized": True,
    "inputImageProcessingAuthorized": True}
PREREQUISITES = frozenset({"inputConsent", "executionPolicy", "costReview"})
SELECTORS = {key: c.SELECTORS[key] for key in ("CURRENT_PROJECT", "CURRENT_SERIES", "CURRENT_EPISODE",
    "CURRENT_INPUT_PLAN", "CURRENT_BACKEND_CONFIG", "CURRENT_RUNTIME_PROCESS", "CURRENT_OWNER_APPROVAL")}


def validate_subject(value: Any) -> dict:
    from services.v4_platform.image_video_execution import INPUT_FIELDS, SUBJECT_FIELDS, OUTPUT
    c.exact(value, SUBJECT_FIELDS | {"schemaVersion"})
    c.require(value["schemaVersion"] == SUBJECT_SCHEMA)
    c.ref(value["generationRef"])
    c.sha(value["inputDigest"])
    image = c.exact(value["inputImage"], INPUT_FIELDS)
    c.ref(image["inputRef"])
    c.sha(image["contentDigest"])
    c.require(image["mediaType"] == "image/png")
    c.require(c.integer(image["byteSize"]) <= 20 * 1024 * 1024)
    for key in ("width", "height"):
        c.require(c.integer(image[key]) <= 16384)
    text = value["description"]
    c.require(type(text) is str and 0 < len(text) <= 4000 and bool(text.strip())
        and all(ord(character) >= 32 for character in text))
    c.require(value["descriptionDigest"] == sha256(text.encode("utf-8")).hexdigest())
    c.require(c.canonical(value["cameraInstruction"]) == c.canonical({"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"}))
    c.require(c.canonical(value["outputConstraints"]) == c.canonical(OUTPUT))
    c.require(value["executionClass"] == "MICRO_MOTION" and value["executionMethod"] == "SINGLE_ANCHOR_I2V")
    return deepcopy(value)


def grant_ref(plan: dict) -> str:
    return "generation-dispatch-grant-" + c.digest({"schemaVersion": GRANT_SCHEMA,
        "workspaceRef": plan["scope"]["workspaceRef"], "productionRunRef": plan["scope"]["productionRunRef"],
        "generationRef": plan["subject"]["generationRef"]})


def validate_approval(value: Any, *, plan: dict | None = None) -> dict:
    c.exact(value, c.APPROVAL_FIELDS)
    for key in ("approvalRef", "authorityRef", "authorityDecisionRef", "actorRef", "approvalEvidenceRef"):
        c.ref(value[key])
    for key in ("approvedPlanDigest", "approvalEvidenceDigest"):
        c.sha(value[key])
    c.require(value["actorKind"] == "HUMAN" and value["actorRole"] == "AUTHORIZED_CREATOR"
        and value["approvalKind"] == "USER_IMAGE_VIDEO_EXECUTION" and value["decision"] == "APPROVED")
    c.utc(value["decidedAt"])
    c.verify_seal(value, "authorityDecisionDigest")
    if plan is not None:
        c.require(plan["subject"].get("schemaVersion") == SUBJECT_SCHEMA, "APPROVAL_PLAN_MISMATCH")
        c.require(value["approvedPlanDigest"] == c.digest(plan), "APPROVAL_PLAN_MISMATCH")
    return deepcopy(value)


def validate_package_approval(package: dict, approval: dict) -> None:
    validate_approval(approval, plan=package["plan"])
    c.require(package["materials"]["prerequisiteEvidence"]["executionPolicy"]
        == {"ref": approval["approvalEvidenceRef"], "digest": approval["approvalEvidenceDigest"]},
        "APPROVAL_UNAVAILABLE")


def issue_command_identity(plan: dict, approval: dict) -> dict:
    """The digest-bearing exact command fields; idempotency and CAS are separate."""
    return {"workspaceRef": plan["scope"]["workspaceRef"], "productionRunRef": plan["scope"]["productionRunRef"],
        "generationRef": plan["subject"]["generationRef"],
        "backendRef": plan["executionBinding"]["backendDecision"]["backendRef"],
        "expectedSubjectDigest": c.subject_digest(plan), "expectedApprovedPlanDigest": c.digest(plan),
        "authorityDecisionRef": approval["authorityDecisionRef"]}


def validate_read_set(value: Any, *, expected_scope: dict | None = None, phase: str | None = None) -> dict:
    c.exact(value, {"schemaVersion", "scope", "phase", "coordinationEpoch", "objects", "selectors"})
    c.require(value["schemaVersion"] == READ_SET_SCHEMA)
    c.scope(value["scope"])
    c.require(expected_scope is None or value["scope"] == expected_scope, "SCOPE_MISMATCH")
    c.require(value["phase"] in {"PREPARE", "ISSUE", "CONSUME", "SEND"}
        and (phase is None or phase == value["phase"]))
    c.sha(value["coordinationEpoch"])
    c.require(type(value["objects"]) is list and bool(value["objects"]) and type(value["selectors"]) is list)
    object_keys, objects = [], set()
    allowed_owners = {owner for owner, _ in SELECTORS.values()}
    for item in value["objects"]:
        c.exact(item, {"owner", "objectKind", "objectRef", "objectDigest"})
        c.require(item["owner"] in allowed_owners)
        c.ref(item["objectKind"]); c.ref(item["objectRef"]); c.sha(item["objectDigest"])
        object_keys.append((item["owner"], item["objectKind"], item["objectRef"]))
        objects.add((item["owner"], item["objectRef"], item["objectDigest"]))
    c.require(object_keys == sorted(set(object_keys)))
    keys, kinds = [], []
    for item in value["selectors"]:
        c.exact(item, {"owner", "selectorKind", "scopeRef", "selectedRef", "selectedDigest", "coordinationRevision"})
        c.require(item["selectorKind"] in SELECTORS)
        owner, scope_key = SELECTORS[item["selectorKind"]]
        c.require(item["owner"] == owner and item["scopeRef"] == value["scope"][scope_key], "SCOPE_MISMATCH")
        c.ref(item["selectedRef"]); c.sha(item["selectedDigest"]); c.integer(item["coordinationRevision"], 0)
        c.require((owner, item["selectedRef"], item["selectedDigest"]) in objects)
        keys.append((owner, item["selectorKind"], item["scopeRef"]))
        kinds.append(item["selectorKind"])
    expected = set(SELECTORS) - ({"CURRENT_OWNER_APPROVAL"} if value["phase"] == "PREPARE" else set())
    c.require(keys == sorted(set(keys)) and len(kinds) == len(expected) and set(kinds) == expected)
    return deepcopy(value)


def validate_read_set_bindings(read_set: dict, plan: dict, approval: dict) -> None:
    validate_read_set(read_set, expected_scope=plan["scope"])
    subject, binding = plan["subject"], plan["executionBinding"]
    selected = {item["selectorKind"]: item for item in read_set["selectors"]}
    for kind, field in (("CURRENT_PROJECT", "projectRef"), ("CURRENT_SERIES", "seriesRef"), ("CURRENT_EPISODE", "episodeRef")):
        c.require(selected[kind]["selectedRef"] == plan["scope"][field], "SCOPE_MISMATCH")
    c.require((selected["CURRENT_INPUT_PLAN"]["selectedRef"], selected["CURRENT_INPUT_PLAN"]["selectedDigest"])
        == (subject["generationRef"], subject["inputDigest"]), "SOURCE_CHANGED")
    c.require(selected["CURRENT_BACKEND_CONFIG"]["selectedDigest"] == binding["executionConfigDigest"], "CONFIG_CHANGED")
    c.require((selected["CURRENT_RUNTIME_PROCESS"]["selectedRef"], selected["CURRENT_RUNTIME_PROCESS"]["selectedDigest"])
        == (binding["runtimeBinding"]["instanceRef"], binding["runtimeBinding"]["processIdentityDigest"]), "RUNTIME_CHANGED")
    if read_set["phase"] != "PREPARE":
        c.require((selected["CURRENT_OWNER_APPROVAL"]["selectedRef"], selected["CURRENT_OWNER_APPROVAL"]["selectedDigest"])
            == (approval["authorityDecisionRef"], approval["authorityDecisionDigest"]), "APPROVAL_UNAVAILABLE")
    objects = {(item["owner"], item["objectRef"], item["objectDigest"]) for item in read_set["objects"]}
    expected = [("V5_EPISODE_PRODUCTION", subject["generationRef"], subject["inputDigest"]),
        ("V4_BACKEND_CONFIG", binding["executionProfile"]["ref"], binding["executionProfile"]["digest"]),
        ("V4_BACKEND_CONFIG", binding["costBasis"]["ref"], binding["costBasis"]["digest"])]
    if read_set["phase"] != "PREPARE":
        expected.append(("OWNER_APPROVAL", approval["approvalEvidenceRef"], approval["approvalEvidenceDigest"]))
    c.require(all(item in objects for item in expected), "SOURCE_CHANGED")


def compile_workflow(plan: dict, materials: dict) -> dict:
    from services.v4_platform.image_video_execution import compile_user_image_video_workflow
    subject, profile = plan["subject"], materials["backendProfile"]
    c.require(profile["schemaVersion"] == "v4.comfyui-a14b-i2v-backend-profile.v3", "CONFIG_CHANGED")
    c.require(profile["parameters"]["positivePrompt"] == subject["description"], "SOURCE_CHANGED")
    c.require(profile["parameters"]["input"]["contentDigest"] == subject["inputImage"]["contentDigest"], "SOURCE_CHANGED")
    c.require(materials["prerequisiteEvidence"]["inputConsent"]
        == {"ref": subject["generationRef"], "digest": subject["inputDigest"]}, "SOURCE_CHANGED")
    try:
        return compile_user_image_video_workflow(
            generation_request_ref="generation-request-" + c.digest(c.request_identity(plan)),
            input_image=subject["inputImage"], backend_profile=profile,
            output_constraints=subject["outputConstraints"])
    except (ValueError, TypeError, KeyError) as exc:
        raise c.DispatchError("APPROVAL_PLAN_MISMATCH") from exc


def validate_grant(value: Any) -> dict:
    c.exact(value, c.SCOPE_FIELDS | {"schemaVersion", "generationDispatchGrantRef", "version", "subject", "subjectDigest",
        "executionBinding", "permissions", "limits", "approval", "issuanceEvidence", "publicationAllowed", "createdAt", "payloadDigest"})
    c.require(value["schemaVersion"] == GRANT_SCHEMA and type(value["version"]) is int
        and value["version"] == 1 and value["publicationAllowed"] is False)
    c.require(value["subject"].get("schemaVersion") == SUBJECT_SCHEMA)
    plan = c.validate_plan(c.plan_from_grant(value))
    c.require(value["subjectDigest"] == c.subject_digest(plan) and value["generationDispatchGrantRef"] == grant_ref(plan))
    validate_approval(value["approval"], plan=plan)
    created = c.utc(value["createdAt"])
    c.require(c.utc(value["approval"]["decidedAt"]) <= created)
    c.require(c.utc(value["limits"]["notBefore"]) <= created < c.utc(value["limits"]["expiresAt"]))
    evidence = c.exact(value["issuanceEvidence"], {"issuerServiceRef", "requestDigest", "approvalBundleSha256", "snapshotTokens",
        "currentSubjectReadSet", "currentSubjectReadSetDigest"})
    c.ref(evidence["issuerServiceRef"])
    for key in ("requestDigest", "approvalBundleSha256", "currentSubjectReadSetDigest"):
        c.sha(evidence[key])
    c.tokens(evidence["snapshotTokens"])
    validate_read_set(evidence["currentSubjectReadSet"], expected_scope=plan["scope"], phase="ISSUE")
    validate_read_set_bindings(evidence["currentSubjectReadSet"], plan, value["approval"])
    c.require(c.digest(evidence["currentSubjectReadSet"]) == evidence["currentSubjectReadSetDigest"])
    c.require(evidence["requestDigest"] == c.issue_request_digest(issue_command_identity(plan, value["approval"]), value["approval"]))
    c.verify_seal(value)
    return deepcopy(value)
