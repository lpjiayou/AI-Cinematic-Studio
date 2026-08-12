"""Application-facing V5 public boundary for Series Planning."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation

from services.v5_core_os.project_engine import ProjectPublicBoundary

from .foundation import (
    DuplicateRecordError,
    InMemorySeriesPlanningAdapter,
    PlanNotConfirmedError,
    RecordNotFoundError,
    ScopeMismatchError,
    SeriesPlanningError,
    SeriesPlanningService,
    SqliteSeriesPlanningAdapter,
    VersionConflictError,
)


class SeriesPlanningPublicError(RuntimeError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class SeriesPlanningPublicBoundary:
    """The only authoritative Series Planning surface exposed to Creator."""

    def __init__(self, service: SeriesPlanningService, *, lifecycle_state=None) -> None:
        self.__service = service
        self.__lifecycle_state = lifecycle_state
        self.__lifecycle_assembly = None

    def _bind_lifecycle_assembly(self, assembly) -> None:
        if self.__lifecycle_assembly is not None:
            raise RuntimeError("lifecycle assembly is already bound")
        self.__lifecycle_assembly = assembly

    def _lifecycle_assembly_or_none(self):
        return self.__lifecycle_assembly

    @staticmethod
    def _error(exc: SeriesPlanningError) -> SeriesPlanningPublicError:
        if isinstance(exc, RecordNotFoundError):
            return SeriesPlanningPublicError(exc.code, 404)
        if isinstance(exc, (DuplicateRecordError, VersionConflictError, PlanNotConfirmedError)):
            return SeriesPlanningPublicError(exc.code, 409)
        if isinstance(exc, ScopeMismatchError):
            return SeriesPlanningPublicError(exc.code, 400)
        return SeriesPlanningPublicError(exc.code, 400)

    def _invoke(self, operation, *args):
        try:
            if self.__lifecycle_state is not None:
                self.__lifecycle_state.assert_ready()
            return operation(*args)
        except SeriesPlanningError as exc:
            raise self._error(exc) from None

    def get_workspace(self, workspace_ref: str, project_ref: str, series_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.get_workspace, workspace_ref, project_ref, series_ref)

    def confirm_candidate(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._lifecycle_write(command, LifecycleOperation.CREATE_SERIES_PLAN, self.__service.confirm_candidate)

    def create_manual_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._lifecycle_write(command, LifecycleOperation.APPEND_SERIES_PLAN_VERSION, self.__service.create_manual_version)

    def confirm_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._lifecycle_write(command, LifecycleOperation.CONFIRM_SERIES_PLAN_VERSION, self.__service.confirm_version)

    def _lifecycle_write(self, command, lifecycle_operation, operation):
        if self.__lifecycle_state is None:
            return self._invoke(operation, command)
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        with self.__lifecycle_state.lease(
            workspace_ref=workspace_ref, operation=lifecycle_operation
        ) as lease:
            return self.__lifecycle_state.apply_mutation(
                lease, lambda: self._invoke(operation, command)
            )

    def build_m6_bootstrap(self, workspace_ref: str, project_ref: str, series_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.build_m6_bootstrap, workspace_ref, project_ref, series_ref)


def create_in_memory_boundary(
    project_boundary: ProjectPublicBoundary,
    *,
    ref_factory=None,
    clock=None,
) -> SeriesPlanningPublicBoundary:
    if ref_factory is None and clock is None:
        assembly = project_boundary._lifecycle_assembly_or_none()
        if assembly is not None:
            return assembly.series_planning
    kwargs = {}
    if ref_factory is not None:
        kwargs["ref_factory"] = ref_factory
    if clock is not None:
        kwargs["clock"] = clock
    return SeriesPlanningPublicBoundary(
        SeriesPlanningService(InMemorySeriesPlanningAdapter(), project_boundary, **kwargs)
    )


def create_local_development_boundary(
    database_path: Path | str,
    project_boundary: ProjectPublicBoundary,
) -> SeriesPlanningPublicBoundary:
    return SeriesPlanningPublicBoundary(
        SeriesPlanningService(SqliteSeriesPlanningAdapter(database_path), project_boundary)
    )


def create_local_development_boundary_from_environment(
    project_boundary: ProjectPublicBoundary,
    environ: Mapping[str, str] | None = None,
) -> SeriesPlanningPublicBoundary:
    values = os.environ if environ is None else environ
    configured_path = values.get("CREATOR_DATA_PATH", "").strip()
    if configured_path:
        database_path = Path(configured_path)
    else:
        local_app_data = values.get("LOCALAPPDATA", "").strip()
        root = Path(local_app_data) if local_app_data else Path.home() / ".ai-cinematic-studio"
        database_path = root / "AI Cinematic Studio" / "creator-workspace.sqlite3"
    return create_local_development_boundary(database_path, project_boundary)
