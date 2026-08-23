"""Application-facing V5 public boundary for Series and Episode capabilities."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation

from .foundation import (
    DependentRecordError,
    DuplicateRecordError,
    InMemorySeriesEpisodeAdapter,
    RecordNotFoundError,
    ScopeMismatchError,
    SeriesEpisodeError,
    SeriesEpisodeService,
    SqliteSeriesEpisodeAdapter,
    UnconfirmedPlanError,
)


class SeriesEpisodePublicError(RuntimeError):
    """Stable public error that does not expose repository or adapter details."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class SeriesEpisodePublicBoundary:
    """The only Series/Episode surface available to Creator Application."""

    def __init__(self, service: SeriesEpisodeService, *, lifecycle_state=None) -> None:
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
    def _error(exc: SeriesEpisodeError) -> SeriesEpisodePublicError:
        if isinstance(exc, RecordNotFoundError):
            return SeriesEpisodePublicError(exc.code, 404)
        if isinstance(exc, (DuplicateRecordError, UnconfirmedPlanError, DependentRecordError)):
            return SeriesEpisodePublicError(exc.code, 409)
        if isinstance(exc, ScopeMismatchError):
            return SeriesEpisodePublicError(exc.code, 400)
        return SeriesEpisodePublicError(exc.code, 400)

    def _invoke(self, operation, *args):
        try:
            if self.__lifecycle_state is not None:
                self.__lifecycle_state.assert_ready()
            return operation(*args)
        except SeriesEpisodeError as exc:
            raise self._error(exc) from None

    def _lifecycle_write(self, workspace_ref, lifecycle_operation, operation, *args):
        if self.__lifecycle_state is None:
            return self._invoke(operation, *args)
        try:
            with self.__lifecycle_state.lease(
                workspace_ref=workspace_ref, operation=lifecycle_operation
            ) as lease:
                return self.__lifecycle_state.apply_mutation(lease, lambda: operation(*args))
        except SeriesEpisodeError as exc:
            raise self._error(exc) from None

    def create_series(self, command: Mapping[str, Any]) -> dict[str, Any]:
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        return self._lifecycle_write(
            workspace_ref, LifecycleOperation.CREATE_SERIES, self.__service.create_series, command
        )

    def get_series(self, workspace_ref: str, series_ref: str) -> dict[str, Any]:
        return self._invoke(self.__service.get_series, workspace_ref, series_ref)

    def list_series(self, workspace_ref: str) -> list[dict[str, Any]]:
        return self._invoke(self.__service.list_series, workspace_ref)

    def confirm_creative_plan(self, command: Mapping[str, Any]) -> dict[str, Any]:
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        return self._lifecycle_write(
            workspace_ref,
            LifecycleOperation.CONFIRM_CREATIVE_PLAN,
            self.__service.confirm_creative_plan,
            command,
        )

    def create_episode(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if self.__lifecycle_coordinator is None:
            return self._invoke(self.__service.create_episode, command)
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        return self._invoke(
            self.__lifecycle_coordinator.create_episode,
            workspace_ref,
            lambda: self.__service.create_episode(command),
        )

    def get_episode(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        return self._invoke(self.__service.get_episode, workspace_ref, series_ref, episode_ref)

    def delete_episode(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        if self.__lifecycle_coordinator is None:
            return self._invoke(self.__service.delete_episode, workspace_ref, series_ref, episode_ref)
        return self._invoke(
            self.__lifecycle_coordinator.delete_episode,
            workspace_ref,
            series_ref,
            episode_ref,
            lambda: self.__service.delete_episode(workspace_ref, series_ref, episode_ref),
        )

    def delete_series(self, workspace_ref: str, series_ref: str) -> dict[str, Any]:
        if self.__lifecycle_coordinator is None:
            return self._invoke(self.__service.delete_series, workspace_ref, series_ref)
        return self._invoke(
            self.__lifecycle_coordinator.delete_series,
            workspace_ref,
            series_ref,
            lambda: self.__service.delete_series(workspace_ref, series_ref),
        )

    def build_script_studio_bootstrap(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        return self._invoke(
            self.__service.build_script_studio_bootstrap,
            workspace_ref,
            series_ref,
            episode_ref,
        )


def create_in_memory_boundary(*, ref_factory=None, clock=None) -> SeriesEpisodePublicBoundary:
    # The default production-like InMemory composition must never construct
    # independent repositories. Explicit factories are retained for isolated
    # compatibility tests only.
    if ref_factory is None and clock is None:
        from services.v5_core_os.lifecycle_integrity.composition import LifecycleAssembly

        return LifecycleAssembly.in_memory().series_episode
    kwargs = {}
    if ref_factory is not None:
        kwargs["ref_factory"] = ref_factory
    if clock is not None:
        kwargs["clock"] = clock
    return SeriesEpisodePublicBoundary(
        SeriesEpisodeService(InMemorySeriesEpisodeAdapter(), **kwargs)
    )


def create_local_development_boundary(database_path: Path | str) -> SeriesEpisodePublicBoundary:
    """Wire the V5-owned local SQLite adapter; this is not production storage."""

    return SeriesEpisodePublicBoundary(
        SeriesEpisodeService(SqliteSeriesEpisodeAdapter(database_path))
    )


def create_local_development_boundary_from_environment(
    environ: Mapping[str, str] | None = None,
) -> SeriesEpisodePublicBoundary:
    """Resolve local adapter placement inside the V5 public composition boundary."""

    values = os.environ if environ is None else environ
    configured_path = values.get("CREATOR_DATA_PATH", "").strip()
    if configured_path:
        database_path = Path(configured_path)
    else:
        local_app_data = values.get("LOCALAPPDATA", "").strip()
        root = Path(local_app_data) if local_app_data else Path.home() / ".ai-cinematic-studio"
        database_path = root / "AI Cinematic Studio" / "creator-workspace.sqlite3"
    return create_local_development_boundary(database_path)
