"""SQLite lease executor: one connection and one BEGIN IMMEDIATE per lifecycle operation."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock, get_ident, local
from typing import Any, Callable, Iterator
from uuid import uuid4

from .contracts import AssemblyState, BackendKind, LeaseState, LifecycleAssemblyIdentity, LifecycleLeaseView, LifecycleOperation
from .errors import AssemblyPoisonedError, LeaseRejectedError, LifecycleRollbackError


class SqliteLifecycleState:
    def __init__(self, database_path: Path | str, *, transaction_hook=None) -> None:
        path = Path(database_path).resolve()
        self.database_path = path
        self.identity = LifecycleAssemblyIdentity(
            f"assembly-{uuid4().hex}", BackendKind.SQLITE_LOCAL, f"sqlite:{path}"
        )
        self._issuer_ref = f"issuer-{uuid4().hex}"
        self._lock = RLock()
        self._thread = local()
        self._active: dict[str, LifecycleLeaseView] = {}
        self._state = AssemblyState.READY
        self._last_failure = ""
        self._transaction_hook = transaction_hook or (lambda _operation: None)

    @property
    def state(self) -> AssemblyState:
        return self._state

    def assert_ready(self) -> None:
        if self._state is AssemblyState.POISONED:
            raise AssemblyPoisonedError()
        if self._state is not AssemblyState.READY:
            raise LeaseRejectedError("assembly is not ready")

    @contextmanager
    def read_snapshot(self):
        """Expose one SQLite snapshot connection for a coherent bounded read."""
        self._lock.acquire()
        connection = None
        try:
            self.assert_ready()
            if getattr(self._thread, "lease", None) is not None:
                raise LeaseRejectedError("nested lifecycle access is forbidden")
            try:
                connection = self._connect()
                # A coherent workspace projection spans several related tables.
                # IMMEDIATE prevents a rollback-journal writer from entering the
                # PENDING state between those SELECTs and deadlocking the reader.
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.DatabaseError as exc:
                if connection is not None:
                    connection.close()
                connection = None
                raise LeaseRejectedError("lifecycle read snapshot is unavailable") from exc
            self._thread.read_connection = connection
            try:
                yield
            finally:
                connection.rollback()
        finally:
            self._thread.read_connection = None
            if connection is not None:
                connection.close()
            self._lock.release()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise LeaseRejectedError("foreign key enforcement unavailable")
        return connection

    @contextmanager
    def lease(self, *, workspace_ref: str, operation: LifecycleOperation) -> Iterator[LifecycleLeaseView]:
        self._lock.acquire()
        connection = None
        lease = None
        try:
            self.assert_ready()
            if getattr(self._thread, "lease", None) is not None:
                raise LeaseRejectedError("nested lifecycle lease is forbidden")
            try:
                connection = self._connect()
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.DatabaseError as exc:
                if connection is not None:
                    connection.close()
                connection = None
                raise LeaseRejectedError("lifecycle write lease is unavailable") from exc
            self._transaction_hook(operation)
            lease = LifecycleLeaseView(
                self._issuer_ref, self.identity, uuid4().hex, get_ident(),
                str(workspace_ref), operation, LeaseState.ACTIVE,
            )
            self._thread.lease = lease
            self._thread.connection = connection
            self._active[lease.nonce] = lease
            try:
                yield lease
            except BaseException:
                try:
                    connection.rollback()
                except BaseException as rollback_error:
                    self._poison(rollback_error)
                    raise LifecycleRollbackError() from rollback_error
                raise
            else:
                try:
                    connection.commit()
                except BaseException as commit_error:
                    self._poison(commit_error)
                    raise LifecycleRollbackError("lifecycle commit outcome is uncertain") from commit_error
        finally:
            if lease is not None:
                self._active.pop(lease.nonce, None)
            self._thread.lease = None
            self._thread.connection = None
            if connection is not None:
                connection.close()
            self._lock.release()

    def _poison(self, error: BaseException) -> None:
        self._state = AssemblyState.POISONED
        self._last_failure = type(error).__name__

    def validate_lease(self, lease: object, *, workspace_ref: str, allowed_operations: frozenset[LifecycleOperation]) -> LifecycleLeaseView:
        if not isinstance(lease, LifecycleLeaseView):
            raise LeaseRejectedError("forged lifecycle lease")
        if self._active.get(lease.nonce) is not lease:
            raise LeaseRejectedError("expired or forged lifecycle lease")
        if lease.issuer_ref != self._issuer_ref or lease.assembly_identity != self.identity:
            raise LeaseRejectedError("cross-assembly lifecycle lease")
        if lease.owner_thread_id != get_ident():
            raise LeaseRejectedError("cross-thread lifecycle lease")
        if lease.workspace_ref != str(workspace_ref):
            raise LeaseRejectedError("cross-workspace lifecycle lease")
        if lease.operation not in allowed_operations or lease.state is not LeaseState.ACTIVE:
            raise LeaseRejectedError("operation is not allowed by lifecycle lease")
        self.assert_ready()
        return lease

    def connection_or_none(self) -> sqlite3.Connection | None:
        lease = getattr(self._thread, "lease", None)
        if lease is None:
            return None
        self.validate_lease(
            lease, workspace_ref=lease.workspace_ref, allowed_operations=frozenset(LifecycleOperation)
        )
        return getattr(self._thread, "connection", None)

    def read_connection_or_none(self) -> sqlite3.Connection | None:
        """Return a validated write lease connection or an active read snapshot."""
        connection = self.connection_or_none()
        if connection is not None:
            return connection
        return getattr(self._thread, "read_connection", None)

    def apply_mutation(self, lease: object, mutation: Callable[[], Any]) -> Any:
        self.validate_lease(
            lease,
            workspace_ref=getattr(lease, "workspace_ref", ""),
            allowed_operations=frozenset(LifecycleOperation),
        )
        return mutation()

    def diagnostic_snapshot(self) -> dict[str, Any]:
        return {
            "assemblyRef": self.identity.assembly_ref,
            "backendKind": self.identity.backend_kind.value,
            "storageIdentity": self.identity.storage_identity,
            "state": self._state.value,
            "activeLeaseCount": len(self._active),
            "lastFailure": self._last_failure,
        }
