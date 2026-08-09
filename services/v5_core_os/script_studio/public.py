"""Application-facing V5 public boundary for Script Studio."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from services.v5_core_os.series_episode import SeriesEpisodePublicBoundary

from .foundation import (
    DuplicateRecordError,
    InMemoryScriptStudioAdapter,
    RecordNotFoundError,
    RepositoryWriteError,
    ScopeMismatchError,
    ScriptNotConfirmedError,
    ScriptStudioError,
    ScriptStudioService,
    SqliteScriptStudioAdapter,
    VersionConflictError,
)


class ScriptStudioPublicError(RuntimeError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class ScriptStudioPublicBoundary:
    """The only Script/ScriptVersion surface available to Creator Application."""

    def __init__(self, service: ScriptStudioService) -> None:
        self.__service = service

    @staticmethod
    def _error(exc: ScriptStudioError) -> ScriptStudioPublicError:
        if isinstance(exc, RecordNotFoundError):
            return ScriptStudioPublicError(exc.code, 404)
        if isinstance(exc, (DuplicateRecordError, VersionConflictError, ScriptNotConfirmedError)):
            return ScriptStudioPublicError(exc.code, 409)
        if isinstance(exc, ScopeMismatchError):
            return ScriptStudioPublicError(exc.code, 400)
        if isinstance(exc, RepositoryWriteError):
            return ScriptStudioPublicError(exc.code, 500)
        return ScriptStudioPublicError(exc.code, 400)

    def _invoke(self, operation, *args):
        try:
            return operation(*args)
        except ScriptStudioError as exc:
            raise self._error(exc) from None

    def get_workspace(self, workspace_ref: str, series_ref: str, episode_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.get_workspace, workspace_ref, series_ref, episode_ref)

    def create_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__service.create_version, command)

    def confirm_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__service.confirm_version, command)

    def build_storyboard_bootstrap(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        return self._invoke(
            self.__service.build_storyboard_bootstrap,
            workspace_ref,
            series_ref,
            episode_ref,
        )


def create_in_memory_boundary(
    upstream: SeriesEpisodePublicBoundary,
    *,
    ref_factory=None,
    clock=None,
) -> ScriptStudioPublicBoundary:
    kwargs = {}
    if ref_factory is not None:
        kwargs["ref_factory"] = ref_factory
    if clock is not None:
        kwargs["clock"] = clock
    return ScriptStudioPublicBoundary(
        ScriptStudioService(InMemoryScriptStudioAdapter(), upstream, **kwargs)
    )


def create_local_development_boundary(
    database_path: Path | str,
    upstream: SeriesEpisodePublicBoundary,
) -> ScriptStudioPublicBoundary:
    return ScriptStudioPublicBoundary(
        ScriptStudioService(SqliteScriptStudioAdapter(database_path), upstream)
    )


def create_local_development_boundary_from_environment(
    upstream: SeriesEpisodePublicBoundary,
    environ: Mapping[str, str] | None = None,
) -> ScriptStudioPublicBoundary:
    values = os.environ if environ is None else environ
    configured_path = values.get("CREATOR_DATA_PATH", "").strip()
    if configured_path:
        database_path = Path(configured_path)
    else:
        local_app_data = values.get("LOCALAPPDATA", "").strip()
        root = Path(local_app_data) if local_app_data else Path.home() / ".ai-cinematic-studio"
        database_path = root / "AI Cinematic Studio" / "creator-workspace.sqlite3"
    return create_local_development_boundary(database_path, upstream)
