"""Internal V5 public boundary for bounded M6 Series Intelligence."""

from __future__ import annotations

from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation
from services.v5_core_os.lifecycle_integrity.errors import LifecycleIntegrityError

from .errors import (
    AuthorityUnavailableError,
    ConfirmationRequiredError,
    DuplicateRecordError,
    IdempotencyConflictError,
    RecordNotFoundError,
    ScopeMismatchError,
    SeriesIntelligenceError,
    StaleSourceError,
    VersionConflictError,
)
from .foundation import SeriesIntelligenceService


class SeriesIntelligencePublicError(RuntimeError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class SeriesIntelligencePublicBoundary:
    def __init__(self, service: SeriesIntelligenceService, *, lifecycle_state) -> None:
        self.__service = service
        self.__state = lifecycle_state
        self.__assembly = None

    def _bind_lifecycle_assembly(self, assembly) -> None:
        if self.__assembly is not None:
            raise RuntimeError("lifecycle assembly is already bound")
        self.__assembly = assembly

    @staticmethod
    def _error(exc: SeriesIntelligenceError) -> SeriesIntelligencePublicError:
        if isinstance(exc, RecordNotFoundError):
            return SeriesIntelligencePublicError(exc.code, 404)
        if isinstance(
            exc,
            (DuplicateRecordError, VersionConflictError, IdempotencyConflictError,
             ConfirmationRequiredError, StaleSourceError),
        ):
            return SeriesIntelligencePublicError(exc.code, 409)
        if isinstance(exc, (AuthorityUnavailableError, ScopeMismatchError)):
            return SeriesIntelligencePublicError(exc.code, 403)
        return SeriesIntelligencePublicError(exc.code, 400)

    def _write(self, command: Mapping[str, Any], operation: LifecycleOperation, method):
        if not isinstance(command, Mapping):
            raise SeriesIntelligencePublicError("invalid_request", 400)
        workspace_ref = str(command.get("workspaceRef") or "")
        try:
            with self.__state.lease(workspace_ref=workspace_ref, operation=operation) as lease:
                return self.__state.apply_mutation(
                    lease,
                    lambda: method(self.__service.resolve_scope(command), command),
                )
        except SeriesIntelligenceError as exc:
            raise self._error(exc) from None
        except LifecycleIntegrityError:
            raise SeriesIntelligencePublicError("lifecycle_unavailable", 503) from None

    def create_bible_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            command, LifecycleOperation.CREATE_SERIES_BIBLE_VERSION,
            self.__service.create_bible_version,
        )

    def submit_bible_candidate(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            command, LifecycleOperation.SUBMIT_SERIES_BIBLE_CANDIDATE,
            self.__service.submit_bible_candidate,
        )

    def confirm_bible_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            command, LifecycleOperation.CONFIRM_SERIES_BIBLE_VERSION,
            self.__service.confirm_bible_version,
        )

    def create_character_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            command, LifecycleOperation.CREATE_CHARACTER_CONTINUITY_VERSION,
            self.__service.create_character_version,
        )

    def submit_character_candidate(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            command, LifecycleOperation.SUBMIT_CHARACTER_CONTINUITY_CANDIDATE,
            self.__service.submit_character_candidate,
        )

    def confirm_character_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            command, LifecycleOperation.CONFIRM_CHARACTER_CONTINUITY_VERSION,
            self.__service.confirm_character_version,
        )

    def activate_baseline(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            command, LifecycleOperation.ACTIVATE_M6_BASELINE,
            self.__service.activate_baseline,
        )

    def get_workspace(self, workspace_ref: str, project_ref: str, series_ref: str) -> dict[str, Any]:
        try:
            with self.__state.read_snapshot():
                scope = self.__service.resolve_scope({
                    "workspaceRef": workspace_ref,
                    "projectRef": project_ref,
                    "seriesRef": series_ref,
                })
                return self.__service.get_workspace(scope)
        except SeriesIntelligenceError as exc:
            raise self._error(exc) from None
        except LifecycleIntegrityError:
            raise SeriesIntelligencePublicError("lifecycle_unavailable", 503) from None

    def get_outbox(
        self,
        workspace_ref: str | None = None,
        project_ref: str | None = None,
        series_ref: str | None = None,
    ) -> list[dict[str, Any]]:
        """Internal diagnostic view; scoped reads require trusted Scope resolution."""
        try:
            self.__state.assert_ready()
            requested = (workspace_ref, project_ref, series_ref)
            if any(value is None for value in requested):
                raise SeriesIntelligencePublicError("invalid_request", 400)
            scope = self.__service.resolve_scope({
                "workspaceRef": workspace_ref,
                "projectRef": project_ref,
                "seriesRef": series_ref,
            })
            return self.__service.repository.list_outbox(scope.key)
        except SeriesIntelligenceError as exc:
            raise self._error(exc) from None
        except LifecycleIntegrityError:
            raise SeriesIntelligencePublicError("lifecycle_unavailable", 503) from None

    def diagnostic_snapshot(self) -> dict[str, int]:
        return self.__service.repository.diagnostic()

    def lifecycle_has_series_dependency(self, workspace_ref: str, series_ref: str) -> bool:
        """Internal lifecycle guard; it exposes no M6 fact or persistence detail."""
        self.__state.assert_ready()
        return self.__service.repository.lifecycle_has_series_dependency(
            workspace_ref, series_ref
        )
