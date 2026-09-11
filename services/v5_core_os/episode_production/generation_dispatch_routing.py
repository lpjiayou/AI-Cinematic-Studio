"""Operation-specific stored-Grant routing. It only reserves an unclaimed Job."""
from __future__ import annotations

from copy import deepcopy

from services.v4_platform.backend_registry import execution_classification
from services.v4_platform.generation_dispatch_jobs import create_generation_dispatch_job
from services.v4_platform.media_jobs import _validate_method_aware_video_request
from services.v4_platform.method_aware_execution import (
    DISPATCH_REQUEST_SCHEMA, MethodAwareExecutionEnvelopeBuilder, validate_dispatch_grant_binding,
)
from . import generation_dispatch_contracts as c
from .evidence import EvidenceRecord
from .method_aware_media import _ROUTE_PLAN_FIELDS, _VIDEO_ROUTE_FIELDS, VIDEO_METHOD_ROUTE_RECORD_KIND


def validate_route_plan(value):
    c.exact(value, set(_ROUTE_PLAN_FIELDS) | {"dispatchGrantBinding"})
    c.require(value["schemaVersion"] == "v5.video-method-route-plan.v2")
    binding = validate_dispatch_grant_binding(value["dispatchGrantBinding"])
    c.verify_seal(value)
    c.integer(value["routingVersion"])
    c.require(type(value["routes"]) is list and len(value["routes"]) == 1
        and type(value["videoGenerationRequests"]) is list and len(value["videoGenerationRequests"]) == 1
        and type(value["queuedJobs"]) is list and len(value["queuedJobs"]) == 1
        and type(value["videoGenerationRequestCount"]) is int and value["videoGenerationRequestCount"] == 1
        and type(value["queuedJobCount"]) is int and value["queuedJobCount"] == 1
        and value["wanFallbackUsed"] is False and value["publicationAllowed"] is False)
    route, request, queued = value["routes"][0], value["videoGenerationRequests"][0], value["queuedJobs"][0]
    c.exact(route, set(_VIDEO_ROUTE_FIELDS) | {"dispatchGrantBinding"})
    c.verify_seal(route)
    c.require(route["schemaVersion"] == "v5.video-method-route.v2"
        and route["dispatchGrantBinding"] == binding and route["fallbackUsed"] is False
        and route["routingState"] == "QUEUED_EXISTING_MEDIA_JOB" and route["targetBoundary"] == "M11_VIDEO_EXECUTION")
    _validate_method_aware_video_request(request)
    c.require(request["schemaVersion"] == DISPATCH_REQUEST_SCHEMA
        and request["dispatchGrantBinding"] == binding
        and all(request[k] == value[k] for k in c.SCOPE_FIELDS)
        and route["videoGenerationRequestRef"] == request["generationRequestRef"]
        and route["videoGenerationRequestDigest"] == request["payloadDigest"])
    c.exact(queued, {"generationRequestRef", "generationRequestDigest", "mediaJobRef", "queueState", "queueReplay"})
    c.require(queued["generationRequestRef"] == request["generationRequestRef"]
        and queued["generationRequestDigest"] == request["payloadDigest"]
        and queued["mediaJobRef"] == route["mediaJobRef"] and type(queued["queueReplay"]) is bool)
    for key in ("creativeShotVersionRef", "creativeShotVersionDigest", "beatRef", "beatDigest",
            "visualExecutionRequirementRef", "visualExecutionRequirementDigest", "executionClass", "executionMethod"):
        c.require(route[key] == request[key])
    return deepcopy(value)


class GenerationDispatchRouting:
    def __init__(self, *, foundation, source_reader, coordinator):
        self.foundation, self.source, self.queue = foundation, source_reader, coordinator

    def route_for_grant(self, workspace_ref, production_run_ref, generation_dispatch_grant_ref, *, idempotency_key):
        """Internal typed operation; no public HTTP/CLI route is installed."""
        for ref in (workspace_ref, production_run_ref, generation_dispatch_grant_ref, idempotency_key):
            c.ref(ref)
        f = self.foundation
        with f._gate(workspace_ref) as lease:
            grant = f._grant({"workspaceRef": workspace_ref, "productionRunRef": production_run_ref,
                "generationDispatchGrantRef": generation_dispatch_grant_ref})
            binding = {"generationDispatchGrantRef": grant["generationDispatchGrantRef"],
                "generationDispatchGrantDigest": grant["payloadDigest"], "subjectDigest": grant["subjectDigest"],
                "approvedPlanDigest": grant["approval"]["approvedPlanDigest"]}
            request_digest = c.digest({"scope": {k: grant[k] for k in c.SCOPE_FIELDS},
                "dispatchGrantBinding": binding})
            repo = f._repository()
            existing = repo.get_record_by_idempotency_key(workspace_ref, production_run_ref, idempotency_key)
            if existing is not None:
                c.require(existing["recordKind"] == VIDEO_METHOD_ROUTE_RECORD_KIND
                    and existing["requestDigest"] == request_digest, "IDEMPOTENCY_CONFLICT")
                payload = validate_route_plan(existing["payload"])
                c.require(existing["recordRef"] == payload["videoMethodRouteRef"]
                    and existing["recordVersion"] == payload["routingVersion"]
                    and existing["payloadDigest"] == payload["payloadDigest"], "PERSISTENCE_UNAVAILABLE")
                return {**payload, "idempotentReplay": True}
            terminal = f._terminal(grant)
            c.require(terminal is None, "ALREADY_REVOKED" if terminal and terminal["kind"] == "REVOKED" else "ALREADY_CONSUMED")
            selected = f._selected(grant["approval"]["authorityDecisionRef"])
            c.require(selected.approval == grant["approval"]
                and selected.plan_package["plan"] == c.plan_from_grant(grant)
                and selected.bundle_sha256 == grant["issuanceEvidence"]["approvalBundleSha256"], "APPROVAL_UNAVAILABLE")
            f._current(selected, lease)
            now = c.utc(f._now())
            c.require(c.utc(grant["limits"]["notBefore"]) <= now < c.utc(grant["limits"]["expiresAt"]), "OUTSIDE_VALIDITY_WINDOW")
            subject = grant["subject"]
            resolved = self.source.resolve({"workspaceRef": workspace_ref, "productionRunRef": production_run_ref,
                "methodAwareInputPlanVersionRef": subject["methodAwareInputPlanVersion"]["ref"],
                "creativeShotVersionRef": subject["creativeShotVersion"]["ref"],
                "beatRef": subject["actionExecutionBeat"]["ref"],
                "inputAssetVersionRef": subject["inputAsset"]["assetVersionRef"]}, lease)
            c.require(resolved.subject == subject, "SOURCE_CHANGED")
            decision = grant["executionBinding"]["backendDecision"]
            reference = "generation-request-" + c.digest(c.request_identity(selected.plan_package["plan"]))
            request = {"schemaVersion": DISPATCH_REQUEST_SCHEMA, **resolved.scope,
                "generationRequestRef": reference, "generationRequestVersionRef": reference + ":v2", "version": 2,
                "dispatchGrantBinding": binding, "executionClass": subject["executionClass"],
                "executionMethod": subject["executionMethod"], "cameraInstruction": deepcopy(subject["cameraInstruction"]),
                "sourceAction": deepcopy(subject["sourceAction"]), "frameRange": deepcopy(subject["frameRange"]),
                "adapterCapability": decision["adapterCapability"], "executionMode": execution_classification(decision)[0],
                "executionAuthorizationState": "QUEUED_NOT_EXECUTED", "requestedProvenance": execution_classification(decision)[1],
                "selectionRequired": True, "publicationAllowed": False, "createdAt": grant["createdAt"]}
            for key, name in (("methodAwareInputPlanVersion", "methodAwareInputPlan"),
                    ("executionMethodPlanVersion", "executionMethodPlan"),
                    ("visualExecutionRequirement", "visualExecutionRequirement"),
                    ("creativeShotVersion", "creativeShotVersion"), ("actionExecutionBeat", "beat")):
                request[name + ("VersionRef" if key in {"methodAwareInputPlanVersion", "executionMethodPlanVersion"} else "Ref")] = subject[key]["ref"]
                request[name + "Digest"] = subject[key]["digest"]
            for source, target in (("assetRef", "AssetRef"), ("assetVersionRef", "AssetVersionRef"),
                    ("assetVersionDigest", "AssetVersionDigest"), ("contentDigest", "ContentDigest"), ("mediaType", "MediaType")):
                request["sourceImage" + target] = subject["inputAsset"][source]
            request = c.sealed(request)
            envelope = MethodAwareExecutionEnvelopeBuilder().build_dispatch_bound(request,
                {k: v for k, v in subject["inputAsset"].items() if k != "inputRole"}, decision,
                selected.plan_package["materials"]["backendProfile"],
                {"sourceText": resolved.source_text, "outputConstraints": subject["outputConstraints"]})
            lease.assert_held()
            # V4 create and V5 append are separate original transactions. Once
            # creation is entered, failures cannot assert a global zero-write result.
            try:
                job, replay = create_generation_dispatch_job(self.queue, verified_grant=grant,
                    request=request, envelope=envelope)
                payload = self._route_payload(grant, binding, resolved, request, job, replay)
                records = repo.list_records(workspace_ref, production_run_ref, record_kind=VIDEO_METHOD_ROUTE_RECORD_KIND)
                previous = [r for r in records if r["recordRef"] == payload["videoMethodRouteRef"]]
                payload["routingVersion"] = len(previous) + 1
                payload["videoMethodRouteVersionRef"] = payload["videoMethodRouteRef"] + ":" + str(payload["routingVersion"])
                payload = c.sealed(payload)
                validate_route_plan(payload)
                token = repo.record_journal_head(workspace_ref, production_run_ref)
                record = EvidenceRecord(workspace_ref, production_run_ref, VIDEO_METHOD_ROUTE_RECORD_KIND,
                    payload["videoMethodRouteRef"], payload["routingVersion"], idempotency_key,
                    request_digest, payload["createdAt"], payload, payload["payloadDigest"])
                rows, replayed = repo.append_records((record,), expected_record_journal_head=token)
                result = validate_route_plan(rows[0]["payload"])
                return {**result, "idempotentReplay": replayed}
            except Exception as exc:
                raise c.CommitOutcomeUnknown() from exc

    def _route_payload(self, grant, binding, resolved, request, job, replay):
        plan = resolved.originals["inputPlan"]
        method = next(m for m in plan["methodInputPlans"] if m["beatRef"] == request["beatRef"]
            and m["creativeShotVersionRef"] == request["creativeShotVersionRef"])
        decision = grant["executionBinding"]["backendDecision"]
        route = {"schemaVersion": "v5.video-method-route.v2",
            "routeRef": "generation-dispatch-route-" + c.digest(binding), "routeOrder": 1,
            "methodInputPlanRef": method["methodInputPlanRef"], "methodInputPlanDigest": method["payloadDigest"],
            **{k: request[k] for k in ("visualExecutionRequirementRef", "visualExecutionRequirementDigest",
                "creativeShotVersionRef", "creativeShotVersionDigest", "beatRef", "beatDigest", "executionClass", "executionMethod")},
            "routingState": "QUEUED_EXISTING_MEDIA_JOB", "adapterCapability": decision["adapterCapability"],
            "adapterIdentity": decision["adapterIdentity"], "videoGenerationRequestRef": request["generationRequestRef"],
            "videoGenerationRequestDigest": request["payloadDigest"], "mediaJobRef": job["jobRef"],
            "fallbackUsed": False, "targetBoundary": "M11_VIDEO_EXECUTION", "dispatchGrantBinding": deepcopy(binding)}
        return {"schemaVersion": "v5.video-method-route-plan.v2", **resolved.scope,
            "videoMethodRouteRef": "generation-dispatch-route-plan-" + c.digest({"grantRef": grant["generationDispatchGrantRef"]}),
            "methodAwareInputPlanRef": plan["methodAwareInputPlanRef"],
            "methodAwareInputPlanVersionRef": plan["methodAwareInputPlanVersionRef"], "methodAwareInputPlanDigest": plan["payloadDigest"],
            "executionMethodPlanVersionRef": plan["executionMethodPlanVersionRef"], "executionMethodPlanDigest": plan["executionMethodPlanDigest"],
            "capabilityRegistryVersion": decision["registryVersion"], "capabilityRegistryDigest": decision["registryDigest"],
            "routes": [c.sealed(route)], "videoGenerationRequests": [deepcopy(request)],
            "queuedJobs": [{"generationRequestRef": request["generationRequestRef"], "generationRequestDigest": request["payloadDigest"],
                "mediaJobRef": job["jobRef"], "queueState": job["state"], "queueReplay": replay}],
            "videoGenerationRequestCount": 1, "queuedJobCount": 1, "wanFallbackUsed": False,
            "publicationAllowed": False, "createdAt": self.foundation._now(), "dispatchGrantBinding": deepcopy(binding)}
