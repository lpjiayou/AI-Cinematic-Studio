"""Composition root for the accepted in-memory lifecycle integrity boundary."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
import sqlite3
import os
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from services.v5_core_os.project_engine.foundation import (
    InMemoryProjectAdapter,
    ProjectContextService,
    SqliteProjectAdapter,
)
from services.v5_core_os.project_engine.public import ProjectPublicBoundary
from services.v5_core_os.project_engine.project_foundation import (
    InMemoryProjectFoundationStore,
)
from services.v5_core_os.project_engine.project_foundation_sqlite import (
    SqliteProjectFoundationStore,
)
from services.v5_core_os.canonical_registration.foundation import (
    CanonicalRegistrationService,
    InMemoryCanonicalRegistrationRepository,
    SqliteCanonicalRegistrationRepository,
)
from services.v5_core_os.canonical_registration.public import (
    CanonicalRegistrationPublicBoundary,
)
from services.v5_core_os.script_studio.foundation import (
    InMemoryScriptStudioAdapter,
    ScriptStudioService,
    SqliteScriptStudioAdapter,
)
from services.v5_core_os.script_studio.public import ScriptStudioPublicBoundary
from services.v5_core_os.script_studio.external_acceptance import (
    script_acceptance_authority_from_environment,
)
from services.v5_core_os.series_episode.foundation import (
    DependentRecordError,
    InMemorySeriesEpisodeAdapter,
    LifecycleUnavailableError,
    SeriesEpisodeService,
    SqliteSeriesEpisodeAdapter,
)
from services.v5_core_os.series_episode.public import SeriesEpisodePublicBoundary
from services.v5_core_os.series_planning.foundation import (
    InMemorySeriesPlanningAdapter,
    SeriesPlanningService,
    SqliteSeriesPlanningAdapter,
)
from services.v5_core_os.series_planning.public import SeriesPlanningPublicBoundary
from services.v5_core_os.series_intelligence.composition import (
    create_in_memory_participant,
    create_sqlite_participant,
)
from services.v5_core_os.series_intelligence.errors import SeriesIntelligenceError
from services.v5_core_os.series_intelligence.external_authority import (
    m6_external_authorities_from_environment,
)

from .contracts import BackendKind, LifecycleAssemblyIdentity
from .coordinator import LifecycleIntegrityCoordinator
from .in_memory import InMemoryLifecycleState
from .migration import migrate_lifecycle_database, validate_lifecycle_database
from .sqlite_backend import SqliteLifecycleState


def _capture(adapter: object, names: tuple[str, ...]) -> Callable[[], dict[str, Any]]:
    return lambda: {name: copy(getattr(adapter, name)) for name in names}


def _restore(adapter: object, names: tuple[str, ...]) -> Callable[[dict[str, Any]], None]:
    def restore(snapshot: dict[str, Any]) -> None:
        for name in names:
            setattr(adapter, name, copy(snapshot[name]))

    return restore


def _in_memory_series_plan_depends_on_series(repository, workspace_ref: str, series_ref: str) -> bool:
    return any(
        key[0] == workspace_ref and key[2] == series_ref
        for key in repository._scope_index
    )


def _sqlite_series_plan_depends_on_series(repository, workspace_ref: str, series_ref: str) -> bool:
    try:
        with repository._session() as connection:
            return connection.execute(
                "SELECT 1 FROM v5_series_plans WHERE workspace_ref = ? AND series_ref = ? LIMIT 1",
                (workspace_ref, series_ref),
            ).fetchone() is not None
    except sqlite3.DatabaseError:
        raise LifecycleUnavailableError("lifecycle dependency state is unavailable") from None


def _series_plan_depends_on_episode(
    repository,
    workspace_ref: str,
    series_ref: str,
    episode_ref: str,
) -> bool:
    try:
        return repository.lifecycle_has_episode_binding_dependency(
            workspace_ref,
            series_ref,
            episode_ref,
        )
    except Exception:
        # An exact-scope historical binding record that cannot be read safely must
        # conservatively retain the Episode rather than permit an orphan.
        return True


def _series_intelligence_depends_on_series(boundary, workspace_ref, series_ref) -> bool:
    try:
        return boundary.lifecycle_has_series_dependency(workspace_ref, series_ref)
    except SeriesIntelligenceError:
        raise LifecycleUnavailableError("lifecycle dependency state is unavailable") from None


@dataclass(frozen=True)
class LifecycleAssembly:
    identity: LifecycleAssemblyIdentity
    state: InMemoryLifecycleState
    coordinator: LifecycleIntegrityCoordinator
    series_episode: SeriesEpisodePublicBoundary
    project_context: ProjectPublicBoundary
    script_studio: ScriptStudioPublicBoundary
    series_planning: SeriesPlanningPublicBoundary
    canonical_registration: CanonicalRegistrationPublicBoundary
    project_foundation_store: object
    series_intelligence: object | None = None

    @classmethod
    def in_memory(
        cls,
        *,
        ref_factory=None,
        clock=None,
        journal_registrar=None,
        m6_scope_authority=None,
        m6_approval_authority=None,
        m6_identity_authority=None,
        m6_outbox_hook=None,
        script_acceptance_authority=None,
        canonical_target_ref=None,
        canonical_registration_fault_hook=None,
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
        registration_repository = InMemoryCanonicalRegistrationRepository()
        project_foundation_store = InMemoryProjectFoundationStore(
            lifecycle_state=state
        )

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
            _capture(
                script_repository,
                (
                    "_scripts",
                    "_episode_index",
                    "_versions",
                    "_acceptances",
                    "_acceptance_idempotency",
                    "_acceptance_uniques",
                ),
            ),
            _restore(
                script_repository,
                (
                    "_scripts",
                    "_episode_index",
                    "_versions",
                    "_acceptances",
                    "_acceptance_idempotency",
                    "_acceptance_uniques",
                ),
            ),
        )
        state.register_resource(
            "series-planning",
            _capture(planning_repository, ("_plans", "_scope_index", "_versions")),
            _restore(planning_repository, ("_plans", "_scope_index", "_versions")),
        )
        state.register_resource(
            "canonical-registration",
            _capture(
                registration_repository,
                ("_records", "_registration_keys", "_idempotency_keys"),
            ),
            _restore(
                registration_repository,
                ("_records", "_registration_keys", "_idempotency_keys"),
            ),
        )
        state.register_resource(
            "project-foundation-command",
            _capture(project_foundation_store, ("_records", "_keys")),
            _restore(project_foundation_store, ("_records", "_keys")),
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
        script_service = ScriptStudioService(
            script_repository,
            series_boundary,
            acceptance_authority=script_acceptance_authority,
            **kwargs,
        )
        script_boundary = ScriptStudioPublicBoundary(script_service, lifecycle_state=state)
        registration_service = CanonicalRegistrationService(
            registration_repository,
            series_repository=series_repository,
            project_repository=project_repository,
            script_repository=script_repository,
            acceptance_authority=script_service.acceptance_authority,
            backend_kind=identity.backend_kind,
            storage_identity=identity.storage_identity,
            canonical_target_ref=canonical_target_ref,
            fault_hook=canonical_registration_fault_hook,
            **({"clock": clock} if clock is not None else {}),
        )
        registration_boundary = CanonicalRegistrationPublicBoundary(
            registration_service, lifecycle_state=state
        )
        planning_service = SeriesPlanningService(
            planning_repository,
            project_boundary,
            binding_context_reader=project_boundary,
            **kwargs,
        )
        planning_boundary = SeriesPlanningPublicBoundary(planning_service, lifecycle_state=state)
        intelligence_boundary = create_in_memory_participant(
            lifecycle_state=state,
            source_reader=planning_boundary,
            consumer_context_reader=project_boundary,
            scope_authority=m6_scope_authority,
            approval_authority=m6_approval_authority,
            identity_authority=m6_identity_authority,
            ref_factory=ref_factory,
            clock=clock,
            outbox_hook=m6_outbox_hook,
        )
        script_boundary._bind_m6_episode_baseline_reader(
            intelligence_boundary._active_m6_baseline_reader_or_none()
        )

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
            series_plan_depends_on_episode=lambda workspace, series, episode: (
                _series_plan_depends_on_episode(
                    planning_repository,
                    workspace,
                    series,
                    episode,
                )
            ),
            series_plan_depends_on_series=lambda workspace, series: (
                _in_memory_series_plan_depends_on_series(
                    planning_repository, workspace, series
                )
            ),
            series_intelligence_depends_on_series=lambda workspace, series: (
                _series_intelligence_depends_on_series(
                    intelligence_boundary, workspace, series
                )
            ),
            dependency_error=lambda code: DependentRecordError(code),
        )
        series_boundary.bind_lifecycle(coordinator)
        project_boundary.bind_lifecycle(coordinator)
        script_boundary.bind_lifecycle(coordinator)
        assembly = cls(
            identity=identity,
            state=state,
            coordinator=coordinator,
            series_episode=series_boundary,
            project_context=project_boundary,
            script_studio=script_boundary,
            series_planning=planning_boundary,
            canonical_registration=registration_boundary,
            project_foundation_store=project_foundation_store,
            series_intelligence=intelligence_boundary,
        )
        for boundary in (
            series_boundary,
            project_boundary,
            script_boundary,
            planning_boundary,
            registration_boundary,
            intelligence_boundary,
        ):
            boundary._bind_lifecycle_assembly(assembly)
        return assembly

    @classmethod
    def sqlite(
        cls,
        database_path,
        *,
        ref_factory=None,
        clock=None,
        initialize_or_upgrade: bool = False,
        transaction_hook=None,
        m6_scope_authority=None,
        m6_approval_authority=None,
        m6_identity_authority=None,
        m6_fault_hook=None,
        script_acceptance_authority=None,
        canonical_target_ref=None,
        canonical_registration_fault_hook=None,
    ) -> "LifecycleAssembly":
        if initialize_or_upgrade:
            migrate_lifecycle_database(database_path, allow_upgrade=True)
        else:
            validate_lifecycle_database(database_path)
        state = SqliteLifecycleState(database_path, transaction_hook=transaction_hook)
        identity = state.identity
        series_repository = SqliteSeriesEpisodeAdapter(database_path, lifecycle_state=state)
        project_repository = SqliteProjectAdapter(database_path, lifecycle_state=state)
        script_repository = SqliteScriptStudioAdapter(database_path, lifecycle_state=state)
        planning_repository = SqliteSeriesPlanningAdapter(database_path, lifecycle_state=state)
        registration_repository = SqliteCanonicalRegistrationRepository(
            database_path, lifecycle_state=state
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
        script_service = ScriptStudioService(
            script_repository,
            series_boundary,
            acceptance_authority=script_acceptance_authority,
            **kwargs,
        )
        script_boundary = ScriptStudioPublicBoundary(script_service, lifecycle_state=state)
        registration_service = CanonicalRegistrationService(
            registration_repository,
            series_repository=series_repository,
            project_repository=project_repository,
            script_repository=script_repository,
            acceptance_authority=script_service.acceptance_authority,
            backend_kind=identity.backend_kind,
            storage_identity=identity.storage_identity,
            canonical_target_ref=canonical_target_ref,
            fault_hook=canonical_registration_fault_hook,
            **({"clock": clock} if clock is not None else {}),
        )
        registration_boundary = CanonicalRegistrationPublicBoundary(
            registration_service, lifecycle_state=state
        )
        planning_service = SeriesPlanningService(
            planning_repository,
            project_boundary,
            binding_context_reader=project_boundary,
            **kwargs,
        )
        planning_boundary = SeriesPlanningPublicBoundary(planning_service, lifecycle_state=state)
        intelligence_boundary = create_sqlite_participant(
            database_path=database_path,
            lifecycle_state=state,
            source_reader=planning_boundary,
            consumer_context_reader=project_boundary,
            scope_authority=m6_scope_authority,
            approval_authority=m6_approval_authority,
            identity_authority=m6_identity_authority,
            ref_factory=ref_factory,
            clock=clock,
            fault_hook=m6_fault_hook,
        )
        project_foundation_store = SqliteProjectFoundationStore(
            database_path,
            lifecycle_state=state,
        )
        script_boundary._bind_m6_episode_baseline_reader(
            intelligence_boundary._active_m6_baseline_reader_or_none()
        )
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
            series_plan_depends_on_episode=lambda workspace, series, episode: (
                _series_plan_depends_on_episode(
                    planning_repository,
                    workspace,
                    series,
                    episode,
                )
            ),
            series_plan_depends_on_series=lambda workspace, series: (
                _sqlite_series_plan_depends_on_series(
                    planning_repository, workspace, series
                )
            ),
            series_intelligence_depends_on_series=lambda workspace, series: (
                _series_intelligence_depends_on_series(
                    intelligence_boundary, workspace, series
                )
            ),
            dependency_error=lambda code: DependentRecordError(code),
        )
        series_boundary.bind_lifecycle(coordinator)
        project_boundary.bind_lifecycle(coordinator)
        script_boundary.bind_lifecycle(coordinator)
        assembly = cls(
            identity=identity,
            state=state,
            coordinator=coordinator,
            series_episode=series_boundary,
            project_context=project_boundary,
            script_studio=script_boundary,
            series_planning=planning_boundary,
            canonical_registration=registration_boundary,
            project_foundation_store=project_foundation_store,
            series_intelligence=intelligence_boundary,
        )
        for boundary in (
            series_boundary,
            project_boundary,
            script_boundary,
            planning_boundary,
            registration_boundary,
            intelligence_boundary,
        ):
            boundary._bind_lifecycle_assembly(assembly)
        return assembly

    @classmethod
    def sqlite_from_environment(cls, environ=None) -> "LifecycleAssembly":
        values = os.environ if environ is None else environ
        m6_scope_authority, m6_approval_authority = (
            m6_external_authorities_from_environment(values)
        )
        script_acceptance_authority = (
            script_acceptance_authority_from_environment(values)
        )
        configured_path = str(values.get("CREATOR_DATA_PATH", "")).strip()
        canonical_target_ref = str(
            values.get("CREATOR_CANONICAL_TARGET_REF", "")
        ).strip() or None
        if configured_path:
            database_path = Path(configured_path)
        else:
            local_app_data = str(values.get("LOCALAPPDATA", "")).strip()
            root = Path(local_app_data) if local_app_data else Path.home() / ".ai-cinematic-studio"
            database_path = root / "AI Cinematic Studio" / "creator-workspace.sqlite3"
        return cls.sqlite(
            database_path,
            m6_scope_authority=m6_scope_authority,
            m6_approval_authority=m6_approval_authority,
            script_acceptance_authority=script_acceptance_authority,
            canonical_target_ref=canonical_target_ref,
        )

    def diagnostic_snapshot(self) -> dict[str, Any]:
        return self.state.diagnostic_snapshot()
