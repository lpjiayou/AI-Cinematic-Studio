"""Unassembled ADR-0022 issue/inspect/revoke domain service.

Only the existing evidence repository writes. All live source/coordination ports
remain unimplemented here; a default instance has no authority to issue records.
The transaction does not encompass another Owner store, V4 queue or transport.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import ContextManager, Mapping, Protocol

from . import generation_dispatch_contracts as c
from .generation_dispatch_authority import ApprovalReaderPort, RejectingApprovalReader, SelectedApproval
from .evidence import (EvidenceRecord, EpisodeProductionEvidenceRepository, GrantIssueValidityCheck,
    RecordAppendValidationRejected, RecordAppendOutcomeUnknown)
from .foundation import IdempotencyConflictError, StaleInputError


class TrustedClockPort(Protocol):
    def now(self) -> str:
        """Return trusted UTC per ADR 4.1, or raise; no implicit wall-clock fallback."""
        ...


@dataclass(frozen=True)
class _TrustedGrantIssueValidity:
    clock: TrustedClockPort
    created_at: datetime
    not_before: datetime
    expires_at: datetime
    last_observed_at: datetime

    def validate_before_commit(self) -> None:
        try:
            reading = self.clock.now()
        except Exception as exc:
            raise c.DispatchError("CURRENTNESS_FENCE_UNAVAILABLE") from exc
        now = c.utc(reading)
        c.require(self.created_at <= now and self.last_observed_at <= now
                  and self.not_before <= now < self.expires_at,
                  "OUTSIDE_VALIDITY_WINDOW")


class CoordinationLease(Protocol):
    epoch: str
    def assert_held(self) -> None:
        """Prove this workspace's full source/writer fence is held, or reject."""
        ...


class GenerationDispatchCoordinationPort(Protocol):
    def critical_section(self, workspace_ref: str) -> ContextManager[CoordinationLease]: ...


class CurrentSubjectPort(Protocol):
    def read_current(self, plan_package: dict, approval: dict, phase: str,
                     lease: CoordinationLease) -> dict:
        """Return the complete original-Owner-validated readSet.

        Validate Run upstreamSnapshot/upstreamDigest, all canonical objects and
        original digests, selection/currentness, exact source text, READY input
        chain, all five prerequisite originals and 16 selector dependencies.
        Client digests or a self-reported readSet cannot implement this port.
        """
        ...


@dataclass(frozen=True)
class BackendObservation:
    decision: dict
    profile: dict
    execution_config: dict
    execution_code: dict


class BackendConfigurationPort(Protocol):
    def read_current(self, plan_package: dict, lease: CoordinationLease) -> BackendObservation:
        """Original backend/config reader; validate paths, credentials binding,
        fixed code, complete launch environment and deadlines without activation."""
        ...


@dataclass(frozen=True)
class RuntimeObservation:
    process_identity: dict
    attestation_file_sha256: str
    attestation: dict


class RuntimeIdentityPort(Protocol):
    def read_current(self, plan_package: dict, lease: CoordinationLease) -> RuntimeObservation:
        """Original trusted runtime reader: actual process/port owner, model and
        input bytes, original v2 attestation and its separate file SHA pin."""
        ...


class CostEvidencePort(Protocol):
    def read_current(self, plan_package: dict, lease: CoordinationLease) -> dict:
        """Original cost Owner validates evidence, available bound and responsibility;
        returns the approved complete costBasis, not a boolean or an estimate."""
        ...


class GenerationDispatchFoundation:
    def __init__(self, *, repository: EpisodeProductionEvidenceRepository | None = None,
                 approval_reader: ApprovalReaderPort | None = None,
                 revocation_reader: ApprovalReaderPort | None = None,
                 source_reader: CurrentSubjectPort | None = None,
                 backend_reader: BackendConfigurationPort | None = None,
                 runtime_reader: RuntimeIdentityPort | None = None,
                 cost_reader: CostEvidencePort | None = None,
                 coordination: GenerationDispatchCoordinationPort | None = None,
                 clock: TrustedClockPort | None = None, issuer_service_ref: str | None = None):
        self.repository = repository
        self.approval_reader = approval_reader if approval_reader is not None else RejectingApprovalReader()
        self.revocation_reader = revocation_reader if revocation_reader is not None else RejectingApprovalReader()
        self.source_reader, self.backend_reader = source_reader, backend_reader
        self.runtime_reader, self.cost_reader = runtime_reader, cost_reader
        self.coordination, self.clock = coordination, clock
        self.issuer_service_ref = issuer_service_ref

    def _repository(self):
        c.require(self.repository is not None, "PERSISTENCE_UNAVAILABLE")
        return self.repository

    def _gate(self, workspace_ref):
        c.require(self.coordination is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
        return self.coordination.critical_section(workspace_ref)

    @contextmanager
    def _write_gate(self, workspace_ref, outcome):
        try:
            with self._gate(workspace_ref) as lease:
                yield lease
        except Exception as exc:
            if outcome["stored"]:
                raise c.CommitOutcomeUnknown() from exc
            raise

    def _now(self):
        c.require(self.clock is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
        value = self.clock.now()
        c.utc(value)
        return value

    @staticmethod
    def _held(lease):
        c.require(lease is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
        lease.assert_held()
        c.sha(lease.epoch)

    def _snapshot_tokens(self, workspace, run):
        repo = self._repository()
        return {"recordJournalHead": repo.record_journal_head(workspace, run),
            "workspaceRecordJournalHead": repo.workspace_record_journal_head(workspace),
            "evidenceRevisionToken": repo.read_snapshot(workspace, run).revisionToken}

    @staticmethod
    def _payload(record, kind, workspace, run):
        c.require(record is not None, "SCOPE_MISMATCH")
        c.require(record["recordKind"] == kind, "IDEMPOTENCY_CONFLICT")
        value = c.validate_grant(record["payload"]) if kind == "GenerationDispatchGrant" else c.validate_terminal(record["payload"])
        c.require(value["workspaceRef"] == workspace and value["productionRunRef"] == run, "SCOPE_MISMATCH")
        c.validate_record_envelope(EvidenceRecord(**{k: record[k] for k in EvidenceRecord.__dataclass_fields__}))
        return value

    def _grant(self, command):
        r = self._repository().get_record(command["workspaceRef"], command["productionRunRef"], command["generationDispatchGrantRef"], 1)
        return self._payload(r, "GenerationDispatchGrant", command["workspaceRef"], command["productionRunRef"])

    def _terminal(self, grant):
        record = self._repository().get_record(grant["workspaceRef"], grant["productionRunRef"], grant["generationDispatchGrantRef"] + ":terminal", 1)
        if record is None:
            return None
        value = self._payload(record, "GenerationDispatchGrantTerminal", grant["workspaceRef"], grant["productionRunRef"])
        c.require(value["generationDispatchGrantDigest"] == grant["payloadDigest"] and c.utc(value["createdAt"]) >= c.utc(grant["createdAt"]))
        if value["kind"] == "CONSUMPTION_COMMITTED":
            c.require(value["attemptBinding"]["workflowDigest"] == grant["executionBinding"]["workflowDigest"])
            plan = c.plan_from_grant(grant)
            read_set = value["attemptBinding"]["currentSubjectReadSet"]
            c.validate_read_set(read_set, expected_scope=plan["scope"], phase="CONSUME")
            c.validate_read_set_bindings(read_set, plan, grant["approval"])
            c.require(c.utc(grant["limits"]["notBefore"]) <= c.utc(value["createdAt"]) < c.utc(grant["limits"]["expiresAt"]))
        return value

    def _selected(self, decision_ref, *, revocation=False):
        reader = self.revocation_reader if revocation else self.approval_reader
        selected = reader.resolve(decision_ref)
        c.require(isinstance(selected, SelectedApproval), "APPROVAL_UNAVAILABLE")
        c.sha(selected.bundle_sha256)
        approval = c.validate_approval(selected.approval, revocation=revocation)
        c.require(approval["authorityDecisionRef"] == decision_ref, "APPROVAL_UNAVAILABLE")
        if revocation:
            c.require(selected.plan_package is None, "APPROVAL_UNAVAILABLE")
        else:
            package = c.validate_plan_package(selected.plan_package)
            c.validate_approval(approval, plan=package["plan"])
        return deepcopy(selected)

    @staticmethod
    def _matches_issue(command, plan, approval):
        s = plan["subject"]
        expected = {"workspaceRef": plan["scope"]["workspaceRef"], "productionRunRef": plan["scope"]["productionRunRef"],
            "methodAwareInputPlanVersionRef": s["methodAwareInputPlanVersion"]["ref"], "creativeShotVersionRef": s["creativeShotVersion"]["ref"],
            "beatRef": s["actionExecutionBeat"]["ref"], "inputAssetVersionRef": s["inputAsset"]["assetVersionRef"],
            "backendRef": plan["executionBinding"]["backendDecision"]["backendRef"], "expectedSubjectDigest": c.subject_digest(plan),
            "expectedApprovedPlanDigest": c.digest(plan), "authorityDecisionRef": approval["authorityDecisionRef"]}
        c.require(all(command[k] == expected[k] for k in ("workspaceRef", "productionRunRef")), "SCOPE_MISMATCH")
        c.require(all(command[k] == v for k, v in expected.items()), "APPROVAL_PLAN_MISMATCH")

    def _current(self, selected, lease, *, phase="ISSUE"):
        self._held(lease)
        package = selected.plan_package
        plan, materials = package["plan"], package["materials"]
        binding = plan["executionBinding"]
        for reader in (self.source_reader, self.backend_reader, self.runtime_reader, self.cost_reader):
            c.require(reader is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
        c.require(phase in {"ISSUE", "CONSUME", "SEND"})
        read_set = self.source_reader.read_current(deepcopy(package), deepcopy(selected.approval), phase, lease)
        read_set = c.validate_read_set(read_set, expected_scope=plan["scope"], phase=phase)
        c.validate_read_set_bindings(read_set, plan, selected.approval)
        c.require(read_set["coordinationEpoch"] == lease.epoch, "CURRENTNESS_FENCE_UNAVAILABLE")
        observed = self.backend_reader.read_current(deepcopy(package), lease)
        c.require(isinstance(observed, BackendObservation), "CONFIG_CHANGED")
        for actual, expected in ((observed.decision, binding["backendDecision"]), (observed.profile, materials["backendProfile"]),
            (observed.execution_config, materials["executionConfig"]), (observed.execution_code, binding["executionCode"])):
            c.require(c.canonical(actual) == c.canonical(expected), "CONFIG_CHANGED")
        runtime = self.runtime_reader.read_current(deepcopy(package), lease)
        c.require(isinstance(runtime, RuntimeObservation), "RUNTIME_CHANGED")
        c.require(c.canonical(runtime.process_identity) == c.canonical(materials["processIdentity"])
            and runtime.attestation_file_sha256 == binding["runtimeBinding"]["attestationFileSha256"], "RUNTIME_CHANGED")
        # Reuse the original pure attestation validator, never probe/start the adapter.
        from services.v4_platform.comfyui import validate_runtime_attestation
        from services.v4_platform.generation_dispatch_a14b_profile import A14B_PROFILE_SCHEMA
        from services.v4_platform.generation_dispatch_a14b_exact import EXACT_PROFILE_SCHEMA
        from services.v4_platform.comfyui_a14b_runtime import (
            A14B_CAPABILITY_MODE, validate_a14b_runtime_attestation,
        )
        a14b = materials["backendProfile"]["schemaVersion"] in {A14B_PROFILE_SCHEMA, EXACT_PROFILE_SCHEMA}
        try:
            facts = (validate_a14b_runtime_attestation(runtime.attestation,
                backend_profile=materials["backendProfile"],
                process_identity=materials["processIdentity"],
                execution_config=materials["executionConfig"])
                if a14b else validate_runtime_attestation(runtime.attestation))
        except Exception as exc:
            raise c.DispatchError("RUNTIME_CHANGED") from exc
        d = binding["backendDecision"]
        c.require(runtime.attestation.get("capabilityMode") ==
            (A14B_CAPABILITY_MODE if a14b else "IMAGE_TO_VIDEO") and runtime.attestation["attestationRef"] == d["runtimeAttestationRef"]
            and runtime.attestation["payloadDigest"] == d["runtimeAttestationDigest"]
            and c.canonical(facts["modelFiles"]) == c.canonical(materials["backendProfile"]["modelFiles"]), "RUNTIME_CHANGED")
        for key in ("providerId", "modelId", "region", "endpointClass"):
            c.require(facts[key] == d[key], "RUNTIME_CHANGED")
        c.require(max(d["resourceShape"]["minimumVramPerGpu"], d["resourceShape"]["minimumTotalVram"]) <= facts["vramTotalBytes"], "RUNTIME_CHANGED")
        cost = self.cost_reader.read_current(deepcopy(package), lease)
        c.require(c.canonical(cost) == c.canonical(materials["costBasis"]), "COST_BOUND_UNVERIFIED")
        self._held(lease)
        return read_set

    def _eligibility(self, grant, terminal=None, *, lease=None):
        terminal = terminal if terminal is not None else self._terminal(grant)
        if terminal is not None:
            return "REVOKED" if terminal["kind"] == "REVOKED" else "CONSUMED"
        if lease is None:
            try:
                with self._gate(grant["workspaceRef"]) as held:
                    return self._eligibility(grant, lease=held)
            except Exception:
                return "FENCE_UNAVAILABLE"
        try:
            self._held(lease)
            now = c.utc(self._now())
            if now < c.utc(grant["limits"]["notBefore"]):
                return "NOT_YET_VALID"
            if now >= c.utc(grant["limits"]["expiresAt"]):
                return "EXPIRED"
            selected = self._selected(grant["approval"]["authorityDecisionRef"])
            c.require(c.canonical(selected.approval) == c.canonical(grant["approval"])
                and selected.bundle_sha256 == grant["issuanceEvidence"]["approvalBundleSha256"], "APPROVAL_UNAVAILABLE")
            c.require(c.canonical(selected.plan_package["plan"]) == c.canonical(c.plan_from_grant(grant)), "APPROVAL_PLAN_MISMATCH")
            self._current(selected, lease)
            return "ELIGIBLE_FOR_CONSUMPTION"
        except c.DispatchError as exc:
            return {"APPROVAL_UNAVAILABLE": "APPROVAL_UNAVAILABLE", "APPROVAL_PLAN_MISMATCH": "APPROVAL_UNAVAILABLE",
                "CONFIG_CHANGED": "CONFIG_CHANGED", "RUNTIME_CHANGED": "CONFIG_CHANGED", "COST_BOUND_UNVERIFIED": "CONFIG_CHANGED",
                "CURRENTNESS_FENCE_UNAVAILABLE": "FENCE_UNAVAILABLE"}.get(exc.code, "SOURCE_CHANGED")
        except Exception:
            return "FENCE_UNAVAILABLE"

    def _append(self, record, snapshot_tokens, lease, *,
                grant_issue_validity: GrantIssueValidityCheck | None = None):
        """One append call. Read-only outcome inspection never retries the transaction."""
        repo = self._repository()
        self._held(lease)
        validity = {} if grant_issue_validity is None else {"grant_issue_validity": grant_issue_validity}
        try:
            rows, replayed = repo.append_records((record,), expected_record_journal_head=snapshot_tokens["recordJournalHead"],
                expected_workspace_record_journal_head=snapshot_tokens["workspaceRecordJournalHead"],
                expected_evidence_revision_token=snapshot_tokens["evidenceRevisionToken"], **validity)
        except RecordAppendOutcomeUnknown as exc:
            raise c.CommitOutcomeUnknown() from exc
        except RecordAppendValidationRejected as exc:
            # Only the adapter can acknowledge rollback/no publication. Do not
            # turn a known validity rejection into a generic persistence error.
            if isinstance(exc.reason, c.DispatchError):
                raise exc.reason from exc
            raise c.DispatchError("PERSISTENCE_UNAVAILABLE") from exc
        except StaleInputError as exc:
            raise c.DispatchError("SNAPSHOT_CHANGED") from exc
        except IdempotencyConflictError as exc:
            raise c.DispatchError("IDEMPOTENCY_CONFLICT") from exc
        except Exception as exc:
            # The original adapter does not expose a commit-phase exception type.
            # Zero writes is provable only if the old three-token snapshot and
            # absent idempotency row are independently observed under this gate.
            try:
                self._held(lease)
                absent = repo.get_record_by_idempotency_key(record.workspaceRef, record.productionRunRef, record.idempotencyKey) is None
                unchanged = self._snapshot_tokens(record.workspaceRef, record.productionRunRef) == snapshot_tokens
            except Exception:
                raise c.CommitOutcomeUnknown() from exc
            if absent and unchanged:
                raise c.DispatchError("PERSISTENCE_UNAVAILABLE") from exc
            raise c.CommitOutcomeUnknown() from exc
        try:
            c.require(type(replayed) is bool and len(rows) == 1)
            value = self._payload(rows[0], record.recordKind, record.workspaceRef, record.productionRunRef)
            c.require(rows[0]["requestDigest"] == record.requestDigest and rows[0]["recordRef"] == record.recordRef)
            return value, replayed
        except Exception as exc:
            raise c.CommitOutcomeUnknown() from exc

    def issue(self, command: Mapping) -> dict:
        command = c.validate_command("ISSUE", command)
        repo = self._repository()
        workspace, run = command["workspaceRef"], command["productionRunRef"]
        outcome = {"stored": False}
        with self._write_gate(workspace, outcome) as lease:
            self._held(lease)
            replay = repo.get_record_by_idempotency_key(workspace, run, command["idempotencyKey"])
            if replay is not None:
                grant = self._payload(replay, "GenerationDispatchGrant", workspace, run)
                c.require(c.issue_request_digest(command, grant["approval"]) == grant["issuanceEvidence"]["requestDigest"], "IDEMPOTENCY_CONFLICT")
                return self._issue_result(grant, True, self._eligibility(grant, lease=lease))
            selected = self._selected(command["authorityDecisionRef"])
            plan = selected.plan_package["plan"]
            self._matches_issue(command, plan, selected.approval)
            c.require(repo.get_record(workspace, run, c.grant_ref(plan), 1) is None, "GRANT_SUBJECT_ALREADY_RECORDED")
            c.require(self._snapshot_tokens(workspace, run) == command["snapshotTokens"], "SNAPSHOT_CHANGED")
            read_set = self._current(selected, lease)
            now = self._now()
            c.require(c.utc(selected.approval["decidedAt"]) <= c.utc(now)
                and c.utc(plan["limits"]["notBefore"]) <= c.utc(now) < c.utc(plan["limits"]["expiresAt"]), "OUTSIDE_VALIDITY_WINDOW")
            c.require(self.issuer_service_ref is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
            c.ref(self.issuer_service_ref)
            request_digest = c.issue_request_digest(command, selected.approval)
            grant = c.sealed({"schemaVersion": c.GRANT_SCHEMA, "generationDispatchGrantRef": c.grant_ref(plan), "version": 1,
                **plan["scope"], **{k: deepcopy(plan[k]) for k in ("subject", "executionBinding", "permissions", "limits")},
                "subjectDigest": c.subject_digest(plan), "approval": deepcopy(selected.approval), "issuanceEvidence": {
                    "issuerServiceRef": self.issuer_service_ref, "requestDigest": request_digest, "approvalBundleSha256": selected.bundle_sha256,
                    "snapshotTokens": deepcopy(command["snapshotTokens"]), "currentSubjectReadSet": read_set, "currentSubjectReadSetDigest": c.digest(read_set)},
                "publicationAllowed": False, "createdAt": now})
            c.validate_grant(grant)
            record = EvidenceRecord(workspace, run, "GenerationDispatchGrant", grant["generationDispatchGrantRef"], 1,
                command["idempotencyKey"], request_digest, now, grant, grant["payloadDigest"])
            before_transaction = c.utc(self._now())
            c.require(c.utc(now) <= before_transaction < c.utc(plan["limits"]["expiresAt"]), "OUTSIDE_VALIDITY_WINDOW")
            # The last validity decision occurs inside the adapter's first-write
            # critical section, after SQLite INSERT/read/decode and before commit.
            # It neither reseals createdAt nor claims an atomic physical commit.
            validity = _TrustedGrantIssueValidity(self.clock, c.utc(now),
                c.utc(grant["limits"]["notBefore"]), c.utc(grant["limits"]["expiresAt"]), before_transaction)
            stored, replayed = self._append(record, command["snapshotTokens"], lease,
                grant_issue_validity=validity)
            outcome["stored"] = not replayed
            return self._issue_result(stored, replayed, self._eligibility(stored, lease=lease))

    @staticmethod
    def _issue_result(grant, replayed, eligibility):
        return {"schemaVersion": c.PREFIX + "issue-result.v1", "operation": "ISSUE", "grant": deepcopy(grant),
            "recordReplay": replayed, "eligibility": eligibility, "sendPermission": "NONE"}

    def inspect(self, command: Mapping) -> dict:
        command = c.validate_command("INSPECT", command)
        if self.coordination is not None:
            try:
                with self._gate(command["workspaceRef"]) as lease:
                    self._held(lease)
                    grant = self._grant(command)
                    terminal = self._terminal(grant)
                    return self._inspect_result(grant, terminal, self._eligibility(grant, terminal, lease=lease))
            except c.DispatchError as exc:
                if exc.code != "CURRENTNESS_FENCE_UNAVAILABLE":
                    raise
        grant = self._grant(command)
        terminal = self._terminal(grant)
        eligibility = "FENCE_UNAVAILABLE" if terminal is None else ("REVOKED" if terminal["kind"] == "REVOKED" else "CONSUMED")
        return self._inspect_result(grant, terminal, eligibility)

    @staticmethod
    def _inspect_result(grant, terminal, eligibility):
        return {"schemaVersion": c.PREFIX + "inspect-result.v1", "operation": "INSPECT", "grant": deepcopy(grant),
            "terminal": deepcopy(terminal), "eligibility": eligibility, "sendPermission": "NONE"}

    def revoke(self, command: Mapping) -> dict:
        command = c.validate_command("REVOKE", command)
        repo = self._repository()
        workspace, run = command["workspaceRef"], command["productionRunRef"]
        outcome = {"stored": False}
        with self._write_gate(workspace, outcome) as lease:
            self._held(lease)
            grant = self._grant(command)
            c.require(command["generationDispatchGrantDigest"] == grant["payloadDigest"], "SCOPE_MISMATCH")
            terminal = self._terminal(grant)
            replay = repo.get_record_by_idempotency_key(workspace, run, command["idempotencyKey"])
            if terminal is not None and terminal["kind"] == "CONSUMPTION_COMMITTED":
                raise c.DispatchError("ALREADY_CONSUMED")
            if replay is not None:
                existing = self._payload(replay, "GenerationDispatchGrantTerminal", workspace, run)
                c.require(existing["kind"] == "REVOKED" and terminal is not None and existing == terminal, "IDEMPOTENCY_CONFLICT")
                c.require(c.revoke_request_digest(command, existing["revocationApproval"]) == existing["requestDigest"], "IDEMPOTENCY_CONFLICT")
                return self._revoke_result(existing, True)
            c.require(terminal is None, "ALREADY_REVOKED")
            selected = self._selected(command["authorityDecisionRef"], revocation=True)
            c.require(selected.approval["grantDigest"] == grant["payloadDigest"], "APPROVAL_PLAN_MISMATCH")
            c.require(self._snapshot_tokens(workspace, run) == command["snapshotTokens"], "SNAPSHOT_CHANGED")
            now = self._now()
            c.require(c.utc(now) >= max(c.utc(selected.approval["decidedAt"]), c.utc(grant["createdAt"])), "OUTSIDE_VALIDITY_WINDOW")
            request_digest = c.revoke_request_digest(command, selected.approval)
            terminal = c.sealed({"schemaVersion": c.TERMINAL_SCHEMA, "grantTerminalRef": grant["generationDispatchGrantRef"] + ":terminal",
                "generationDispatchGrantRef": grant["generationDispatchGrantRef"], "generationDispatchGrantDigest": grant["payloadDigest"],
                "workspaceRef": workspace, "productionRunRef": run, "kind": "REVOKED", "attemptBinding": None,
                "revocationApproval": deepcopy(selected.approval), "requestDigest": request_digest,
                "snapshotTokens": deepcopy(command["snapshotTokens"]), "createdAt": now})
            c.validate_terminal(terminal)
            record = EvidenceRecord(workspace, run, "GenerationDispatchGrantTerminal", terminal["grantTerminalRef"], 1,
                command["idempotencyKey"], request_digest, now, terminal, terminal["payloadDigest"])
            stored, replayed = self._append(record, command["snapshotTokens"], lease)
            outcome["stored"] = not replayed
            return self._revoke_result(stored, replayed)

    @staticmethod
    def _revoke_result(terminal, replayed):
        return {"schemaVersion": c.PREFIX + "revoke-result.v1", "operation": "REVOKE", "terminal": deepcopy(terminal),
            "recordReplay": replayed, "eligibility": "REVOKED", "sendPermission": "NONE"}
