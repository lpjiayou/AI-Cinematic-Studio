"""Trusted internal D1 public orchestration. No default runtime, network or store.

The hosting composition supplies original Owner ports and original participants;
commands cannot choose an endpoint, approve content, or construct an observation.
An operator is bound to one prepare subject, then optionally one approved plan.
An unapproved selection permits only PREPARE; it cannot issue or execute.
"""
from copy import deepcopy
from dataclasses import dataclass
from contextlib import contextmanager

from . import generation_dispatch_contracts as c
from .generation_dispatch_composition import compose_generation_dispatch
from .generation_dispatch_consumption import GenerationDispatchConsumer


@dataclass(frozen=True)
class OperatorSelection:
    prepare_command: dict
    approved_plan_digest: str | None = None
    authority_decision_ref: str | None = None
    issue_idempotency_key: str | None = None
    route_idempotency_key: str | None = None

    def validate(self, *, require_approval=False):
        c.validate_command("PREPARE", self.prepare_command)
        values = (self.approved_plan_digest, self.authority_decision_ref,
            self.issue_idempotency_key, self.route_idempotency_key)
        if all(value is None for value in values):
            c.require(not require_approval, "APPROVAL_UNAVAILABLE")
            return
        # Partial approval configuration is never a pre-approval selection.
        c.require(all(value is not None for value in values), "APPROVAL_UNAVAILABLE")
        c.sha(self.approved_plan_digest)
        for value in (self.authority_decision_ref, self.issue_idempotency_key,
                self.route_idempotency_key):
            c.ref(value)


class GenerationDispatchOperator:
    """No scanning, daemon, automatic retry, or raw Grant/approval DTO input."""
    def __init__(self, *, assembly, coordinator, clock, worker_context,
            endpoint, selection, public_boundaries=None):
        selection.validate()
        self._selection = deepcopy(selection)
        self._assembly, self._coordinator = assembly, coordinator
        self._clock, self._worker, self._endpoint = clock, worker_context, endpoint
        self._public_boundaries = dict(public_boundaries or {})

    def public_boundaries(self):
        """Original host participants, not newly opened stores or private adapters."""
        c.require(bool(self._public_boundaries), "CURRENTNESS_FENCE_UNAVAILABLE")
        return dict(self._public_boundaries)

    def prepare(self):
        result = self._assembly.boundary.prepare(deepcopy(self._selection.prepare_command))
        if "planPackage" in result:
            self._require_live(result["planPackage"])
        return result

    @staticmethod
    def _require_live(package):
        from services.v4_platform.generation_dispatch_a14b_live import LIVE_PROFILE_SCHEMA
        c.require(package["materials"]["backendProfile"]["schemaVersion"] == LIVE_PROFILE_SCHEMA,
            "APPROVAL_UNAVAILABLE")
        return c.validate_plan_package(package)

    def _selected(self):
        self._selection.validate(require_approval=True)
        selected = self._assembly.selections["approval"].resolve(self._selection.authority_decision_ref)
        self._require_live(selected.plan_package)
        c.require(c.digest(selected.plan_package["plan"]) == self._selection.approved_plan_digest,
            "APPROVAL_PLAN_MISMATCH")
        plan = selected.plan_package["plan"]
        command = self._selection.prepare_command
        c.require(all(plan["scope"][k] == command[k] for k in ("workspaceRef", "productionRunRef")),
            "SCOPE_MISMATCH")
        subject = plan["subject"]
        c.require(subject["methodAwareInputPlanVersion"]["ref"] == command["methodAwareInputPlanVersionRef"]
            and subject["creativeShotVersion"]["ref"] == command["creativeShotVersionRef"]
            and subject["actionExecutionBeat"]["ref"] == command["beatRef"]
            and subject["inputAsset"]["assetVersionRef"] == command["inputAssetVersionRef"], "SCOPE_MISMATCH")
        return selected

    def inspect(self, grant_ref):
        self._selection.validate(require_approval=True)
        command = self._selection.prepare_command
        result = self._assembly.boundary.inspect({"workspaceRef": command["workspaceRef"],
            "productionRunRef": command["productionRunRef"], "generationDispatchGrantRef": c.ref(grant_ref)})
        if "grant" in result:
            c.require(result["grant"]["approval"]["approvedPlanDigest"] == self._selection.approved_plan_digest,
                "APPROVAL_PLAN_MISMATCH")
        return result

    def issue(self):
        """Explicit future authorized action; prepare/inspect never invoke it."""
        selected = self._selected()
        prepared = self.prepare()
        c.require("planPackage" in prepared, prepared.get("code", "APPROVAL_UNAVAILABLE"))
        c.require(c.canonical(prepared["planPackage"]) == c.canonical(selected.plan_package), "SOURCE_CHANGED")
        command = {k: v for k, v in self._selection.prepare_command.items()
            if k not in {"limits", "executionConfigRef", "costBasisRef"}}
        command.update(expectedSubjectDigest=prepared["subjectDigest"],
            expectedApprovedPlanDigest=self._selection.approved_plan_digest,
            authorityDecisionRef=self._selection.authority_decision_ref,
            idempotencyKey=self._selection.issue_idempotency_key, snapshotTokens=prepared["snapshotTokens"])
        return self._assembly.boundary.issue(command)

    def route(self, grant_ref):
        self._selected()
        inspected = self.inspect(grant_ref)
        c.require("grant" in inspected, inspected.get("code", "APPROVAL_UNAVAILABLE"))
        command = self._selection.prepare_command
        return self._assembly.routing.route_for_grant(command["workspaceRef"], command["productionRunRef"],
            grant_ref, idempotency_key=self._selection.route_idempotency_key)

    def replace_unconsumed_failure(self, predecessor_job_ref, *, revocation_decision_ref):
        """Explicit one-child replacement; does not route, claim or send.

        Two independently resolved Owner decisions are required: revoke the
        exact original Grant, and approve the exact repaired-code plan. The
        failed original Job/Attempt remains untouched. No replacement of v2.
        """
        selected = self._selected()
        plan = selected.plan_package["plan"]
        command = self._selection.prepare_command
        f = self._assembly.boundary._foundation
        with self._assembly.coordination.critical_section(command["workspaceRef"]) as lease:
            original = f._grant({**plan["scope"], "generationDispatchGrantRef": c.grant_ref(plan)})
            f._validate_replacement_selected(original, selected)
            c.require(f.failure_reader is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
            f.failure_reader.read_zero_send_failure(command["workspaceRef"], command["productionRunRef"],
                predecessor_job_ref, original, lease)
            terminal = f._terminal(original)
            if terminal is not None:
                c.require(terminal["kind"] == "REVOKED", "ALREADY_CONSUMED")
                c.require(terminal["revocationApproval"]["authorityDecisionRef"] == revocation_decision_ref,
                    "APPROVAL_UNAVAILABLE")
            else:
                f.revoke({"workspaceRef": command["workspaceRef"], "productionRunRef": command["productionRunRef"],
                    "generationDispatchGrantRef": original["generationDispatchGrantRef"],
                    "generationDispatchGrantDigest": original["payloadDigest"],
                    "authorityDecisionRef": c.ref(revocation_decision_ref),
                    "idempotencyKey": "replacement-revoke-" + c.digest(original["generationDispatchGrantRef"]),
                    "snapshotTokens": f._snapshot_tokens(command["workspaceRef"], command["productionRunRef"])})
            # Revocation may commit even if the following issue fails. That is
            # safe and preserved; an uncertain write must be inspected, not retried.
            prepared = self.prepare()
            c.require("planPackage" in prepared, prepared.get("code", "APPROVAL_UNAVAILABLE"))
            c.require(c.canonical(prepared["planPackage"]) == c.canonical(selected.plan_package), "SOURCE_CHANGED")
            issue = {k: v for k, v in command.items() if k not in {"limits", "executionConfigRef", "costBasisRef"}}
            issue.update(expectedSubjectDigest=prepared["subjectDigest"],
                expectedApprovedPlanDigest=self._selection.approved_plan_digest,
                authorityDecisionRef=self._selection.authority_decision_ref,
                idempotencyKey=self._selection.issue_idempotency_key,
                snapshotTokens=prepared["snapshotTokens"], predecessorJobRef=c.ref(predecessor_job_ref))
            return f.issue_replacement(issue)

    def _executor(self, media_job_ref):
        from services.v4_platform.generation_dispatch_execution import GenerationDispatchExecutor, MediaJobGenerationDispatchPort
        from services.v4_platform.generation_dispatch_live_result import GenerationDispatchLiveResultBoundary
        from services.v4_platform.comfyui_staged_transport import _bind_staged_transport
        selected = self._selected()
        command = self._selection.prepare_command
        job = self._coordinator.repository.get(command["workspaceRef"], command["productionRunRef"], c.ref(media_job_ref))
        c.require(job is not None, "ATTEMPT_OR_LEASE_CHANGED")
        c.require(job["dispatchGrantBinding"]["approvedPlanDigest"] == self._selection.approved_plan_digest,
            "APPROVAL_PLAN_MISMATCH")
        binding = selected.plan_package["plan"]["executionBinding"]
        transport = _bind_staged_transport(self._endpoint,
            execution_config=selected.plan_package["materials"]["executionConfig"],
            runtime_binding=binding["runtimeBinding"], backend_decision=binding["backendDecision"])
        job_port = MediaJobGenerationDispatchPort(coordinator=self._coordinator,
            coordination=self._assembly.coordination, clock=self._clock)
        consumer = GenerationDispatchConsumer(foundation=self._assembly.boundary._foundation,
            job_port=job_port, worker_context=self._worker, clock=self._clock)
        return GenerationDispatchExecutor.compose_live(coordinator=self._coordinator, consumer=consumer,
            worker_context=self._worker, transport=transport, clock=self._clock,
            coordination=self._assembly.coordination,
            result_boundary=GenerationDispatchLiveResultBoundary(self._coordinator, clock=self._clock), job_port=job_port)

    def execute_one(self, media_job_ref):
        command = self._selection.prepare_command
        return self._executor(media_job_ref).execute(command["workspaceRef"], command["productionRunRef"], media_job_ref)

    def read_job(self, media_job_ref):
        """Local durable read, including after expiry. Never constructs transport.

        The host selects the Job; a public caller cannot choose another Grant,
        plan, endpoint or worker. Reading completed work needs no live GPU.
        """
        from services.v4_platform.media_jobs import _validate_job
        self._selection.validate(require_approval=True)
        command = self._selection.prepare_command
        job = self._coordinator.repository.get(command["workspaceRef"],
            command["productionRunRef"], c.ref(media_job_ref))
        c.require(job is not None, "ATTEMPT_OR_LEASE_CHANGED")
        _validate_job(job)
        c.require(job["workspaceRef"] == command["workspaceRef"]
            and job["productionRunRef"] == command["productionRunRef"]
            and job["jobRef"] == media_job_ref, "SCOPE_MISMATCH")
        c.require(job.get("dispatchGrantBinding", {}).get("approvedPlanDigest")
            == self._selection.approved_plan_digest, "APPROVAL_PLAN_MISMATCH")
        request = job["request"]
        c.require(all(request[k] == command[k] for k in (
            "methodAwareInputPlanVersionRef", "creativeShotVersionRef", "beatRef")), "SCOPE_MISMATCH")
        return deepcopy(job)

    def read_job_content(self, media_job_ref):
        """Read the original verified artifact, never recover or ingest it."""
        from services.v4_platform.generation_dispatch_live_result import GenerationDispatchLiveResultBoundary
        job = self.read_job(media_job_ref)
        result = GenerationDispatchLiveResultBoundary(self._coordinator, clock=self._clock)
        return result.read_verified_content(job)

    def finalize_unconsumed_expired(self, media_job_ref):
        """Explicit trusted-host failure cleanup, never a retry or send command.

        The original read-only recover/HTTP/CLI contracts are unchanged. This
        cannot grant another Attempt, resurrect a lease or recover a capability.
        """
        command = self._selection.prepare_command
        return self._executor(media_job_ref).finalize_unconsumed_expired(
            command["workspaceRef"], command["productionRunRef"], media_job_ref)

    def recover(self, media_job_ref):
        """Original Job/Terminal and bounded GET recovery, never a new Attempt.

        UNKNOWN stays UNKNOWN in the journal. A recovered byte observation is
        explicitly not a successful durable Job or an admitted asset. No caller
        can supply a prompt ID or extend the original approval's deadline.
        """
        import time
        from services.v4_platform.generation_dispatch_a14b_live import request_for_original_job
        command = self._selection.prepare_command
        executor = self._executor(media_job_ref)
        result = executor.recover_read_only(command["workspaceRef"], command["productionRunRef"], media_job_ref)
        job = result["job"]
        dispatch = job.get("dispatchResult")
        if not dispatch or dispatch["outcome"] != "UNKNOWN" or dispatch.get("providerPromptId") is None:
            return result
        with self._assembly.coordination.critical_section(command["workspaceRef"]) as lease:
            selected = self._selected()
            now = c.utc(self._clock.now())
            limits = selected.plan_package["plan"]["limits"]
            c.require(c.utc(limits["notBefore"]) <= now < c.utc(limits["expiresAt"]), "OUTSIDE_VALIDITY_WINDOW")
            foundation = self._assembly.boundary._foundation
            # GET recovery checks the selected endpoint/process, not the SEND
            # prerequisite that the output prefix must still be absent.
            backend = foundation.backend_reader.read_current(selected.plan_package, lease)
            runtime = foundation.runtime_reader.read_current(selected.plan_package, lease)
            binding = selected.plan_package["plan"]["executionBinding"]
            c.require(c.canonical(backend.decision) == c.canonical(binding["backendDecision"])
                and c.canonical(backend.execution_config) == c.canonical(selected.plan_package["materials"]["executionConfig"]),
                "CONFIG_CHANGED")
            c.require(c.digest(runtime.process_identity) == binding["runtimeBinding"]["processIdentityDigest"]
                and runtime.attestation_file_sha256 == binding["runtimeBinding"]["attestationFileSha256"], "RUNTIME_CHANGED")
            current = executor.result_boundary.read_only(command["workspaceRef"], command["productionRunRef"], media_job_ref)
            c.require(current == job and len(job["attempts"]) == 1, "ATTEMPT_OR_LEASE_CHANGED")
            request = request_for_original_job(selected.plan_package, job)
            deadline = time.monotonic() + (c.utc(limits["expiresAt"]) - now).total_seconds()
        observed = executor.transport.recover_result_read_only(request, dispatch["providerPromptId"],
            deadline_monotonic=deadline)
        # JSON-facing result contains only evidence, never raw media bytes. The
        # original durable result/intent recovery remains the canonical writer.
        result["recoveryObservation"] = {k: v for k, v in observed.items() if k != "artifactBytes"}
        result["recoveryObservation"]["classification"] = "READ_ONLY_OBSERVATION_NOT_DURABLE_JOB_SUCCESS"
        return result


def compose_live_operator(*, selection, endpoint, worker_context, public_boundaries=None, **participants):
    """The only D1 assembly: enroll all original writers before exposing actions."""
    selection.validate()
    c.require(selection.prepare_command["workspaceRef"] == participants["workspace_ref"], "SCOPE_MISMATCH")
    assembly = compose_generation_dispatch(**participants)
    return GenerationDispatchOperator(assembly=assembly, coordinator=participants["queue_coordinators"][0],
        clock=participants["clock"], worker_context=worker_context, endpoint=endpoint, selection=selection,
        public_boundaries=public_boundaries)


class ExistingStoreOperatorDeployment:
    """Host-installed dependencies; never constructed from a CLI JSON document.

    Creation has no I/O. Explicit open uses the original existing-store factory;
    even prepare must not initialize a missing store. Hosting permission is not
    generation approval: every action still traverses the original Owner gates.
    """
    def __init__(self, **dependencies):
        self._dependencies = dict(dependencies)
        selection = dependencies.get("selection")
        c.require(type(selection) is OperatorSelection, "APPROVAL_UNAVAILABLE")
        selection.validate()
        self._dependencies["selection"] = deepcopy(selection)

    @contextmanager
    def open(self):
        from .generation_dispatch_composition import open_existing_live_operator
        operator, domain = open_existing_live_operator(**self._dependencies)
        try:
            yield operator
        finally:
            domain.close()
