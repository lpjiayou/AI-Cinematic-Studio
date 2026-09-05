"""Application orchestration for non-authoritative Series Plan receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from apps.creator_workspace_mvp.series_director import (
    validate_series_plan_candidate,
)
from services.v5_core_os.series_planning.candidate_receipt_sqlite import (
    CANDIDATE_RECEIPT_SCHEMA_VERSION,
    SOURCE_CONTEXT_SCHEMA_VERSION,
    MARKER_TABLE as SQLITE_MARKER_TABLE,
    TABLE as SQLITE_RECEIPT_TABLE,
    CandidateReceiptSqliteError,
    SeriesPlanCandidateReceipt,
    SqliteSeriesPlanCandidateReceiptStore,
    canonical_json,
    canonical_json_digest,
    validate_candidate_receipt_record,
)


SERIES_DIRECTOR_CONTEXT_SCHEMA_VERSION = "creator.series-director.context.v1"

_SHARED_CONTEXT_FIELDS = frozenset(
    {
        "workspaceRef",
        "contentProfileRef",
        "projectRef",
        "projectTitle",
        "projectDescription",
        "targetPlatform",
        "aspectRatio",
        "plannedEpisodeCount",
        "seriesRef",
        "seriesTitle",
        "seriesDescription",
        "createdEpisodeCount",
    }
)
_GENERATION_CONTEXT_FIELDS = _SHARED_CONTEXT_FIELDS | {"schemaVersion"}
_SOURCE_CONTEXT_FIELDS = _SHARED_CONTEXT_FIELDS | {
    "schemaVersion",
    "projectVersion",
    "seriesVersion",
    "projectStatus",
    "seriesStatus",
}


class SeriesPlanCandidateReceiptError(RuntimeError):
    """Stable application error for candidate provenance failures."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _error(code: str, status: int = 409) -> SeriesPlanCandidateReceiptError:
    return SeriesPlanCandidateReceiptError(code, status)


def _unavailable() -> SeriesPlanCandidateReceiptError:
    return _error("series_plan_candidate_receipt_unavailable", 503)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _required_ref(value: Any) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 200
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        raise _unavailable()
    return value


def _trusted_text(value: Any, *, limit: int = 6000) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise _unavailable()
    return value


def _positive_int(value: Any, *, maximum: int = 100_000) -> int:
    if type(value) is not int or value < 1 or value > maximum:
        raise _unavailable()
    return value


def build_series_plan_candidate_context(
    trusted_context: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build the sole generation/source context from trusted Project facts."""

    if not isinstance(trusted_context, Mapping):
        raise _unavailable()
    project = trusted_context.get("project")
    series = trusted_context.get("series")
    if series is None:
        raise _error("series_scope_required")
    if not isinstance(project, Mapping) or not isinstance(series, Mapping):
        raise _unavailable()

    workspace_ref = _required_ref(trusted_context.get("workspaceRef"))
    content_profile_ref = _required_ref(
        trusted_context.get("contentProfileRef")
    )
    project_ref = _required_ref(trusted_context.get("projectRef"))
    series_ref = _required_ref(trusted_context.get("seriesRef"))
    series_refs = project.get("seriesRefs")
    if (
        project.get("workspaceRef") != workspace_ref
        or project.get("contentProfileRef") != content_profile_ref
        or project.get("projectRef") != project_ref
        or not isinstance(series_refs, list)
        or series_ref not in series_refs
        or series.get("workspaceRef") != workspace_ref
        or series.get("contentProfileRef") != content_profile_ref
        or series.get("seriesRef") != series_ref
    ):
        raise _error("series_plan_candidate_scope_mismatch")

    episodes = series.get("episodes")
    if not isinstance(episodes, list):
        raise _unavailable()
    shared = {
        "workspaceRef": workspace_ref,
        "contentProfileRef": content_profile_ref,
        "projectRef": project_ref,
        "projectTitle": _trusted_text(project.get("title"), limit=500),
        "projectDescription": _trusted_text(
            project.get("description"), limit=2000
        ),
        "targetPlatform": _trusted_text(
            project.get("targetPlatform"), limit=200
        ),
        "aspectRatio": _trusted_text(project.get("aspectRatio"), limit=20),
        "plannedEpisodeCount": _positive_int(
            project.get("plannedEpisodeCount"), maximum=500
        ),
        "seriesRef": series_ref,
        "seriesTitle": _trusted_text(series.get("title"), limit=500),
        "seriesDescription": _trusted_text(
            series.get("description"), limit=2000
        ),
        "createdEpisodeCount": len(episodes),
    }
    return {
        "generationContext": {
            "schemaVersion": SERIES_DIRECTOR_CONTEXT_SCHEMA_VERSION,
            **shared,
        },
        "sourceContext": {
            "schemaVersion": SOURCE_CONTEXT_SCHEMA_VERSION,
            **shared,
            "projectVersion": _positive_int(project.get("version")),
            "seriesVersion": _positive_int(series.get("version")),
            "projectStatus": _trusted_text(project.get("status"), limit=100),
            "seriesStatus": _trusted_text(series.get("status"), limit=100),
        },
    }


class SeriesPlanCandidateReceiptStore(Protocol):
    def issue(
        self, receipt: SeriesPlanCandidateReceipt
    ) -> tuple[SeriesPlanCandidateReceipt, bool]: ...

    def get(
        self, workspace_ref: str, candidate_ref: str
    ) -> SeriesPlanCandidateReceipt | None: ...

    def find_exact(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        source_context_digest: str,
        candidate_digest: str,
    ) -> list[SeriesPlanCandidateReceipt]: ...

    def count(self, workspace_ref: str | None = None) -> int: ...


def _dedupe_key(receipt: SeriesPlanCandidateReceipt) -> tuple[str, ...]:
    return (
        receipt.workspaceRef,
        receipt.projectRef,
        receipt.seriesRef,
        receipt.sourceContextDigest,
        receipt.candidateDigest,
    )


def _validate_receipt_integrity(
    receipt: SeriesPlanCandidateReceipt,
) -> dict[str, Any]:
    try:
        return validate_candidate_receipt_record(receipt)
    except CandidateReceiptSqliteError:
        raise _unavailable() from None


class InMemorySeriesPlanCandidateReceiptStore:
    """Deterministic append-only store for tests and in-memory servers."""

    def __init__(self) -> None:
        self._receipts: dict[
            tuple[str, str], SeriesPlanCandidateReceipt
        ] = {}
        self._dedupe: dict[tuple[str, ...], tuple[str, str]] = {}
        self._lock = RLock()

    def issue(self, receipt):
        _validate_receipt_integrity(receipt)
        key = (receipt.workspaceRef, receipt.candidateRef)
        dedupe = _dedupe_key(receipt)
        with self._lock:
            existing_key = self._dedupe.get(dedupe)
            if existing_key is not None:
                existing = self._receipts.get(existing_key)
                if existing is None:
                    raise _unavailable()
                _validate_receipt_integrity(existing)
                return existing, True
            if key in self._receipts:
                raise _unavailable()
            self._receipts[key] = receipt
            self._dedupe[dedupe] = key
        return receipt, False

    def get(self, workspace_ref, candidate_ref):
        with self._lock:
            receipt = self._receipts.get((workspace_ref, candidate_ref))
        if receipt is not None:
            _validate_receipt_integrity(receipt)
        return receipt

    def find_exact(
        self,
        workspace_ref,
        project_ref,
        series_ref,
        source_context_digest,
        candidate_digest,
    ):
        dedupe = (
            workspace_ref,
            project_ref,
            series_ref,
            source_context_digest,
            candidate_digest,
        )
        with self._lock:
            key = self._dedupe.get(dedupe)
            if key is None:
                return []
            receipt = self._receipts.get(key)
        if receipt is None:
            raise _unavailable()
        _validate_receipt_integrity(receipt)
        return [receipt]

    def count(self, workspace_ref=None):
        with self._lock:
            if workspace_ref is None:
                return len(self._receipts)
            return sum(
                receipt.workspaceRef == workspace_ref
                for receipt in self._receipts.values()
            )


class SeriesPlanCandidateReceiptService:
    """Issue and verify receipts without creating canonical Series Plan facts."""

    def __init__(
        self,
        store: SeriesPlanCandidateReceiptStore,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.store = store
        self._ref_factory = ref_factory or (
            lambda prefix: f"{prefix}-{uuid4().hex}"
        )
        self._clock = clock

    @staticmethod
    def _parts(
        context: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        if not isinstance(context, Mapping):
            raise _unavailable()
        generation = context.get("generationContext")
        source = context.get("sourceContext")
        if not isinstance(generation, Mapping) or not isinstance(source, Mapping):
            raise _unavailable()
        if (
            set(generation) != _GENERATION_CONTEXT_FIELDS
            or set(source) != _SOURCE_CONTEXT_FIELDS
            or generation.get("schemaVersion")
            != SERIES_DIRECTOR_CONTEXT_SCHEMA_VERSION
            or source.get("schemaVersion") != SOURCE_CONTEXT_SCHEMA_VERSION
            or any(
                generation.get(field) != source.get(field)
                for field in _SHARED_CONTEXT_FIELDS
            )
        ):
            raise _unavailable()
        return generation, source

    def issue(
        self,
        context: Mapping[str, Any],
        creative_input: Any,
        candidate: Mapping[str, Any],
    ) -> tuple[SeriesPlanCandidateReceipt, bool]:
        generation, source = self._parts(context)
        validated = validate_series_plan_candidate(candidate, generation)
        candidate_json = canonical_json(validated)
        source_context_json = canonical_json(source)
        creative_text = str(creative_input or "").strip()
        receipt = SeriesPlanCandidateReceipt(
            CANDIDATE_RECEIPT_SCHEMA_VERSION,
            self._ref_factory("series-plan-candidate"),
            _required_ref(source.get("workspaceRef")),
            _required_ref(source.get("contentProfileRef")),
            _required_ref(source.get("projectRef")),
            _required_ref(source.get("seriesRef")),
            _positive_int(source.get("projectVersion")),
            _positive_int(source.get("seriesVersion")),
            canonical_json_digest(source),
            source_context_json,
            sha256(creative_text.encode("utf-8")).hexdigest(),
            sha256(candidate_json.encode("utf-8")).hexdigest(),
            candidate_json,
            self._clock(),
            1,
        )
        _validate_receipt_integrity(receipt)
        try:
            stored, replay = self.store.issue(receipt)
        except SeriesPlanCandidateReceiptError:
            raise
        except Exception:
            raise _unavailable() from None
        stored_candidate = _validate_receipt_integrity(stored)
        if (
            stored.workspaceRef != receipt.workspaceRef
            or stored.contentProfileRef != receipt.contentProfileRef
            or stored.projectRef != receipt.projectRef
            or stored.seriesRef != receipt.seriesRef
            or stored.sourceProjectVersion != receipt.sourceProjectVersion
            or stored.sourceSeriesVersion != receipt.sourceSeriesVersion
            or stored.sourceContextDigest != receipt.sourceContextDigest
            or stored.sourceContextJson != receipt.sourceContextJson
            or stored.candidateDigest != receipt.candidateDigest
            or stored_candidate != validated
        ):
            raise _unavailable()
        return stored, replay

    def resolve(
        self,
        context: Mapping[str, Any],
        candidate: Any,
        *,
        candidate_ref: Any = None,
    ) -> dict[str, Any]:
        generation, source = self._parts(context)
        validated_request = validate_series_plan_candidate(candidate, generation)
        request_digest = canonical_json_digest(validated_request)
        source_digest = canonical_json_digest(source)
        workspace_ref = _required_ref(source.get("workspaceRef"))
        project_ref = _required_ref(source.get("projectRef"))
        series_ref = _required_ref(source.get("seriesRef"))

        try:
            if candidate_ref is not None:
                if not isinstance(candidate_ref, str):
                    raise _error("series_plan_candidate_not_issued")
                try:
                    validated_ref = _required_ref(candidate_ref)
                except SeriesPlanCandidateReceiptError:
                    raise _error("series_plan_candidate_not_issued") from None
                receipt = self.store.get(workspace_ref, validated_ref)
                if receipt is None:
                    raise _error("series_plan_candidate_not_issued")
            else:
                matches = self.store.find_exact(
                    workspace_ref,
                    project_ref,
                    series_ref,
                    source_digest,
                    request_digest,
                )
                if not matches:
                    raise _error("series_plan_candidate_not_issued")
                if len(matches) != 1:
                    raise _error("series_plan_candidate_receipt_ambiguous")
                receipt = matches[0]
        except SeriesPlanCandidateReceiptError:
            raise
        except Exception:
            raise _unavailable() from None

        stored_candidate = _validate_receipt_integrity(receipt)
        if (
            receipt.workspaceRef != workspace_ref
            or receipt.projectRef != project_ref
            or receipt.seriesRef != series_ref
            or receipt.contentProfileRef != source.get("contentProfileRef")
        ):
            raise _error("series_plan_candidate_scope_mismatch")
        if (
            receipt.sourceProjectVersion != source.get("projectVersion")
            or receipt.sourceSeriesVersion != source.get("seriesVersion")
            or receipt.sourceContextDigest != source_digest
        ):
            raise _error("series_plan_candidate_stale")
        if receipt.candidateDigest != request_digest:
            raise _error("series_plan_candidate_content_mismatch")

        validated_stored = validate_series_plan_candidate(
            stored_candidate, generation
        )
        if canonical_json_digest(validated_stored) != receipt.candidateDigest:
            raise _unavailable()
        return validated_stored


def create_in_memory_receipt_service(
    *, ref_factory=None, clock=None
) -> SeriesPlanCandidateReceiptService:
    kwargs = {}
    if ref_factory is not None:
        kwargs["ref_factory"] = ref_factory
    if clock is not None:
        kwargs["clock"] = clock
    return SeriesPlanCandidateReceiptService(
        InMemorySeriesPlanCandidateReceiptStore(), **kwargs
    )


def create_local_development_receipt_service(
    database_path: Path | str,
) -> SeriesPlanCandidateReceiptService:
    try:
        store = SqliteSeriesPlanCandidateReceiptStore(database_path)
    except CandidateReceiptSqliteError:
        raise _unavailable() from None
    return SeriesPlanCandidateReceiptService(store)


def create_local_development_receipt_service_from_environment(
    environ: Mapping[str, str] | None = None,
) -> SeriesPlanCandidateReceiptService:
    values = os.environ if environ is None else environ
    configured_path = str(values.get("CREATOR_DATA_PATH", "")).strip()
    if configured_path:
        database_path = Path(configured_path)
    else:
        local_app_data = str(values.get("LOCALAPPDATA", "")).strip()
        root = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / ".ai-cinematic-studio"
        )
        database_path = (
            root / "AI Cinematic Studio" / "creator-workspace.sqlite3"
        )
    return create_local_development_receipt_service(database_path)
