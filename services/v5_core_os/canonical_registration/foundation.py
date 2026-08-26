"""V5 orchestration for atomic, durable canonical root registration."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol

from services.v5_core_os.lifecycle_integrity.contracts import BackendKind
from services.v5_core_os.project_engine.foundation import (
    InMemoryProjectAdapter,
    ProjectContextService,
)
from services.v5_core_os.script_studio.foundation import (
    InMemoryScriptStudioAdapter,
    ScriptAcceptanceAuthorityPort,
    ScriptAcceptanceSubject,
    ScriptStudioService,
)
from services.v5_core_os.series_episode.foundation import (
    InMemorySeriesEpisodeAdapter,
    SeriesEpisodeService,
)

from .sqlite_schema import TABLE


CANONICAL_REGISTRATION_SCHEMA_VERSION = "v5.canonical-registration.v1"
CANONICAL_REGISTRATION_RESULT_SCHEMA_VERSION = (
    "v5.canonical-registration-result.v1"
)
CANONICAL_REGISTRATION_RECEIPT_SCHEMA_VERSION = (
    "v5.canonical-registration-receipt.v1"
)
CANONICAL_REGISTRATION_PREFLIGHT_SCHEMA_VERSION = (
    "v5.canonical-registration-preflight.v1"
)


class CanonicalRegistrationError(ValueError):
    code = "invalid_request"


class CanonicalRegistrationConflictError(CanonicalRegistrationError):
    code = "idempotency_conflict"


class CanonicalRegistrationUnavailableError(CanonicalRegistrationError):
    code = "canonical_registration_unavailable"


class CanonicalRegistrationRepositoryError(CanonicalRegistrationError):
    code = "application_error"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalRegistrationError(
            "canonical registration input must be JSON-compatible"
        ) from exc


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _required_text(value: Any, field: str, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit:
        raise CanonicalRegistrationError(f"{field} is invalid")
    return text


def _required_ref(value: Any, field: str) -> str:
    text = _required_text(value, field, limit=200)
    if not text.isprintable() or any(character.isspace() for character in text):
        raise CanonicalRegistrationError(f"{field} is invalid")
    return text


def _required_sha256(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise CanonicalRegistrationError(f"{field} is invalid")
    return text


def _strict_object(
    value: Any,
    *,
    field: str,
    fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CanonicalRegistrationError(f"{field} fields are invalid")
    return json.loads(_canonical_json(dict(value)))


def normalize_registration_command(value: Mapping[str, Any]) -> dict[str, Any]:
    top_fields = {
        "workspaceRef",
        "importedByRef",
        "registrationKey",
        "idempotencyKey",
        "packageDigest",
        "contentProfileRef",
        "series",
        "project",
        "creativePlan",
        "episode",
        "reviewedScript",
        "acceptance",
    }
    command = _strict_object(
        value,
        field="canonical registration",
        fields=top_fields,
    )
    command["workspaceRef"] = _required_ref(
        command["workspaceRef"], "workspaceRef"
    )
    command["importedByRef"] = _required_ref(
        command["importedByRef"], "importedByRef"
    )
    command["registrationKey"] = _required_ref(
        command["registrationKey"], "registrationKey"
    )
    command["idempotencyKey"] = _required_ref(
        command["idempotencyKey"], "idempotencyKey"
    )
    command["packageDigest"] = _required_sha256(
        command["packageDigest"], "packageDigest"
    )
    command["contentProfileRef"] = _required_ref(
        command["contentProfileRef"], "contentProfileRef"
    )
    command["series"] = _strict_object(
        command["series"],
        field="series",
        fields={"title", "description", "plannedEpisodeCount"},
    )
    command["project"] = _strict_object(
        command["project"],
        field="project",
        fields={
            "title",
            "description",
            "targetPlatform",
            "aspectRatio",
            "defaultDurationSec",
            "plannedEpisodeCount",
        },
    )
    command["creativePlan"] = _strict_object(
        command["creativePlan"],
        field="creativePlan",
        fields={
            "sourcePlanRef",
            "sourcePlanSchemaVersion",
            "sourcePlanVersion",
            "brief",
            "sourcePlan",
        },
    )
    command["episode"] = _strict_object(
        command["episode"],
        field="episode",
        fields={
            "episodeNumber",
            "seasonNumber",
            "volumeNumber",
            "title",
        },
    )
    command["reviewedScript"] = _strict_object(
        command["reviewedScript"],
        field="reviewedScript",
        fields={
            "uploadedSourceByteDigest",
            "normalizedSourceDocumentDigest",
            "reviewedDocumentDigest",
            "content",
        },
    )
    for field in (
        "uploadedSourceByteDigest",
        "normalizedSourceDocumentDigest",
        "reviewedDocumentDigest",
    ):
        command["reviewedScript"][field] = _required_sha256(
            command["reviewedScript"][field], field
        )
    command["acceptance"] = _strict_object(
        command["acceptance"],
        field="acceptance",
        fields={"idempotencyKey", "approvalRef"},
    )
    command["acceptance"]["idempotencyKey"] = _required_ref(
        command["acceptance"]["idempotencyKey"],
        "acceptance.idempotencyKey",
    )
    command["acceptance"]["approvalRef"] = _required_ref(
        command["acceptance"]["approvalRef"], "acceptance.approvalRef"
    )
    return command


def registration_request_digest(
    command: Mapping[str, Any],
    canonical_target_ref: str,
    canonical_target_digest: str,
) -> str:
    return _digest(
        {
            "canonicalTargetRef": _required_ref(
                canonical_target_ref, "canonicalTargetRef"
            ),
            "canonicalTargetDigest": _required_sha256(
                canonical_target_digest, "canonicalTargetDigest"
            ),
            "command": normalize_registration_command(command),
        }
    )


def canonical_target_digest(
    *,
    backend_kind: BackendKind,
    canonical_target_ref: str,
    storage_identity: str,
) -> str:
    if not isinstance(backend_kind, BackendKind):
        raise CanonicalRegistrationError("backendKind is invalid")
    return _digest(
        {
            "backendKind": backend_kind.value,
            "canonicalTargetRef": _required_ref(
                canonical_target_ref, "canonicalTargetRef"
            ),
            "storageIdentity": _required_text(
                storage_identity, "storageIdentity", limit=4096
            ),
        }
    )


class DeterministicRegistrationRefFactory:
    """Server-owned stable refs for preflight/apply equivalence and replay."""

    def __init__(
        self,
        *,
        canonical_target_ref: str,
        workspace_ref: str,
        registration_key: str,
        request_digest: str,
    ) -> None:
        self._seed = _canonical_json(
            {
                "canonicalTargetRef": canonical_target_ref,
                "workspaceRef": workspace_ref,
                "registrationKey": registration_key,
                "requestDigest": _required_sha256(
                    request_digest, "requestDigest"
                ),
            }
        )
        self._counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        prefix = _required_ref(prefix, "refPrefix")
        count = self._counts.get(prefix, 0) + 1
        self._counts[prefix] = count
        suffix = sha256(
            f"{self._seed}:{prefix}:{count}".encode("utf-8")
        ).hexdigest()[:32]
        return f"{prefix}-{suffix}"


@dataclass(frozen=True)
class CanonicalRegistrationRecord:
    schemaVersion: str
    workspaceRef: str
    registrationRef: str
    canonicalTargetRef: str
    canonicalTargetDigest: str
    registrationKey: str
    idempotencyKey: str
    packageDigest: str
    requestJson: str
    requestDigest: str
    projectRef: str
    seriesRef: str
    episodeRef: str
    creativePlanRef: str
    scriptRef: str
    scriptVersionRef: str
    acceptanceRef: str
    resultJson: str
    resultDigest: str
    receiptDigest: str
    registeredAt: str
    publicationAllowed: bool


class CanonicalRegistrationRepository(Protocol):
    def get_by_registration_key(
        self, workspace_ref: str, registration_key: str
    ) -> CanonicalRegistrationRecord | None: ...

    def get_by_idempotency_key(
        self, workspace_ref: str, idempotency_key: str
    ) -> CanonicalRegistrationRecord | None: ...

    def list_target_bindings(self) -> set[tuple[str, str]]: ...

    def create(
        self, record: CanonicalRegistrationRecord
    ) -> CanonicalRegistrationRecord: ...


class InMemoryCanonicalRegistrationRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], CanonicalRegistrationRecord] = {}
        self._registration_keys: dict[tuple[str, str], tuple[str, str]] = {}
        self._idempotency_keys: dict[tuple[str, str], tuple[str, str]] = {}
        self._lock = RLock()

    def get_by_registration_key(self, workspace_ref, registration_key):
        key = self._registration_keys.get((workspace_ref, registration_key))
        return self._records.get(key) if key is not None else None

    def get_by_idempotency_key(self, workspace_ref, idempotency_key):
        key = self._idempotency_keys.get((workspace_ref, idempotency_key))
        return self._records.get(key) if key is not None else None

    def list_target_bindings(self) -> set[tuple[str, str]]:
        return {
            (record.canonicalTargetRef, record.canonicalTargetDigest)
            for record in self._records.values()
        }

    def create(self, record):
        record_key = (record.workspaceRef, record.registrationRef)
        registration_key = (record.workspaceRef, record.registrationKey)
        idempotency_key = (record.workspaceRef, record.idempotencyKey)
        with self._lock:
            if (
                record_key in self._records
                or registration_key in self._registration_keys
                or idempotency_key in self._idempotency_keys
            ):
                raise CanonicalRegistrationConflictError(
                    "canonical registration identity already exists"
                )
            self._records[record_key] = record
            self._registration_keys[registration_key] = record_key
            self._idempotency_keys[idempotency_key] = record_key
        return record


class SqliteCanonicalRegistrationRepository:
    def __init__(self, database_path: Path | str, *, lifecycle_state) -> None:
        self.database_path = Path(database_path).resolve()
        self._lifecycle_state = lifecycle_state
        self._lock = RLock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise CanonicalRegistrationRepositoryError(
                "SQLite foreign key enforcement is unavailable"
            )
        return connection

    @contextmanager
    def _session(self):
        shared = self._lifecycle_state.connection_or_none()
        if shared is not None:
            yield shared
            return
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_session(self):
        shared = self._lifecycle_state.connection_or_none()
        if shared is None:
            raise CanonicalRegistrationRepositoryError(
                "valid lifecycle lease is required"
            )
        yield shared

    @staticmethod
    def _record(row: sqlite3.Row) -> CanonicalRegistrationRecord:
        return CanonicalRegistrationRecord(
            row["schema_version"],
            row["workspace_ref"],
            row["registration_ref"],
            row["canonical_target_ref"],
            row["canonical_target_digest"],
            row["registration_key"],
            row["idempotency_key"],
            row["package_digest"],
            row["request_json"],
            row["request_digest"],
            row["project_ref"],
            row["series_ref"],
            row["episode_ref"],
            row["creative_plan_ref"],
            row["script_ref"],
            row["script_version_ref"],
            row["acceptance_ref"],
            row["result_json"],
            row["result_digest"],
            row["receipt_digest"],
            row["registered_at"],
            bool(row["publication_allowed"]),
        )

    def get_by_registration_key(self, workspace_ref, registration_key):
        try:
            with self._session() as connection:
                row = connection.execute(
                    f"SELECT * FROM {TABLE} WHERE workspace_ref=? "
                    "AND registration_key=?",
                    (workspace_ref, registration_key),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise CanonicalRegistrationRepositoryError(
                "canonical registration read failed"
            ) from exc
        return self._record(row) if row is not None else None

    def get_by_idempotency_key(self, workspace_ref, idempotency_key):
        try:
            with self._session() as connection:
                row = connection.execute(
                    f"SELECT * FROM {TABLE} WHERE workspace_ref=? "
                    "AND idempotency_key=?",
                    (workspace_ref, idempotency_key),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise CanonicalRegistrationRepositoryError(
                "canonical registration read failed"
            ) from exc
        return self._record(row) if row is not None else None

    def list_target_bindings(self) -> set[tuple[str, str]]:
        try:
            with self._session() as connection:
                rows = connection.execute(
                    f"SELECT DISTINCT canonical_target_ref,"
                    f"canonical_target_digest FROM {TABLE}"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise CanonicalRegistrationRepositoryError(
                "canonical registration target read failed"
            ) from exc
        return {(str(row[0]), str(row[1])) for row in rows}

    def create(self, record):
        try:
            with self._lock, self._write_session() as connection:
                connection.execute(
                    f"INSERT INTO {TABLE} VALUES ("
                    + ",".join("?" for _ in range(22))
                    + ")",
                    (
                        record.workspaceRef,
                        record.registrationRef,
                        record.schemaVersion,
                        record.canonicalTargetRef,
                        record.canonicalTargetDigest,
                        record.registrationKey,
                        record.idempotencyKey,
                        record.packageDigest,
                        record.requestJson,
                        record.requestDigest,
                        record.projectRef,
                        record.seriesRef,
                        record.episodeRef,
                        record.creativePlanRef,
                        record.scriptRef,
                        record.scriptVersionRef,
                        record.acceptanceRef,
                        record.resultJson,
                        record.resultDigest,
                        record.receiptDigest,
                        record.registeredAt,
                        int(record.publicationAllowed),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise CanonicalRegistrationConflictError(
                "canonical registration identity already exists"
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise CanonicalRegistrationRepositoryError(
                "canonical registration write failed"
            ) from exc
        return record


def _receipt_mapping(record: CanonicalRegistrationRecord) -> dict[str, Any]:
    content = {
        "schemaVersion": CANONICAL_REGISTRATION_RECEIPT_SCHEMA_VERSION,
        "workspaceRef": record.workspaceRef,
        "canonicalTargetRef": record.canonicalTargetRef,
        "canonicalTargetDigest": record.canonicalTargetDigest,
        "registrationRef": record.registrationRef,
        "registrationKey": record.registrationKey,
        "idempotencyKey": record.idempotencyKey,
        "packageDigest": record.packageDigest,
        "requestDigest": record.requestDigest,
        "resultDigest": record.resultDigest,
        "registeredAt": record.registeredAt,
        "publicationAllowed": False,
    }
    if _digest(content) != record.receiptDigest:
        raise CanonicalRegistrationRepositoryError(
            "persisted canonical registration receipt is invalid"
        )
    return {**content, "receiptDigest": record.receiptDigest}


_RESULT_FIELDS = {
    "schemaVersion",
    "workspaceRef",
    "contentProfileRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "creativePlanRef",
    "sourcePlanRef",
    "sourcePlanSchemaVersion",
    "sourcePlanVersion",
    "scriptRef",
    "scriptVersionRef",
    "scriptAcceptanceRef",
    "scriptAcceptancePayloadDigest",
    "canonicalScriptContentDigest",
    "reviewedDocumentDigest",
    "publicationAllowed",
}


def registration_record_mapping(
    record: CanonicalRegistrationRecord,
) -> dict[str, Any]:
    try:
        package_digest = _required_sha256(
            record.packageDigest, "packageDigest"
        )
    except CanonicalRegistrationError as exc:
        raise CanonicalRegistrationRepositoryError(
            "persisted canonical registration is invalid"
        ) from exc
    if (
        record.schemaVersion != CANONICAL_REGISTRATION_SCHEMA_VERSION
        or record.publicationAllowed is not False
        or record.packageDigest != package_digest
    ):
        raise CanonicalRegistrationRepositoryError(
            "persisted canonical registration is invalid"
        )
    try:
        request = json.loads(record.requestJson)
        result = json.loads(record.resultJson)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CanonicalRegistrationRepositoryError(
            "persisted canonical registration JSON is invalid"
        ) from exc
    try:
        normalized = normalize_registration_command(request)
    except CanonicalRegistrationError as exc:
        raise CanonicalRegistrationRepositoryError(
            "persisted canonical registration request is invalid"
        ) from exc
    try:
        if not isinstance(result, Mapping):
            raise CanonicalRegistrationError(
                "persisted canonical registration result is invalid"
            )
        expected_request_json = _canonical_json(normalized)
        expected_request_digest = registration_request_digest(
            normalized,
            record.canonicalTargetRef,
            record.canonicalTargetDigest,
        )
        refs = DeterministicRegistrationRefFactory(
            canonical_target_ref=record.canonicalTargetRef,
            workspace_ref=record.workspaceRef,
            registration_key=record.registrationKey,
            request_digest=expected_request_digest,
        )
        expected_refs = {
            "projectRef": refs("project"),
            "seriesRef": refs("series"),
            "episodeRef": refs("episode"),
            "creativePlanRef": refs("creative-plan"),
            "scriptRef": refs("script"),
            "scriptVersionRef": refs("script-version"),
            "acceptanceRef": refs("script-acceptance"),
            "registrationRef": refs("canonical-registration"),
        }
        expected_result_json = _canonical_json(result)
        expected_result_digest = _digest(result)
        _required_text(record.registeredAt, "registeredAt", limit=100)
        for field in (
            "scriptAcceptancePayloadDigest",
            "canonicalScriptContentDigest",
            "reviewedDocumentDigest",
        ):
            _required_sha256(result.get(field), field)
    except (CanonicalRegistrationError, TypeError, ValueError) as exc:
        raise CanonicalRegistrationRepositoryError(
            "persisted canonical registration content is invalid"
        ) from exc
    if (
        record.requestJson != expected_request_json
        or record.requestDigest != expected_request_digest
        or not isinstance(result, Mapping)
        or set(result) != _RESULT_FIELDS
        or record.resultJson != expected_result_json
        or record.resultDigest != expected_result_digest
        or result.get("schemaVersion")
        != CANONICAL_REGISTRATION_RESULT_SCHEMA_VERSION
        or result.get("workspaceRef") != record.workspaceRef
        or result.get("projectRef") != record.projectRef
        or result.get("seriesRef") != record.seriesRef
        or result.get("episodeRef") != record.episodeRef
        or result.get("creativePlanRef") != record.creativePlanRef
        or result.get("scriptRef") != record.scriptRef
        or result.get("scriptVersionRef") != record.scriptVersionRef
        or result.get("scriptAcceptanceRef") != record.acceptanceRef
        or result.get("publicationAllowed") is not False
        or result.get("contentProfileRef")
        != normalized["contentProfileRef"]
        or result.get("sourcePlanRef")
        != normalized["creativePlan"]["sourcePlanRef"]
        or result.get("sourcePlanSchemaVersion")
        != normalized["creativePlan"]["sourcePlanSchemaVersion"]
        or isinstance(result.get("sourcePlanVersion"), bool)
        or not isinstance(result.get("sourcePlanVersion"), int)
        or result.get("sourcePlanVersion")
        != int(normalized["creativePlan"]["sourcePlanVersion"])
        or result.get("reviewedDocumentDigest")
        != normalized["reviewedScript"]["reviewedDocumentDigest"]
        or normalized["workspaceRef"] != record.workspaceRef
        or normalized["registrationKey"] != record.registrationKey
        or normalized["idempotencyKey"] != record.idempotencyKey
        or normalized["packageDigest"] != record.packageDigest
        or record.projectRef != expected_refs["projectRef"]
        or record.seriesRef != expected_refs["seriesRef"]
        or record.episodeRef != expected_refs["episodeRef"]
        or record.creativePlanRef != expected_refs["creativePlanRef"]
        or record.scriptRef != expected_refs["scriptRef"]
        or record.scriptVersionRef != expected_refs["scriptVersionRef"]
        or record.acceptanceRef != expected_refs["acceptanceRef"]
        or record.registrationRef != expected_refs["registrationRef"]
    ):
        raise CanonicalRegistrationRepositoryError(
            "persisted canonical registration content is invalid"
        )
    return {
        "registration": dict(result),
        "registrationReceipt": _receipt_mapping(record),
    }


class CanonicalRegistrationService:
    def __init__(
        self,
        repository: CanonicalRegistrationRepository,
        *,
        series_repository,
        project_repository,
        script_repository,
        acceptance_authority: ScriptAcceptanceAuthorityPort,
        backend_kind: BackendKind,
        storage_identity: str,
        canonical_target_ref: str | None,
        clock: Callable[[], str] = _utc_now,
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.repository = repository
        self.series_repository = series_repository
        self.project_repository = project_repository
        self.script_repository = script_repository
        self.acceptance_authority = acceptance_authority
        self.backend_kind = backend_kind
        self.storage_identity = _required_text(
            storage_identity, "storageIdentity", limit=4096
        )
        self.canonical_target_ref = (
            _required_ref(canonical_target_ref, "canonicalTargetRef")
            if canonical_target_ref
            else None
        )
        self.canonical_target_digest = (
            canonical_target_digest(
                backend_kind=self.backend_kind,
                canonical_target_ref=self.canonical_target_ref,
                storage_identity=self.storage_identity,
            )
            if self.canonical_target_ref is not None
            else None
        )
        self._clock = clock
        self._fault_hook = fault_hook or (lambda _point: None)

    def _target(self) -> str:
        if self.canonical_target_ref is None:
            raise CanonicalRegistrationUnavailableError(
                "an explicit canonical target is required"
            )
        return self.canonical_target_ref

    def _services(
        self,
        command: Mapping[str, Any],
        *,
        series_repository,
        project_repository,
        script_repository,
        acceptance_authority=None,
    ):
        request_digest = registration_request_digest(
            command,
            self._target(),
            self._target_digest(),
        )
        refs = DeterministicRegistrationRefFactory(
            canonical_target_ref=self._target(),
            workspace_ref=command["workspaceRef"],
            registration_key=command["registrationKey"],
            request_digest=request_digest,
        )
        series = SeriesEpisodeService(
            series_repository, ref_factory=refs, clock=self._clock
        )
        project = ProjectContextService(
            project_repository,
            get_series=series.get_series,
            get_episode=series.get_episode,
            ref_factory=refs,
            clock=self._clock,
        )
        script = ScriptStudioService(
            script_repository,
            series,
            acceptance_authority=(
                acceptance_authority or self.acceptance_authority
            ),
            ref_factory=refs,
            clock=self._clock,
        )
        return refs, series, project, script

    def _target_digest(self) -> str:
        if self.canonical_target_digest is None:
            raise CanonicalRegistrationUnavailableError(
                "an explicit canonical target is required"
            )
        return self.canonical_target_digest

    @staticmethod
    def _create_roots_and_import(
        command,
        *,
        series,
        project,
        script,
        fault_hook,
    ):
        workspace = command["workspaceRef"]
        profile = command["contentProfileRef"]
        created_series = series.create_series(
            {
                "workspaceRef": workspace,
                "contentProfileRef": profile,
                **command["series"],
            }
        )
        fault_hook("after-series")
        created_project = project.create_project(
            {
                "workspaceRef": workspace,
                "contentProfileRef": profile,
                "projectType": "series",
                "seriesRef": created_series["seriesRef"],
                **command["project"],
            }
        )
        fault_hook("after-project")
        confirmed_plan = series.confirm_creative_plan(
            {
                "workspaceRef": workspace,
                "humanConfirmed": True,
                **command["creativePlan"],
            }
        )
        fault_hook("after-creative-plan")
        created_episode = series.create_episode(
            {
                "workspaceRef": workspace,
                "seriesRef": created_series["seriesRef"],
                "creativePlanRef": confirmed_plan["creativePlanRef"],
                **command["episode"],
            }
        )
        fault_hook("after-episode")
        reviewed = command["reviewedScript"]
        imported = script.create_version(
            {
                "workspaceRef": workspace,
                "seriesRef": created_series["seriesRef"],
                "episodeRef": created_episode["episodeRef"],
                "changeKind": "reviewed-import",
                "uploadedSourceByteDigest": reviewed[
                    "uploadedSourceByteDigest"
                ],
                "normalizedSourceDocumentDigest": reviewed[
                    "normalizedSourceDocumentDigest"
                ],
                "reviewedDocumentDigest": reviewed[
                    "reviewedDocumentDigest"
                ],
                "importedByRef": command["importedByRef"],
                "content": reviewed["content"],
            }
        )
        fault_hook("after-reviewed-import")
        return (
            created_series,
            created_project,
            confirmed_plan,
            created_episode,
            imported,
        )

    @staticmethod
    def _acceptance_subject(imported: Mapping[str, Any]) -> ScriptAcceptanceSubject:
        version = imported["scriptVersion"]
        provenance = version.get("importProvenance")
        if not isinstance(provenance, Mapping):
            raise CanonicalRegistrationRepositoryError(
                "reviewed import provenance is unavailable"
            )
        return ScriptAcceptanceSubject.create(
            workspaceRef=version["workspaceRef"],
            seriesRef=version["seriesRef"],
            episodeRef=version["episodeRef"],
            scriptRef=version["scriptRef"],
            scriptVersionRef=version["scriptVersionRef"],
            uploadedSourceByteDigest=provenance[
                "uploadedSourceByteDigest"
            ],
            normalizedSourceDocumentDigest=provenance[
                "normalizedSourceDocumentDigest"
            ],
            reviewedDocumentDigest=provenance["reviewedDocumentDigest"],
            canonicalScriptContentDigest=provenance[
                "canonicalScriptContentDigest"
            ],
            importProvenanceDigest=provenance["importProvenanceDigest"],
        )

    def preflight(self, value: Mapping[str, Any]) -> dict[str, Any]:
        command = normalize_registration_command(value)
        refs, series, project, script = self._services(
            command,
            series_repository=InMemorySeriesEpisodeAdapter(),
            project_repository=InMemoryProjectAdapter(),
            script_repository=InMemoryScriptStudioAdapter(),
        )
        del refs
        roots = self._create_roots_and_import(
            command,
            series=series,
            project=project,
            script=script,
            fault_hook=lambda _point: None,
        )
        created_series, created_project, plan, episode, imported = roots
        subject = self._acceptance_subject(imported)
        return {
            "schemaVersion": CANONICAL_REGISTRATION_PREFLIGHT_SCHEMA_VERSION,
            "canonicalTargetRef": self._target(),
            "canonicalTargetDigest": self._target_digest(),
            "registrationKey": command["registrationKey"],
            "packageDigest": command["packageDigest"],
            "requestDigest": registration_request_digest(
                command, self._target(), self._target_digest()
            ),
            "projectRef": created_project["projectRef"],
            "seriesRef": created_series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "creativePlanRef": plan["creativePlanRef"],
            "scriptRef": imported["script"]["scriptRef"],
            "scriptVersionRef": imported["scriptVersion"][
                "scriptVersionRef"
            ],
            "scriptAcceptanceSubject": subject.as_mapping(),
            "canonicalMutationCount": 0,
            "publicationAllowed": False,
        }

    def _existing(self, command, request_digest):
        workspace = command["workspaceRef"]
        by_registration = self.repository.get_by_registration_key(
            workspace, command["registrationKey"]
        )
        by_idempotency = self.repository.get_by_idempotency_key(
            workspace, command["idempotencyKey"]
        )
        if by_registration is None and by_idempotency is None:
            return None
        existing = by_registration or by_idempotency
        if (
            by_registration is not None
            and by_idempotency is not None
            and by_registration != by_idempotency
        ):
            raise CanonicalRegistrationConflictError(
                "canonical registration identities disagree"
            )
        if (
            existing.canonicalTargetRef != self._target()
            or existing.canonicalTargetDigest != self._target_digest()
            or existing.registrationKey != command["registrationKey"]
            or existing.idempotencyKey != command["idempotencyKey"]
            or existing.packageDigest != command["packageDigest"]
            or existing.requestDigest != request_digest
        ):
            raise CanonicalRegistrationConflictError(
                "canonical registration idempotency content changed"
            )
        return existing

    def register(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if self.backend_kind is not BackendKind.SQLITE_LOCAL:
            raise CanonicalRegistrationUnavailableError(
                "durable canonical registration requires SQLite lifecycle storage"
            )
        command = normalize_registration_command(value)
        target = self._target()
        request_digest = registration_request_digest(
            command, target, self._target_digest()
        )
        existing = self._existing(command, request_digest)
        if existing is not None:
            return {
                **registration_record_mapping(existing),
                "idempotentReplay": True,
            }
        target_bindings = self.repository.list_target_bindings()
        expected_binding = {(target, self._target_digest())}
        if target_bindings and target_bindings != expected_binding:
            raise CanonicalRegistrationConflictError(
                "canonical registration database target changed"
            )
        refs, series, project, script = self._services(
            command,
            series_repository=self.series_repository,
            project_repository=self.project_repository,
            script_repository=self.script_repository,
        )
        created_series, created_project, plan, episode, imported = (
            self._create_roots_and_import(
                command,
                series=series,
                project=project,
                script=script,
                fault_hook=self._fault_hook,
            )
        )
        accepted = script.accept_reviewed_import(
            {
                "workspaceRef": command["workspaceRef"],
                "seriesRef": created_series["seriesRef"],
                "episodeRef": episode["episodeRef"],
                "scriptRef": imported["script"]["scriptRef"],
                "scriptVersionRef": imported["scriptVersion"][
                    "scriptVersionRef"
                ],
                **command["acceptance"],
            }
        )
        self._fault_hook("after-script-acceptance")
        acceptance = accepted["scriptAcceptance"]
        provenance = imported["scriptVersion"]["importProvenance"]
        result = {
            "schemaVersion": CANONICAL_REGISTRATION_RESULT_SCHEMA_VERSION,
            "workspaceRef": command["workspaceRef"],
            "contentProfileRef": command["contentProfileRef"],
            "projectRef": created_project["projectRef"],
            "seriesRef": created_series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "creativePlanRef": plan["creativePlanRef"],
            "sourcePlanRef": plan["sourcePlanRef"],
            "sourcePlanSchemaVersion": plan["sourcePlanSchemaVersion"],
            "sourcePlanVersion": plan["sourcePlanVersion"],
            "scriptRef": imported["script"]["scriptRef"],
            "scriptVersionRef": imported["scriptVersion"][
                "scriptVersionRef"
            ],
            "scriptAcceptanceRef": acceptance["acceptanceRef"],
            "scriptAcceptancePayloadDigest": acceptance["payloadDigest"],
            "canonicalScriptContentDigest": provenance[
                "canonicalScriptContentDigest"
            ],
            "reviewedDocumentDigest": provenance["reviewedDocumentDigest"],
            "publicationAllowed": False,
        }
        result_json = _canonical_json(result)
        result_digest = _digest(result)
        registered_at = self._clock()
        registration_ref = refs("canonical-registration")
        receipt_content = {
            "schemaVersion": CANONICAL_REGISTRATION_RECEIPT_SCHEMA_VERSION,
            "workspaceRef": command["workspaceRef"],
            "canonicalTargetRef": target,
            "canonicalTargetDigest": self._target_digest(),
            "registrationRef": registration_ref,
            "registrationKey": command["registrationKey"],
            "idempotencyKey": command["idempotencyKey"],
            "packageDigest": command["packageDigest"],
            "requestDigest": request_digest,
            "resultDigest": result_digest,
            "registeredAt": registered_at,
            "publicationAllowed": False,
        }
        record = CanonicalRegistrationRecord(
            CANONICAL_REGISTRATION_SCHEMA_VERSION,
            command["workspaceRef"],
            registration_ref,
            target,
            self._target_digest(),
            command["registrationKey"],
            command["idempotencyKey"],
            command["packageDigest"],
            _canonical_json(command),
            request_digest,
            created_project["projectRef"],
            created_series["seriesRef"],
            episode["episodeRef"],
            plan["creativePlanRef"],
            imported["script"]["scriptRef"],
            imported["scriptVersion"]["scriptVersionRef"],
            acceptance["acceptanceRef"],
            result_json,
            result_digest,
            _digest(receipt_content),
            registered_at,
            False,
        )
        registration_record_mapping(record)
        self._fault_hook("before-registration-receipt")
        stored = self.repository.create(record)
        return {
            **registration_record_mapping(stored),
            "idempotentReplay": False,
        }


__all__ = [
    "CANONICAL_REGISTRATION_PREFLIGHT_SCHEMA_VERSION",
    "CANONICAL_REGISTRATION_RECEIPT_SCHEMA_VERSION",
    "CANONICAL_REGISTRATION_RESULT_SCHEMA_VERSION",
    "CANONICAL_REGISTRATION_SCHEMA_VERSION",
    "CanonicalRegistrationConflictError",
    "CanonicalRegistrationError",
    "CanonicalRegistrationRecord",
    "CanonicalRegistrationRepositoryError",
    "CanonicalRegistrationService",
    "CanonicalRegistrationUnavailableError",
    "DeterministicRegistrationRefFactory",
    "InMemoryCanonicalRegistrationRepository",
    "SqliteCanonicalRegistrationRepository",
    "canonical_target_digest",
    "normalize_registration_command",
    "registration_record_mapping",
    "registration_request_digest",
]
