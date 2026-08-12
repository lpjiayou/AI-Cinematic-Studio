"""Atomic coordinator for exactly three cross-domain lifecycle relationships."""

from __future__ import annotations

from typing import Any, Callable

from .contracts import LifecycleOperation
class LifecycleIntegrityCoordinator:
    """Coordinates dependencies without owning any Project or production fact."""

    def __init__(
        self,
        state,
        *,
        episode_exists: Callable[[str, str, str], bool],
        series_exists: Callable[[str, str], bool],
        project_depends_on_series: Callable[[str, str], bool],
        script_depends_on_episode: Callable[[str, str, str], bool],
        script_depends_on_series: Callable[[str, str], bool],
        dependency_error: Callable[[str], BaseException],
    ) -> None:
        self._state = state
        self._episode_exists = episode_exists
        self._series_exists = series_exists
        self._project_depends_on_series = project_depends_on_series
        self._script_depends_on_episode = script_depends_on_episode
        self._script_depends_on_series = script_depends_on_series
        self._dependency_error = dependency_error

    def _mutate(
        self,
        workspace_ref: str,
        operation: LifecycleOperation,
        mutation: Callable[[], Any],
    ) -> Any:
        with self._state.lease(workspace_ref=workspace_ref, operation=operation) as lease:
            return self._state.apply_mutation(lease, mutation)

    def create_project(self, workspace_ref: str, mutation: Callable[[], Any]) -> Any:
        return self._mutate(workspace_ref, LifecycleOperation.CREATE_PROJECT, mutation)

    def create_episode(self, workspace_ref: str, mutation: Callable[[], Any]) -> Any:
        return self._mutate(workspace_ref, LifecycleOperation.CREATE_EPISODE, mutation)

    def create_script_version(self, workspace_ref: str, mutation: Callable[[], Any]) -> Any:
        return self._mutate(workspace_ref, LifecycleOperation.CREATE_SCRIPT_VERSION, mutation)

    def delete_episode(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
        mutation: Callable[[], Any],
    ) -> Any:
        def checked() -> Any:
            # Delegate not-found to the domain operation to preserve its exact error.
            if not self._episode_exists(workspace_ref, series_ref, episode_ref):
                return mutation()
            if self._script_depends_on_episode(workspace_ref, series_ref, episode_ref):
                raise self._dependency_error("dependent_script_exists")
            return mutation()

        return self._mutate(workspace_ref, LifecycleOperation.DELETE_EPISODE, checked)

    def delete_series(
        self,
        workspace_ref: str,
        series_ref: str,
        mutation: Callable[[], Any],
    ) -> Any:
        def checked() -> Any:
            if not self._series_exists(workspace_ref, series_ref):
                return mutation()
            if self._project_depends_on_series(workspace_ref, series_ref):
                raise self._dependency_error("dependent_project_exists")
            if self._script_depends_on_series(workspace_ref, series_ref):
                raise self._dependency_error("dependent_script_exists")
            return mutation()

        return self._mutate(workspace_ref, LifecycleOperation.DELETE_SERIES, checked)
