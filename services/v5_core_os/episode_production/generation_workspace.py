"""Bounded public projection/trigger for a host-selected original D1 Operator.

No Grant issuance, replacement, queue, persistent state or default deployment.
The transient task flag is only HTTP supervision; Job/Attempt is the durable truth.
The trusted host keeps this boundary in the original single control process.
"""
from threading import RLock, Thread

from . import generation_dispatch_contracts as c
from .generation_dispatch_operator import GenerationDispatchOperator
from .public import EpisodeProductionPublicError


class GenerationWorkspaceError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class GenerationWorkspaceBoundary:
    def __init__(self, *, operator, media_job_ref, run_reader,
                 allowed_credential_refs=frozenset()):
        if not isinstance(operator, GenerationDispatchOperator):
            raise TypeError("The original GenerationDispatchOperator is required")
        self._operator, self._job_ref, self._runs = operator, c.ref(media_job_ref), run_reader
        self._writers = frozenset(c.ref(value) for value in allowed_credential_refs)
        self._lock = RLock()
        self._thread = None
        self._activity = "IDLE"
        self._error = None

    def _read(self, scope):
        if set(scope) != c.SCOPE_FIELDS:
            raise GenerationWorkspaceError("invalid_request", 400)
        if any(not isinstance(v, str) or not v or v.strip() != v for v in scope.values()):
            raise GenerationWorkspaceError("invalid_request", 400)
        try:
            run = self._runs.get_run(scope["workspaceRef"], scope["productionRunRef"])
        except EpisodeProductionPublicError as exc:
            if exc.code in {"not_found", "scope_mismatch"}:
                raise GenerationWorkspaceError("generation_target_not_found", 404) from exc
            raise GenerationWorkspaceError("generation_target_unavailable", 503) from exc
        if any(run.get(k) != v for k, v in scope.items()):
            raise GenerationWorkspaceError("generation_target_not_found", 404)
        try:
            job = self._operator.read_job(self._job_ref)
        except c.DispatchError as exc:
            raise GenerationWorkspaceError("generation_target_unavailable", 503) from exc
        if any(job["request"].get(k) != v for k, v in scope.items()):
            raise GenerationWorkspaceError("generation_target_not_found", 404)
        return job

    def project(self, scope, credential_ref):
        job = self._read(scope)
        with self._lock:
            activity, error = self._activity, self._error
        dispatch = job.get("dispatchResult") or {}
        state = "UNKNOWN" if dispatch.get("outcome") == "UNKNOWN" else job["state"]
        output = job["executionEnvelope"]["outputConstraints"]
        artifact = job.get("artifact")
        summary = None
        if state == "SUCCEEDED" and artifact and job.get("artifactCommitIntent") is None:
            summary = {"sha256": artifact["sha256"], "byteSize": artifact["byteSize"],
                "mediaType": artifact["mediaType"], **{k: output[k] for k in (
                    "width", "height", "durationFrames", "frameRate")}}
        writable = credential_ref in self._writers
        return {"schemaVersion": "creator.generation-workspace.v1", **scope,
            "mediaJobRef": job["jobRef"], "jobRevision": job["revision"],
            "approvedPlanDigest": job["dispatchGrantBinding"]["approvedPlanDigest"],
            "creativeShotVersionRef": job["request"]["creativeShotVersionRef"],
            "beatRef": job["request"]["beatRef"], "state": state,
            "attemptCount": len(job["attempts"]), "activity": activity,
            "errorCode": error, "artifact": summary,
            "canPrepare": writable and activity == "IDLE" and state == "QUEUED" and not job["attempts"],
            "canExecute": writable and activity == "IDLE" and state == "QUEUED" and not job["attempts"],
            "publicationAllowed": False, "automaticRetryAllowed": False}

    def start(self, scope, credential_ref, command):
        required = {"operation", "mediaJobRef", "expectedJobRevision", "approvedPlanDigest"}
        if (set(command) != required or command["operation"] not in {"PREPARE", "EXECUTE_APPROVED"}
                or type(command["expectedJobRevision"]) is not int):
            raise GenerationWorkspaceError("invalid_request", 400)
        if credential_ref not in self._writers:
            raise GenerationWorkspaceError("generation_operation_not_authorized", 403)
        with self._lock:
            job = self._read(scope)
            if (command["mediaJobRef"] != self._job_ref
                    or command["approvedPlanDigest"] != job["dispatchGrantBinding"]["approvedPlanDigest"]):
                raise GenerationWorkspaceError("generation_binding_changed")
            if self._activity != "IDLE":
                # Duplicate requests never schedule a second worker or command.
                return
            if command["expectedJobRevision"] != job["revision"]:
                raise GenerationWorkspaceError("generation_revision_changed")
            if job["state"] != "QUEUED" or job["attempts"]:
                raise GenerationWorkspaceError("generation_not_restartable")
            self._error = None
            self._activity = "PREPARING" if command["operation"] == "PREPARE" else "EXECUTING"
            self._thread = Thread(target=self._work, args=(command["operation"],),
                name="creator-original-operator", daemon=False)
            try:
                self._thread.start()
            except Exception:
                self._activity = "IDLE"
                self._thread = None
                raise GenerationWorkspaceError("generation_start_failed", 503)

    def _work(self, operation):
        try:
            result = (self._operator.prepare() if operation == "PREPARE"
                else self._operator.execute_one(self._job_ref))
            if operation == "PREPARE" and "planPackage" not in result:
                code = result.get("code")
                raise c.DispatchError(code if code in c.ERROR_CODES else "APPROVAL_UNAVAILABLE")
        except Exception as exc:
            with self._lock:
                self._error = exc.code if isinstance(exc, c.DispatchError) else "generation_operation_failed"
        finally:
            with self._lock:
                self._activity = "IDLE"

    def content(self, scope, media_job_ref, digest):
        job = self._read(scope)
        artifact = job.get("artifact") or {}
        if media_job_ref != job["jobRef"] or digest != artifact.get("sha256"):
            raise GenerationWorkspaceError("generation_result_not_found", 404)
        try:
            return self._operator.read_job_content(self._job_ref)
        except Exception as exc:
            raise GenerationWorkspaceError("generation_result_unavailable") from exc

    def close(self):
        """Host shutdown joins existing work; never abandons a live send thread."""
        thread = self._thread
        if thread is not None:
            thread.join()
