"""Explicit single-process coordination over existing Owner storage ports.

No production facts or authorization decisions are stored here. Enrollment wraps
the actual repository write methods and the lifecycle transaction, not public
projections. The original methods and SQLite operations remain the persistence
implementation. This mode must be composed explicitly over a private workset.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import fcntl
from functools import wraps
from hashlib import sha256
import os
from pathlib import Path
import stat
from threading import RLock, get_ident, local
from uuid import uuid4


def _unavailable():
    # Lazy import preserves the existing V5 -> V4 dependency initialization.
    from services.v5_core_os.episode_production.generation_dispatch_contracts import DispatchError
    raise DispatchError("CURRENTNESS_FENCE_UNAVAILABLE")


class _ControlledAccessPermit:
    def __init__(self, domain, owner):
        self.domain, self.owner = domain, owner
        self.closed = False

    def check(self):
        if self.closed:
            _unavailable()
        self.domain._coordination._check_access_owner(self.owner)

    def unknown(self):
        self.domain.mark_unknown()

    def close(self):
        self.closed = True


class ControlledStorageDomain:
    """Sorted exclusive leases after ordinary connections/locks have drained.

    Lease files persist. Cooperative ordinary access acquires SH before original
    locks or SQLite open, even when the sidecar did not previously exist.
    """
    def __init__(self, root, database_paths):
        from services.v4_platform.generation_dispatch_jobs import storage_lock_open, _STORAGE_MUTEX, storage_access_snapshot
        self._mutex = _STORAGE_MUTEX
        self._locks, self._registrations, self._installations = [], [], []
        self._uncertain_lock_closes = []
        self._closed = False
        self._closing = False
        self._uncertain = False
        self._entries = 0
        self._coordination = None
        self._installer_thread = get_ident()
        self._pid = os.getpid()
        self.state = "ACQUIRING"
        self.events = []
        self.paths = ()
        raw = Path(root)
        if not raw.is_absolute() or raw.is_symlink():
            _unavailable()
        self.root = raw.resolve(strict=True)
        info = self.root.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            _unavailable()
        filesystem, longest = None, -1
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            left, right = line.split(" - ", 1)
            mount = Path(left.split()[4].replace("\\040", " "))
            if self.root.is_relative_to(mount) and len(str(mount)) > longest:
                filesystem, longest = right.split()[0], len(str(mount))
        if filesystem not in {"ext4", "xfs", "btrfs", "tmpfs", "overlay", "zfs"}:
            _unavailable()
        raw_paths = tuple(Path(p) for p in database_paths)
        if any(not p.is_absolute() or p.is_symlink() for p in raw_paths):
            _unavailable()
        self.paths = tuple(sorted(p.resolve(strict=True) for p in raw_paths))
        if not self.paths or len(set(self.paths)) != len(self.paths):
            _unavailable()
        try:
            with self._mutex:
                for path in self.paths:
                    if not path.is_relative_to(self.root) or not path.is_file() or path.is_symlink():
                        _unavailable()
                    s = path.stat()
                    if s.st_uid != os.geteuid() or s.st_mode & 0o022 or s.st_nlink != 1:
                        _unavailable()
                    self._locks.append(storage_lock_open(path, exclusive=True))
                    if storage_access_snapshot(path)["activeAccesses"]:
                        _unavailable()
                    self.events.append({"phase": "EXCLUSIVE_ACQUIRED", "path": str(path)})
                self._stamp = self._observe()
                self.state = "TAKEOVER"
                self.events.append({"phase": "DRAIN_CONFIRMED", "paths": len(self.paths)})
        except BaseException:
            self.close()
            raise

    def _observe(self):
        observations = []
        for path in self.paths:
            if not path.exists():
                _unavailable()
            for item in (path, Path(str(path) + "-wal"), Path(str(path) + "-journal")):
                if item.exists():
                    if item.is_symlink() or not item.resolve().is_relative_to(self.root):
                        _unavailable()
                    s = item.stat()
                    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.geteuid():
                        _unavailable()
                    observations.append((str(item), s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns))
        return tuple(observations)

    def assert_exclusive(self, *, compare_files=True):
        if self._closed or self._uncertain or os.getpid() != self._pid:
            _unavailable()
        for path, fd, identity in self._locks:
            current, opened = path.lstat(), os.fstat(fd)
            if path.is_symlink() or (current.st_dev, current.st_ino) != identity or (opened.st_dev, opened.st_ino) != identity:
                self.mark_unknown()
                _unavailable()
        if compare_files and self._observe() != self._stamp:
            self.mark_unknown()
            _unavailable()

    def mark_unknown(self):
        with self._mutex:
            self._uncertain = True
            if self._coordination is not None and self._coordination._workspace_ref is not None:
                self._coordination._poisoned.add(self._coordination._workspace_ref)
            self.events.append({"phase": "POISONED"})

    def accept_transaction_boundary(self, path):
        """Only the real SQLite observer calls this after a known boundary."""
        self.assert_exclusive(compare_files=False)
        observed = self._observe()
        names = {str(path), str(path) + "-wal", str(path) + "-journal"}
        if ([x for x in observed if x[0] not in names] != [x for x in self._stamp if x[0] not in names]
                or [(x[0], x[1], x[2]) for x in observed if x[0] == str(path)]
                != [(x[0], x[1], x[2]) for x in self._stamp if x[0] == str(path)]):
            self.mark_unknown()
            _unavailable()
        self._stamp = observed

    def acknowledge_controlled_operations(self):
        # End-of-gate and activate may verify a baseline, never reset it.
        self.assert_exclusive()

    def begin_entry(self, coordination):
        with self._mutex:
            if (self._closing or self.state != "ACTIVE" or self._coordination is not coordination):
                _unavailable()
            self.assert_exclusive(compare_files=False)
            self._entries += 1

    def end_entry(self):
        with self._mutex:
            self._entries -= 1

    def assert_installing(self):
        if (self.state != "TAKEOVER" or self._closing or get_ident() != self._installer_thread):
            _unavailable()
        self.assert_exclusive()

    def snapshot(self):
        from services.v4_platform.generation_dispatch_jobs import storage_access_snapshot
        with self._mutex:
            return {"state": self.state, "closing": self._closing, "uncertain": self._uncertain,
                "activeEntries": self._entries, "paths": {str(p): storage_access_snapshot(p) for p in self.paths},
                "ownedLockCount": len(self._locks), "registrationCount": len(self._registrations),
                "installationCount": len(self._installations),
                "uncertainLockCloseCount": len(self._uncertain_lock_closes)}

    def close(self):
        from services.v4_platform.generation_dispatch_jobs import unregister_controlled_storage, storage_access_snapshot, _UNCERTAIN
        with self._mutex:
            if self._closed:
                return
            if self._uncertain_lock_closes:
                # An interrupted close may have released/reused the descriptor.
                # Never retry that numeric fd or claim a completed handback.
                _unavailable()
            self._closing = True
            if self.state != "ACQUIRING" and (self._entries or any(
                    storage_access_snapshot(p)["activeAccesses"] for p in self.paths)):
                self.events.append({"phase": "CLOSE_REFUSED_INFLIGHT", "snapshot": self.snapshot()})
                _unavailable()
            safe = not self._uncertain
            if self.state != "ACQUIRING":
                try:
                    self.assert_exclusive()
                except BaseException:
                    safe = False
            if any(getattr(obj, name, None) is not wrapper for obj, name, wrapper in self._installations):
                safe = False
            if self._coordination is not None:
                self._coordination._active = False
            if safe:
                for obj, name, wrapper in reversed(self._installations):
                    delattr(obj, name)
            elif self.state != "ACQUIRING":
                # Leave old installed entries invalid, and prevent a fresh
                # control epoch from laundering unresolved changes as a baseline.
                for _, fd, _ in self._locks:
                    os.pwrite(fd, _UNCERTAIN, 0)
            for path, callback in reversed(self._registrations):
                unregister_controlled_storage(path, callback)
            self._registrations.clear()
            self._installations.clear()
            while self._locks:
                owned = self._locks.pop()
                try:
                    os.close(owned[1])
                except BaseException:
                    self._uncertain_lock_closes.append(owned)
                    self.mark_unknown()
                    self.state = "CLOSE_OUTCOME_UNKNOWN"
                    raise
            self._closed = True
            self.state = "CLOSED" if safe else "CLOSED_POISONED"
            self.events.append({"phase": self.state, "originalMethodsRestored": safe})


@dataclass(frozen=True)
class _Lease:
    coordinator: object
    workspace_ref: str
    thread_id: int
    epoch: str

    def assert_held(self):
        c = self.coordinator
        if (get_ident() != self.thread_id or c.epoch != self.epoch
                or getattr(c._thread, "depth", 0) < 1
                or self.workspace_ref in c._poisoned or not c._active):
            _unavailable()
        c.assert_coverage()


class _ConnectionObservation:
    """Forward real SQLite work, observing the original commit/rollback boundary."""
    def __init__(self, inner, coordinator, path, watch):
        object.__setattr__(self, "inner", inner)
        object.__setattr__(self, "coordinator", coordinator)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "watch", watch)
        object.__setattr__(self, "baseline", inner.total_changes)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def __setattr__(self, name, value):
        setattr(self.inner, name, value)

    def execute(self, sql, parameters=()):
        before = self.inner.in_transaction
        starts = sql.strip().upper().startswith(("BEGIN", "INSERT", "UPDATE", "DELETE", "REPLACE"))
        if starts:
            self.coordinator._enter_transaction(self)
        try:
            result = self.inner.execute(sql, parameters)
        except BaseException:
            if starts:
                self.coordinator._leave_transaction(self)
            raise
        if not before and self.inner.in_transaction:
            self.coordinator._enter_transaction(self)
        return result

    def executemany(self, sql, parameters):
        self.coordinator._enter_transaction(self)
        return self.inner.executemany(sql, parameters)

    def executescript(self, sql):
        # Schema initialization occurs before enrollment. No new-mode migration.
        _unavailable()

    def commit(self):
        changes = self.inner.total_changes - self.baseline
        active = self.inner.in_transaction
        if not active:
            self.coordinator.domain.assert_exclusive()
        try:
            self.inner.commit()
        except BaseException:
            self.watch["unknown"] = True
            raise
        else:
            self.watch["committedChanges"] += changes
            self.watch["commits"] += 1
            object.__setattr__(self, "baseline", self.inner.total_changes)
            if active:
                self.coordinator.domain.accept_transaction_boundary(self.path)
            self.coordinator._leave_transaction(self)

    def rollback(self):
        active = self.inner.in_transaction
        try:
            self.inner.rollback()
        except BaseException:
            self.watch["unknown"] = True
            raise
        else:
            self.watch["rollbacks"] += 1
            object.__setattr__(self, "baseline", self.inner.total_changes)
            if active:
                self.coordinator.domain.accept_transaction_boundary(self.path)
            self.coordinator._leave_transaction(self)

    def close(self):
        active = self.inner.in_transaction
        try:
            self.inner.close()
        except BaseException:
            self.watch["unknown"] = True
            raise
        else:
            if active:
                self.watch["rollbacks"] += 1
                self.coordinator.domain.accept_transaction_boundary(self.path)
            self.coordinator._leave_transaction(self)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if kind is None:
            self.commit()
        else:
            self.rollback()
        return False


def _installation_step(operation):
    @wraps(operation)
    def call(self, *args, **kwargs):
        try:
            return operation(self, *args, **kwargs)
        except BaseException:
            domain = getattr(self, "domain", None)
            if (domain is not None and domain.state == "TAKEOVER"
                    and domain._installer_thread == get_ident()
                    and domain._coordination is self):
                domain.close()
            raise
    return call


class GenerationDispatchCoordination:
    @_installation_step
    def __init__(self, *, storage_domain):
        if not isinstance(storage_domain, ControlledStorageDomain):
            _unavailable()
        self.domain = storage_domain
        self.domain.assert_installing()
        if self.domain._coordination is not None:
            _unavailable()
        self.domain._coordination = self
        self.epoch = sha256((str(os.getpid()) + ":" + uuid4().hex).encode()).hexdigest()
        self._thread = local()
        self._locks = {}
        self._locks_lock = RLock()
        self._bindings = []
        self._dependencies = []
        self._storage_bindings = []
        self._counters = {}
        self._poisoned = set()
        self._active = False
        self.observations = []
        self._owners = set()
        # One workset uses one workspace. This also serializes shared database
        # identity observations; no claim of cross-workspace distributed locks.
        self._workspace_ref = None
        def open_guard(owner):
            if (id(owner) not in self._owners or getattr(self._thread, "depth", 0) < 1
                    or not self._active or os.getpid() != self.domain._pid):
                _unavailable()
            return _ControlledAccessPermit(self.domain, owner)
        from services.v4_platform.generation_dispatch_jobs import register_controlled_storage
        for path in self.domain.paths:
            # Track our intent before a registration result could be lost;
            # rollback removes only an identity-equal callback, never another's.
            self.domain._registrations.append((path, open_guard))
            register_controlled_storage(path, open_guard)

    def _check_access_owner(self, owner):
        if (id(owner) not in self._owners or getattr(self._thread, "depth", 0) < 1
                or not self._active or os.getpid() != self.domain._pid):
            _unavailable()
        self.domain.assert_exclusive(compare_files=False)

    def assert_coverage(self):
        if not self._active or not self._bindings:
            _unavailable()
        self.domain.assert_exclusive(compare_files=False)
        for obj, name, installed, original in self._bindings:
            if getattr(obj, name, None) is not installed or getattr(type(obj), name, None) is not original:
                _unavailable()
        for obj, name, expected in self._dependencies:
            if getattr(obj, name, None) is not expected:
                _unavailable()
        for obj, name, expected in self._storage_bindings:
            if Path(getattr(obj, name)).resolve(strict=True) != expected:
                _unavailable()

    def bind_dependency(self, obj, name, target):
        if self._active or getattr(obj, name, None) is not target:
            _unavailable()
        self._dependencies.append((obj, name, target))

    def _bind_storage(self, obj):
        name = "database_path" if hasattr(obj, "database_path") else "path"
        if not hasattr(obj, name):
            return
        path = Path(getattr(obj, name)).resolve(strict=True)
        if path not in self.domain.paths:
            _unavailable()
        self._storage_bindings.append((obj, name, path))
        if hasattr(obj, "_lock"):
            from services.v4_platform.generation_dispatch_jobs import StorageAccessRLock
            if not isinstance(obj._lock, StorageAccessRLock) or obj._lock.owner is not obj:
                _unavailable()
            self.bind_dependency(obj, "_lock", obj._lock)
        for attribute in ("_state", "_lifecycle_state"):
            if hasattr(obj, attribute):
                self.bind_dependency(obj, attribute, getattr(obj, attribute))

    @_installation_step
    def activate(self, required_bindings):
        self.domain.assert_installing()
        actual = {(id(obj), name) for obj, name, _, _ in self._bindings}
        if actual != {(id(obj), name) for obj, name in required_bindings}:
            _unavailable()
        self._active = True
        self.assert_coverage()
        self.domain.acknowledge_controlled_operations()
        self.domain.state = "ACTIVE"

    @contextmanager
    def critical_section(self, workspace_ref):
        from sys import exc_info
        from services.v5_core_os.episode_production.generation_dispatch_contracts import CommitOutcomeUnknown

        if type(workspace_ref) is not str or not workspace_ref:
            _unavailable()
        if workspace_ref != self._workspace_ref:
            _unavailable()
        outer = getattr(self._thread, "depth", 0) == 0
        primary_unknown = None
        if outer:
            self.domain.begin_entry(self)
        try:
            with self._locks_lock:
                lock = self._locks.setdefault(workspace_ref, RLock())
            with lock:
                depth = getattr(self._thread, "depth", 0)
                if depth and self._thread.workspace != workspace_ref:
                    _unavailable()
                if not depth:
                    self.assert_coverage()
                elif not self._active:
                    _unavailable()
                if workspace_ref in self._poisoned:
                    _unavailable()
                if not depth:
                    try:
                        self.domain.assert_exclusive()
                    except BaseException:
                        self._poisoned.add(workspace_ref)
                        raise
                self._thread.depth, self._thread.workspace = depth + 1, workspace_ref
                try:
                    yield _Lease(self, workspace_ref, get_ident(), self.epoch)
                except CommitOutcomeUnknown as exc:
                    primary_unknown = exc
                    raise
                finally:
                    self._thread.depth = depth
                    if not depth:
                        pending = exc_info()[1]
                        try:
                            self.domain.acknowledge_controlled_operations()
                        except Exception as exit_error:
                            if pending is not primary_unknown or not self._retain_unknown_gate_exit(pending, exit_error, "ACKNOWLEDGE"):
                                raise
        finally:
            if outer:
                pending = exc_info()[1]
                try:
                    self.domain.end_entry()
                except Exception as exit_error:
                    if pending is not primary_unknown or not self._retain_unknown_gate_exit(pending, exit_error, "END_ENTRY"):
                        raise

    @staticmethod
    def _retain_unknown_gate_exit(pending, exit_error, phase):
        from services.v5_core_os.episode_production.generation_dispatch_contracts import (
            CommitOutcomeUnknown, DispatchError,
        )

        if not isinstance(pending, CommitOutcomeUnknown):
            return False
        if isinstance(exit_error, DispatchError):
            if exit_error.code != "CURRENTNESS_FENCE_UNAVAILABLE":
                return False
            code = exit_error.code
        elif isinstance(exit_error, OSError):
            code = "OS_ERROR"
        else:
            return False
        # Preserve the pending exception by continuing its original unwind, not
        # by raising it from the exit error (whose context points back to it).
        # Only bounded private metadata is retained: no exception objects,
        # messages, paths, or claim that the failed cleanup completed.
        previous = getattr(pending, "_gate_exit_diagnostics", ())
        pending._gate_exit_diagnostics = (*previous[-7:], {
            "phase": phase, "errorType": type(exit_error).__name__[:80], "code": code,
        })
        return True

    def revision(self, lease, owner, selector_kind, scope_ref):
        lease.assert_held()
        key = (lease.workspace_ref, owner, selector_kind, scope_ref)
        return self._counters.setdefault(key, 0)

    def _invalidate(self, workspace, selector_kinds, *, unknown=False):
        for key in tuple(self._counters):
            if key[0] == workspace and key[2] in selector_kinds:
                self._counters[key] += 1
        if unknown:
            self._poisoned.add(workspace)

    def _enter_transaction(self, connection):
        current = getattr(self._thread, "transaction", None)
        if current is not None and current is not connection:
            _unavailable()
        if current is None:
            self.domain.assert_exclusive()
        self._thread.transaction = connection

    def _leave_transaction(self, connection):
        if getattr(self._thread, "transaction", None) is connection:
            self._thread.transaction = None

    def _install(self, obj, name, wrapper):
        self.domain.assert_installing()
        original = getattr(type(obj), name, None)
        if not callable(original) or name in getattr(obj, "__dict__", {}):
            _unavailable()
        setattr(obj, name, wrapper)
        self._bindings.append((obj, name, wrapper, original))
        self.domain._installations.append((obj, name, wrapper))

    @_installation_step
    def bind_repository(self, obj, *, workspace_ref, writers, readers=(), memory_fields=()):
        """Called only by the explicit composition's closed Owner enrollment map."""
        if self._active:
            _unavailable()
        self._select_workspace(workspace_ref)
        self._owners.add(id(obj))
        self._bind_storage(obj)
        path = getattr(obj, "database_path", getattr(obj, "path", None))
        if path is not None:
            path = Path(path).resolve(strict=True)
            if path not in self.domain.paths:
                _unavailable()
        if hasattr(obj, "_connect"):
            original_connect = obj._connect
            def connect():
                watches = getattr(self._thread, "watches", [])
                if not watches or getattr(self._thread, "depth", 0) < 1:
                    _unavailable()
                return _ConnectionObservation(original_connect(), self, path, watches[-1])
            self._install(obj, "_connect", connect)
        for name in (*writers, *readers):
            original_method = getattr(obj, name)
            kinds = writers.get(name, ())
            def make_wrapper(original_method, name, kinds):
                @wraps(original_method)
                def call(*args, **kwargs):
                    with self.critical_section(workspace_ref):
                        if args and isinstance(args[0], str) and args[0] != workspace_ref:
                            _unavailable()
                        candidates = [*args, *kwargs.values()]
                        for value in candidates:
                            values = value if isinstance(value, (list, tuple)) else (value,)
                            for item in values:
                                workspace = item.get("workspaceRef") if isinstance(item, dict) else getattr(item, "workspaceRef", None)
                                if workspace is not None and workspace != workspace_ref:
                                    _unavailable()
                        affected = kinds(args, kwargs) if callable(kinds) else kinds
                        watch = {"committedChanges": 0, "commits": 0, "rollbacks": 0, "unknown": False}
                        before = {k: deepcopy(getattr(obj, k)) for k in memory_fields}
                        watches = getattr(self._thread, "watches", [])
                        self._thread.watches = [*watches, watch]
                        failed = False
                        try:
                            return original_method(*args, **kwargs)
                        except BaseException:
                            failed = True
                            raise
                        finally:
                            self._thread.watches = watches
                            changed = any(before[k] != getattr(obj, k) for k in before)
                            if watch["committedChanges"] or changed or watch["unknown"]:
                                self._invalidate(workspace_ref, affected,
                                    unknown=watch["unknown"] or (failed and (changed or bool(watch["committedChanges"]))))
                            self.observations.append({"ownerClass": type(obj).__name__, "method": name,
                                "thread": get_ident(), "workspaceRef": workspace_ref,
                                "gateHeld": self._thread.depth > 0, "memoryChanged": changed,
                                "raised": failed, **watch})
                return call
            self._install(obj, name, make_wrapper(original_method, name, kinds))

    @_installation_step
    def bind_lifecycle(self, state, *, workspace_ref, selector_kinds):
        """Cover the outer lease including ProjectFoundation/registration writes."""
        if self._active:
            _unavailable()
        self._select_workspace(workspace_ref)
        self._owners.add(id(state))
        self._bind_storage(state)
        selected_workspace = workspace_ref
        original = state.lease
        if hasattr(state, "_connect"):
            connect = state._connect
            def observed_connect():
                watches = getattr(self._thread, "watches", [])
                if not watches:
                    _unavailable()
                return _ConnectionObservation(connect(), self,
                    Path(state.database_path).resolve(), watches[-1])
            self._install(state, "_connect", observed_connect)
        @contextmanager
        def lease(*, workspace_ref: str, operation):
            workspace = workspace_ref
            if workspace != selected_workspace:
                _unavailable()
            with self.critical_section(workspace):
                watch = {"committedChanges": 0, "commits": 0, "rollbacks": 0, "unknown": False}
                before = [(capture, deepcopy(capture())) for _, capture, _ in getattr(state, "_resources", ())]
                watches = getattr(self._thread, "watches", [])
                self._thread.watches = [*watches, watch]
                failed = False
                try:
                    with original(workspace_ref=workspace, operation=operation) as held:
                        yield held
                except BaseException:
                    failed = True
                    raise
                finally:
                    self._thread.watches = watches
                    memory_changed = any(capture() != value for capture, value in before)
                    if watch["committedChanges"] or watch["unknown"] or memory_changed:
                        self._invalidate(workspace, selector_kinds,
                            unknown=watch["unknown"] or (failed and (bool(watch["committedChanges"]) or memory_changed)))
                    self.observations.append({"ownerClass": type(state).__name__, "method": "lease",
                        "operation": str(operation), "gateHeld": self._thread.depth > 0,
                        "raised": failed, "memoryChanged": memory_changed, **watch})
        self._install(state, "lease", lease)
        original_read = state.read_snapshot
        @contextmanager
        def read_snapshot():
            with self.critical_section(selected_workspace):
                watch = {"committedChanges": 0, "commits": 0, "rollbacks": 0, "unknown": False}
                watches = getattr(self._thread, "watches", [])
                self._thread.watches = [*watches, watch]
                try:
                    with original_read():
                        yield
                finally:
                    self._thread.watches = watches
                    if watch["unknown"] or watch["committedChanges"]:
                        self._invalidate(selected_workspace, selector_kinds, unknown=True)
        self._install(state, "read_snapshot", read_snapshot)

    def _select_workspace(self, workspace_ref):
        if self._workspace_ref is not None and self._workspace_ref != workspace_ref:
            _unavailable()
        self._workspace_ref = workspace_ref


class ControlledSourceSelection:
    """A gate-owned locator selection, delegating evidence to its original port.

    Changing a selected port is an observable configuration action, not an
    approval decision. Original port pin/identity/drift checks still apply.
    """
    def __init__(self, port, *, coordination, workspace_ref, selector_kinds):
        if port is None or not selector_kinds:
            _unavailable()
        self._port = port
        self._pin_methods(port)
        self.coordination, self.workspace_ref = coordination, workspace_ref
        self.selector_kinds = frozenset(selector_kinds)
        original = self.select_port
        def select(port):
            return original(port)
        coordination._install(self, "select_port", select)

    def select_port(self, port):
        if port is None:
            _unavailable()
        with self.coordination.critical_section(self.workspace_ref):
            if port is not self._port:
                self._port = port
                self._pin_methods(port)
                self.coordination._invalidate(self.workspace_ref, self.selector_kinds)

    def _pin_methods(self, port):
        self._methods = {name: (getattr(method, "__func__", method), getattr(method, "__self__", None))
            for name in ("read_current", "prepare", "resolve")
            if callable(method := getattr(port, name, None))}
        if not self._methods:
            _unavailable()

    def _check_port(self):
        for name, original in self._methods.items():
            method = getattr(self._port, name, None)
            if (getattr(method, "__func__", method), getattr(method, "__self__", None)) != original:
                self.coordination._invalidate(self.workspace_ref, self.selector_kinds, unknown=True)
                _unavailable()

    def read_current(self, *args, **kwargs):
        with self.coordination.critical_section(self.workspace_ref):
            self._check_port()
            return self._port.read_current(*args, **kwargs)

    def prepare(self, *args, **kwargs):
        with self.coordination.critical_section(self.workspace_ref):
            self._check_port()
            return self._port.prepare(*args, **kwargs)

    def resolve(self, *args, **kwargs):
        with self.coordination.critical_section(self.workspace_ref):
            self._check_port()
            return self._port.resolve(*args, **kwargs)
