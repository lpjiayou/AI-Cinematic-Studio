"""Explicit internal CPU/workset composition; never imported by app startup.

The closed enrollment below identifies the original storage participants. It is
not an Owner approval and does not create a persistence source or a transport.
"""
from __future__ import annotations

from dataclasses import dataclass

from services.v5_core_os.lifecycle_integrity.composition import LifecycleAssembly
from services.v5_core_os.lifecycle_integrity.generation_dispatch_coordination import (
    ControlledStorageDomain, GenerationDispatchCoordination, ControlledSourceSelection,
)
from services.v4_platform.media_jobs import MediaJobCoordinator, SqliteMediaJobAdapter
from . import generation_dispatch_contracts as c
from .generation_dispatch_foundation import GenerationDispatchFoundation
from .generation_dispatch_public import GenerationDispatchPublicBoundary
from .generation_dispatch_readers import GenerationDispatchOwnerReaders
from .generation_dispatch_preparation import GenerationDispatchPreparation
from .generation_dispatch_routing import GenerationDispatchRouting


CORE_SELECTORS = frozenset({
    "CURRENT_PROJECT", "CURRENT_SERIES", "CURRENT_EPISODE",
    "CURRENT_CONFIRMED_SERIES_PLAN", "CURRENT_EPISODE_PLAN_BINDING",
    "CURRENT_CONFIRMED_SCRIPT", "ACTIVE_M6_BINDING",
})
INPUT_KINDS = frozenset({"MethodAwareInputPlanVersion", "MethodAwareInputArtifact",
    "UserImageVideoInput",
    "MethodAwareInputAppendAuthority", "Candidate", "TechnicalValidation",
    "SemanticVisualQCDecision", "HumanSelectionDecision", "AssetAdmission", "AssetVersion"})


def _record_changes(args, kwargs):
    values = kwargs.get("records", args[0] if args else ())
    if not isinstance(values, (list, tuple)):
        values = (values,)
    result = set()
    for record in values:
        kind = getattr(record, "recordKind", None)
        if kind in INPUT_KINDS:
            result.add("CURRENT_INPUT_PLAN")
        if kind == "ConsistencyValidationVersion":
            result.add("CURRENT_M7_PASS")
        if kind == "ExecutionMethodPlanVersion":
            result.add("CURRENT_METHOD_PLAN")
    return result


def _records_and_gate_changes(args, kwargs):
    return _record_changes(args, kwargs) | {"CURRENT_IDENTITY_REFERENCE"}


@dataclass(frozen=True)
class GenerationDispatchAssembly:
    boundary: GenerationDispatchPublicBoundary
    routing: GenerationDispatchRouting
    source: GenerationDispatchOwnerReaders
    coordination: GenerationDispatchCoordination
    selections: dict
    coverage: tuple
    image_video: object = None


def _cleanup_failed_takeover(operation):
    from functools import wraps
    from threading import get_ident
    @wraps(operation)
    def call(*args, **kwargs):
        domain = kwargs.get("storage_domain")
        owns_takeover = (isinstance(domain, ControlledStorageDomain)
            and domain.state == "TAKEOVER" and domain._installer_thread == get_ident()
            and domain._coordination is None)
        try:
            return operation(*args, **kwargs)
        except BaseException:
            if owns_takeover:
                domain.close()
            raise
    return call


@_cleanup_failed_takeover
def compose_generation_dispatch(*, lifecycle, root_service, method_media,
        input_assets, policy_service, queue_coordinators, storage_domain,
        workspace_ref, technical_target_id, clock, approval_reader,
        prerequisite_reader, material_reader, backend_reader, runtime_reader,
        cost_reader, issuer_service_ref, revocation_reader=None, image_video_installation=None):
    """Enroll concrete original SQLite participants for one private workspace.

    External authority/configuration ports remain independent. None is read
    from environment variables. All queue adapters must be constructed before
    exclusive enrollment; a later unregistered adapter is refused on open.
    """
    c.require(isinstance(lifecycle, LifecycleAssembly)
        and isinstance(storage_domain, ControlledStorageDomain), "CURRENTNESS_FENCE_UNAVAILABLE")
    c.ref(workspace_ref)
    c.ref(issuer_service_ref)
    c.require(all(x is not None for x in (clock, approval_reader, prerequisite_reader,
        material_reader, backend_reader, runtime_reader, cost_reader, policy_service)),
        "CURRENTNESS_FENCE_UNAVAILABLE")
    c.require(root_service.project_reader is lifecycle.project_context
        and root_service.series_reader is lifecycle.series_episode
        and root_service.script_reader is lifecycle.script_studio
        and root_service.planning_reader is lifecycle.series_planning,
        "CURRENTNESS_FENCE_UNAVAILABLE")
    evidence = method_media.evidence_repository
    c.require(input_assets.evidence is evidence and policy_service.root_service is root_service,
        "CURRENTNESS_FENCE_UNAVAILABLE")
    c.require(queue_coordinators and all(type(q) is MediaJobCoordinator
        and type(q.repository) is SqliteMediaJobAdapter for q in queue_coordinators),
        "CURRENTNESS_FENCE_UNAVAILABLE")
    c.require(len({str(q.repository.path.resolve()) for q in queue_coordinators}) == 1,
        "CURRENTNESS_FENCE_UNAVAILABLE")
    coordination = GenerationDispatchCoordination(storage_domain=storage_domain)
    for attribute in ("project_reader", "series_reader", "script_reader", "planning_reader", "repository"):
        coordination.bind_dependency(root_service, attribute, getattr(root_service, attribute))
    for obj, attributes in ((method_media, ("execution_method_planning", "evidence_repository", "candidate_review")),
            (input_assets, ("planning", "evidence", "review")),
            (policy_service, ("repository", "root_service")),
            (lifecycle, ("state", "project_foundation_store", "coordinator"))):
        for attribute in attributes:
            coordination.bind_dependency(obj, attribute, getattr(obj, attribute))
    coverage = []
    required = []

    def enroll(owner, repo, writers, readers=(), selectors=()):
        c.require(type(repo).__module__.startswith("services.")
            and type(repo).__name__.startswith("Sqlite"), "CURRENTNESS_FENCE_UNAVAILABLE")
        before = len(coordination._bindings)
        coordination.bind_repository(repo, workspace_ref=workspace_ref,
            writers={name: selectors for name in writers} if not isinstance(writers, dict) else writers,
            readers=readers)
        for obj, name, _, _ in coordination._bindings[before:]:
            required.append((obj, name))
        coverage.append({"owner": owner, "adapter": type(repo).__module__ + "." + type(repo).__name__,
            "writers": list(writers), "readers": list(readers), "selectorKinds": sorted(selectors),
            "connectionGuard": hasattr(repo, "_connect"), "gate": "shared-workspace-gate"})

    before = len(coordination._bindings)
    coordination.bind_lifecycle(lifecycle.state, workspace_ref=workspace_ref, selector_kinds=CORE_SELECTORS)
    required.extend((obj, name) for obj, name, _, _ in coordination._bindings[before:])
    coverage.append({"owner": "LIFECYCLE_COMPOSITES", "writers": ["lease", "apply_mutation"],
        "participants": ["ProjectFoundation", "CanonicalRegistration", "M6", "ScriptGenerationRecovery"],
        "selectorKinds": sorted(CORE_SELECTORS), "gate": "outer-original-lifecycle-lease"})
    def service(boundary):
        attribute = "_" + type(boundary).__name__ + "__service"
        value = getattr(boundary, attribute)
        coordination.bind_dependency(boundary, attribute, value)
        coordination.bind_dependency(value, "repository", value.repository)
        return value
    enroll("V5_PROJECT_CONTEXT", service(lifecycle.project_context).repository,
        ("create_project", "archive_project"),
        ("get_project", "list_projects", "list_series_relationships", "get_project_for_series"),
        ("CURRENT_PROJECT",))
    enroll("V5_SERIES_EPISODE", service(lifecycle.series_episode).repository,
        ("create_series", "store_confirmed_plan", "create_episode_with_binding", "delete_episode", "delete_series"),
        ("get_series", "list_series", "get_confirmed_plan", "get_episode", "list_episodes", "get_plan_binding"),
        ("CURRENT_SERIES", "CURRENT_EPISODE"))
    enroll("V5_SERIES_PLANNING", service(lifecycle.series_planning).repository,
        ("create_plan_with_version", "append_version", "confirm_version"),
        ("get_plan", "get_plan_by_ref", "get_version", "list_versions", "lifecycle_has_episode_binding_dependency"),
        ("CURRENT_CONFIRMED_SERIES_PLAN", "CURRENT_EPISODE_PLAN_BINDING"))
    enroll("V5_SCRIPT", service(lifecycle.script_studio).repository,
        ("create_script_with_version", "append_version", "confirm_version", "accept_reviewed_import"),
        ("get_script", "get_script_by_ref", "get_version", "list_versions", "get_acceptance",
         "get_acceptance_by_idempotency_key", "lifecycle_has_episode_dependency", "lifecycle_has_series_dependency"),
        ("CURRENT_CONFIRMED_SCRIPT",))
    m6 = service(lifecycle.series_intelligence).repository
    enroll("V5_M6", m6, ("record_operation", "append_event"),
        ("replay", "list_outbox", "list_bible_versions", "list_character_versions", "list_snapshots",
         "lifecycle_has_series_dependency", "diagnostic"), ("ACTIVE_M6_BINDING",))
    # M6 mapping writes use _write_connection, which requires the original
    # lifecycle lease. They cannot commit independently of that outer observer.
    enroll("CANONICAL_REGISTRATION", service(lifecycle.canonical_registration).repository,
        ("create",), ("get_by_registration_key", "get_by_idempotency_key", "list_target_bindings"), CORE_SELECTORS)
    enroll("PROJECT_FOUNDATION", lifecycle.project_foundation_store,
        ("reserve", "complete"), ("get_by_key", "get_by_ref", "count"), CORE_SELECTORS)
    recovery = lifecycle.script_studio._ScriptStudioPublicBoundary__generation_recovery
    c.require(recovery is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
    enroll("SCRIPT_GENERATION_RECOVERY", recovery.store, ("save",), ("get", "pending"),
        ("CURRENT_CONFIRMED_SCRIPT",))
    enroll("RUN_JOURNAL", root_service.repository, ("create",), ("get", "get_by_idempotency", "list"))
    enroll("V5_EPISODE_PRODUCTION", evidence,
        {"append_record": _record_changes, "append_records": _record_changes,
         "append_records_and_gate": _records_and_gate_changes, "append_gate": ("CURRENT_IDENTITY_REFERENCE",)},
        ("list_workspace_records", "get_record_by_idempotency_key", "current_state", "get_gate", "list_gates",
         "get_record", "list_records", "record_journal_head", "workspace_record_journal_head", "read_snapshot"))
    enroll("V5_RIGHTS_PROVIDER", policy_service.repository, ("create",), ("get",),
        ("CURRENT_RIGHTS_EVALUATION", "CURRENT_PROVIDER_POLICY"))
    for q in queue_coordinators:
        coordination.bind_dependency(q, "repository", q.repository)
        enroll("V4_ORIGINAL_QUEUE", q.repository, ("create", "reserve_batch", "save"),
            ("get", "list"))
    c.require({path for _, _, path in coordination._storage_bindings} == set(storage_domain.paths),
        "CURRENTNESS_FENCE_UNAVAILABLE")

    image_video = None
    if image_video_installation is not None:
        from .image_video import ImageVideoRuntime, ImageVideoPort
        c.require(image_video_installation.policy["scope"]["workspaceRef"] == workspace_ref, "SCOPE_MISMATCH")
        image_video = ImageVideoRuntime(image_video_installation, evidence=evidence,
            root=root_service, coordination=coordination, clock=clock)
        approval_reader = ImageVideoPort(approval_reader, image_video, "approval")
        material_reader = ImageVideoPort(material_reader, image_video, "materials")
        backend_reader = ImageVideoPort(backend_reader, image_video, "backend")
        runtime_reader = ImageVideoPort(runtime_reader, image_video, "runtime")
        cost_reader = ImageVideoPort(cost_reader, image_video, "cost")
    ports = {"approval": (approval_reader, ("CURRENT_OWNER_APPROVAL",)),
        "prerequisites": (prerequisite_reader, ("CURRENT_IDENTITY_REFERENCE", "CURRENT_RIGHTS_EVALUATION",
            "CURRENT_PROVIDER_POLICY", "CURRENT_CONFIRMED_SCRIPT")),
        "materials": (material_reader, ("CURRENT_BACKEND_CONFIG", "CURRENT_RUNTIME_PROCESS")),
        "backend": (backend_reader, ("CURRENT_BACKEND_CONFIG",)),
        "runtime": (runtime_reader, ("CURRENT_RUNTIME_PROCESS",)),
        "cost": (cost_reader, ("CURRENT_BACKEND_CONFIG",))}
    selections = {}
    for key, (port, selectors) in ports.items():
        selection = ControlledSourceSelection(port, coordination=coordination,
            workspace_ref=workspace_ref, selector_kinds=selectors)
        selections[key] = selection
        required.append((selection, "select_port"))
    source = GenerationDispatchOwnerReaders(root_service=root_service, method_media=method_media,
        input_assets=input_assets, coordination=coordination, technical_target_id=technical_target_id,
        prerequisite_reader=selections["prerequisites"], material_reader=selections["materials"])
    if image_video is not None:
        from .image_video import ImageVideoSource
        source = ImageVideoSource(source, image_video)
    from services.v4_platform.generation_dispatch_execution import MediaJobGenerationDispatchPort
    failure_reader = MediaJobGenerationDispatchPort(coordinator=queue_coordinators[0],
        coordination=coordination, clock=clock)
    foundation = GenerationDispatchFoundation(repository=evidence, clock=clock, coordination=coordination,
        issuer_service_ref=issuer_service_ref, revocation_reader=revocation_reader,
        approval_reader=selections["approval"], source_reader=source, backend_reader=selections["backend"],
        runtime_reader=selections["runtime"], cost_reader=selections["cost"], failure_reader=failure_reader)
    preparation = GenerationDispatchPreparation(source_reader=source, repository=evidence, coordination=coordination)
    boundary = GenerationDispatchPublicBoundary(foundation, preparation=preparation)
    coordination.activate(required)
    routing = GenerationDispatchRouting(foundation=foundation, source_reader=source, coordinator=queue_coordinators[0])
    return GenerationDispatchAssembly(boundary, routing, source, coordination, selections, tuple(coverage), image_video)


def open_existing_live_operator(*, storage_root, lifecycle_path, run_path, queue_path,
        artifact_root, lifecycle_authorities, episode_authorities, selection,
        endpoint, technical_target_id, clock, worker_context, approval_reader,
        prerequisite_reader, material_reader, backend_reader, runtime_reader,
        cost_reader, issuer_service_ref, production_policy_database_path=None, revocation_reader=None,
        image_video_installation=None):
    """Explicit hosting seam. Validate/open existing stores, never bootstrap.

    This function is called only after independent deployment authorization.
    Construction of the CLI/host description does not call it. The usual Creator
    environment factory (which may initialize optional stores) is not used.
    An explicit policy path binds the original store without renaming facts;
    omission preserves the original sibling-path convention.
    """
    from pathlib import Path
    from uuid import uuid4
    from .public import create_local_development_boundary
    from .generation_dispatch_operator import compose_live_operator

    lifecycle_keys = {"m6_scope_authority", "m6_approval_authority", "m6_identity_authority",
        "script_acceptance_authority", "canonical_target_ref"}
    episode_keys = {"identity_reference_authority", "identity_reference_current_reader",
        "rights_evidence_authority", "provider_policy_authority", "media_selection_approval_authority",
        "method_aware_input_artifact_evidence", "method_aware_input_append_authority"}
    c.require(set(lifecycle_authorities) == lifecycle_keys and set(episode_authorities) == episode_keys,
        "CURRENTNESS_FENCE_UNAVAILABLE")
    root = Path(storage_root)
    c.require(root.is_absolute() and root.is_dir() and not root.is_symlink(), "PERSISTENCE_UNAVAILABLE")
    lifecycle_path, run_path, queue_path = map(Path, (lifecycle_path, run_path, queue_path))
    policy_path = (Path(production_policy_database_path) if production_policy_database_path is not None
        else Path(str(run_path) + ".production-policy.sqlite3"))
    owned_paths = [lifecycle_path, run_path, Path(str(run_path) + ".evidence.sqlite3"),
        policy_path, queue_path]
    # Optional existing service adapters are opened by the original public
    # factory, but have no D1 consumer. Still require them present: no implicit DDL.
    required_paths = owned_paths + [Path(str(run_path) + suffix)
        for suffix in (".provider-experiments.sqlite3", ".voice-locks.sqlite3")]
    for path in required_paths:
        c.require(path.is_absolute() and path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve()), "PERSISTENCE_UNAVAILABLE")
    c.require(len(set(p.resolve() for p in required_paths)) == len(required_paths), "PERSISTENCE_UNAVAILABLE")
    c.require(Path(artifact_root).is_absolute() and Path(artifact_root).is_dir()
        and not Path(artifact_root).is_symlink(), "PERSISTENCE_UNAVAILABLE")
    lifecycle = LifecycleAssembly.sqlite(lifecycle_path, initialize_or_upgrade=False,
        existing_only=True, **lifecycle_authorities)
    queue = SqliteMediaJobAdapter(queue_path, initialize_if_missing=False)

    class NoOrdinaryGenerate:
        def generate(self, *args, **kwargs):
            raise c.DispatchError("APPROVAL_UNAVAILABLE")

    coordinator = MediaJobCoordinator(queue, NoOrdinaryGenerate(), artifact_root=artifact_root,
        ref_factory=lambda prefix: prefix + "-" + uuid4().hex, clock=clock.now, max_attempts=1)
    boundary = create_local_development_boundary(run_path,
        project_boundary=lifecycle.project_context, series_episode_boundary=lifecycle.series_episode,
        series_planning_boundary=lifecycle.series_planning, script_studio_boundary=lifecycle.script_studio,
        production_policy_database_path=policy_path, initialize_if_missing=False, **episode_authorities)
    domain = ControlledStorageDomain(root, owned_paths)
    try:
        operator = compose_live_operator(selection=selection, endpoint=endpoint, worker_context=worker_context,
            public_boundaries={"series_episode_boundary": lifecycle.series_episode,
                "project_boundary": lifecycle.project_context, "series_planning_boundary": lifecycle.series_planning,
                "script_studio_boundary": lifecycle.script_studio, "series_intelligence_boundary": lifecycle.series_intelligence,
                "episode_production_boundary": boundary},
            lifecycle=lifecycle, root_service=boundary._EpisodeProductionPublicBoundary__service,
            method_media=boundary._EpisodeProductionPublicBoundary__method_aware_media,
            input_assets=boundary._EpisodeProductionPublicBoundary__method_aware_input_assets,
            policy_service=boundary._EpisodeProductionPublicBoundary__production_policy,
            queue_coordinators=[coordinator], storage_domain=domain,
            workspace_ref=selection.prepare_command["workspaceRef"], technical_target_id=technical_target_id,
            clock=clock, approval_reader=approval_reader, prerequisite_reader=prerequisite_reader,
            material_reader=material_reader, backend_reader=backend_reader, runtime_reader=runtime_reader,
            cost_reader=cost_reader, issuer_service_ref=issuer_service_ref, revocation_reader=revocation_reader,
            image_video_installation=image_video_installation)
    except BaseException:
        domain.close()
        raise
    return operator, domain
