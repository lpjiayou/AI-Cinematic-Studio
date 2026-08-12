"""Application-facing V5 public boundary for Script Studio."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation

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

    def __init__(self, service: ScriptStudioService, *, lifecycle_state=None) -> None:
        self.__service = service
        self.__lifecycle_state = lifecycle_state
        self.__lifecycle_coordinator = None
        self.__lifecycle_assembly = None

    def bind_lifecycle(self, coordinator) -> None:
        if self.__lifecycle_coordinator is not None:
            raise RuntimeError("lifecycle coordinator is already bound")
        self.__lifecycle_coordinator = coordinator

    def _bind_lifecycle_assembly(self, assembly) -> None:
        if self.__lifecycle_assembly is not None:
            raise RuntimeError("lifecycle assembly is already bound")
        self.__lifecycle_assembly = assembly

    def _lifecycle_assembly_or_none(self):
        return self.__lifecycle_assembly

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
            if self.__lifecycle_state is not None:
                self.__lifecycle_state.assert_ready()
            return operation(*args)
        except ScriptStudioError as exc:
            raise self._error(exc) from None

    def get_workspace(self, workspace_ref: str, series_ref: str, episode_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.get_workspace, workspace_ref, series_ref, episode_ref)

    def create_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if self.__lifecycle_coordinator is None:
            return self._invoke(self.__service.create_version, command)
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        return self._invoke(
            self.__lifecycle_coordinator.create_script_version,
            workspace_ref,
            lambda: self.__service.create_version(command),
        )

    def confirm_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if self.__lifecycle_state is None:
            return self._invoke(self.__service.confirm_version, command)
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        with self.__lifecycle_state.lease(
            workspace_ref=workspace_ref, operation=LifecycleOperation.CONFIRM_SCRIPT_VERSION
        ) as lease:
            return self.__lifecycle_state.apply_mutation(
                lease, lambda: self._invoke(self.__service.confirm_version, command)
            )

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
    if ref_factory is None and clock is None:
        assembly = upstream._lifecycle_assembly_or_none()
        if assembly is not None:
            return assembly.script_studio
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
