"""Application-facing V5 boundary for K2 EpisodeProductionRun roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    MediaJobCoordinator,
    SqliteMediaJobAdapter,
    V4CompositionExecutor,
)

from .authority import (
    AuthorityRequiredError,
    K2AuthorityIdentityService,
    RejectingIdentityReferenceAuthority,
)
from .assets import K2AssetPipelineService
from .evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
    InvalidStateTransitionError,
    SqliteEpisodeProductionEvidenceAdapter,
)

from .foundation import (
    EpisodeProductionError,
    EpisodeProductionService,
    IdempotencyConflictError,
    InMemoryEpisodeProductionAdapter,
    RecordNotFoundError,
    RepositoryUnavailableError,
    ScopeMismatchError,
    SqliteEpisodeProductionAdapter,
    StaleInputError,
    UpstreamNotReadyError,
    _utc_now,
)
from .shot_graph import K2ShotGraphService, ValidationFailedError
from .media import (
    ArtifactRejectedError,
    K2MediaExecutionService,
    RejectingMediaExecution,
    WorkerUnavailableError,
)
from .delivery import (
    ApprovalRejectedError,
    ApprovalRequiredError,
    K2DeliveryService,
    RejectingApprovalAuthority,
)


class EpisodeProductionPublicError(RuntimeError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class EpisodeProductionPublicBoundary:
    def __init__(
        self,
        service: EpisodeProductionService,
        authority_identity: K2AuthorityIdentityService,
        shot_graph: K2ShotGraphService,
        assets: K2AssetPipelineService,
        media: K2MediaExecutionService,
        delivery: K2DeliveryService,
    ) -> None:
        self.__service = service
        self.__authority_identity = authority_identity
        self.__shot_graph = shot_graph
        self.__assets = assets
        self.__media = media
        self.__delivery = delivery

    @staticmethod
    def _error(exc: EpisodeProductionError) -> EpisodeProductionPublicError:
        if isinstance(exc, RecordNotFoundError):
            return EpisodeProductionPublicError(exc.code, 404)
        if isinstance(exc, ScopeMismatchError):
            return EpisodeProductionPublicError(exc.code, 400)
        if isinstance(exc, ValidationFailedError):
            return EpisodeProductionPublicError(exc.code, 400)
        if isinstance(exc, AuthorityRequiredError):
            return EpisodeProductionPublicError(exc.code, 403)
        if isinstance(exc, ApprovalRequiredError):
            return EpisodeProductionPublicError(exc.code, 403)
        if isinstance(exc, ApprovalRejectedError):
            return EpisodeProductionPublicError(exc.code, 409)
        if isinstance(exc, ArtifactRejectedError):
            return EpisodeProductionPublicError(exc.code, 422)
        if isinstance(exc, WorkerUnavailableError):
            return EpisodeProductionPublicError(exc.code, 503)
        if isinstance(
            exc,
            (
                UpstreamNotReadyError,
                IdempotencyConflictError,
                InvalidStateTransitionError,
                StaleInputError,
            ),
        ):
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
        run = self._invoke(self.__service.create_run, command)
        return self._invoke(self.__authority_identity.project_run, run)

    def get_run(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        run = self._invoke(self.__service.get_run, workspace_ref, run_ref)
        return self._invoke(self.__authority_identity.project_run, run)

    def list_runs(self, workspace_ref: str) -> list[dict[str, Any]]:
        runs = self._invoke(self.__service.list_runs, workspace_ref)
        return [self._invoke(self.__authority_identity.project_run, run) for run in runs]

    def authorize_and_lock(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__authority_identity.authorize_and_lock, command)

    def get_authority_identity(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        return self._invoke(
            self.__authority_identity.get_authority_identity, workspace_ref, run_ref
        )

    def compile_shot_graph(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__shot_graph.compile_shot_graph, command)

    def get_shot_graph_bundle(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        return self._invoke(
            self.__shot_graph.get_shot_graph_bundle, workspace_ref, run_ref
        )

    def resolve_assets(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__assets.resolve_assets, command)

    def get_asset_plan(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        return self._invoke(self.__assets.get_asset_plan, workspace_ref, run_ref)

    def execute_media(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__media.execute_media, command)

    def get_media_bundle(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        return self._invoke(self.__media.get_media_bundle, workspace_ref, run_ref)

    def compose_and_qc(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__delivery.compose_and_qc, command)

    def approve_and_finalize(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__delivery.approve_and_finalize, command)

    def get_delivery_bundle(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        return self._invoke(
            self.__delivery.get_delivery_bundle, workspace_ref, run_ref
        )

    def get_export_file(
        self, workspace_ref: str, run_ref: str, export_ref: str
    ) -> dict[str, Any]:
        return self._invoke(
            self.__delivery.get_export_file, workspace_ref, run_ref, export_ref
        )


def _services(
    repository,
    evidence_repository,
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    identity_reference_authority=None,
    media_execution=None,
    composition_execution=None,
    approval_authority=None,
    ref_factory=None,
    clock=None,
) -> tuple[
    EpisodeProductionService,
    K2AuthorityIdentityService,
    K2ShotGraphService,
    K2AssetPipelineService,
    K2MediaExecutionService,
    K2DeliveryService,
]:
    selected_ref_factory = ref_factory or (
        lambda prefix: f"{prefix}-{uuid4().hex}"
    )
    selected_clock = clock or _utc_now
    service = EpisodeProductionService(
        repository,
        project_reader=project_boundary,
        series_reader=series_episode_boundary,
        planning_reader=series_planning_boundary,
        script_reader=script_studio_boundary,
        ref_factory=selected_ref_factory,
        clock=selected_clock,
    )
    authority_identity = K2AuthorityIdentityService(
        service,
        evidence_repository,
        m6_reader=script_studio_boundary,
        identity_reference_authority=(
            identity_reference_authority or RejectingIdentityReferenceAuthority()
        ),
        ref_factory=selected_ref_factory,
        clock=selected_clock,
    )
    shot_graph = K2ShotGraphService(
        service,
        authority_identity,
        evidence_repository,
        script_reader=script_studio_boundary,
        ref_factory=selected_ref_factory,
        clock=selected_clock,
    )
    assets = K2AssetPipelineService(
        shot_graph,
        evidence_repository,
        ref_factory=selected_ref_factory,
        clock=selected_clock,
    )
    media = K2MediaExecutionService(
        assets,
        evidence_repository,
        media_execution or RejectingMediaExecution(),
        ref_factory=selected_ref_factory,
        clock=selected_clock,
    )
    delivery = K2DeliveryService(
        media,
        evidence_repository,
        composition_execution,
        approval_authority or RejectingApprovalAuthority(),
        ref_factory=selected_ref_factory,
        clock=selected_clock,
    )
    return service, authority_identity, shot_graph, assets, media, delivery


def create_in_memory_boundary(
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    identity_reference_authority=None,
    media_execution=None,
    composition_execution=None,
    approval_authority=None,
    ref_factory=None,
    clock=None,
) -> EpisodeProductionPublicBoundary:
    service, authority_identity, shot_graph, assets, media, delivery = _services(
        InMemoryEpisodeProductionAdapter(),
        InMemoryEpisodeProductionEvidenceAdapter(),
        project_boundary=project_boundary,
        series_episode_boundary=series_episode_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=script_studio_boundary,
        identity_reference_authority=identity_reference_authority,
        media_execution=media_execution,
        composition_execution=composition_execution,
        approval_authority=approval_authority,
        ref_factory=ref_factory,
        clock=clock,
    )
    return EpisodeProductionPublicBoundary(
        service, authority_identity, shot_graph, assets, media, delivery
    )


def create_local_development_boundary(
    database_path: Path | str,
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    evidence_database_path: Path | str | None = None,
    identity_reference_authority=None,
    media_execution=None,
    composition_execution=None,
    approval_authority=None,
    ref_factory=None,
    clock=None,
    initialize_if_missing: bool = True,
) -> EpisodeProductionPublicBoundary:
    evidence_path = (
        Path(evidence_database_path)
        if evidence_database_path is not None
        else Path(f"{database_path}.evidence.sqlite3")
    )
    service, authority_identity, shot_graph, assets, media, delivery = _services(
        SqliteEpisodeProductionAdapter(
            database_path, initialize_if_missing=initialize_if_missing
        ),
        SqliteEpisodeProductionEvidenceAdapter(
            evidence_path, initialize_if_missing=initialize_if_missing
        ),
        project_boundary=project_boundary,
        series_episode_boundary=series_episode_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=script_studio_boundary,
        identity_reference_authority=identity_reference_authority,
        media_execution=media_execution,
        composition_execution=composition_execution,
        approval_authority=approval_authority,
        ref_factory=ref_factory,
        clock=clock,
    )
    return EpisodeProductionPublicBoundary(
        service, authority_identity, shot_graph, assets, media, delivery
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
    job_path = Path(
        str(values.get("CREATOR_MEDIA_JOB_DATA_PATH", "")).strip()
        or f"{path}.media-jobs.sqlite3"
    )
    artifact_root = Path(
        str(values.get("CREATOR_MEDIA_ARTIFACT_ROOT", "")).strip()
        or f"{path}.artifacts"
    )
    execution = MediaJobCoordinator(
        SqliteMediaJobAdapter(job_path),
        DeterministicLocalFfmpegAdapter(),
        artifact_root,
        ref_factory=lambda prefix: f"{prefix}-{uuid4().hex}",
        clock=_utc_now,
    )
    return create_local_development_boundary(
        path,
        project_boundary=project_boundary,
        series_episode_boundary=series_episode_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=script_studio_boundary,
        media_execution=execution,
        composition_execution=V4CompositionExecutor.from_artifact_root(artifact_root),
        initialize_if_missing=True,
    )
