"""Creator-owned, non-authoritative AI Director command and issuance service."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import uuid4

from apps.creator_workspace_mvp.ai_director import (
    CreativeBrief, PlanGenerationError, validate_plan,
)
from services.v5_core_os.series_episode.ai_director_candidate_receipt_sqlite import (
    AiDirectorCandidateCommand, AiDirectorCandidateStorageError,
    CANDIDATE_SCHEMA, COMMAND_SCHEMA, FAILURE_CODES, IDENTITY_SCHEMA,
    RECEIPT_SCHEMA, REQUEST_SCHEMA, SqliteAiDirectorCandidateCommandStore,
    canonical_digest, canonical_json, seal_record, source_ref,
    validate_command, validate_transition,
)


class AiDirectorCandidateReceiptError(RuntimeError):
    def __init__(self, code: str, status: int, *, idempotent_replay=False):
        super().__init__(code)
        self.code = code
        self.status = status
        self.idempotent_replay = idempotent_replay


class CandidateCommandStore(Protocol):
    def reserve(self, pending: AiDirectorCandidateCommand) -> tuple[AiDirectorCandidateCommand, bool]: ...
    def finish(self, pending: AiDirectorCandidateCommand, terminal: AiDirectorCandidateCommand) -> None: ...
    def get_by_source(self, workspace_ref: str, source_plan_ref: str) -> AiDirectorCandidateCommand | None: ...


def validate_idempotency_key(value) -> str:
    if (not isinstance(value, str) or not value or len(value) > 200
            or value != value.strip() or not value.isprintable()
            or "/" in value or "\\" in value or value in {".", ".."}):
        raise AiDirectorCandidateReceiptError("invalid_request", 400)
    return value


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_pending_command(workspace_ref, brief, idempotency_key=None):
    normalized = CreativeBrief.from_mapping(brief).as_prompt_payload()
    if idempotency_key is not None:
        identity = {"schemaVersion": IDENTITY_SCHEMA, "operation": "AI_DIRECTOR_CANDIDATE",
                    "workspaceRef": workspace_ref, "idempotencyKey": validate_idempotency_key(idempotency_key)}
        mode = "KEYED"
    else:
        identity = {"schemaVersion": "creator.ai-director-candidate-unkeyed-identity.v1",
                    "workspaceRef": workspace_ref, "nonce": uuid4().hex}
        mode = "UNKEYED"
    digest = canonical_digest(identity)
    return seal_record(AiDirectorCandidateCommand(
        schemaVersion=COMMAND_SCHEMA, commandRef="ai-director-candidate-command-" + digest,
        workspaceRef=workspace_ref, identityMode=mode, identityDigest=digest,
        requestDigest=canonical_digest({"schemaVersion": REQUEST_SCHEMA, "brief": normalized}),
        briefDigest=canonical_digest(normalized), state="PENDING",
        sourcePlanRef=source_ref(workspace_ref, digest), sourcePlanVersion=1,
        planDigest=None, candidateDigest=None, candidateJson=None, failureCode=None,
        createdAt=_now(), completedAt=None, version=1,
    ))


class AiDirectorCandidateReceiptService:
    def __init__(self, store: CandidateCommandStore):
        self.store = store

    @staticmethod
    def _result(record, replay):
        candidate = validate_command(record)
        if record.state == "PENDING":
            raise AiDirectorCandidateReceiptError("ai_director_candidate_generation_pending", 409)
        if record.state == "FAILED":
            raise AiDirectorCandidateReceiptError(record.failureCode, 200, idempotent_replay=replay)
        result = {"ok": True, "kind": "candidate-creative-plan", "confirmationRequired": True,
                  "sourcePlanRef": record.sourcePlanRef, "sourcePlanVersion": record.sourcePlanVersion,
                  "plan": candidate["plan"]}
        if record.identityMode == "KEYED":
            result.update(candidateDigest=record.candidateDigest,
                          candidateReceiptSchemaVersion=RECEIPT_SCHEMA, idempotentReplay=replay)
        return result

    def generate_candidate(self, workspace_ref, brief, *, idempotency_key=None, generator):
        pending = new_pending_command(workspace_ref, brief, idempotency_key)
        try:
            record, reserved = self.store.reserve(pending)
            if not reserved:
                if record.requestDigest != pending.requestDigest:
                    raise AiDirectorCandidateReceiptError("ai_director_candidate_idempotency_conflict", 409)
                return self._result(record, True)
            # The reservation transaction is already committed and closed.
            # BaseException deliberately propagates: a process crash leaves PENDING.
            try:
                plan = validate_plan(generator(brief), CreativeBrief.from_mapping(brief))
                candidate = {"schemaVersion": CANDIDATE_SCHEMA, "sourcePlanRef": record.sourcePlanRef,
                             "sourcePlanVersion": 1, "briefDigest": record.briefDigest,
                             "planDigest": canonical_digest(plan), "plan": plan}
                terminal = seal_record(replace(record, state="COMPLETED", completedAt=_now(),
                                              planDigest=candidate["planDigest"], candidateDigest=canonical_digest(candidate),
                                              candidateJson=canonical_json(candidate)))
                validate_command(terminal)
            except Exception as exc:
                code = exc.code if isinstance(exc, PlanGenerationError) and exc.code in FAILURE_CODES else "application_error"
                terminal = seal_record(replace(record, state="FAILED", failureCode=code, completedAt=_now()))
            self.store.finish(record, terminal)
            return self._result(terminal, False)
        except AiDirectorCandidateStorageError as exc:
            raise AiDirectorCandidateReceiptError("ai_director_candidate_receipt_unavailable", 503) from exc

    def resolve_for_confirmation(self, workspace_ref, source_plan_ref, source_plan_version, brief, plan):
        try:
            if not isinstance(source_plan_ref, str):
                raise AiDirectorCandidateReceiptError("ai_director_candidate_not_issued", 404)
            record = self.store.get_by_source(workspace_ref, source_plan_ref)
            if record is None or record.state != "COMPLETED":
                raise AiDirectorCandidateReceiptError("ai_director_candidate_not_issued", 404)
            candidate = validate_command(record)
            if type(source_plan_version) is not int or source_plan_version != record.sourcePlanVersion:
                raise AiDirectorCandidateReceiptError("ai_director_candidate_version_mismatch", 409)
            normalized = CreativeBrief.from_mapping(brief)
            if canonical_digest(normalized.as_prompt_payload()) != record.briefDigest:
                raise AiDirectorCandidateReceiptError("ai_director_candidate_content_mismatch", 409)
            validated = validate_plan(plan, normalized)
            if canonical_digest(validated) != record.planDigest:
                raise AiDirectorCandidateReceiptError("ai_director_candidate_content_mismatch", 409)
            # Confirmation consumes the server's canonical copy, never the browser object.
            return candidate["plan"]
        except AiDirectorCandidateStorageError as exc:
            raise AiDirectorCandidateReceiptError("ai_director_candidate_receipt_unavailable", 503) from exc


class InMemoryAiDirectorCandidateCommandStore:
    """Development/test parity adapter, without durable restart claims."""

    def __init__(self):
        self._records = {}
        self._lock = RLock()

    def reserve(self, pending):
        validate_command(pending)
        if pending.state != "PENDING":
            raise AiDirectorCandidateStorageError("reservation must be pending")
        with self._lock:
            key = (pending.workspaceRef, pending.identityDigest)
            if key in self._records:
                return self._records[key], False
            self._records[key] = pending
            return pending, True

    def finish(self, pending, terminal):
        validate_transition(pending, terminal)
        with self._lock:
            key = (pending.workspaceRef, pending.identityDigest)
            if self._records.get(key) != pending:
                raise AiDirectorCandidateStorageError("AI Director candidate reservation changed")
            self._records[key] = terminal

    def get_by_source(self, workspace_ref, source_plan_ref):
        with self._lock:
            return next((record for record in self._records.values()
                         if record.workspaceRef == workspace_ref and record.sourcePlanRef == source_plan_ref), None)

    def count(self):
        with self._lock:
            return len(self._records)

    def close(self):
        pass


def create_candidate_receipt_service(database_path=None):
    store = (SqliteAiDirectorCandidateCommandStore(database_path) if database_path is not None
             else InMemoryAiDirectorCandidateCommandStore())
    return AiDirectorCandidateReceiptService(store)
