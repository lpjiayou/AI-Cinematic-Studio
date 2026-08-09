"""Application-facing V5 public boundary for Project Context."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from services.v5_core_os.series_episode import SeriesEpisodePublicBoundary

from .foundation import (
    InMemoryProjectAdapter,
    ProjectContextError,
    ProjectContextService,
    ProjectDuplicateError,
    ProjectLifecycleError,
    ProjectRecordNotFoundError,
    ProjectScopeMismatchError,
    SqliteProjectAdapter,
)


class ProjectPublicError(RuntimeError):
    """Stable public error that does not expose repository or adapter details."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class ProjectPublicBoundary:
    """The only Project Context surface available to Creator Application."""

    def __init__(self, service: ProjectContextService) -> None:
        self.__service = service

    @staticmethod
    def _error(exc: ProjectContextError) -> ProjectPublicError:
        if isinstance(exc, ProjectRecordNotFoundError):
            return ProjectPublicError(exc.code, 404)
        if isinstance(exc, (ProjectDuplicateError, ProjectLifecycleError)):
            return ProjectPublicError(exc.code, 409)
        if isinstance(exc, ProjectScopeMismatchError):
            return ProjectPublicError(exc.code, 400)
        return ProjectPublicError(exc.code, 400)

    def _invoke(self, operation, *args):
        try:
            return operation(*args)
        except ProjectContextError as exc:
            raise self._error(exc) from None

    def create_project(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__service.create_project, command)

    def get_project(self, workspace_ref: str, project_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.get_project, workspace_ref, project_ref)

    def list_projects(self, workspace_ref: str) -> list[dict[str, Any]]:
        return self._invoke(self.__service.list_projects, workspace_ref)

    def get_project_for_series(self, workspace_ref: str, series_ref: str) -> dict[str, Any] | None:
        return self._invoke(self.__service.get_project_for_series, workspace_ref, series_ref)

    def build_context(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str | None = None,
        episode_ref: str | None = None,
    ) -> dict[str, Any]:
        return self._invoke(
            self.__service.build_context,
            workspace_ref,
            project_ref,
            series_ref,
            episode_ref,
        )

    def archive_project(self, workspace_ref: str, project_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.archive_project, workspace_ref, project_ref)


def create_in_memory_boundary(
    series_episode_boundary: SeriesEpisodePublicBoundary,
    *,
    ref_factory=None,
    clock=None,
) -> ProjectPublicBoundary:
    kwargs = {}
    if ref_factory is not None:
        kwargs["ref_factory"] = ref_factory
    if clock is not None:
        kwargs["clock"] = clock
    return ProjectPublicBoundary(
        ProjectContextService(
            InMemoryProjectAdapter(),
            get_series=series_episode_boundary.get_series,
            get_episode=series_episode_boundary.get_episode,
            **kwargs,
        )
    )


def create_local_development_boundary(
    database_path: Path | str,
    series_episode_boundary: SeriesEpisodePublicBoundary,
) -> ProjectPublicBoundary:
    return ProjectPublicBoundary(
        ProjectContextService(
            SqliteProjectAdapter(database_path),
            get_series=series_episode_boundary.get_series,
            get_episode=series_episode_boundary.get_episode,
        )
    )


def create_local_development_boundary_from_environment(
    series_episode_boundary: SeriesEpisodePublicBoundary,
    environ: Mapping[str, str] | None = None,
) -> ProjectPublicBoundary:
    values = os.environ if environ is None else environ
    configured_path = values.get("CREATOR_DATA_PATH", "").strip()
    if configured_path:
        database_path = Path(configured_path)
    else:
        local_app_data = values.get("LOCALAPPDATA", "").strip()
        root = Path(local_app_data) if local_app_data else Path.home() / ".ai-cinematic-studio"
        database_path = root / "AI Cinematic Studio" / "creator-workspace.sqlite3"
    return create_local_development_boundary(database_path, series_episode_boundary)
