"""Composition root for the accepted in-memory lifecycle integrity boundary."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from services.v5_core_os.project_engine.foundation import (
    InMemoryProjectAdapter,
    ProjectContextService,
)
from services.v5_core_os.project_engine.public import ProjectPublicBoundary
from services.v5_core_os.script_studio.foundation import (
    InMemoryScriptStudioAdapter,
    ScriptStudioService,
)
from services.v5_core_os.script_studio.public import ScriptStudioPublicBoundary
from services.v5_core_os.series_episode.foundation import (
    DependentRecordError,
    InMemorySeriesEpisodeAdapter,
    SeriesEpisodeService,
)
from services.v5_core_os.series_episode.public import SeriesEpisodePublicBoundary
from services.v5_core_os.series_planning.foundation import (
    InMemorySeriesPlanningAdapter,
    SeriesPlanningService,
)
from services.v5_core_os.series_planning.public import SeriesPlanningPublicBoundary

from .contracts import BackendKind, LifecycleAssemblyIdentity
from .coordinator import LifecycleIntegrityCoordinator
from .in_memory import InMemoryLifecycleState


def _capture(adapter: object, names: tuple[str, ...]) -> Callable[[], dict[str, Any]]:
    return lambda: {name: copy(getattr(adapter, name)) for name in names}


def _restore(adapter: object, names: tuple[str, ...]) -> Callable[[dict[str, Any]], None]:
    def restore(snapshot: dict[str, Any]) -> None:
        for name in names:
            setattr(adapter, name, copy(snapshot[name]))

    return restore


@dataclass(frozen=True)
class LifecycleAssembly:
    identity: LifecycleAssemblyIdentity
    state: InMemoryLifecycleState
    coordinator: LifecycleIntegrityCoordinator
    series_episode: SeriesEpisodePublicBoundary
    project_context: ProjectPublicBoundary
    script_studio: ScriptStudioPublicBoundary
    series_planning: SeriesPlanningPublicBoundary

    @classmethod
    def in_memory(
        cls,
        *,
        ref_factory=None,
        clock=None,
        journal_registrar=None,
    ) -> "LifecycleAssembly":
        identity = LifecycleAssemblyIdentity(
            f"assembly-{uuid4().hex}",
            BackendKind.IN_MEMORY,
            f"memory:{uuid4().hex}",
        )
        state = InMemoryLifecycleState(identity, journal_registrar=journal_registrar)
        series_repository = InMemorySeriesEpisodeAdapter()
        project_repository = InMemoryProjectAdapter()
        script_repository = InMemoryScriptStudioAdapter()
        planning_repository = InMemorySeriesPlanningAdapter()

        state.register_resource(
            "series-episode",
            _capture(series_repository, ("_series", "_plans", "_episodes", "_bindings")),
            _restore(series_repository, ("_series", "_plans", "_episodes", "_bindings")),
        )
        state.register_resource(
            "project-context",
            _capture(project_repository, ("_projects", "_relationships")),
            _restore(project_repository, ("_projects", "_relationships")),
        )
        state.register_resource(
            "script-studio",
            _capture(script_repository, ("_scripts", "_episode_index", "_versions")),
            _restore(script_repository, ("_scripts", "_episode_index", "_versions")),
        )
        state.register_resource(
            "series-planning",
            _capture(planning_repository, ("_plans", "_scope_index", "_versions")),
            _restore(planning_repository, ("_plans", "_scope_index", "_versions")),
        )

        kwargs: dict[str, Any] = {}
        if ref_factory is not None:
            kwargs["ref_factory"] = ref_factory
        if clock is not None:
            kwargs["clock"] = clock

        series_service = SeriesEpisodeService(series_repository, **kwargs)
        series_boundary = SeriesEpisodePublicBoundary(series_service, lifecycle_state=state)
        project_service = ProjectContextService(
            project_repository,
            get_series=series_boundary.get_series,
            get_episode=series_boundary.get_episode,
            **kwargs,
        )
        project_boundary = ProjectPublicBoundary(project_service, lifecycle_state=state)
        script_service = ScriptStudioService(script_repository, series_boundary, **kwargs)
        script_boundary = ScriptStudioPublicBoundary(script_service, lifecycle_state=state)
        planning_service = SeriesPlanningService(planning_repository, project_boundary, **kwargs)
        planning_boundary = SeriesPlanningPublicBoundary(planning_service, lifecycle_state=state)

        coordinator = LifecycleIntegrityCoordinator(
            state,
            episode_exists=lambda workspace, series, episode: (
                series_repository.get_episode(workspace, series, episode) is not None
            ),
            series_exists=lambda workspace, series: (
                series_repository.get_series(workspace, series) is not None
            ),
            project_depends_on_series=lambda workspace, series: (
                project_repository.get_project_for_series(workspace, series) is not None
            ),
            script_depends_on_episode=script_repository.lifecycle_has_episode_dependency,
            script_depends_on_series=script_repository.lifecycle_has_series_dependency,
            dependency_error=lambda code: DependentRecordError(code),
        )
        series_boundary.bind_lifecycle(coordinator)
        project_boundary.bind_lifecycle(coordinator)
        script_boundary.bind_lifecycle(coordinator)
        assembly = cls(
            identity,
            state,
            coordinator,
            series_boundary,
            project_boundary,
            script_boundary,
            planning_boundary,
        )
        for boundary in (
            series_boundary,
            project_boundary,
            script_boundary,
            planning_boundary,
        ):
            boundary._bind_lifecycle_assembly(assembly)
        return assembly

    def diagnostic_snapshot(self) -> dict[str, Any]:
        return self.state.diagnostic_snapshot()
