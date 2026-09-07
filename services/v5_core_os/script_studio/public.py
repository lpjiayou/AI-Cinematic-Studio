"""Application-facing V5 public boundary for Script Studio."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation
from services.v5_core_os.lifecycle_integrity.errors import LifecycleIntegrityError

from services.v5_core_os.series_episode import SeriesEpisodePublicBoundary
from services.v5_core_os.series_intelligence.errors import SeriesIntelligenceError

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
    TrustedApprovalRequiredError,
    VersionConflictError,
)
from .generation_recovery import (
    GenerationRecoveryError, ScriptGenerationRecovery, InMemoryGenerationStore,
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
        self.__m6_episode_baseline_reader = None
        self.__generation_recovery = None

    def _bind_generation_store(self, store) -> None:
        if self.__generation_recovery is not None:
            raise RuntimeError("Script generation recovery is already bound")
        self.__generation_recovery = ScriptGenerationRecovery(self.__service, store)

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

    def _bind_m6_episode_baseline_reader(self, reader) -> None:
        if self.__m6_episode_baseline_reader is not None:
            raise RuntimeError("M6 Episode baseline reader is already bound")
        if reader is None:
            raise RuntimeError("M6 Episode baseline reader is unavailable")
        self.__m6_episode_baseline_reader = reader
        bind_service_reader = getattr(
            self.__service,
            "bind_m6_episode_baseline_reader",
            None,
        )
        if callable(bind_service_reader):
            bind_service_reader(reader)

    @staticmethod
    def _error(exc: ScriptStudioError) -> ScriptStudioPublicError:
        if isinstance(exc, GenerationRecoveryError):
            return ScriptStudioPublicError(exc.code, exc.status)
        if exc.code == "script_confirmation_precondition_required":
            return ScriptStudioPublicError(exc.code, 409)
        if exc.code in {
            "m6_baseline_not_available",
            "m6_episode_mapping_unavailable",
        }:
            return ScriptStudioPublicError(exc.code, 404)
        if exc.code in {"m6_baseline_stale", "m6_lineage_mismatch"}:
            return ScriptStudioPublicError(exc.code, 409)
        if exc.code == "m6_consumer_authority_unavailable":
            return ScriptStudioPublicError(exc.code, 403)
        if exc.code == "m6_consumer_internal_error":
            return ScriptStudioPublicError(exc.code, 500)
        if isinstance(exc, RecordNotFoundError):
            return ScriptStudioPublicError(exc.code, 404)
        if isinstance(exc, (DuplicateRecordError, VersionConflictError, ScriptNotConfirmedError)):
            return ScriptStudioPublicError(exc.code, 409)
        if isinstance(exc, ScopeMismatchError):
            return ScriptStudioPublicError(exc.code, 400)
        if isinstance(exc, TrustedApprovalRequiredError):
            return ScriptStudioPublicError(exc.code, 403)
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

    def get_m6_episode_baseline(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        if self.__m6_episode_baseline_reader is None or self.__lifecycle_state is None:
            raise ScriptStudioPublicError("m6_consumer_authority_unavailable", 503)
        try:
            with self.__lifecycle_state.read_snapshot():
                return self.__m6_episode_baseline_reader.get_active_episode_baseline(
                    workspace_ref,
                    project_ref,
                    series_ref,
                    episode_ref,
                )
        except SeriesIntelligenceError as exc:
            status = {
                "m6_baseline_not_available": 404,
                "m6_episode_mapping_unavailable": 404,
                "m6_baseline_stale": 409,
                "m6_lineage_mismatch": 409,
                "m6_consumer_authority_unavailable": 403,
            }.get(exc.code, 400)
            raise ScriptStudioPublicError(exc.code, status) from None
        except LifecycleIntegrityError:
            raise ScriptStudioPublicError(
                "m6_consumer_authority_unavailable", 503
            ) from None
        except Exception:
            raise ScriptStudioPublicError("m6_consumer_internal_error", 500) from None

    def resolve_current_m6_consumer_binding(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        if self.__lifecycle_state is None:
            return self._invoke(
                self.__service.resolve_current_m6_consumer_binding,
                workspace_ref,
                project_ref,
                series_ref,
                episode_ref,
            )
        try:
            with self.__lifecycle_state.read_snapshot():
                return self._invoke(
                    self.__service.resolve_current_m6_consumer_binding,
                    workspace_ref,
                    project_ref,
                    series_ref,
                    episode_ref,
                )
        except LifecycleIntegrityError:
            raise ScriptStudioPublicError(
                "m6_consumer_authority_unavailable", 503
            ) from None

    def resolve_current_m6_consumer_context(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        if self.__lifecycle_state is None:
            return self._invoke(
                self.__service.resolve_current_m6_consumer_context,
                workspace_ref,
                project_ref,
                series_ref,
                episode_ref,
            )
        try:
            with self.__lifecycle_state.read_snapshot():
                return self._invoke(
                    self.__service.resolve_current_m6_consumer_context,
                    workspace_ref,
                    project_ref,
                    series_ref,
                    episode_ref,
                )
        except LifecycleIntegrityError:
            raise ScriptStudioPublicError(
                "m6_consumer_authority_unavailable", 503
            ) from None

    def create_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if self.__lifecycle_coordinator is None:
            if self.__lifecycle_state is not None:
                return self._script_mutation(command, self.__service.create_version)
            return self._invoke(self.__service.create_version, command)
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        return self._invoke(
            self.__lifecycle_coordinator.create_script_version,
            workspace_ref,
            lambda: self.__service.create_version(command),
        )

    def _script_mutation(self, command, operation):
        workspace = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        with self.__lifecycle_state.lease(
            workspace_ref=workspace, operation=LifecycleOperation.CREATE_SCRIPT_VERSION,
        ) as lease:
            return self.__lifecycle_state.apply_mutation(lease, lambda: self._invoke(operation, command))

    def _generation_operation(self, name, command, *args):
        if self.__generation_recovery is None or self.__lifecycle_state is None:
            raise ScriptStudioPublicError("script_generation_storage_unavailable", 503)
        scope = command if name == "reserve" else command.get("scope", {})
        try:
            return self._script_mutation(scope, lambda _: getattr(self.__generation_recovery, name)(command, *args))
        except LifecycleIntegrityError:
            raise ScriptStudioPublicError("script_generation_storage_unavailable", 503) from None

    def reserve_generation(self, command):
        return self._generation_operation("reserve", command)

    def save_generation_result(self, ticket, content):
        return self._generation_operation("save_result", ticket, content)

    def complete_generation(self, ticket):
        return self._generation_operation("complete", ticket)

    def fail_generation(self, ticket, failure_code):
        return self._generation_operation("fail", ticket, failure_code)

    def confirm_version(self, command: Mapping[str, Any], *, include_outcome=False) -> dict[str, Any]:
        def confirm(value):
            result = self.__service.confirm_version(value)
            if not include_outcome:
                result.pop("confirmationNoOp")
            return result
        if self.__lifecycle_state is None:
            return self._invoke(confirm, command)
        workspace_ref = str(command.get("workspaceRef") or "") if isinstance(command, Mapping) else ""
        with self.__lifecycle_state.lease(
            workspace_ref=workspace_ref, operation=LifecycleOperation.CONFIRM_SCRIPT_VERSION
        ) as lease:
            return self.__lifecycle_state.apply_mutation(
                lease, lambda: self._invoke(confirm, command)
            )

    def accept_reviewed_import(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        if self.__lifecycle_state is None:
            return self._invoke(self.__service.accept_reviewed_import, command)
        workspace_ref = (
            str(command.get("workspaceRef") or "")
            if isinstance(command, Mapping)
            else ""
        )
        with self.__lifecycle_state.lease(
            workspace_ref=workspace_ref,
            operation=LifecycleOperation.CONFIRM_SCRIPT_VERSION,
        ) as lease:
            return self.__lifecycle_state.apply_mutation(
                lease,
                lambda: self._invoke(
                    self.__service.accept_reviewed_import, command
                ),
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
    from services.v5_core_os.lifecycle_integrity.in_memory import InMemoryLifecycleState
    from services.v5_core_os.lifecycle_integrity.contracts import BackendKind, LifecycleAssemblyIdentity
    repository = InMemoryScriptStudioAdapter()
    state = InMemoryLifecycleState(LifecycleAssemblyIdentity(
        "script-standalone-" + uuid4().hex, BackendKind.IN_MEMORY, "memory:" + uuid4().hex))
    names = ("_scripts", "_episode_index", "_versions", "_acceptances", "_acceptance_idempotency", "_acceptance_uniques")
    state.register_resource("script-studio", lambda: {k: deepcopy(getattr(repository, k)) for k in names},
        lambda snapshot: [setattr(repository, k, deepcopy(snapshot[k])) for k in names])
    store = InMemoryGenerationStore()
    state.register_resource("script-generation-recovery", lambda: deepcopy(store._records),
                            lambda snapshot: setattr(store, "_records", deepcopy(snapshot)))
    boundary = ScriptStudioPublicBoundary(ScriptStudioService(repository, upstream, **kwargs), lifecycle_state=state)
    boundary._bind_generation_store(store)
    return boundary


def create_local_development_boundary(
    database_path: Path | str,
    upstream: SeriesEpisodePublicBoundary,
) -> ScriptStudioPublicBoundary:
    from services.v5_core_os.lifecycle_integrity.sqlite_backend import SqliteLifecycleState
    from .generation_recovery_sqlite import SqliteGenerationStore
    state = SqliteLifecycleState(database_path)
    boundary = ScriptStudioPublicBoundary(ScriptStudioService(
        SqliteScriptStudioAdapter(database_path, lifecycle_state=state), upstream), lifecycle_state=state)
    boundary._bind_generation_store(SqliteGenerationStore(database_path, lifecycle_state=state))
    return boundary


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
