"""Shared in-memory lease executor and pre-image rollback journal."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from threading import RLock, get_ident, local
from typing import Any, Callable, Iterator
from uuid import uuid4

from .contracts import (
    AssemblyState,
    LeaseState,
    LifecycleAssemblyIdentity,
    LifecycleLeaseView,
    LifecycleOperation,
)
from .errors import AssemblyPoisonedError, LeaseRejectedError, LifecycleRollbackError


class InMemoryLifecycleState:
    """One atomic state shared by all participants in an in-memory assembly."""

    def __init__(
        self,
        identity: LifecycleAssemblyIdentity,
        *,
        journal_registrar: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self.identity = identity
        self._issuer_ref = f"issuer-{uuid4().hex}"
        self._lock = RLock()
        self._thread = local()
        self._active: dict[str, LifecycleLeaseView] = {}
        self._resources: list[tuple[str, Callable[[], Any], Callable[[Any], None]]] = []
        self._state = AssemblyState.READY
        self._journal_registrar = journal_registrar or (lambda undo: None)
        self._last_failure = ""

    @property
    def state(self) -> AssemblyState:
        return self._state

    def register_resource(
        self,
        name: str,
        capture: Callable[[], Any],
        restore: Callable[[Any], None],
    ) -> None:
        if self._state is not AssemblyState.READY or self._active:
            raise LeaseRejectedError("resources must be registered before lifecycle use")
        if any(item[0] == name for item in self._resources):
            raise LeaseRejectedError("resource is already registered")
        self._resources.append((name, capture, restore))

    def assert_ready(self) -> None:
        if self._state is AssemblyState.POISONED:
            raise AssemblyPoisonedError()
        if self._state is not AssemblyState.READY:
            raise LeaseRejectedError("assembly is not ready")

    @contextmanager
    def read_snapshot(self):
        """Hold one coherent in-memory view for a multi-resource read."""
        self._lock.acquire()
        try:
            self.assert_ready()
            if getattr(self._thread, "lease", None) is not None:
                raise LeaseRejectedError("nested lifecycle access is forbidden")
            yield
        finally:
            self._lock.release()

    @contextmanager
    def lease(
        self,
        *,
        workspace_ref: str,
        operation: LifecycleOperation,
    ) -> Iterator[LifecycleLeaseView]:
        self._lock.acquire()
        try:
            # Re-check readiness only after the shared lock is owned. A waiter
            # that observed READY before another mutation poisoned the assembly
            # must never receive a new lease after that mutation releases it.
            self.assert_ready()
            if getattr(self._thread, "lease", None) is not None:
                raise LeaseRejectedError("nested lifecycle lease is forbidden")
            lease = LifecycleLeaseView(
                self._issuer_ref,
                self.identity,
                uuid4().hex,
                get_ident(),
                str(workspace_ref),
                operation,
                LeaseState.ACTIVE,
            )
            self._thread.lease = lease
            self._active[lease.nonce] = lease
            try:
                yield lease
            finally:
                self._active.pop(lease.nonce, None)
                self._thread.lease = None
        finally:
            self._lock.release()

    def validate_lease(
        self,
        lease: object,
        *,
        workspace_ref: str,
        allowed_operations: frozenset[LifecycleOperation],
    ) -> LifecycleLeaseView:
        if not isinstance(lease, LifecycleLeaseView):
            raise LeaseRejectedError("forged lifecycle lease")
        active = self._active.get(lease.nonce)
        if active is not lease:
            raise LeaseRejectedError("expired or forged lifecycle lease")
        if lease.issuer_ref != self._issuer_ref:
            raise LeaseRejectedError("lease issuer does not match")
        if lease.assembly_identity != self.identity:
            raise LeaseRejectedError("cross-assembly lifecycle lease")
        if lease.owner_thread_id != get_ident():
            raise LeaseRejectedError("cross-thread lifecycle lease")
        if lease.workspace_ref != str(workspace_ref):
            raise LeaseRejectedError("cross-workspace lifecycle lease")
        if lease.operation not in allowed_operations:
            raise LeaseRejectedError("operation is not allowed by lifecycle lease")
        if lease.state is not LeaseState.ACTIVE:
            raise LeaseRejectedError("terminal lifecycle lease")
        self.assert_ready()
        return lease

    def apply_preimaged(self, lease: object, mutation: Callable[[], Any]) -> Any:
        active = self.validate_lease(
            lease,
            workspace_ref=getattr(lease, "workspace_ref", ""),
            allowed_operations=frozenset(LifecycleOperation),
        )
        snapshots = [(name, restore, capture()) for name, capture, restore in self._resources]
        restored = False

        def undo() -> None:
            nonlocal restored
            if restored:
                return
            for _name, restore, snapshot in reversed(snapshots):
                restore(snapshot)
            restored = True

        # Registration precedes every mutation. A registration failure therefore
        # leaves every participant unchanged.
        self._journal_registrar(undo)
        try:
            result = mutation()
        except BaseException:
            try:
                undo()
            except BaseException as rollback_error:
                self._state = AssemblyState.POISONED
                self._last_failure = type(rollback_error).__name__
                self._active[active.nonce] = replace(active, state=LeaseState.POISONED)
                raise LifecycleRollbackError() from rollback_error
            self._active[active.nonce] = replace(active, state=LeaseState.ROLLED_BACK)
            raise
        self._active[active.nonce] = replace(active, state=LeaseState.COMMITTED)
        return result

    apply_mutation = apply_preimaged

    def diagnostic_snapshot(self) -> dict[str, Any]:
        return {
            "assemblyRef": self.identity.assembly_ref,
            "backendKind": self.identity.backend_kind.value,
            "storageIdentity": self.identity.storage_identity,
            "state": self._state.value,
            "activeLeaseCount": len(self._active),
            "registeredResources": [item[0] for item in self._resources],
            "lastFailure": self._last_failure,
        }
