"""Application orchestration for one recoverable Project foundation command."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping
from uuid import uuid4

from services.v5_core_os.lifecycle_integrity.errors import LifecycleIntegrityError
from services.v5_core_os.project_engine.project_foundation import (
    PROJECT_FOUNDATION_RECORD_SCHEMA_VERSION,
    PROJECT_FOUNDATION_RESULT_SCHEMA_VERSION,
    ProjectFoundationRecord,
    ProjectFoundationStorageError,
    ProjectFoundationValidationError,
    canonical_json,
    normalize_project_foundation_command,
    validate_project_foundation_record,
)
from services.v5_core_os.project_engine.public import ProjectPublicError
from services.v5_core_os.series_episode.public import SeriesEpisodePublicError


class ProjectFoundationApplicationError(RuntimeError):
    """Stable application error for the public command resource."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class ProjectFoundationApplicationService:
    """Persist intent, then atomically create all requested V5 foundation facts."""

    def __init__(
        self,
        store,
        coordinator,
        series_episode_boundary,
        project_boundary,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.store = store
        self._coordinator = coordinator
        self._series_episode = series_episode_boundary
        self._project = project_boundary
        self._ref_factory = ref_factory or (
            lambda prefix: f"{prefix}-{uuid4().hex}"
        )
        self._clock = clock
        self._fault_hook = fault_hook or (lambda _point: None)

    @staticmethod
    def _unavailable() -> ProjectFoundationApplicationError:
        return ProjectFoundationApplicationError(
            "project_foundation_unavailable", 503
        )

    @staticmethod
    def _pending_projection(
        record: ProjectFoundationRecord,
        request_value: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "schemaVersion": PROJECT_FOUNDATION_RESULT_SCHEMA_VERSION,
            "foundationRef": record.foundationRef,
            "workspaceRef": record.workspaceRef,
            "contentProfileRef": request_value["contentProfileRef"],
            "state": "PENDING",
            "series": None,
            "project": None,
            "episode": None,
            "createdAt": record.createdAt,
            "completedAt": None,
            "version": 1,
        }

    def _validate_authority(
        self,
        record: ProjectFoundationRecord,
        request_value: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            expected_project = result["project"]
            current_project = self._project.get_project(
                record.workspaceRef,
                expected_project["projectRef"],
            )
            project_fields = (
                "workspaceRef",
                "projectRef",
                "contentProfileRef",
                "projectType",
                "title",
                "description",
                "targetPlatform",
                "aspectRatio",
                "defaultDurationSec",
                "plannedEpisodeCount",
                "seriesRefs",
                "createdAt",
            )
            if any(
                current_project.get(field) != expected_project.get(field)
                for field in project_fields
            ):
                raise ProjectFoundationValidationError(
                    "project authority no longer matches receipt"
                )

            expected_series = result.get("series")
            if expected_series is not None:
                current_series = self._series_episode.get_series(
                    record.workspaceRef,
                    expected_series["seriesRef"],
                )
                series_fields = (
                    "workspaceRef",
                    "seriesRef",
                    "contentProfileRef",
                    "title",
                    "description",
                    "plannedEpisodeCount",
                    "createdAt",
                )
                if any(
                    current_series.get(field) != expected_series.get(field)
                    for field in series_fields
                ):
                    raise ProjectFoundationValidationError(
                        "series authority no longer matches receipt"
                    )

            expected_episode = result.get("episode")
            if expected_episode is not None:
                current_episode = self._series_episode.get_episode(
                    record.workspaceRef,
                    expected_series["seriesRef"],
                    expected_episode["episodeRef"],
                )
                episode_fields = (
                    "workspaceRef",
                    "seriesRef",
                    "episodeRef",
                    "episodeNumber",
                    "seasonNumber",
                    "volumeNumber",
                    "title",
                    "creativePlanRef",
                    "sourcePlanRef",
                    "sourcePlanSchemaVersion",
                    "sourcePlanVersion",
                    "createdAt",
                )
                if any(
                    current_episode.get(field) != expected_episode.get(field)
                    for field in episode_fields
                ):
                    raise ProjectFoundationValidationError(
                        "episode authority no longer matches receipt"
                    )
            return dict(result)
        except (ProjectFoundationApplicationError,):
            raise
        except Exception as exc:
            raise self._unavailable() from exc

    def _record_projection(
        self,
        record: ProjectFoundationRecord,
        *,
        validate_authority: bool,
    ) -> dict[str, Any]:
        try:
            request_value, result = validate_project_foundation_record(record)
        except ProjectFoundationValidationError as exc:
            raise self._unavailable() from exc
        if result is None:
            return self._pending_projection(record, request_value)
        if validate_authority:
            return self._validate_authority(record, request_value, result)
        return dict(result)

    def execute(
        self,
        workspace_ref: str,
        payload: Mapping[str, Any] | Any,
    ) -> dict[str, Any]:
        try:
            idempotency_key, command = normalize_project_foundation_command(
                payload
            )
        except ProjectFoundationValidationError as exc:
            raise ProjectFoundationApplicationError(
                "invalid_project_foundation", 400
            ) from exc

        request_json = canonical_json(command)
        request_digest = sha256(request_json.encode("utf-8")).hexdigest()
        created_at = self._clock()
        pending = ProjectFoundationRecord(
            PROJECT_FOUNDATION_RECORD_SCHEMA_VERSION,
            workspace_ref,
            self._ref_factory("project-foundation"),
            idempotency_key,
            request_digest,
            request_json,
            "PENDING",
            None,
            None,
            created_at,
            created_at,
            1,
        )
        try:
            record, inserted = self.store.reserve(pending)
        except (ProjectFoundationStorageError, ProjectFoundationValidationError) as exc:
            raise self._unavailable() from exc
        if record.requestDigest != request_digest or record.requestJson != request_json:
            raise ProjectFoundationApplicationError(
                "project_foundation_idempotency_conflict", 409
            )
        if record.state == "COMPLETED":
            return {
                "foundation": self._record_projection(
                    record, validate_authority=True
                ),
                "idempotentReplay": True,
                "recoveredFromPending": False,
            }

        recovered_from_pending = not inserted
        if inserted:
            self._fault_hook("after-intent-commit")
        try:
            result = self._coordinator.create_project_foundation(
                workspace_ref,
                lambda lease: self._complete_pending(
                    lease,
                    workspace_ref,
                    idempotency_key,
                    request_digest,
                    command,
                ),
            )
        except ProjectFoundationApplicationError:
            raise
        except LifecycleIntegrityError as exc:
            raise self._unavailable() from exc
        except (ProjectFoundationStorageError, ProjectFoundationValidationError) as exc:
            raise self._unavailable() from exc
        self._fault_hook("after-transaction-commit-before-http-response")
        return {
            "foundation": result,
            "idempotentReplay": False,
            "recoveredFromPending": recovered_from_pending,
        }

    def _complete_pending(
        self,
        lease: object,
        workspace_ref: str,
        idempotency_key: str,
        request_digest: str,
        command: Mapping[str, Any],
    ) -> dict[str, Any]:
        current = self.store.get_by_key(workspace_ref, idempotency_key)
        if current is None:
            raise ProjectFoundationStorageError(
                "pending project foundation intent is missing"
            )
        if current.requestDigest != request_digest or current.requestJson != canonical_json(command):
            raise ProjectFoundationApplicationError(
                "project_foundation_idempotency_conflict", 409
            )
        if current.state == "COMPLETED":
            return self._record_projection(current, validate_authority=True)

        content_profile_ref = command["contentProfileRef"]
        series = None
        try:
            if command["series"] is not None:
                series = self._series_episode._create_series_participant(
                    lease,
                    {
                        "workspaceRef": workspace_ref,
                        "contentProfileRef": content_profile_ref,
                        "title": command["series"]["title"],
                        "description": command["series"]["description"],
                        "plannedEpisodeCount": command["project"][
                            "plannedEpisodeCount"
                        ],
                    },
                )
                self._fault_hook("after-series-create")

            project_command = {
                "workspaceRef": workspace_ref,
                "contentProfileRef": content_profile_ref,
                **command["project"],
                "seriesRef": series["seriesRef"] if series is not None else None,
            }
            project = self._project._create_project_participant(
                lease,
                project_command,
            )
            self._fault_hook("after-project-create")

            episode = None
            if command["episode"] is not None:
                episode = self._series_episode._create_episode_participant(
                    lease,
                    {
                        "workspaceRef": workspace_ref,
                        "seriesRef": series["seriesRef"],
                        **command["episode"],
                    },
                )
                self._fault_hook("after-episode-create")
        except SeriesEpisodePublicError as exc:
            if exc.code == "creative_plan_not_confirmed":
                raise ProjectFoundationApplicationError(exc.code, 409) from None
            if exc.status >= 500 or exc.code == "lifecycle_unavailable":
                raise self._unavailable() from None
            raise ProjectFoundationApplicationError(
                "invalid_project_foundation", 400
            ) from None
        except ProjectPublicError as exc:
            if exc.status >= 500:
                raise self._unavailable() from None
            raise ProjectFoundationApplicationError(
                "invalid_project_foundation", 400
            ) from None

        completed_at = self._clock()
        result = {
            "schemaVersion": PROJECT_FOUNDATION_RESULT_SCHEMA_VERSION,
            "foundationRef": current.foundationRef,
            "workspaceRef": workspace_ref,
            "contentProfileRef": content_profile_ref,
            "state": "COMPLETED",
            "series": series,
            "project": project,
            "episode": episode,
            "createdAt": current.createdAt,
            "completedAt": completed_at,
            "version": 1,
        }
        result = self._validate_authority(current, command, result)
        self._fault_hook("before-result-receipt-update")
        completed = self.store.complete(
            lease,
            current,
            result,
            completed_at,
        )
        return self._record_projection(completed, validate_authority=False)

    def get(self, workspace_ref: str, foundation_ref: str) -> dict[str, Any]:
        if (
            not isinstance(foundation_ref, str)
            or not foundation_ref
            or len(foundation_ref) > 200
            or "/" in foundation_ref
            or "\\" in foundation_ref
            or any(character.isspace() for character in foundation_ref)
        ):
            raise ProjectFoundationApplicationError(
                "project_foundation_not_found", 404
            )
        try:
            record = self.store.get_by_ref(workspace_ref, foundation_ref)
        except (ProjectFoundationStorageError, ProjectFoundationValidationError) as exc:
            raise self._unavailable() from exc
        if record is None:
            raise ProjectFoundationApplicationError(
                "project_foundation_not_found", 404
            )
        return self._record_projection(record, validate_authority=True)
