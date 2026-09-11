"""Coordination mechanism tests; complete Owner coverage is integration evidence."""
from pathlib import Path
import os
import tempfile
from types import SimpleNamespace
import unittest
from threading import Event, Thread, get_ident
from unittest.mock import patch
import sqlite3

from services.v4_platform.media_jobs import SqliteMediaJobAdapter
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.lifecycle_integrity.generation_dispatch_coordination import (
    ControlledStorageDomain, GenerationDispatchCoordination, ControlledSourceSelection,
)


class GenerationDispatchCoordinationUnitTests(unittest.TestCase):
    def _export_unknown_exit_case(self, name, domain, coordination, observed):
        import sys
        from tests.support.generation_dispatch_binding_fixtures import export_evidence
        pending = sys.exc_info()[1]
        def snapshot():
            return {"domain": domain.snapshot(), "depth": getattr(coordination._thread, "depth", 0),
                "poisoned": sorted(coordination._poisoned), "active": coordination._active,
                "gateOwnedByCurrentThread": coordination._locks.get("test-workspace")._is_owned()
                    if "test-workspace" in coordination._locks else "NOT_CREATED"}
        observed["beforeClose"] = snapshot()
        try:
            domain.close()
            observed["closeResult"] = "RETURNED"
        except BaseException as exc:
            observed["closeResult"] = {"errorType": type(exc).__name__}
            raise
        finally:
            observed["afterCloseAttempt"] = snapshot()
            try:
                export_evidence("unknown_exit_unit_" + name, observed)
            except Exception as exc:
                if pending is None:
                    raise
                pending.add_note("Gate exit evidence export failed: " + type(exc).__name__)
                print("Gate exit evidence export failed: " + type(exc).__name__, file=sys.stderr)

    def test_unknown_exit_original_unknown_survives_normal_exit(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        unknown, cause, observed = c.CommitOutcomeUnknown(), OSError("synthetic receipt loss"), {}
        try:
            with self.assertRaises(c.CommitOutcomeUnknown) as result:
                with coordination.critical_section("test-workspace"):
                    try: raise cause
                    except OSError: raise unknown from cause
            self.assertIs(result.exception, unknown); self.assertIs(unknown.__cause__, cause)
            self.assertIs(unknown.__context__, cause); self.assertIsNone(cause.__context__)
            observed.update(primaryType=type(result.exception).__name__, causeType=type(unknown.__cause__).__name__,
                diagnostics=list(getattr(unknown, "_gate_exit_diagnostics", ())))
            self.assertEqual(observed["diagnostics"], [])
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
            self.assertFalse(coordination._locks["test-workspace"]._is_owned())
        finally: self._export_unknown_exit_case("normal_exit", domain, coordination, observed)

    def test_unknown_exit_fence_failure_preserves_cause_and_poison(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        unknown, cause, observed = c.CommitOutcomeUnknown(), OSError("synthetic receipt loss"), {}
        try:
            with patch.object(domain, "acknowledge_controlled_operations", wraps=domain.acknowledge_controlled_operations) as acknowledge:
                with patch.object(domain, "end_entry", wraps=domain.end_entry) as end_entry:
                    with self.assertRaises(c.CommitOutcomeUnknown) as result:
                        with coordination.critical_section("test-workspace"):
                            domain.mark_unknown()
                            try: raise cause
                            except OSError: raise unknown from cause
            observed.update(primaryType=type(result.exception).__name__, causeType=type(unknown.__cause__).__name__,
                diagnostics=list(unknown._gate_exit_diagnostics), acknowledgeCalls=acknowledge.call_count,
                endEntryCalls=end_entry.call_count)
            self.assertIs(result.exception, unknown); self.assertIs(unknown.__cause__, cause)
            self.assertIs(unknown.__context__, cause); self.assertIsNone(cause.__context__)
            self.assertEqual(observed["diagnostics"], [{"phase": "ACKNOWLEDGE", "errorType": "DispatchError",
                "code": "CURRENTNESS_FENCE_UNAVAILABLE"}])
            self.assertEqual(acknowledge.call_count, 1); self.assertEqual(end_entry.call_count, 1)
            self.assertTrue(domain._uncertain); self.assertIn("test-workspace", coordination._poisoned)
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
            self.assertFalse(coordination._locks["test-workspace"]._is_owned())
            with self.assertRaises(c.DispatchError) as refused:
                with coordination.critical_section("test-workspace"): self.fail("poisoned gate entered")
            observed["subsequentCode"] = refused.exception.code
            self.assertEqual(refused.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")
        finally: self._export_unknown_exit_case("fence_failure", domain, coordination, observed)

    def test_unknown_exit_normal_body_cannot_hide_exit_failure(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        observed = {"phases": []}
        try:
            with self.assertRaises(c.DispatchError) as result:
                with coordination.critical_section("test-workspace"):
                    observed["phases"].append("BODY_COMPLETED"); domain.mark_unknown()
                observed["phases"].append("RETURNED_SUCCESS")
            observed["code"] = result.exception.code
            self.assertEqual(observed["phases"], ["BODY_COMPLETED"])
            self.assertEqual(result.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
        finally: self._export_unknown_exit_case("normal_body_failed_exit", domain, coordination, observed)

    def test_unknown_exit_ordinary_body_exception_keeps_original_semantics(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        original, observed = c.DispatchError("SOURCE_CHANGED"), {}
        try:
            with self.assertRaises(c.DispatchError) as result:
                with coordination.critical_section("test-workspace"): raise original
            self.assertIs(result.exception, original); self.assertEqual(result.exception.code, "SOURCE_CHANGED")
            self.assertFalse(hasattr(original, "_gate_exit_diagnostics"))
            observed["code"] = result.exception.code
            with coordination.critical_section("test-workspace") as lease: lease.assert_held()
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
        finally: self._export_unknown_exit_case("ordinary_body", domain, coordination, observed)

    def test_unknown_exit_caller_handled_unknown_is_not_this_gate_primary(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        unrelated, observed = c.CommitOutcomeUnknown(), {"phases": []}
        try:
            try: raise unrelated
            except c.CommitOutcomeUnknown:
                with self.assertRaises(c.DispatchError) as result:
                    with coordination.critical_section("test-workspace"):
                        observed["phases"].append("BODY_COMPLETED"); domain.mark_unknown()
                    observed["phases"].append("RETURNED_SUCCESS")
            self.assertEqual(result.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")
            self.assertEqual(observed["phases"], ["BODY_COMPLETED"])
            self.assertFalse(hasattr(unrelated, "_gate_exit_diagnostics"))
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
            observed["outwardCode"] = result.exception.code
        finally: self._export_unknown_exit_case("caller_handled_unknown", domain, coordination, observed)

    def test_unknown_exit_ordinary_error_does_not_override_fence_failure(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        original, observed = c.DispatchError("SOURCE_CHANGED"), {}
        try:
            with self.assertRaises(c.DispatchError) as result:
                with coordination.critical_section("test-workspace"):
                    domain.mark_unknown(); raise original
            self.assertIsNot(result.exception, original)
            self.assertEqual(result.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")
            self.assertFalse(hasattr(original, "_gate_exit_diagnostics"))
            observed.update(primaryCode=original.code, outwardCode=result.exception.code)
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
        finally: self._export_unknown_exit_case("ordinary_and_exit_error", domain, coordination, observed)

    def test_unknown_exit_nested_gate_restores_depth_and_single_entry(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        unknown, cause = c.CommitOutcomeUnknown(), OSError("synthetic nested receipt loss")
        observed = {"depths": [], "entries": []}
        try:
            with patch.object(domain, "end_entry", wraps=domain.end_entry) as end_entry:
                with self.assertRaises(c.CommitOutcomeUnknown) as result:
                    with coordination.critical_section("test-workspace"):
                        observed["depths"].append(coordination._thread.depth); observed["entries"].append(domain._entries)
                        try:
                            with coordination.critical_section("test-workspace"):
                                observed["depths"].append(coordination._thread.depth); observed["entries"].append(domain._entries)
                                domain.mark_unknown()
                                try: raise cause
                                except OSError: raise unknown from cause
                        finally:
                            observed["depths"].append(coordination._thread.depth); observed["entries"].append(domain._entries)
            self.assertIs(result.exception, unknown); self.assertIs(unknown.__cause__, cause)
            self.assertIs(unknown.__context__, cause); self.assertIsNone(cause.__context__)
            self.assertEqual(observed["depths"], [1, 2, 1]); self.assertEqual(observed["entries"], [1, 1, 1])
            self.assertEqual(end_entry.call_count, 1)
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
            self.assertFalse(coordination._locks["test-workspace"]._is_owned())
            observed.update(diagnostics=list(unknown._gate_exit_diagnostics), endEntryCalls=end_entry.call_count)
            self.assertEqual(len(observed["diagnostics"]), 1)
        finally: self._export_unknown_exit_case("nested_gate", domain, coordination, observed)

    def test_unknown_exit_entry_refusal_never_runs_body(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        observed = {"bodyCalls": 0}; domain.mark_unknown()
        try:
            with patch.object(domain, "end_entry", wraps=domain.end_entry) as end_entry:
                with self.assertRaises(c.DispatchError) as result:
                    with coordination.critical_section("test-workspace"): observed["bodyCalls"] += 1
            observed.update(code=result.exception.code, endEntryCalls=end_entry.call_count)
            self.assertEqual(observed["bodyCalls"], 0); self.assertEqual(end_entry.call_count, 0)
            self.assertEqual(result.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")
            self.assertNotIsInstance(result.exception, c.CommitOutcomeUnknown)
            self.assertEqual(domain._entries, 0)
        finally: self._export_unknown_exit_case("entry_refusal", domain, coordination, observed)

    def test_unknown_exit_interrupts_and_unrelated_errors_are_not_suppressed(self):
        for secondary in (KeyboardInterrupt(), SystemExit(7), ValueError("unrelated bug"), c.DispatchError("SOURCE_CHANGED")):
            with self.subTest(errorType=type(secondary).__name__):
                _, _, domain, coordination = self.fixture(); self.activate(coordination)
                unknown, observed = c.CommitOutcomeUnknown(), {}
                try:
                    with patch.object(domain, "acknowledge_controlled_operations", side_effect=secondary):
                        with self.assertRaises(type(secondary)) as result:
                            with coordination.critical_section("test-workspace"): raise unknown
                    self.assertIs(result.exception, secondary)
                    self.assertFalse(hasattr(unknown, "_gate_exit_diagnostics"))
                    self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
                    self.assertFalse(coordination._locks["test-workspace"]._is_owned())
                    observed["outwardType"] = type(result.exception).__name__
                finally: self._export_unknown_exit_case(type(secondary).__name__, domain, coordination, observed)

    def test_unknown_exit_end_entry_error_is_diagnostic_not_false_cleanup_success(self):
        _, _, domain, coordination = self.fixture(); self.activate(coordination)
        unknown, cause, observed = c.CommitOutcomeUnknown(), OSError("synthetic receipt loss"), {"entryExitPhases": []}
        original_end_entry = domain.end_entry
        def end_entry():
            observed["entryExitPhases"].append({"phase": "BEFORE", "entries": domain._entries})
            original_end_entry()
            observed["entryExitPhases"].append({"phase": "RETURNED", "entries": domain._entries})
            raise OSError("synthetic loss after actual end_entry returned")
        try:
            with patch.object(domain, "end_entry", side_effect=end_entry):
                with self.assertRaises(c.CommitOutcomeUnknown) as result:
                    with coordination.critical_section("test-workspace"):
                        domain.mark_unknown()
                        try: raise cause
                        except OSError: raise unknown from cause
            self.assertIs(result.exception, unknown); self.assertIs(unknown.__cause__, cause)
            self.assertIs(unknown.__context__, cause); self.assertIsNone(cause.__context__)
            observed["diagnostics"] = list(unknown._gate_exit_diagnostics)
            self.assertEqual([x["phase"] for x in observed["diagnostics"]], ["ACKNOWLEDGE", "END_ENTRY"])
            self.assertEqual(observed["diagnostics"][1], {"phase": "END_ENTRY", "errorType": "OSError", "code": "OS_ERROR"})
            self.assertEqual(observed["entryExitPhases"], [{"phase": "BEFORE", "entries": 1}, {"phase": "RETURNED", "entries": 0}])
            self.assertEqual(coordination._thread.depth, 0); self.assertEqual(domain._entries, 0)
            self.assertTrue(domain._uncertain); self.assertIn("test-workspace", coordination._poisoned)
        finally: self._export_unknown_exit_case("end_entry_error", domain, coordination, observed)

    def test_f01_ordinary_open_connection_blocks_takeover_until_writer_finishes(self):
        from services.v4_platform import MediaJobCoordinator, DeterministicLocalFfmpegAdapter
        from tests.unit.test_v4_media_jobs import one_request
        from tests.support.generation_dispatch_binding_fixtures import export_evidence
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        repository = SqliteMediaJobAdapter(root / "queue.sqlite3")
        refs, run, request = one_request()
        queue = MediaJobCoordinator(repository, DeterministicLocalFfmpegAdapter(), root / "artifacts",
            ref_factory=refs, clock=lambda: "2026-08-17T01:00:00Z")
        opened, release = Event(), Event()
        phases, outcome, identities = [], {}, {}
        original_connect = sqlite3.connect
        class Connection:
            def __init__(self, connection): object.__setattr__(self, "inner", connection)
            def __getattr__(self, name): return getattr(self.inner, name)
            def __setattr__(self, name, value): setattr(self.inner, name, value)
            def execute(self, sql, *args):
                value = self.inner.execute(sql, *args)
                phases.append({"phase": sql.split()[0], "inTransaction": self.inner.in_transaction})
                return value
            def commit(self):
                value = self.inner.commit(); phases.append({"phase": "COMMIT_RETURNED", "inTransaction": self.inner.in_transaction}); return value
            def rollback(self): return self.inner.rollback()
            def close(self):
                value = self.inner.close(); phases.append({"phase": "CLOSE_RETURNED"}); return value
            def __enter__(self): self.inner.__enter__(); return self
            def __exit__(self, *args): return self.inner.__exit__(*args)
        def connect(path, *args, **kwargs):
            connection = original_connect(path, *args, **kwargs)
            if get_ident() == identities.get("writer") and Path(path) == repository.path:
                phases.append({"phase": "ACTUAL_SQLITE_OPEN_RETURNED", "inTransaction": connection.in_transaction})
                opened.set()
                if not release.wait(10):
                    connection.close(); raise AssertionError("bounded writer release missing")
                return Connection(connection)
            return connection
        def writer():
            identities["writer"] = get_ident()
            try: outcome["result"] = queue.dispatch(request, idempotency_key="test-takeover-original-writer")
            except BaseException as exc: outcome["error"] = type(exc).__name__ + ": " + str(exc)
        domain = None; refused = False; active_during_old_access = False
        with patch.object(sqlite3, "connect", side_effect=connect):
            thread = Thread(target=writer); thread.start()
            try:
                self.assertTrue(opened.wait(10), outcome)
                try:
                    domain = ControlledStorageDomain(root, [repository.path])
                    coordination = GenerationDispatchCoordination(storage_domain=domain)
                    coordination.bind_repository(repository, workspace_ref=request["workspaceRef"],
                        writers={"create": (), "save": (), "reserve_batch": ()}, readers=("get", "list"))
                    self.activate(coordination)
                    active_during_old_access = coordination._active
                except (BlockingIOError, c.DispatchError, RuntimeError): refused = True
            finally:
                release.set(); thread.join(10)
                if domain is not None: domain.close()
        self.assertFalse(thread.is_alive(), "writer must finish normally, never be killed")
        self.assertNotIn("error", outcome)
        reopened = SqliteMediaJobAdapter(repository.path, initialize_if_missing=False)
        jobs = reopened.list(request["workspaceRef"], request["productionRunRef"])
        export_evidence("f01_T1_ordinary_open", {"phases": phases, "takeoverRefused": refused,
            "activeDuringOldAccess": active_during_old_access, "writer": outcome,
            "reopenedJobs": jobs, "writerAliveAfterJoin": thread.is_alive()})
        self.assertEqual(len(jobs), 1)
        self.assertTrue(refused, "F01: takeover became ACTIVE while original ordinary SQLite writer already held an open connection")
        self.assertFalse(active_during_old_access)
        next_domain = ControlledStorageDomain(root, [repository.path])
        try:
            next_coordination = GenerationDispatchCoordination(storage_domain=next_domain)
            next_coordination.bind_repository(reopened, workspace_ref=request["workspaceRef"],
                writers={"create": (), "save": (), "reserve_batch": ()}, readers=("get", "list"))
            self.activate(next_coordination)
            self.assertEqual(reopened.list(request["workspaceRef"], request["productionRunRef"]), jobs)
            export_evidence("f01_T1_explicit_later_takeover", {"snapshot": next_domain.snapshot(),
                "jobs": jobs, "epoch": next_coordination.epoch})
        finally:
            next_domain.close()

    def test_f01_first_sidecar_open_gap_and_saved_old_entry(self):
        from shutil import copyfile
        from services.v4_platform.generation_dispatch_jobs import storage_access_snapshot
        from tests.support.generation_dispatch_binding_fixtures import export_evidence
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        seed = SqliteMediaJobAdapter(root / "seed.sqlite3")
        target = root / "new.sqlite3"; copyfile(seed.path, target)
        sidecar = target.with_name(target.name + ".dispatch-lock")
        self.assertFalse(sidecar.exists())
        ready, release = Event(), Event(); result, phases, ids = {}, [], {}
        original = sqlite3.connect
        def connect(path, *args, **kwargs):
            if Path(path) == target and get_ident() == ids.get("thread") and not ready.is_set():
                phases.append({"phase": "BEFORE_ACTUAL_SQLITE_OPEN", "sidecarExists": sidecar.exists(),
                    **storage_access_snapshot(target)})
                ready.set()
                if not release.wait(10): raise AssertionError("bounded release missing")
            value = original(path, *args, **kwargs)
            phases.append({"phase": "ACTUAL_SQLITE_OPEN_RETURNED"})
            return value
        def run():
            ids["thread"] = get_ident()
            try: result["repository"] = SqliteMediaJobAdapter(target, initialize_if_missing=False)
            except BaseException as exc: result["error"] = repr(exc)
        with patch.object(sqlite3, "connect", side_effect=connect):
            thread = Thread(target=run); thread.start()
            try:
                self.assertTrue(ready.wait(10), result)
                self.assertEqual([p["phase"] for p in phases], ["BEFORE_ACTUAL_SQLITE_OPEN"])
                with self.assertRaises((BlockingIOError, c.DispatchError, RuntimeError)):
                    ControlledStorageDomain(root, [target])
            finally:
                release.set(); thread.join(10)
        self.assertFalse(thread.is_alive()); self.assertNotIn("error", result)
        repo = result["repository"]; old_list, old_connect = repo.list, repo._connect
        domain = ControlledStorageDomain(root, [target])
        try:
            coordination = GenerationDispatchCoordination(storage_domain=domain)
            coordination.bind_repository(repo, workspace_ref="test-workspace",
                writers={"create": (), "save": (), "reserve_batch": ()}, readers=("get", "list"))
            self.activate(coordination)
            with patch.object(sqlite3, "connect", wraps=original) as observed:
                for entry in (lambda: old_list("test-workspace", "test-run"), old_connect):
                    with self.assertRaises(c.DispatchError): entry()
                self.assertEqual(observed.call_count, 0)
            self.assertEqual(repo.list("test-workspace", "test-run"), [])
            export_evidence("f01_T2_first_sidecar", {"initialSidecarAbsent": True, "phases": phases,
                "afterOldAccess": storage_access_snapshot(target), "active": domain.snapshot(),
                "savedEntriesActualOpens": observed.call_count, "threadAlive": thread.is_alive()})
        finally: domain.close()

    def test_f01_lifecycle_original_lock_and_active_lease_drain_before_install(self):
        from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
        from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation
        from services.v4_platform.generation_dispatch_jobs import storage_access_snapshot
        from tests.support.generation_dispatch_binding_fixtures import export_evidence
        evidence = []
        for phase in ("ORIGINAL_LOCK_BEFORE_OPEN", "ACTIVE_LEASE_TRANSACTION", "ACTIVE_READ_SNAPSHOT"):
            with self.subTest(phase=phase):
                temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
                root = Path(temp.name).resolve(); os.chmod(root, 0o700)
                assembly = LifecycleAssembly.sqlite(root / "lifecycle.sqlite3", initialize_or_upgrade=True)
                state = assembly.state; path = state.database_path
                ready, release = Event(), Event(); ids, result, observed = {}, {}, {}
                original = sqlite3.connect
                def pause(stage, connection=None):
                    observed.update(phase=stage, originalLockOwned=state._lock._is_owned(),
                        inTransaction=connection.in_transaction if connection is not None else "NOT_OPENED",
                        activeLeaseCount=len(state._active), access=storage_access_snapshot(path))
                    ready.set()
                    if not release.wait(10): raise AssertionError("bounded release missing")
                def connect(database, *args, **kwargs):
                    if (phase == "ORIGINAL_LOCK_BEFORE_OPEN" and Path(database) == path
                            and get_ident() == ids.get("thread") and not ready.is_set()): pause(phase)
                    return original(database, *args, **kwargs)
                def run():
                    ids["thread"] = get_ident()
                    try:
                        if phase == "ACTIVE_LEASE_TRANSACTION":
                            with state.lease(workspace_ref="test-workspace", operation=LifecycleOperation.CREATE_PROJECT):
                                pause(phase, state.connection_or_none())
                        else:
                            with state.read_snapshot():
                                if phase == "ACTIVE_READ_SNAPSHOT": pause(phase, state.read_connection_or_none())
                        result["completed"] = True
                    except BaseException as exc: result["error"] = repr(exc)
                with patch.object(sqlite3, "connect", side_effect=connect):
                    thread = Thread(target=run); thread.start()
                    try:
                        self.assertTrue(ready.wait(10), result)
                        with self.assertRaises((BlockingIOError, c.DispatchError, RuntimeError)):
                            ControlledStorageDomain(root, [path])
                        self.assertNotIn("lease", state.__dict__)
                        self.assertNotIn("read_snapshot", state.__dict__)
                        self.assertTrue(observed["originalLockOwned"])
                        self.assertGreater(observed["access"]["activeAccesses"], 0)
                    finally: release.set(); thread.join(10)
                self.assertFalse(thread.is_alive()); self.assertNotIn("error", result)
                after = storage_access_snapshot(path); self.assertEqual(after["activeAccesses"], 0)
                domain = ControlledStorageDomain(root, [path])
                coordination = GenerationDispatchCoordination(storage_domain=domain)
                coordination.bind_lifecycle(state, workspace_ref="test-workspace", selector_kinds=())
                self.activate(coordination)
                with state.read_snapshot(): self.assertTrue(state.read_connection_or_none().in_transaction)
                domain.close()
                evidence.append({"observed": observed, "writerResult": result, "after": after,
                    "domainEvents": domain.events, "closed": domain.snapshot(), "threadAlive": thread.is_alive()})
        export_evidence("f01_T3_lifecycle", evidence)

    def test_f01_takeover_failure_releases_only_own_resources_and_restores_methods(self):
        from services.v4_platform import generation_dispatch_jobs as storage
        from tests.support.generation_dispatch_binding_fixtures import export_evidence
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        a, b = (SqliteMediaJobAdapter(root / name) for name in ("a.sqlite3", "b.sqlite3"))
        connection = b._connect(); acquired = []; original_open = storage.storage_lock_open
        def lock_open(path, **kwargs):
            value = original_open(path, **kwargs)
            if kwargs["exclusive"]: acquired.append(value)
            return value
        with patch.object(storage, "storage_lock_open", side_effect=lock_open):
            with self.assertRaises(BlockingIOError): ControlledStorageDomain(root, [b.path, a.path])
        self.assertEqual([item[0] for item in acquired], [a.path.with_name(a.path.name + ".dispatch-lock")])
        for _, fd, _ in acquired:
            with self.assertRaises(OSError): os.fstat(fd)
        self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
        self.assertEqual(a.list("test-workspace", "test-run"), [])
        connection.close(); cases = []
        for phase in ("REGISTRATION", "WRAPPER_INSTALLATION", "ACTIVATION"):
            domain = ControlledStorageDomain(root, [a.path, b.path]); coordination = None
            before = {id(obj): dict(obj.__dict__) for obj in (a, b)}
            try:
                if phase == "REGISTRATION":
                    calls = []; register = storage.register_controlled_storage
                    def injected(path, callback):
                        calls.append(str(path))
                        value = register(path, callback)
                        if len(calls) == 2: raise RuntimeError("synthetic second registration receipt loss")
                        return value
                    with patch.object(storage, "register_controlled_storage", side_effect=injected):
                        with self.assertRaises(RuntimeError): GenerationDispatchCoordination(storage_domain=domain)
                else:
                    coordination = GenerationDispatchCoordination(storage_domain=domain)
                    if phase == "WRAPPER_INSTALLATION":
                        install = coordination._install; calls = []
                        def injected(obj, name, wrapper):
                            calls.append(name)
                            if len(calls) == 3: raise RuntimeError("synthetic third installation failure")
                            return install(obj, name, wrapper)
                        with patch.object(coordination, "_install", side_effect=injected):
                            with self.assertRaises(RuntimeError):
                                coordination.bind_repository(a, workspace_ref="test-workspace",
                                    writers={"create": (), "save": ()}, readers=("list",))
                    else:
                        coordination.bind_repository(a, workspace_ref="test-workspace", writers={"create": ()}, readers=("list",))
                        with patch.object(coordination, "assert_coverage", side_effect=RuntimeError("synthetic activation failure")):
                            with self.assertRaises(RuntimeError): self.activate(coordination)
                self.assertEqual(domain.state, "CLOSED")
                for obj in (a, b):
                    self.assertEqual(obj.__dict__, before[id(obj)])
                    self.assertEqual(storage.storage_access_snapshot(obj.path), {"activeAccesses": 0, "controlledRegistered": False})
                    self.assertEqual(obj.list("test-workspace", "test-run"), [])
                cases.append({"phase": phase, "snapshot": domain.snapshot(), "events": domain.events,
                    "methodsRestored": all(obj.__dict__ == before[id(obj)] for obj in (a, b))})
            finally: domain.close()
        export_evidence("f01_T5_failed_takeover", {"partialExclusivePaths": [str(x[0]) for x in acquired],
            "ordinaryBQuery": 1, "cases": cases})

    def test_f01_close_refuses_inflight_controlled_transaction_until_normal_commit(self):
        from services.v4_platform import MediaJobCoordinator, DeterministicLocalFfmpegAdapter
        from tests.unit.test_v4_media_jobs import one_request
        from tests.support.generation_dispatch_binding_fixtures import export_evidence
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        repo = SqliteMediaJobAdapter(root / "queue.sqlite3")
        refs, run, request = one_request()
        domain = ControlledStorageDomain(root, [repo.path]); self.addCleanup(domain.close)
        coordination = GenerationDispatchCoordination(storage_domain=domain)
        coordination.bind_repository(repo, workspace_ref=request["workspaceRef"],
            writers={"create": (), "save": (), "reserve_batch": ()}, readers=("get", "list"))
        self.activate(coordination)
        queue = MediaJobCoordinator(repo, DeterministicLocalFfmpegAdapter(), root / "artifacts",
            ref_factory=refs, clock=lambda: "2026-08-17T01:00:00Z")
        ready, release = Event(), Event(); result, snapshots = {}, []
        original = sqlite3.connect
        from tests.support.generation_dispatch_binding_fixtures import ForwardingSqliteConnection
        def boundary(phase, connection):
            if phase == "BEFORE_COMMIT" and connection.in_transaction and not ready.is_set():
                snapshots.append({"phase": phase, "inTransaction": connection.in_transaction, "domain": domain.snapshot()})
                ready.set()
                if not release.wait(10): raise AssertionError("bounded release missing")
        def connect(path, *args, **kwargs): return ForwardingSqliteConnection(original(path, *args, **kwargs), boundary)
        def writer():
            try: result["result"] = queue.dispatch(request, idempotency_key="test-close-writer")
            except BaseException as exc: result["error"] = repr(exc)
        with patch.object(sqlite3, "connect", side_effect=connect):
            thread = Thread(target=writer); thread.start()
            try:
                self.assertTrue(ready.wait(10), result)
                with self.assertRaises(c.DispatchError): domain.close()
                snapshots.append({"phase": "CLOSE_REFUSED", "domain": domain.snapshot()})
                self.assertTrue(coordination._active)
                with self.assertRaises(BlockingIOError): ControlledStorageDomain(root, [repo.path])
                with self.assertRaises(c.DispatchError): repo.list(request["workspaceRef"], request["productionRunRef"])
            finally: release.set(); thread.join(10)
        self.assertFalse(thread.is_alive()); self.assertNotIn("error", result)
        domain.close(); first_close = domain.snapshot(); domain.close()
        self.assertEqual(domain.snapshot(), first_close)
        reopened = SqliteMediaJobAdapter(repo.path, initialize_if_missing=False)
        jobs = reopened.list(request["workspaceRef"], request["productionRunRef"])
        self.assertEqual(len(jobs), 1); self.assertEqual(jobs[0]["attempts"], []); self.assertIsNone(jobs[0]["lease"])
        export_evidence("f01_T5_close_inflight", {"snapshots": snapshots, "closed": first_close,
            "events": domain.events, "writer": result, "jobsAfterReopen": jobs, "threadAlive": thread.is_alive()})

    def test_f01_unknown_file_and_lock_identity_cannot_be_acknowledged(self):
        from tests.support.generation_dispatch_binding_fixtures import export_evidence
        rows = []
        for fault in ("UNATTRIBUTED_FILE_CHANGE", "LOCK_IDENTITY_CHANGE"):
            root, repo, domain, coordination = self.fixture(); self.activate(coordination)
            before = domain._stamp
            lock = repo.path.with_name(repo.path.name + ".dispatch-lock")
            held = lock.with_name(lock.name + ".held-test-inode")
            if fault == "UNATTRIBUTED_FILE_CHANGE":
                info = repo.path.stat(); os.utime(repo.path, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
            else:
                lock.rename(held); lock.touch(mode=0o600)
            try:
                with self.assertRaises(c.DispatchError): domain.acknowledge_controlled_operations()
                self.assertEqual(domain._stamp, before)
                self.assertTrue(domain._uncertain)
            finally:
                if held.exists():
                    lock.unlink(); held.rename(lock)  # only remove the unheld injected inode
                domain.close()
            self.assertEqual(domain.state, "CLOSED_POISONED")
            with self.assertRaises(RuntimeError): ControlledStorageDomain(root, [repo.path])
            rows.append({"fault": fault, "closed": domain.snapshot(), "events": domain.events,
                "baselineUnchanged": domain._stamp == before, "marker": lock.read_text()})
        export_evidence("f01_T6_unknown_change", rows)

    def test_f01_cooperative_process_access_excludes_takeover_and_is_reaped(self):
        import json, select, subprocess, sys
        from tests.support.generation_dispatch_binding_fixtures import COOPERATIVE_ACCESS_HELPER, export_evidence
        from services.v4_platform.generation_dispatch_jobs import storage_access_snapshot
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        repo = SqliteMediaJobAdapter(root / "queue.sqlite3")
        repository = Path(__file__).resolve().parents[2]
        command = [sys.executable, "-c", COOPERATIVE_ACCESS_HELPER, str(root), str(repo.path), str(repository)]
        environment = dict(os.environ, TMPDIR=str(root), PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=environment)
        received, rest, errors = None, "", ""
        try:
            self.assertTrue(select.select([process.stdout], [], [], 10)[0], "bounded helper READY missing")
            received = json.loads(process.stdout.readline())
            self.assertEqual(received["phase"], "READY"); self.assertTrue(received["inTransaction"])
            self.assertGreater(received["access"]["activeAccesses"], 0)
            # Parent process has no local registration: the real flock holds it out.
            self.assertEqual(storage_access_snapshot(repo.path)["activeAccesses"], 0)
            with self.assertRaises(BlockingIOError): ControlledStorageDomain(root, [repo.path])
        finally:
            rest, errors = process.communicate("release\n", timeout=10)
        self.assertEqual(process.returncode, 0, errors)
        released = json.loads(rest.strip()); self.assertEqual(released["phase"], "RELEASED")
        self.assertEqual(released["access"]["activeAccesses"], 0)
        domain = ControlledStorageDomain(root, [repo.path])
        try:
            with self.assertRaises(BlockingIOError): ControlledStorageDomain(root, [repo.path])
            acquired = domain.snapshot()
        finally: domain.close()
        export_evidence("f01_T7_cooperative_process", {"ready": received, "released": released,
            "returncode": process.returncode, "stderr": errors, "parentTakeoverAfterExit": acquired,
            "closed": domain.snapshot(), "helperCodeSha256": __import__("hashlib").sha256(COOPERATIVE_ACCESS_HELPER.encode()).hexdigest()})

    def test_f01_connection_failure_rollback_close_and_native_context_lifetimes(self):
        from services.v4_platform import generation_dispatch_jobs as storage
        from tests.support.generation_dispatch_binding_fixtures import ForwardingSqliteConnection, export_evidence
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        repo = SqliteMediaJobAdapter(root / "queue.sqlite3")
        baseline = storage.storage_access_snapshot(repo.path)
        with patch.object(sqlite3, "connect", side_effect=sqlite3.OperationalError("synthetic open failure")):
            with self.assertRaises(sqlite3.OperationalError): repo._connect()
        self.assertEqual(storage.storage_access_snapshot(repo.path), baseline)
        connection = repo._connect()
        with connection:
            cursor = connection.execute("SELECT 1"); self.assertIs(cursor.connection, connection)
            self.assertEqual(cursor.fetchone()[0], 1)
        context_after = storage.storage_access_snapshot(repo.path)
        self.assertGreater(context_after["activeAccesses"], 0)
        with self.assertRaises(BlockingIOError): ControlledStorageDomain(root, [repo.path])
        self.assertEqual(connection.execute("SELECT 2").fetchone()[0], 2)
        cursor.close(); connection.close(); connection.close()
        self.assertEqual(storage.storage_access_snapshot(repo.path), baseline)
        cases = []
        for phase in ("BEFORE_ROLLBACK", "BEFORE_CLOSE"):
            path = root / (phase + ".sqlite3"); repository = SqliteMediaJobAdapter(path)
            original = sqlite3.connect; observed = []; fired = []
            def boundary(at, inner):
                observed.append({"phase": at, "inTransaction": inner.in_transaction if at != "AFTER_CLOSE" else "CLOSED"})
                if at == phase and not fired:
                    fired.append(at); raise sqlite3.OperationalError("synthetic uncertain cleanup")
            with patch.object(sqlite3, "connect", side_effect=lambda *a, **kw: ForwardingSqliteConnection(original(*a, **kw), boundary)):
                connection = repository._connect()
            connection.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                connection.rollback() if phase == "BEFORE_ROLLBACK" else connection.close()
            unresolved = storage.storage_access_snapshot(path)
            self.assertGreater(unresolved["activeAccesses"], 0)
            with self.assertRaises((BlockingIOError, RuntimeError)): ControlledStorageDomain(root, [path])
            connection.close()  # the same owner's explicit retry completes real close
            after = storage.storage_access_snapshot(path); self.assertEqual(after["activeAccesses"], 0)
            with self.assertRaises(RuntimeError): ControlledStorageDomain(root, [path])
            self.assertEqual(repository.list("test-workspace", "test-run"), [])
            cases.append({"injection": phase, "phases": observed, "unresolved": unresolved,
                "afterActualClose": after, "marker": path.with_name(path.name + ".dispatch-lock").read_text()})
        export_evidence("f01_T7_connection_lifetimes", {"before": baseline,
            "nativeContextAfter": context_after, "afterClose": storage.storage_access_snapshot(repo.path), "faults": cases})

    def fixture(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        repo = SqliteMediaJobAdapter(root / "queue.sqlite3")
        domain = ControlledStorageDomain(root, [repo.path]); self.addCleanup(domain.close)
        coordination = GenerationDispatchCoordination(storage_domain=domain)
        coordination.bind_repository(repo, workspace_ref="test-workspace", writers={"create": (), "save": (), "reserve_batch": ()}, readers=("get", "list"))
        return root, repo, domain, coordination

    def activate(self, coordination):
        coordination.activate([(obj, name) for obj, name, _, _ in coordination._bindings])

    def test_cooperative_exclusive_open_rejects_unregistered_adapter(self):
        root, repo, domain, coordination = self.fixture(); self.activate(coordination)
        self.assertEqual(repo.list("test-workspace", "test-run"), [])
        with self.assertRaises((c.DispatchError, RuntimeError)):
            SqliteMediaJobAdapter(repo.path, initialize_if_missing=False)
        with self.assertRaises((BlockingIOError, c.DispatchError)):
            ControlledStorageDomain(root, [repo.path])

    def test_missing_hook_and_closed_domain_fail_without_default_permission(self):
        root, repo, domain, coordination = self.fixture(); self.activate(coordination)
        original = repo.create
        repo.create = type(repo).create.__get__(repo)
        with self.assertRaises(c.DispatchError):
            with coordination.critical_section("test-workspace"):
                self.fail("missing hook entered gate")
        repo.create = original
        domain.close()
        with self.assertRaises(c.DispatchError):
            with coordination.critical_section("test-workspace"):
                self.fail("closed domain entered gate")

    def test_selector_aba_does_not_restore_revision_and_noop_is_stable(self):
        _, _, _, coordination = self.fixture()
        a, b = SimpleNamespace(read_current=lambda: "A"), SimpleNamespace(read_current=lambda: "B")
        selector = ControlledSourceSelection(a, coordination=coordination, workspace_ref="test-workspace",
            selector_kinds=("CURRENT_BACKEND_CONFIG",))
        self.activate(coordination)
        def revision():
            with coordination.critical_section("test-workspace") as lease:
                return coordination.revision(lease, "V4_BACKEND_CONFIG", "CURRENT_BACKEND_CONFIG", "test-run")
        self.assertEqual(revision(), 0)
        selector.select_port(a); self.assertEqual(revision(), 0)
        selector.select_port(b); self.assertEqual(revision(), 1)
        selector.select_port(a); self.assertEqual(revision(), 2)
        self.assertEqual(selector.read_current(), "A")

    def test_epoch_changes_on_reopen_and_old_lease_never_revalidates(self):
        root, repo, domain, coordination = self.fixture(); self.activate(coordination)
        with coordination.critical_section("test-workspace") as lease:
            epoch = lease.epoch
        with self.assertRaises(c.DispatchError): lease.assert_held()
        domain.close()
        next_domain = ControlledStorageDomain(root, [repo.path]); self.addCleanup(next_domain.close)
        next_coordination = GenerationDispatchCoordination(storage_domain=next_domain)
        self.assertNotEqual(next_coordination.epoch, epoch)
        with self.assertRaises(c.DispatchError):
            with next_coordination.critical_section("test-workspace"):
                self.fail("unenrolled epoch permitted operation")

    def test_scope_and_method_replacement_poison_fail_closed(self):
        _, _, _, coordination = self.fixture()
        port = SimpleNamespace(read_current=lambda: "original")
        selector = ControlledSourceSelection(port, coordination=coordination, workspace_ref="test-workspace",
            selector_kinds=("CURRENT_RUNTIME_PROCESS",))
        self.activate(coordination)
        with self.assertRaises(c.DispatchError):
            with coordination.critical_section("other-workspace"):
                self.fail("wrong workspace accepted")
        port.read_current = lambda: "replacement"
        with self.assertRaises(c.DispatchError): selector.read_current()
        self.assertIn("test-workspace", coordination._poisoned)
