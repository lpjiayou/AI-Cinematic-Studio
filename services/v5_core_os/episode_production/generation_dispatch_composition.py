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
        cost_reader, issuer_service_ref, revocation_reader=None):
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
    foundation = GenerationDispatchFoundation(repository=evidence, clock=clock, coordination=coordination,
        issuer_service_ref=issuer_service_ref, revocation_reader=revocation_reader,
        approval_reader=selections["approval"], source_reader=source, backend_reader=selections["backend"],
        runtime_reader=selections["runtime"], cost_reader=selections["cost"])
    preparation = GenerationDispatchPreparation(source_reader=source, repository=evidence, coordination=coordination)
    boundary = GenerationDispatchPublicBoundary(foundation, preparation=preparation)
    coordination.activate(required)
    routing = GenerationDispatchRouting(foundation=foundation, source_reader=source, coordinator=queue_coordinators[0])
    return GenerationDispatchAssembly(boundary, routing, source, coordination, selections, tuple(coverage))
