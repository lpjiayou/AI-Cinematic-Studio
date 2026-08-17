"""Application-facing V5 boundary for K2 EpisodeProductionRun roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from .foundation import (
    EpisodeProductionError,
    EpisodeProductionService,
    IdempotencyConflictError,
    InMemoryEpisodeProductionAdapter,
    RecordNotFoundError,
    RepositoryUnavailableError,
    ScopeMismatchError,
    SqliteEpisodeProductionAdapter,
    UpstreamNotReadyError,
)


class EpisodeProductionPublicError(RuntimeError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class EpisodeProductionPublicBoundary:
    def __init__(self, service: EpisodeProductionService) -> None:
        self.__service = service

    @staticmethod
    def _error(exc: EpisodeProductionError) -> EpisodeProductionPublicError:
        if isinstance(exc, RecordNotFoundError):
            return EpisodeProductionPublicError(exc.code, 404)
        if isinstance(exc, ScopeMismatchError):
            return EpisodeProductionPublicError(exc.code, 400)
        if isinstance(exc, (UpstreamNotReadyError, IdempotencyConflictError)):
            return EpisodeProductionPublicError(exc.code, 409)
        if isinstance(exc, RepositoryUnavailableError):
            return EpisodeProductionPublicError(exc.code, 503)
        return EpisodeProductionPublicError(exc.code, 400)

    def _invoke(self, operation, *args):
        try:
            return operation(*args)
        except EpisodeProductionError as exc:
            raise self._error(exc) from None

    def create_run(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__service.create_run, command)

    def get_run(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.get_run, workspace_ref, run_ref)

    def list_runs(self, workspace_ref: str) -> list[dict[str, Any]]:
        return self._invoke(self.__service.list_runs, workspace_ref)


def _service(
    repository,
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    ref_factory=None,
    clock=None,
) -> EpisodeProductionService:
    kwargs = {}
    if ref_factory is not None:
        kwargs["ref_factory"] = ref_factory
    if clock is not None:
        kwargs["clock"] = clock
    return EpisodeProductionService(
        repository,
        project_reader=project_boundary,
        series_reader=series_episode_boundary,
        planning_reader=series_planning_boundary,
        script_reader=script_studio_boundary,
        **kwargs,
    )


def create_in_memory_boundary(
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    ref_factory=None,
    clock=None,
) -> EpisodeProductionPublicBoundary:
    return EpisodeProductionPublicBoundary(
        _service(
            InMemoryEpisodeProductionAdapter(),
            project_boundary=project_boundary,
            series_episode_boundary=series_episode_boundary,
            series_planning_boundary=series_planning_boundary,
            script_studio_boundary=script_studio_boundary,
            ref_factory=ref_factory,
            clock=clock,
        )
    )


def create_local_development_boundary(
    database_path: Path | str,
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    initialize_if_missing: bool = True,
) -> EpisodeProductionPublicBoundary:
    return EpisodeProductionPublicBoundary(
        _service(
            SqliteEpisodeProductionAdapter(
                database_path, initialize_if_missing=initialize_if_missing
            ),
            project_boundary=project_boundary,
            series_episode_boundary=series_episode_boundary,
            series_planning_boundary=series_planning_boundary,
            script_studio_boundary=script_studio_boundary,
        )
    )


def create_local_development_boundary_from_environment(
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    environ: Mapping[str, str] | None = None,
) -> EpisodeProductionPublicBoundary:
    values = os.environ if environ is None else environ
    configured = str(values.get("CREATOR_EPISODE_PRODUCTION_DATA_PATH", "")).strip()
    if configured:
        path = Path(configured)
    else:
        lifecycle = str(values.get("CREATOR_DATA_PATH", "")).strip()
        if lifecycle:
            path = Path(f"{lifecycle}.episode-production.sqlite3")
        else:
            local_app_data = str(values.get("LOCALAPPDATA", "")).strip()
            root = Path(local_app_data) if local_app_data else Path.home() / ".ai-cinematic-studio"
            path = root / "AI Cinematic Studio" / "episode-production.sqlite3"
    return create_local_development_boundary(
        path,
        project_boundary=project_boundary,
        series_episode_boundary=series_episode_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=script_studio_boundary,
        initialize_if_missing=True,
    )
