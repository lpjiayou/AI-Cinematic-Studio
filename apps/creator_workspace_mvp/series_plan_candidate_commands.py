"""Reserve keyed M5 generation before calling the existing Series Director."""

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from threading import RLock

from apps.creator_workspace_mvp.series_director import (
    SeriesDirectorGenerationError, SeriesPlanCandidateError,
    validate_series_plan_candidate,
)
from services.v5_core_os.series_planning.candidate_command_sqlite import (
    COMMAND_SCHEMA, IDENTITY_SCHEMA, FAILURE_CODES,
    SeriesPlanCandidateCommand, SeriesPlanCandidateCommandStorageError,
    SqliteSeriesPlanCandidateCommandStore, candidate_ref, completed_projection,
    request_digest, seal_record, validate_command, validate_transition,
)
from services.v5_core_os.series_planning.candidate_receipt_sqlite import canonical_json, canonical_json_digest
from services.v5_core_os.series_planning.foundation import SeriesPlanningError, validate_series_plan_idempotency_key


class SeriesPlanCandidateCommandError(RuntimeError):
    def __init__(self, code, status):
        super().__init__(code)
        self.code, self.status = code, status


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_idempotency_key(key):
    try:
        return validate_series_plan_idempotency_key(key)
    except SeriesPlanningError:
        raise SeriesPlanCandidateCommandError("invalid_request", 400) from None


def new_pending_command(source, creative_input, key, *, clock=utc_now):
    validate_idempotency_key(key)
    # This is the existing Series Director normalization, performed before any
    # reservation. Neither raw text nor the client key enters the durable row.
    text = str(creative_input or "").strip()
    if not text or len(text) > 4000:
        raise SeriesPlanCandidateCommandError("invalid_request", 400)
    identity = canonical_json_digest({
        "schemaVersion": IDENTITY_SCHEMA, "operation": "SERIES_PLAN_CANDIDATE",
        "workspaceRef": source["workspaceRef"], "idempotencyKey": key,
    })
    source_digest = canonical_json_digest(source)
    creative_digest = sha256(text.encode("utf-8")).hexdigest()
    return seal_record(SeriesPlanCandidateCommand(
        COMMAND_SCHEMA, "series-plan-candidate-command-" + identity,
        source["workspaceRef"], source["projectRef"], source["seriesRef"], identity,
        request_digest(source["projectRef"], source["seriesRef"], source_digest, creative_digest),
        source_digest, canonical_json(source), creative_digest, "PENDING",
        candidate_ref(source["workspaceRef"], identity), None, None, None, clock(), None, 1,
    ))


class InMemorySeriesPlanCandidateCommandStore:
    def __init__(self):
        self._records = {}
        self._lock = RLock()

    def reserve(self, pending):
        validate_command(pending)
        if pending.state != "PENDING":
            raise SeriesPlanCandidateCommandStorageError("reservation must be pending")
        key = (pending.workspaceRef, pending.identityDigest)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                validate_command(existing)
                return existing, False
            self._records[key] = pending
            return pending, True

    def finish(self, pending, terminal):
        validate_transition(pending, terminal)
        key = (pending.workspaceRef, pending.identityDigest)
        with self._lock:
            if self._records.get(key) != pending:
                raise SeriesPlanCandidateCommandStorageError("M5 reservation changed")
            self._records[key] = terminal

    def get_by_candidate(self, workspace_ref, candidate_ref):
        with self._lock:
            matches = [row for row in self._records.values()
                       if row.workspaceRef == workspace_ref and row.candidateRef == candidate_ref]
            if len(matches) > 1:
                raise SeriesPlanCandidateCommandStorageError("ambiguous M5 candidate identity")
            for row in matches:
                validate_command(row)
            return matches[0] if matches else None

    def find_exact(self, workspace_ref, project_ref, series_ref, source_digest, candidate_digest):
        with self._lock:
            matches = [row for row in self._records.values() if (
                row.workspaceRef, row.projectRef, row.seriesRef, row.sourceContextDigest,
                row.candidateDigest, row.state
            ) == (workspace_ref, project_ref, series_ref, source_digest, candidate_digest, "COMPLETED")]
            for row in matches:
                validate_command(row)
            return matches

    def count(self):
        with self._lock:
            return len(self._records)


class SeriesPlanCandidateCommandService:
    def __init__(self, store, *, clock=utc_now):
        self.store, self.clock = store, clock

    @staticmethod
    def _storage(operation, *args):
        try:
            return operation(*args)
        except SeriesPlanCandidateCommandStorageError:
            raise SeriesPlanCandidateCommandError("series_plan_candidate_command_unavailable", 503) from None

    def generate(self, context, creative_input, key, director):
        pending = new_pending_command(context["sourceContext"], creative_input, key, clock=self.clock)
        stored, reserved = self._storage(self.store.reserve, pending)
        if not reserved:
            if stored.requestDigest != pending.requestDigest:
                raise SeriesPlanCandidateCommandError("series_plan_candidate_idempotency_conflict", 409)
            if stored.state == "PENDING":
                raise SeriesPlanCandidateCommandError("series_plan_candidate_generation_pending", 409)
            if stored.state == "FAILED":
                raise SeriesDirectorGenerationError(stored.failureCode)
            return self._storage(completed_projection, stored), True, self._storage(validate_command, stored)
        # reserve() has committed and released its connection before this call.
        failure = None
        try:
            candidate = director.generate(context["generationContext"], creative_input)
            candidate = validate_series_plan_candidate(candidate, context["generationContext"])
            terminal = seal_record(replace(pending, state="COMPLETED",
                candidateJson=canonical_json(candidate), candidateDigest=canonical_json_digest(candidate),
                completedAt=self.clock()))
            validate_command(terminal)
        except SeriesDirectorGenerationError as exc:
            failure = exc.code if exc.code in FAILURE_CODES else "application_error"
        except SeriesPlanCandidateError:
            failure = "invalid_provider_output"
        except Exception:
            failure = "application_error"
        if failure is not None:
            terminal = seal_record(replace(pending, state="FAILED", failureCode=failure, completedAt=self.clock()))
        self._storage(self.store.finish, pending, terminal)
        if failure is not None:
            # The first response and every replay expose only the stable code.
            raise SeriesDirectorGenerationError(failure)
        return self._storage(completed_projection, terminal), False, candidate

    def get(self, workspace_ref, candidate_ref):
        row = self._storage(self.store.get_by_candidate, workspace_ref, candidate_ref)
        return self._storage(completed_projection, row) if row is not None and row.state == "COMPLETED" else None

    def find_exact(self, *args):
        return [self._storage(completed_projection, row) for row in self._storage(self.store.find_exact, *args)]


def create_command_service(database_path=None):
    try:
        store = (SqliteSeriesPlanCandidateCommandStore(database_path) if database_path is not None
                 else InMemorySeriesPlanCandidateCommandStore())
    except SeriesPlanCandidateCommandStorageError:
        raise SeriesPlanCandidateCommandError("series_plan_candidate_command_unavailable", 503) from None
    return SeriesPlanCandidateCommandService(store)
