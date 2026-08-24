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
    create_comfyui_wan22_adapter_from_environment,
    real_image_candidate_evidence_from_environment,
)
from services.v4_platform.real_video_candidates import (
    MediaJobRealVideoCandidateEvidence,
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
from .production_policy import (
    InMemoryProductionPolicyAdapter,
    K2ProductionPolicyService,
    ProductionPolicyRequiredError,
    RejectingProviderPolicyAuthority,
    RejectingRightsEvidenceAuthority,
    SqliteProductionPolicyAdapter,
)
from .provider_experiments import (
    InMemoryProviderExperimentAdapter,
    K2ProviderExperimentService,
    ProviderCandidateRejectedError,
    ProviderExperimentUnavailableError,
    SqliteProviderExperimentAdapter,
)
from .internal_execution import (
    K2InternalExecutionGrant,
    internal_execution_grant_from_environment,
)
from .real_media_revision import (
    K2RealMediaRevisionService,
    RealImageCandidateRejectedError,
    RealVideoCandidateRejectedError,
)
from .media_candidate_review import (
    CandidateLifecycleError,
    CandidateNotSelectableError,
    K2MediaCandidateReviewService,
    MediaSelectionApprovalRequiredError,
)
from .state_projection import K2ProductionStateProjectionService
from .external_authority import (
    external_authorities_from_environment,
    identity_reference_authority_from_environment,
)
from .external_delivery_approval import (
    delivery_approval_authority_from_environment,
)
from .external_media_selection_approval import (
    media_selection_approval_authority_from_environment,
)


_INTERNAL_MEDIA_LOCATOR_FIELDS = frozenset(
    {
        "absolutepath",
        "artifactpath",
        "artifactroot",
        "candidatepath",
        "filesystempath",
        "finalpath",
        "inputpath",
        "internalpath",
        "outputpath",
    }
)


def _is_internal_media_locator(field: Any) -> bool:
    if not isinstance(field, str):
        return False
    normalized = field.replace("_", "").replace("-", "").lower()
    return (
        normalized in _INTERNAL_MEDIA_LOCATOR_FIELDS
        or normalized.endswith("storagekey")
        or normalized.endswith("storagekeys")
    )


def _strip_internal_media_locators(value: Any) -> Any:
    """Return a detached public DTO without filesystem/storage locators."""

    if isinstance(value, Mapping):
        return {
            key: _strip_internal_media_locators(item)
            for key, item in value.items()
            if not _is_internal_media_locator(key)
        }
    if isinstance(value, list):
        return [_strip_internal_media_locators(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_internal_media_locators(item) for item in value)
    return value


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
        production_policy: K2ProductionPolicyService,
        provider_experiments: K2ProviderExperimentService,
        shot_graph: K2ShotGraphService,
        assets: K2AssetPipelineService,
        media: K2MediaExecutionService,
        delivery: K2DeliveryService,
        real_media_revision: K2RealMediaRevisionService,
    ) -> None:
        self.__service = service
        self.__authority_identity = authority_identity
        self.__production_policy = production_policy
        self.__provider_experiments = provider_experiments
        self.__shot_graph = shot_graph
        self.__assets = assets
        self.__media = media
        self.__delivery = delivery
        self.__real_media_revision = real_media_revision
        self.__candidate_review = real_media_revision.candidate_review
        self.__state_projection = real_media_revision.state_projection

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
        if isinstance(exc, MediaSelectionApprovalRequiredError):
            return EpisodeProductionPublicError(exc.code, 403)
        if isinstance(exc, ApprovalRejectedError):
            return EpisodeProductionPublicError(exc.code, 409)
        if isinstance(exc, ProductionPolicyRequiredError):
            return EpisodeProductionPublicError(exc.code, 409)
        if isinstance(exc, ArtifactRejectedError):
            return EpisodeProductionPublicError(exc.code, 422)
        if isinstance(exc, ProviderCandidateRejectedError):
            return EpisodeProductionPublicError(exc.code, 422)
        if isinstance(exc, RealImageCandidateRejectedError):
            return EpisodeProductionPublicError(exc.code, 422)
        if isinstance(exc, RealVideoCandidateRejectedError):
            return EpisodeProductionPublicError(exc.code, 422)
        if isinstance(exc, CandidateNotSelectableError):
            return EpisodeProductionPublicError(exc.code, 409)
        if isinstance(exc, CandidateLifecycleError):
            return EpisodeProductionPublicError(exc.code, 400)
        if isinstance(exc, WorkerUnavailableError):
            return EpisodeProductionPublicError(exc.code, 503)
        if isinstance(exc, ProviderExperimentUnavailableError):
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

    def _invoke(self, operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except EpisodeProductionError as exc:
            raise self._error(exc) from None

    def _invoke_public_media(self, operation, *args, **kwargs):
        return _strip_internal_media_locators(
            self._invoke(operation, *args, **kwargs)
        )

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

    def record_production_policy(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke(self.__production_policy.record_bundle, command)

    def get_production_readiness(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        return self._invoke(
            self.__production_policy.get_readiness, workspace_ref, run_ref
        )

    def run_provider_experiment(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._invoke(
            self.__provider_experiments.run_video_experiment, command
        )

    def list_provider_experiments(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        return self._invoke(
            self.__provider_experiments.list_experiments,
            workspace_ref,
            run_ref,
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

    def plan_real_images(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.plan_images, command
        )

    def select_real_images(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.select_and_admit_images, command
        )

    def record_real_image_candidates(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.record_real_image_candidates, command
        )

    def admit_real_images(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.admit_real_images, command
        )

    def admit_real_image_successor(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.admit_real_image_successor, command
        )

    def plan_real_videos(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.plan_videos, command
        )

    def record_real_video_candidates(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.record_real_video_candidates, command
        )

    def record_semantic_visual_qc(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__candidate_review.record_semantic_visual_qc, command
        )

    def record_human_selection(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__candidate_review.record_human_selection, command
        )

    def admit_real_videos(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__real_media_revision.admit_real_videos, command
        )

    def get_state_projection(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        return self._invoke_public_media(
            self.__state_projection.get_projection, workspace_ref, run_ref
        )

    def get_real_media_revision(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        snapshot = self._invoke(
            self.__real_media_revision.evidence.read_snapshot,
            workspace_ref,
            run_ref,
        )
        revision = self._invoke(
            self.__real_media_revision.get_revision_bundle,
            workspace_ref,
            run_ref,
            evidence_snapshot=snapshot,
        )
        axes = self._invoke(
            self.__state_projection.get_projection,
            workspace_ref,
            run_ref,
            evidence_snapshot=snapshot,
        )
        # ADR-0013 extends the existing real-media projection; the dedicated
        # state query remains a compatibility/convenience view, not a second
        # source of truth.  Preserve all legacy revision fields and add only the
        # canonical axes owned by the shared projection service.
        merged = dict(revision)
        for field in (
            "state",
            "rootState",
            "productionState",
            "runtimeState",
            "visualQcState",
            "activeRevision",
            "productionProjection",
            "candidates",
            "candidateLifecycle",
            "invariants",
        ):
            if field in axes:
                merged[field] = axes[field]
        return _strip_internal_media_locators(merged)

    def get_preview_file(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        return self._invoke(
            self.__delivery.get_preview_file, workspace_ref, run_ref
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
    production_policy_repository,
    provider_experiment_repository,
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    identity_reference_authority=None,
    rights_evidence_authority=None,
    provider_policy_authority=None,
    provider_experiment_execution=None,
    internal_execution_grant: K2InternalExecutionGrant | None = None,
    real_image_candidate_evidence=None,
    real_video_candidate_evidence=None,
    media_execution=None,
    composition_execution=None,
    approval_authority=None,
    media_selection_approval_authority=None,
    ref_factory=None,
    clock=None,
) -> tuple[
    EpisodeProductionService,
    K2AuthorityIdentityService,
    K2ProductionPolicyService,
    K2ProviderExperimentService,
    K2ShotGraphService,
    K2AssetPipelineService,
    K2MediaExecutionService,
    K2DeliveryService,
    K2RealMediaRevisionService,
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
    production_policy = K2ProductionPolicyService(
        service,
        authority_identity,
        production_policy_repository,
        rights_evidence_authority or RejectingRightsEvidenceAuthority(),
        provider_policy_authority or RejectingProviderPolicyAuthority(),
        internal_execution_grant=internal_execution_grant,
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
    provider_experiments = K2ProviderExperimentService(
        assets,
        production_policy,
        provider_experiment_repository,
        provider_experiment_execution,
        internal_execution_grant=internal_execution_grant,
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
    real_media_revision = K2RealMediaRevisionService(
        shot_graph,
        evidence_repository,
        real_image_candidate_evidence,
        real_video_candidate_evidence,
        K2MediaCandidateReviewService(
            service,
            evidence_repository,
            clock=selected_clock,
            selection_authority=media_selection_approval_authority,
        ),
        ref_factory=selected_ref_factory,
        clock=selected_clock,
    )
    real_media_revision.state_projection = K2ProductionStateProjectionService(
        service,
        evidence_repository,
        real_media_revision.candidate_review,
        media.execution if hasattr(media.execution, "list_jobs") else None,
        real_media_revision,
    )
    return (
        service,
        authority_identity,
        production_policy,
        provider_experiments,
        shot_graph,
        assets,
        media,
        delivery,
        real_media_revision,
    )


def create_in_memory_boundary(
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    identity_reference_authority=None,
    rights_evidence_authority=None,
    provider_policy_authority=None,
    provider_experiment_execution=None,
    internal_execution_grant: K2InternalExecutionGrant | None = None,
    real_image_candidate_evidence=None,
    real_video_candidate_evidence=None,
    media_execution=None,
    composition_execution=None,
    approval_authority=None,
    media_selection_approval_authority=None,
    ref_factory=None,
    clock=None,
) -> EpisodeProductionPublicBoundary:
    (
        service,
        authority_identity,
        production_policy,
        provider_experiments,
        shot_graph,
        assets,
        media,
        delivery,
        real_media_revision,
    ) = _services(
        InMemoryEpisodeProductionAdapter(),
        InMemoryEpisodeProductionEvidenceAdapter(),
        InMemoryProductionPolicyAdapter(),
        InMemoryProviderExperimentAdapter(),
        project_boundary=project_boundary,
        series_episode_boundary=series_episode_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=script_studio_boundary,
        identity_reference_authority=identity_reference_authority,
        rights_evidence_authority=rights_evidence_authority,
        provider_policy_authority=provider_policy_authority,
        provider_experiment_execution=provider_experiment_execution,
        internal_execution_grant=internal_execution_grant,
        real_image_candidate_evidence=real_image_candidate_evidence,
        real_video_candidate_evidence=real_video_candidate_evidence,
        media_execution=media_execution,
        composition_execution=composition_execution,
        approval_authority=approval_authority,
        media_selection_approval_authority=media_selection_approval_authority,
        ref_factory=ref_factory,
        clock=clock,
    )
    return EpisodeProductionPublicBoundary(
        service,
        authority_identity,
        production_policy,
        provider_experiments,
        shot_graph,
        assets,
        media,
        delivery,
        real_media_revision,
    )


def create_local_development_boundary(
    database_path: Path | str,
    *,
    project_boundary,
    series_episode_boundary,
    series_planning_boundary,
    script_studio_boundary,
    evidence_database_path: Path | str | None = None,
    production_policy_database_path: Path | str | None = None,
    provider_experiment_database_path: Path | str | None = None,
    identity_reference_authority=None,
    rights_evidence_authority=None,
    provider_policy_authority=None,
    provider_experiment_execution=None,
    internal_execution_grant: K2InternalExecutionGrant | None = None,
    real_image_candidate_evidence=None,
    real_video_candidate_evidence=None,
    media_execution=None,
    composition_execution=None,
    approval_authority=None,
    media_selection_approval_authority=None,
    ref_factory=None,
    clock=None,
    initialize_if_missing: bool = True,
) -> EpisodeProductionPublicBoundary:
    evidence_path = (
        Path(evidence_database_path)
        if evidence_database_path is not None
        else Path(f"{database_path}.evidence.sqlite3")
    )
    production_policy_path = (
        Path(production_policy_database_path)
        if production_policy_database_path is not None
        else Path(f"{database_path}.production-policy.sqlite3")
    )
    provider_experiment_path = (
        Path(provider_experiment_database_path)
        if provider_experiment_database_path is not None
        else Path(f"{database_path}.provider-experiments.sqlite3")
    )
    (
        service,
        authority_identity,
        production_policy,
        provider_experiments,
        shot_graph,
        assets,
        media,
        delivery,
        real_media_revision,
    ) = _services(
        SqliteEpisodeProductionAdapter(
            database_path, initialize_if_missing=initialize_if_missing
        ),
        SqliteEpisodeProductionEvidenceAdapter(
            evidence_path, initialize_if_missing=initialize_if_missing
        ),
        SqliteProductionPolicyAdapter(
            production_policy_path, initialize_if_missing=initialize_if_missing
        ),
        SqliteProviderExperimentAdapter(
            provider_experiment_path,
            initialize_if_missing=initialize_if_missing,
        ),
        project_boundary=project_boundary,
        series_episode_boundary=series_episode_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=script_studio_boundary,
        identity_reference_authority=identity_reference_authority,
        rights_evidence_authority=rights_evidence_authority,
        provider_policy_authority=provider_policy_authority,
        provider_experiment_execution=provider_experiment_execution,
        internal_execution_grant=internal_execution_grant,
        real_image_candidate_evidence=real_image_candidate_evidence,
        real_video_candidate_evidence=real_video_candidate_evidence,
        media_execution=media_execution,
        composition_execution=composition_execution,
        approval_authority=approval_authority,
        media_selection_approval_authority=media_selection_approval_authority,
        ref_factory=ref_factory,
        clock=clock,
    )
    return EpisodeProductionPublicBoundary(
        service,
        authority_identity,
        production_policy,
        provider_experiments,
        shot_graph,
        assets,
        media,
        delivery,
        real_media_revision,
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
    rights_authority, provider_authority = external_authorities_from_environment(values)
    identity_reference_authority = (
        identity_reference_authority_from_environment(values)
    )
    approval_authority = delivery_approval_authority_from_environment(values)
    media_selection_approval_authority = (
        media_selection_approval_authority_from_environment(values)
    )
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
    production_policy_path = Path(
        str(values.get("CREATOR_PRODUCTION_POLICY_DATA_PATH", "")).strip()
        or f"{path}.production-policy.sqlite3"
    )
    provider_experiment_execution = None
    internal_provider_profile = None
    comfyui_configured = any(
        key.startswith("COMFYUI_") and str(value).strip()
        for key, value in values.items()
    )
    if comfyui_configured:
        provider_adapter = create_comfyui_wan22_adapter_from_environment(values)
        internal_provider_profile = {
            "providerId": provider_adapter.config.provider_id,
            "modelId": provider_adapter.config.model_id,
            "region": provider_adapter.config.region,
            "endpointClass": provider_adapter.config.endpoint_class,
            "runtimeAttestationRef": (
                provider_adapter.config.runtime_attestation_ref
            ),
            "runtimeAttestationDigest": (
                provider_adapter.config.runtime_attestation_digest
            ),
            "costCurrency": provider_adapter.config.cost_currency,
            "maxCostMinor": provider_adapter.config.cost_minor_per_attempt,
            "timeoutSeconds": int(
                provider_adapter.config.execution_timeout_seconds
            ),
        }
        provider_job_path = Path(
            str(
                values.get("CREATOR_PROVIDER_EXPERIMENT_JOB_DATA_PATH", "")
            ).strip()
            or f"{job_path}.provider-experiments.sqlite3"
        )
        provider_artifact_root = Path(
            str(
                values.get("CREATOR_PROVIDER_EXPERIMENT_ARTIFACT_ROOT", "")
            ).strip()
            or artifact_root / "provider-experiments"
        )
        provider_experiment_execution = MediaJobCoordinator(
            SqliteMediaJobAdapter(provider_job_path),
            provider_adapter,
            provider_artifact_root,
            ref_factory=lambda prefix: f"{prefix}-{uuid4().hex}",
            clock=_utc_now,
            max_attempts=1,
        )
    internal_execution_grant = internal_execution_grant_from_environment(
        values,
        provider_profile=internal_provider_profile,
    )
    real_image_candidate_evidence = (
        real_image_candidate_evidence_from_environment(values)
    )
    job_repository = SqliteMediaJobAdapter(job_path)
    execution = MediaJobCoordinator(
        job_repository,
        DeterministicLocalFfmpegAdapter(),
        artifact_root,
        ref_factory=lambda prefix: f"{prefix}-{uuid4().hex}",
        clock=_utc_now,
    )
    real_video_candidate_evidence = MediaJobRealVideoCandidateEvidence(
        job_repository,
        artifact_root,
    )
    return create_local_development_boundary(
        path,
        project_boundary=project_boundary,
        series_episode_boundary=series_episode_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=script_studio_boundary,
        production_policy_database_path=production_policy_path,
        identity_reference_authority=identity_reference_authority,
        rights_evidence_authority=rights_authority,
        provider_policy_authority=provider_authority,
        provider_experiment_execution=provider_experiment_execution,
        internal_execution_grant=internal_execution_grant,
        real_image_candidate_evidence=real_image_candidate_evidence,
        real_video_candidate_evidence=real_video_candidate_evidence,
        media_execution=execution,
        composition_execution=V4CompositionExecutor.from_artifact_root(artifact_root),
        approval_authority=approval_authority,
        media_selection_approval_authority=media_selection_approval_authority,
        initialize_if_missing=True,
    )
