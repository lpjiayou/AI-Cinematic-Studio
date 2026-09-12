"""Internal ADR-0022 Package 3 consume and one-shot send capability.

Nothing in this module is installed on the public episode-production boundary.
The continuation is intentionally an in-process object whose authority is held
only by a weak, private registry entry and is irrecoverable after loss/restart.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from threading import RLock, get_ident
from typing import Any, Mapping, Protocol
from weakref import WeakKeyDictionary

from . import generation_dispatch_contracts as c
from .evidence import EvidenceRecord


class WorkerExecutionContextPort(Protocol):
    def current(self) -> Mapping[str, Any]:
        """Return a trusted worker/process/thread observation or fail closed."""
        ...


@dataclass(frozen=True, slots=True)
class CurrentExecutionObservation:
    """V4's validated, internal view of the one active Attempt and lease."""

    job: dict[str, Any]
    lease_token: str
    stable_binding_digest: str

    def __post_init__(self) -> None:
        if type(self.job) is not dict or type(self.lease_token) is not str or not self.lease_token:
            raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
        c.sha(self.stable_binding_digest)
        object.__setattr__(self, "job", deepcopy(self.job))


class GenerationDispatchJobPort(Protocol):
    def read_current(self, command: Mapping[str, Any], grant: Mapping[str, Any],
                     worker_identity: Mapping[str, Any], now: str, lease: Any,
                     *, phase: str) -> CurrentExecutionObservation:
        """Read and validate the real V4 Job/Attempt/lease under the V5 gate."""
        ...


def validate_worker_identity(value: Any) -> dict[str, Any]:
    c.exact(value, {"workerRef", "workerProcessIdentityDigest", "processId", "threadId"})
    c.ref(value["workerRef"])
    c.sha(value["workerProcessIdentityDigest"])
    c.integer(value["processId"])
    c.integer(value["threadId"])
    return deepcopy(value)


def _v4_utc(value: Any) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED") from exc
    c.require(result.tzinfo is not None, "ATTEMPT_OR_LEASE_CHANGED")
    return result


@dataclass(slots=True)
class _CapabilityState:
    command: dict[str, Any]
    grant: dict[str, Any]
    terminal: dict[str, Any]
    worker_identity: dict[str, Any]
    observation: CurrentExecutionObservation
    l1_read_set: dict[str, Any]
    workflow: dict[str, Any]
    execution_config: dict[str, Any]
    execution_deadline_monotonic: float
    execution_deadline_utc: str
    invoked: bool = False
    spent: bool = False


_CAPABILITY_CONSTRUCTOR = object()


class SendCapability:
    """Opaque, non-copyable and non-serializable single-use continuation."""

    __slots__ = ("_consumer", "__weakref__")

    def __init__(self, constructor: object, consumer: "GenerationDispatchConsumer") -> None:
        if constructor is not _CAPABILITY_CONSTRUCTOR:
            raise TypeError("SendCapability cannot be constructed directly")
        object.__setattr__(self, "_consumer", consumer)

    def __copy__(self):
        raise TypeError("SendCapability cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("SendCapability cannot be deep-copied")

    def __reduce__(self):
        raise TypeError("SendCapability cannot be serialized")

    def __reduce_ex__(self, protocol):
        raise TypeError("SendCapability cannot be serialized")

    def __getstate__(self):
        raise TypeError("SendCapability cannot be serialized")

    def send_once(self, transport):
        return self._consumer._send_once(self, transport)

    @property
    def spent(self) -> bool:
        return self._consumer._capability_spent(self)


class GenerationDispatchConsumer:
    """Typed internal L1/L2 boundary; never exposed as HTTP, CLI or public DTO."""

    def __init__(self, *, foundation, job_port: GenerationDispatchJobPort,
                 worker_context: WorkerExecutionContextPort, clock):
        c.require(foundation is not None and job_port is not None
                  and worker_context is not None and clock is not None,
                  "CURRENTNESS_FENCE_UNAVAILABLE")
        c.require(clock is foundation.clock, "CURRENTNESS_FENCE_UNAVAILABLE")
        c.require(callable(getattr(clock, "now", None))
                  and callable(getattr(clock, "monotonic", None)),
                  "CURRENTNESS_FENCE_UNAVAILABLE")
        self._foundation = foundation
        self._job_port = job_port
        self._worker_context = worker_context
        self._clock = clock
        self._capability_lock = RLock()
        self._capabilities: WeakKeyDictionary[SendCapability, _CapabilityState] = WeakKeyDictionary()

    def snapshot_tokens(self, workspace_ref: str, production_run_ref: str) -> dict[str, Any]:
        c.ref(workspace_ref); c.ref(production_run_ref)
        with self._foundation._gate(workspace_ref) as lease:
            self._foundation._held(lease)
            return deepcopy(self._foundation._snapshot_tokens(workspace_ref, production_run_ref))

    @staticmethod
    def _same_plan(grant: Mapping[str, Any], selected) -> None:
        c.require(c.canonical(selected.approval) == c.canonical(grant["approval"])
            and selected.bundle_sha256 == grant["issuanceEvidence"]["approvalBundleSha256"],
            "APPROVAL_UNAVAILABLE")
        c.require(c.canonical(selected.plan_package["plan"])
            == c.canonical(c.plan_from_grant(dict(grant))), "APPROVAL_PLAN_MISMATCH")

    @staticmethod
    def _read_set_identity(value: Mapping[str, Any]) -> bytes:
        normalized = deepcopy(dict(value))
        normalized["phase"] = "CURRENTNESS_COMPARISON"
        return c.canonical(normalized)

    @staticmethod
    def _receipt(terminal: Mapping[str, Any], replayed: bool) -> dict[str, Any]:
        return c.validate_consume_receipt({"schemaVersion": c.PREFIX + "consume-result.v1",
            "operation": "CONSUME", "terminal": deepcopy(dict(terminal)),
            "recordReplay": replayed, "eligibility": "CONSUMED",
            "sendPermission": "NONE"})

    def _history_replay(self, command: Mapping[str, Any], grant: Mapping[str, Any],
                        terminal: Mapping[str, Any] | None):
        repo = self._foundation._repository()
        replay = repo.get_record_by_idempotency_key(command["workspaceRef"],
            command["productionRunRef"], command["idempotencyKey"])
        if replay is None:
            return None
        existing = self._foundation._payload(replay, "GenerationDispatchGrantTerminal",
            command["workspaceRef"], command["productionRunRef"])
        c.require(terminal is not None and existing == terminal
                  and existing["kind"] == "CONSUMPTION_COMMITTED",
                  "IDEMPOTENCY_CONFLICT")
        binding = existing["attemptBinding"]
        c.require(command["generationDispatchGrantDigest"] == grant["payloadDigest"]
            and command["mediaJobRef"] == binding["mediaJobRef"]
            and command["attemptRef"] == binding["attemptRef"]
            and command["workerRef"] == binding["workerRef"]
            and command["expectedLeaseTokenDigest"] == binding["leaseTokenDigest"]
            and c.consumption_request_digest(dict(command), grant["payloadDigest"], binding)
                == existing["requestDigest"], "IDEMPOTENCY_CONFLICT")
        return {"receipt": self._receipt(existing, True), "continuation": None}

    def consume(self, command: Mapping[str, Any]) -> dict[str, Any]:
        command = c.validate_command("CONSUME", command)
        identity = validate_worker_identity(self._worker_context.current())
        c.require(identity["workerRef"] == command["workerRef"], "ATTEMPT_OR_LEASE_CHANGED")
        outcome = {"stored": False}
        f = self._foundation
        with f._write_gate(command["workspaceRef"], outcome) as lease:
            f._held(lease)
            grant = f._grant(command)
            c.require(command["generationDispatchGrantDigest"] == grant["payloadDigest"],
                      "SCOPE_MISMATCH")
            terminal = f._terminal(grant)
            replay = self._history_replay(command, grant, terminal)
            if replay is not None:
                return replay
            if terminal is not None:
                raise c.DispatchError("ALREADY_REVOKED" if terminal["kind"] == "REVOKED"
                                      else "ALREADY_CONSUMED")
            now = f._now()
            selected = f._selected(grant["approval"]["authorityDecisionRef"])
            self._same_plan(grant, selected)
            before = self._job_port.read_current(command, grant, identity, now,
                lease, phase="CONSUME")
            read_set = f._current(selected, lease, phase="CONSUME")
            after_now = f._now()
            after = self._job_port.read_current(command, grant, identity, after_now,
                lease, phase="CONSUME")
            c.require(before.stable_binding_digest == after.stable_binding_digest
                and before.job["revision"] == after.job["revision"]
                and before.lease_token == after.lease_token,
                "ATTEMPT_OR_LEASE_CHANGED")
            c.require(f._snapshot_tokens(command["workspaceRef"], command["productionRunRef"])
                == command["snapshotTokens"], "SNAPSHOT_CHANGED")
            limits = grant["limits"]
            execution_seconds = limits["executionTimeoutSeconds"]
            deadline = c.utc(after_now) + timedelta(seconds=execution_seconds)
            c.require(c.utc(limits["notBefore"]) <= c.utc(after_now)
                and deadline <= c.utc(limits["expiresAt"]), "OUTSIDE_VALIDITY_WINDOW")
            config = selected.plan_package["materials"]["executionConfig"]
            request_seconds = (config["connectionTimeoutMs"] + config["requestTimeoutMs"]) / 1000.0
            c.require(_v4_utc(after.job["lease"]["expiresAt"])
                >= c.utc(after_now) + timedelta(seconds=request_seconds),
                "ATTEMPT_OR_LEASE_CHANGED")
            attempt = {"mediaJobRef": command["mediaJobRef"],
                "attemptRef": command["attemptRef"], "workerRef": command["workerRef"],
                "workerProcessIdentityDigest": identity["workerProcessIdentityDigest"],
                "jobRevision": after.job["revision"],
                "leaseTokenDigest": command["expectedLeaseTokenDigest"],
                "executionEnvelopeDigest": after.job["executionEnvelope"]["envelopeDigest"],
                "workflowDigest": grant["executionBinding"]["workflowDigest"],
                "currentSubjectReadSet": deepcopy(read_set),
                "currentSubjectReadSetDigest": c.digest(read_set)}
            request_digest = c.consumption_request_digest(command,
                grant["payloadDigest"], attempt)
            terminal = c.sealed({"schemaVersion": c.TERMINAL_SCHEMA,
                "grantTerminalRef": grant["generationDispatchGrantRef"] + ":terminal",
                "generationDispatchGrantRef": grant["generationDispatchGrantRef"],
                "generationDispatchGrantDigest": grant["payloadDigest"],
                "workspaceRef": command["workspaceRef"],
                "productionRunRef": command["productionRunRef"],
                "kind": "CONSUMPTION_COMMITTED", "attemptBinding": attempt,
                "revocationApproval": None, "requestDigest": request_digest,
                "snapshotTokens": deepcopy(command["snapshotTokens"]),
                "createdAt": after_now})
            c.validate_terminal(terminal)
            record = EvidenceRecord(command["workspaceRef"], command["productionRunRef"],
                "GenerationDispatchGrantTerminal", terminal["grantTerminalRef"], 1,
                command["idempotencyKey"], request_digest, after_now, terminal,
                terminal["payloadDigest"])
            stored, replayed = f._append(record, command["snapshotTokens"], lease)
            outcome["stored"] = not replayed
            if replayed:
                return {"receipt": self._receipt(stored, True), "continuation": None}
            capability = SendCapability(_CAPABILITY_CONSTRUCTOR, self)
            state = _CapabilityState(deepcopy(command), deepcopy(grant), deepcopy(stored),
                deepcopy(identity), after, deepcopy(read_set),
                deepcopy(selected.plan_package["materials"]["workflow"]), deepcopy(config),
                float(self._clock.monotonic()) + execution_seconds,
                deadline.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
            with self._capability_lock:
                self._capabilities[capability] = state
            return {"receipt": self._receipt(stored, False), "continuation": capability}

    def read_consumption_receipt(self, workspace_ref: str, production_run_ref: str,
                                 generation_dispatch_grant_ref: str) -> dict[str, Any] | None:
        """Read history only.  It can never reconstruct a continuation."""
        for value in (workspace_ref, production_run_ref, generation_dispatch_grant_ref):
            c.ref(value)
        command = {"workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "generationDispatchGrantRef": generation_dispatch_grant_ref}
        grant = self._foundation._grant(command)
        terminal = self._foundation._terminal(grant)
        if terminal is None or terminal["kind"] != "CONSUMPTION_COMMITTED":
            return None
        return {"receipt": self._receipt(terminal, True), "continuation": None}

    def _capability_spent(self, capability: SendCapability) -> bool:
        with self._capability_lock:
            state = self._capabilities.get(capability)
            return True if state is None else state.invoked or state.spent

    def _reserve_capability(self, capability: SendCapability) -> _CapabilityState:
        with self._capability_lock:
            state = self._capabilities.get(capability)
            if state is None or state.invoked:
                raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
            state.invoked = True
            return state

    def _send_once(self, capability: SendCapability, transport):
        state = self._reserve_capability(capability)
        if os.getpid() != state.worker_identity["processId"] or get_ident() != state.worker_identity["threadId"]:
            state.spent = True
            raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
        current_identity = validate_worker_identity(self._worker_context.current())
        if current_identity != state.worker_identity:
            state.spent = True
            raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
        from services.v4_platform.generation_dispatch_transport import (
            GenerationDispatchTransportError, make_transport_request,
            validate_transport_submission, validate_transport_result,
        )
        if (getattr(transport, "TEST_ONLY", None) is not True
                or getattr(transport, "CPU_ISOLATED", None) is not True):
            state.spent = True
            raise c.DispatchError("CONFIG_CHANGED")
        f = self._foundation
        submission = None
        exchange = None
        try:
            with f._gate(state.command["workspaceRef"]) as lease:
                state.spent = True
                f._held(lease)
                current_grant = f._grant(state.command)
                c.require(c.canonical(current_grant) == c.canonical(state.grant),
                          "SOURCE_CHANGED")
                current_terminal = f._terminal(current_grant)
                c.require(current_terminal is not None
                    and c.canonical(current_terminal) == c.canonical(state.terminal)
                    and current_terminal["kind"] == "CONSUMPTION_COMMITTED",
                    "ATTEMPT_OR_LEASE_CHANGED")
                selected = f._selected(state.grant["approval"]["authorityDecisionRef"])
                self._same_plan(state.grant, selected)
                read_set = f._current(selected, lease, phase="SEND")
                c.require(self._read_set_identity(read_set)
                    == self._read_set_identity(state.l1_read_set), "SOURCE_CHANGED")
                now = f._now()
                observation = self._job_port.read_current(state.command, state.grant,
                    state.worker_identity, now, lease, phase="SEND")
                c.require(observation.stable_binding_digest
                    == state.observation.stable_binding_digest
                    and observation.lease_token == state.observation.lease_token,
                    "ATTEMPT_OR_LEASE_CHANGED")
                config = selected.plan_package["materials"]["executionConfig"]
                c.require(c.canonical(config) == c.canonical(state.execution_config),
                          "CONFIG_CHANGED")
                remaining = state.execution_deadline_monotonic - float(self._clock.monotonic())
                request_seconds = (config["connectionTimeoutMs"] + config["requestTimeoutMs"]) / 1000.0
                wall_deadline = c.utc(state.execution_deadline_utc)
                c.require(remaining >= request_seconds
                    and c.utc(now) + timedelta(seconds=request_seconds) <= wall_deadline
                    and c.utc(now) + timedelta(seconds=request_seconds) <= c.utc(state.grant["limits"]["expiresAt"]),
                    "OUTSIDE_VALIDITY_WINDOW")
                c.require(_v4_utc(observation.job["lease"]["expiresAt"])
                    >= c.utc(now) + timedelta(seconds=request_seconds),
                    "ATTEMPT_OR_LEASE_CHANGED")
                envelope = observation.job["executionEnvelope"]
                request = observation.job["request"]
                transport_request = make_transport_request(
                    workspace_ref=state.command["workspaceRef"],
                    production_run_ref=state.command["productionRunRef"],
                    worker_ref=state.worker_identity["workerRef"],
                    generation_dispatch_grant_ref=state.grant["generationDispatchGrantRef"],
                    generation_dispatch_grant_digest=state.grant["payloadDigest"],
                    media_job_ref=observation.job["jobRef"],
                    attempt_ref=observation.job["attempts"][-1]["attemptRef"],
                    generation_request_ref=request["generationRequestRef"],
                    generation_request_digest=observation.job["requestDigest"],
                    execution_envelope_digest=envelope["envelopeDigest"],
                    workflow_digest=state.grant["executionBinding"]["workflowDigest"],
                    output_constraints=envelope["outputConstraints"],
                    workflow=state.workflow,
                    connection_timeout_ms=config["connectionTimeoutMs"],
                    request_timeout_ms=config["requestTimeoutMs"],
                    transport_policy=config["transportPolicy"])
                exchange = transport.open_exchange(transport_request)
                submission = validate_transport_submission(
                    transport.commit_request_once(exchange))
                if submission["requestDigest"] != transport_request["payloadDigest"]:
                    raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
            # Response waiting and result reads are deliberately outside the gate.
            result = transport.read_result(exchange, submission)
            receipt = validate_transport_result(result.receipt)
            if (result.submission != submission
                    or receipt["requestDigest"] != submission["requestDigest"]
                    or receipt["transportSubmissionRef"] != submission["transportSubmissionRef"]
                    or receipt["transportSubmissionDigest"] != submission["payloadDigest"]):
                raise GenerationDispatchTransportError("TRANSPORT_RESULT_BINDING_CHANGED",
                    "SUBMISSION_OUTCOME_UNKNOWN", request_committed=True,
                    submission=submission)
            return result
        except GenerationDispatchTransportError:
            raise
        except c.DispatchError:
            raise
        except Exception as exc:
            if submission is not None:
                raise GenerationDispatchTransportError("TRANSPORT_RESPONSE_UNAVAILABLE",
                    "SUBMISSION_OUTCOME_UNKNOWN", request_committed=True,
                    submission=submission) from exc
            raise GenerationDispatchTransportError("TRANSPORT_NOT_COMMITTED",
                "REQUEST_BYTES_NOT_COMMITTED", request_committed=False) from exc
