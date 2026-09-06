"""Atomic, provider-neutral handoff from verified V4 results to V5 evidence.

V4 remains a read-only terminal fact source.  The existing V5 journal commits
exactly three records; this is not a transaction across the two databases.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Protocol, Sequence

from services.v4_platform.method_aware_results import MethodAwareJobResultError

from .evidence import EvidenceRecord
from .foundation import (
    EpisodeProductionError, IdempotencyConflictError, RecordNotFoundError,
    StaleInputError, _digest, _idempotency_key, _required_ref,
)
from .media_candidate_review import CANDIDATE, TECHNICAL_VALIDATION, _digest_value

METHOD_AWARE_MEDIA_JOB_RESULT_RECORD_KIND = "MethodAwareMediaJobResult"
METHOD_AWARE_MEDIA_JOB_RESULT_RECEIPT_SCHEMA = "v5.method-aware-media-job-result-receipt.v1"
METHOD_AWARE_VIDEO_JOB_PROJECTION_SCHEMA = "v5.method-aware-video-job-projection.v1"
SCOPE_FIELDS = ("workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef")
COMMAND_FIELDS = frozenset((*SCOPE_FIELDS, "videoMethodRouteVersionRef", "videoMethodRouteDigest",
    "mediaJobRef", "mediaJobResultDigest", "idempotencyKey"))


class MethodAwareResultReaderPort(Protocol):
    def project_statuses(self, workspace_ref: str, production_run_ref: str,
                         exact_job_refs: Sequence[str]) -> list[dict[str, Any]]: ...

    def require_verified_succeeded_result(self, workspace_ref: str, production_run_ref: str,
        media_job_ref: str, expected_generation_request_ref: str, expected_generation_request_digest: str,
        expected_route_registry_version: str, expected_route_registry_digest: str) -> dict[str, Any]: ...


class MethodAwareResultIntakeError(EpisodeProductionError):
    def __init__(self, code: str) -> None:
        self.code = code
        self.status = {"method_aware_job_result_unavailable": 503,
            "method_aware_job_not_found": 404, "method_aware_job_scope_mismatch": 404}.get(code, 409)
        super().__init__(code)


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["payloadDigest"] = _digest(result)
    return result


class MethodAwareResultIntakeService:
    def __init__(self, routes, reader: MethodAwareResultReaderPort | None, candidate_review) -> None:
        self.routes = routes
        self.reader = reader
        self.review = candidate_review
        self.evidence = candidate_review.evidence

    def _read(self, operation: str, *args):
        if self.reader is None:
            raise MethodAwareResultIntakeError("method_aware_job_result_unavailable")
        try:
            return getattr(self.reader, operation)(*args)
        except MethodAwareJobResultError as exc:
            raise MethodAwareResultIntakeError(exc.code) from exc

    def _route(self, scope, version):
        try:
            return self.routes.get_video_method_route(*[scope[k] for k in SCOPE_FIELDS], version)
        except RecordNotFoundError as exc:
            raise MethodAwareResultIntakeError("method_aware_job_scope_mismatch") from exc

    @staticmethod
    def _binding(route, job_ref):
        queued = [q for q in route["queuedJobs"] if q["mediaJobRef"] == job_ref]
        if len(queued) != 1:
            raise MethodAwareResultIntakeError("method_aware_job_not_found")
        mapping = queued[0]
        requests = [r for r in route["videoGenerationRequests"]
            if r["generationRequestRef"] == mapping["generationRequestRef"]
            and r["payloadDigest"] == mapping["generationRequestDigest"]]
        routes = [r for r in route["routes"] if r.get("mediaJobRef") == job_ref
            and r.get("videoGenerationRequestRef") == mapping["generationRequestRef"]
            and r.get("videoGenerationRequestDigest") == mapping["generationRequestDigest"]]
        if len(requests) != 1 or len(routes) != 1:
            raise MethodAwareResultIntakeError("method_aware_job_result_invalid")
        request, item = requests[0], routes[0]
        if (item["adapterCapability"] != request["adapterCapability"]
                or any(request[k] != route[k] for k in SCOPE_FIELDS)):
            raise MethodAwareResultIntakeError("method_aware_job_result_invalid")
        return request, item

    def _receipts(self, workspace, run_ref):
        return self.evidence.list_records(workspace, run_ref, record_kind=METHOD_AWARE_MEDIA_JOB_RESULT_RECORD_KIND)

    def _existing(self, command, request_digest):
        workspace, run_ref = command["workspaceRef"], command["productionRunRef"]
        keyed = self.evidence.get_record_by_idempotency_key(workspace, run_ref, command["idempotencyKey"])
        if keyed is not None and (keyed["recordKind"] != METHOD_AWARE_MEDIA_JOB_RESULT_RECORD_KIND
                                  or keyed["requestDigest"] != request_digest):
            raise IdempotencyConflictError("result intake idempotency conflict")
        matches = [r for r in self._receipts(workspace, run_ref)
            if r["payload"].get("mediaJobRef") == command["mediaJobRef"]]
        if len(matches) > 1:
            raise MethodAwareResultIntakeError("method_aware_job_result_conflict")
        if matches:
            record = matches[0]
            value = record["payload"]
            if (value["v4JobResultDigest"] != command["mediaJobResultDigest"]
                    or value["videoMethodRouteVersionRef"] != command["videoMethodRouteVersionRef"]
                    or value["videoMethodRouteDigest"] != command["videoMethodRouteDigest"]):
                raise MethodAwareResultIntakeError("method_aware_job_result_conflict")
            return record
        return None

    def _response(self, receipt, *, replayed):
        workspace, run_ref = receipt["workspaceRef"], receipt["productionRunRef"]
        snapshot = self.evidence.read_snapshot(workspace, run_ref)
        records = snapshot.records
        candidates = [r for r in records if r["recordKind"] == CANDIDATE
            and r["payload"].get("methodAwareMediaJobResultRef") == receipt["recordRef"]
            and r["payload"].get("methodAwareMediaJobResultDigest") == receipt["payloadDigest"]]
        validation_ref = "method-aware-validation-" + receipt["recordRef"].removeprefix("method-aware-result-")
        validations = [r for r in records if r["recordKind"] == TECHNICAL_VALIDATION
            and r["recordRef"] == validation_ref and r["recordVersion"] == 1
            and len(candidates) == 1 and r["payload"].get("candidateRef") == candidates[0]["recordRef"]
            and r["payload"].get("candidateDigest") == candidates[0]["payloadDigest"]]
        if len(candidates) != 1 or len(validations) != 1:
            raise MethodAwareResultIntakeError("method_aware_job_result_conflict")
        lifecycle = self.review.get_projection(workspace, run_ref, records=records, gates=snapshot.gates)
        item = next(c for c in lifecycle["candidates"] if c["candidateRef"] == candidates[0]["recordRef"])
        return {"resultReceipt": deepcopy(receipt["payload"]), "candidate": deepcopy(candidates[0]["payload"]),
            "technicalValidation": deepcopy(validations[0]["payload"]), "candidateLifecycle": item,
            "idempotentReplay": replayed, "publicationAllowed": False}

    def ingest(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != COMMAND_FIELDS:
            raise EpisodeProductionError("invalid result intake command")
        scope = {k:_required_ref(command[k], k) for k in SCOPE_FIELDS}
        version = _required_ref(command["videoMethodRouteVersionRef"], "videoMethodRouteVersionRef")
        _required_ref(command["mediaJobRef"], "mediaJobRef")
        _idempotency_key(command["idempotencyKey"])
        for k in ("videoMethodRouteDigest", "mediaJobResultDigest"):
            _digest_value(command[k], k)
        workspace, run_ref = scope["workspaceRef"], scope["productionRunRef"]
        head = self.evidence.record_journal_head(workspace, run_ref)
        route = self._route(scope, version)
        request_digest = _digest({k:v for k,v in command.items() if k != "idempotencyKey"})
        existing = self._existing(command, request_digest)
        if route["currentness"] != "CURRENT" or route["payloadDigest"] != command["videoMethodRouteDigest"]:
            raise MethodAwareResultIntakeError("method_aware_job_route_stale")
        request, item = self._binding(route, command["mediaJobRef"])
        result = self._read("require_verified_succeeded_result", workspace, run_ref, command["mediaJobRef"],
            request["generationRequestRef"], request["payloadDigest"],
            route["capabilityRegistryVersion"], route["capabilityRegistryDigest"])
        if result["payloadDigest"] != command["mediaJobResultDigest"]:
            raise MethodAwareResultIntakeError("method_aware_job_result_digest_mismatch")
        fields = ("workspaceRef", "productionRunRef", "creativeShotVersionRef", "creativeShotVersionDigest", "beatRef", "beatDigest")
        source_fields = {"sourceAssetRef":"sourceImageAssetRef", "sourceAssetVersionRef":"sourceImageAssetVersionRef",
            "sourceAssetVersionDigest":"sourceImageAssetVersionDigest", "sourceContentDigest":"sourceImageContentDigest"}
        if (any(result[k] != request[k] for k in fields)
                or any(result[k] != request[v] for k,v in source_fields.items())
                or result["publicationAllowed"] is not False):
            raise MethodAwareResultIntakeError("method_aware_job_result_invalid")
        if existing is not None:
            return self._response(existing, replayed=True)
        identity = _digest({**scope, "mediaJobRef":command["mediaJobRef"]})[:40]
        receipt_ref = "method-aware-result-" + identity
        payload = _seal({
            "schemaVersion": METHOD_AWARE_MEDIA_JOB_RESULT_RECEIPT_SCHEMA,
            "methodAwareMediaJobResultRef": receipt_ref, "methodAwareMediaJobResultVersion": 1, **scope,
            **{k:route[k] for k in ("videoMethodRouteRef", "videoMethodRouteVersionRef")},
            "videoMethodRouteDigest": route["payloadDigest"], "routeRef": item["routeRef"], "routeDigest": item["payloadDigest"],
            **{k:result[k] for k in ("generationRequestRef", "generationRequestDigest", "creativeShotVersionRef",
                "creativeShotVersionDigest", "beatRef", "beatDigest", "sourceAssetVersionRef", "sourceAssetVersionDigest",
                "sourceContentDigest", "mediaJobRef", "attemptRef", "attemptBackendBindingDigest", "artifactRef",
                "artifactByteSize", "artifactStorageKey", "artifactProbeDigest", "providerExecutionDigest")},
            "v4JobResultDigest": result["payloadDigest"], "artifactDigest": result["artifactSha256"],
            "resultState": "SUCCEEDED_VERIFIED", "publicationAllowed": False,
        })
        receipt = EvidenceRecord(workspaceRef=workspace, productionRunRef=run_ref,
            recordKind=METHOD_AWARE_MEDIA_JOB_RESULT_RECORD_KIND, recordRef=receipt_ref, recordVersion=1,
            idempotencyKey=command["idempotencyKey"], requestDigest=request_digest,
            createdAt=self.review._clock(), payload=payload, payloadDigest=payload["payloadDigest"])
        candidate = self.review.prepare_method_aware_candidate_record(receipt,
            candidate_ref="method-aware-candidate-"+identity, idempotency_key="method-aware-candidate:"+identity)
        checks = deepcopy(result["technicalChecks"]) + [
            {"check":name, "passed":True} for name in ("route-request-job-binding-exact", "source-asset-version-current")]
        validation = self.review.prepare_technical_validation_record({
            **scope, "idempotencyKey":"method-aware-validation:"+identity,
            "candidateRef":candidate.recordRef, "candidateVersion":1, "candidateDigest":candidate.payloadDigest,
            "technicalValidationRef":"method-aware-validation-"+identity,
            "validatorRef":"v4-method-aware-job-result-verifier-v1", "result":"PASS", "checks":checks,
        }, candidate_record=candidate)
        if self._route(scope, version)["currentness"] != "CURRENT":
            raise MethodAwareResultIntakeError("method_aware_job_route_stale")
        try:
            stored, replayed = self.evidence.append_records((receipt, candidate, validation),
                expected_record_journal_head=head)
        except (IdempotencyConflictError, StaleInputError):
            # A racing identical intake may have won the entire batch.  Never
            # retry an append or complete a partially present result.
            existing = self._existing(command, request_digest)
            if existing is not None:
                return self._response(existing, replayed=True)
            raise
        return self._response(stored[0], replayed=replayed)

    def project_jobs(self, workspace_ref, project_ref, series_ref, episode_ref,
                     production_run_ref, version_ref=None):
        scope = dict(zip(SCOPE_FIELDS, (workspace_ref, project_ref, series_ref, episode_ref, production_run_ref)))
        route = self._route(scope, version_ref)
        refs = [q["mediaJobRef"] for q in route["queuedJobs"]]
        statuses = self._read("project_statuses", workspace_ref, production_run_ref, refs)
        receipts = self._receipts(workspace_ref, production_run_ref)
        jobs = []
        for status in statuses:
            request, _ = self._binding(route, status["mediaJobRef"])
            if (status["generationRequestRef"] != request["generationRequestRef"]
                    or status["generationRequestDigest"] != request["payloadDigest"]):
                raise MethodAwareResultIntakeError("method_aware_job_result_invalid")
            if status["state"] == "SUCCEEDED":
                verified = self._read("require_verified_succeeded_result", workspace_ref, production_run_ref,
                    status["mediaJobRef"], request["generationRequestRef"], request["payloadDigest"],
                    route["capabilityRegistryVersion"], route["capabilityRegistryDigest"])
                if verified["payloadDigest"] != status["resultDigest"]:
                    raise MethodAwareResultIntakeError("method_aware_job_result_invalid")
            receipt = next((r for r in receipts if r["payload"]["mediaJobRef"] == status["mediaJobRef"]), None)
            state = {"FAILED":"FAILED", "CANCELLED":"CANCELLED", "SUCCEEDED":"READY_FOR_INTAKE"}.get(status["state"], "NOT_READY")
            recorded = self._response(receipt, replayed=True) if receipt else None
            if recorded:
                if receipt["payload"]["v4JobResultDigest"] != status["resultDigest"]:
                    raise MethodAwareResultIntakeError("method_aware_job_result_conflict")
                state = "RECORDED"
            if route["currentness"] != "CURRENT" and status["state"] == "SUCCEEDED":
                state = "BLOCKED_STALE_ROUTE"
            jobs.append({**{k:status[k] for k in ("generationRequestRef", "generationRequestDigest", "mediaJobRef",
                    "attemptCount", "failureClass", "errorCode", "resultDigest", "artifactSummary")},
                **{k:request[k] for k in ("creativeShotVersionRef", "beatRef")},
                "jobState":status["state"], "candidateIntakeState":state,
                "candidateRef":recorded["candidate"]["candidateRef"] if recorded else None,
                "technicalValidationRef":recorded["technicalValidation"]["technicalValidationRef"] if recorded else None,
                "publicationAllowed":False})
        return _seal({"schemaVersion":METHOD_AWARE_VIDEO_JOB_PROJECTION_SCHEMA, **scope,
            "videoMethodRouteVersionRef":route["videoMethodRouteVersionRef"], "videoMethodRouteDigest":route["payloadDigest"],
            "jobs":jobs, "publicationAllowed":False})
