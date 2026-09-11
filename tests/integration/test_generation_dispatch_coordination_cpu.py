"""Real Owner writes and transaction observations in the single-process workset."""
from copy import deepcopy
from threading import Event, Thread
import unittest

from apps.creator_workspace_mvp.project_foundation import ProjectFoundationApplicationService
from tests.unit.test_project_foundation import valid_command as foundation_command
from tests.support.generation_dispatch_binding_fixtures import BindingFixture, export_evidence, advance_native_m6
from services.v5_core_os.episode_production import generation_dispatch_contracts as c


def revisions(f):
    coordination = f.dispatch.coordination
    with coordination.critical_section(f.scope["workspaceRef"]) as lease:
        return {kind: coordination.revision(lease, owner, kind, f.scope[scope_field])
            for kind, (owner, scope_field) in c.SELECTORS.items()}


class GenerationDispatchCoordinationCpuTests(unittest.TestCase):
    def test_f01_shared_borrowed_connection_lasts_until_original_lease_exits(self):
        import os, sqlite3, tempfile
        from pathlib import Path
        from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
        from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation
        from services.v5_core_os.lifecycle_integrity.generation_dispatch_coordination import ControlledStorageDomain
        from services.v4_platform.generation_dispatch_jobs import storage_access_snapshot
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        assembly = LifecycleAssembly.sqlite(root / "lifecycle.sqlite3", initialize_or_upgrade=True)
        state = assembly.state; path = state.database_path
        repository = assembly.project_context._ProjectPublicBoundary__service.repository
        observed = []
        with state.lease(workspace_ref="test-workspace", operation=LifecycleOperation.CREATE_PROJECT):
            held = state.connection_or_none()
            for repeat in range(2):
                with repository._session() as borrowed:
                    self.assertIs(borrowed, held); self.assertIs(borrowed.row_factory, sqlite3.Row)
                    self.assertEqual(borrowed.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                    self.assertEqual(repository.list_projects("test-workspace"), [])
                self.assertTrue(held.in_transaction)
                self.assertEqual(held.execute("SELECT 1").fetchone()[0], 1)
                with self.assertRaises(BlockingIOError): ControlledStorageDomain(root, [path])
                observed.append({"repeat": repeat, "borrowedSameConnection": borrowed is held,
                    "inTransactionAfterBorrowerExit": held.in_transaction, "access": storage_access_snapshot(path)})
        self.assertIsNone(state.connection_or_none())
        with self.assertRaises(sqlite3.ProgrammingError): held.execute("SELECT 1")
        after = storage_access_snapshot(path); self.assertEqual(after["activeAccesses"], 0)
        domain = ControlledStorageDomain(root, [path]); domain.close()
        export_evidence("f01_T7_shared_borrowed", {"observations": observed, "afterLeaseExit": after,
            "closed": domain.snapshot(), "originalRowsAfterReopen": repository.list_projects("test-workspace")})

    def test_f01_lifecycle_close_failure_releases_original_lock_but_keeps_unresolved_access(self):
        import os, sqlite3, tempfile
        from pathlib import Path
        from unittest.mock import patch
        from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
        from services.v5_core_os.lifecycle_integrity.generation_dispatch_coordination import ControlledStorageDomain
        from services.v4_platform.generation_dispatch_jobs import storage_access_snapshot
        from tests.support.generation_dispatch_binding_fixtures import ForwardingSqliteConnection
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve(); os.chmod(root, 0o700)
        assembly = LifecycleAssembly.sqlite(root / "lifecycle.sqlite3", initialize_or_upgrade=True)
        state = assembly.state; path = state.database_path
        original = sqlite3.connect; phases, fired = [], []
        def observer(phase, inner):
            phases.append(phase)
            if phase == "BEFORE_CLOSE" and not fired:
                fired.append(phase); raise sqlite3.OperationalError("synthetic lifecycle close uncertainty")
        with patch.object(sqlite3, "connect", side_effect=lambda *a, **kw: ForwardingSqliteConnection(original(*a, **kw), observer)):
            with self.assertRaises(sqlite3.OperationalError):
                with state.read_snapshot(): held = state.read_connection_or_none()
        self.assertFalse(state._lock._is_owned())
        unresolved = storage_access_snapshot(path); self.assertGreater(unresolved["activeAccesses"], 0)
        with self.assertRaises(BlockingIOError): ControlledStorageDomain(root, [path])
        held.close()
        after = storage_access_snapshot(path); self.assertEqual(after["activeAccesses"], 0)
        with self.assertRaises(RuntimeError): ControlledStorageDomain(root, [path])
        export_evidence("f01_T7_lifecycle_close_uncertain", {"phases": phases, "unresolved": unresolved,
            "afterActualClose": after, "originalLockOwnedAfterFailure": state._lock._is_owned(),
            "marker": path.with_name(path.name + ".dispatch-lock").read_text()})

    def test_m5_actual_binding_writes_invalidate_both_rows_and_aba_does_not_restore(self):
        f = BindingFixture(self)
        before = revisions(f)
        w, p, s = (f.scope[k] for k in ("workspaceRef", "projectRef", "seriesRef"))
        original = f.assembly.series_planning.get_workspace(w, p, s)
        current = original["plan"]
        bindings = next(v for v in original["versions"] if v["seriesPlanVersionRef"] == current["confirmedSeriesPlanVersionRef"])["episodePlanItemBindings"]
        stages = []
        # Original M5 version/confirmation operations, A content -> unbound B -> A content.
        for selected_bindings in ([], bindings):
            value = f.assembly.series_planning.create_episode_plan_item_binding_version({
                "workspaceRef": w, "projectRef": p, "seriesRef": s,
                "seriesPlanRef": current["seriesPlanRef"], "expectedPlanVersion": current["version"],
                "episodePlanItemBindings": deepcopy(selected_bindings)})
            command = {"workspaceRef": w, "seriesPlanRef": value["plan"]["seriesPlanRef"],
                "seriesPlanVersionRef": value["version"]["seriesPlanVersionRef"],
                "expectedPlanVersion": value["plan"]["version"], "humanConfirmed": True}
            confirmed = f.assembly.series_planning.confirm_version(command)
            current = f.assembly.series_planning.get_workspace(w, p, s)["plan"]
            stages.append(revisions(f))
        for kind in ("CURRENT_CONFIRMED_SERIES_PLAN", "CURRENT_EPISODE_PLAN_BINDING"):
            self.assertGreater(stages[0][kind], before[kind]); self.assertGreater(stages[1][kind], stages[0][kind])
        denied = f.dispatch.boundary.prepare(f.prepare_command())
        self.assertIn("code", denied)
        export_evidence("m5_binding_actual_aba", {"before": before, "stages": stages, "oldPlanPreparation": denied,
            "writerObservations": f.dispatch.coordination.observations})

    def test_composite_foundation_participants_share_outer_lease_and_gate(self):
        f = BindingFixture(self); before = revisions(f)
        assembly = f.assembly
        service = ProjectFoundationApplicationService(assembly.project_foundation_store, assembly.coordinator,
            assembly.series_episode, assembly.project_context)
        command = foundation_command(key="test-pkg2-composite")
        first = service.execute(f.scope["workspaceRef"], command)
        after = revisions(f)
        second = service.execute(f.scope["workspaceRef"], command)
        replay = revisions(f)
        self.assertEqual(after, replay)
        self.assertGreater(after["CURRENT_PROJECT"], before["CURRENT_PROJECT"])
        self.assertGreater(after["CURRENT_SERIES"], before["CURRENT_SERIES"])
        observations = f.dispatch.coordination.observations
        for method in ("reserve", "complete", "create_series", "create_project"):
            observed = [row for row in observations if row.get("method") == method]
            self.assertTrue(observed, method); self.assertTrue(all(row["gateHeld"] for row in observed))
        self.assertTrue(any(row.get("method") == "lease" and row["committedChanges"] > 0 for row in observations))
        export_evidence("foundation_composite_gate", {"before": before, "after": after, "afterReplay": replay,
            "first": first, "replay": second, "observations": observations})

    def test_actual_issue_transaction_excludes_source_writer_until_commit(self):
        import sys
        import traceback
        from threading import get_ident
        from time import monotonic_ns
        from services.v4_platform import generation_dispatch_jobs as storage

        f, thread, primary_error = None, None, None
        transaction_reached, attempted, finished = Event(), Event(), Event()
        start_claimed = False
        errors, observations, timeline = [], [], []
        evidence = {"issue": "NOT_RETURNED", "issueException": "NOT_OBSERVED",
            "observerException": "NOT_OBSERVED", "writerException": "NOT_OBSERVED",
            "testException": "NOT_OBSERVED", "afterWriterPrepare": "NOT_OBSERVED",
            "methodOutcome": "NOT_FINISHED", "exportErrors": [],
            "physicalCommitTime": "NOT_OBSERVED"}

        def record(phase, **values):
            timeline.append({"phase": phase, "monotonicNs": monotonic_ns(),
                "threadId": get_ident(), **values})

        def exception_value(exc):
            return {"type": type(exc).__name__, "message": str(exc),
                "traceback": traceback.format_exc()}

        def resources():
            if f is None:
                return "NOT_OBSERVED"
            domain = f.domain
            # Primitive observations only: do not take another gate or query SQLite.
            return {"atomicSnapshot": False, "domainState": domain.state,
                "closing": domain._closing, "activeEntries": domain._entries,
                "uncertain": domain._uncertain, "ownedLockCount": len(domain._locks),
                "registrationCount": len(domain._registrations),
                "installationCount": len(domain._installations),
                "activeStorageAccesses": dict(storage._ACCESS_COUNTS),
                "controlledRegistrations": list(storage._CONTROLLED_STORAGE),
                "threadStarted": thread is not None and thread.ident is not None,
                "threadAlive": thread.is_alive() if thread is not None else False}

        def export_cleanup():
            # Registered first, so the original fixture cleanups run before this.
            record("AFTER_ORIGINAL_FIXTURE_CLEANUP")
            try:
                export_evidence("source_writer_excluded_through_commit_cleanup", {
                    "timeline": timeline, "resources": resources(),
                    "domainEvents": deepcopy(f.domain.events) if f is not None else "NOT_OBSERVED",
                    "earlierExportErrors": evidence["exportErrors"]})
            except BaseException:
                print("TEST_CLEANUP_EVIDENCE_EXPORT_FAILED", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                raise

        self.addCleanup(export_cleanup)

        def writer():
            record("WRITER_STARTED")
            try:
                record("WRITER_ATTEMPTED")
                attempted.set()
                result = f.assembly.project_context.archive_project(f.scope["workspaceRef"], f.scope["projectRef"])
                evidence["writerResult"] = result
                record("WRITER_RETURNED")
            except BaseException as exc:
                errors.append(repr(exc))
                evidence["writerException"] = exception_value(exc)
                record("WRITER_EXCEPTION", errorType=type(exc).__name__)
            finally:
                finished.set()
                record("WRITER_FINISHED", finished=finished.is_set())

        def clock_observer():
            nonlocal thread, start_claimed
            try:
                connection = getattr(f.dispatch.coordination._thread, "transaction", None)
                target = connection is not None and connection.path == f.evidence.database_path
                active = connection.inner.in_transaction if connection is not None else False
                record("CLOCK_OBSERVATION", targetEvidence=target, inTransaction=active,
                    transactionPresent=connection is not None, startClaimed=start_claimed)
                if not target or not active or start_claimed:
                    return
                # Claim before starting: later/nested clock callbacks cannot start again.
                start_claimed = True
                transaction_reached.set()
                record("TARGET_TRANSACTION_REACHED", inTransaction=active,
                    evidencePath=str(connection.path))
                thread = Thread(target=writer, name="pkg2-source-writer")
                record("WRITER_START_CALL")
                thread.start()
                record("WRITER_START_RETURN", writerThreadId=thread.ident)
                record("ATTEMPT_HANDSHAKE_BEGIN", timeoutSeconds=5)
                signalled = attempted.wait(5)
                record("ATTEMPT_HANDSHAKE_END", signalled=signalled)
                observations.append({"monotonicNs": monotonic_ns(), "threadId": get_ident(),
                    "inTransaction": connection.inner.in_transaction,
                    "targetEvidence": target, "sourceWriterAttempted": attempted.is_set(),
                    "sourceWriterFinishedBeforeCommit": finished.is_set()})
                self.assertTrue(signalled, "source writer did not attempt within transaction handshake")
                self.assertIs(getattr(f.dispatch.coordination._thread, "transaction", None), connection)
                self.assertTrue(connection.inner.in_transaction)
                self.assertFalse(finished.is_set())
            except BaseException as exc:
                evidence["observerException"] = exception_value(exc)
                record("OBSERVER_EXCEPTION", errorType=type(exc).__name__)
                raise

        record("TEST_METHOD_BEGIN")
        try:
            f = BindingFixture(self)
            record("FIXTURE_READY")
            previous_observer = f.clock.on_now
            f.clock.on_now = clock_observer
            record("ISSUE_BEGIN")
            try:
                issued = f.issue()
                evidence["issue"] = issued
                record("ISSUE_RETURNED")
            except BaseException as exc:
                evidence["issueException"] = exception_value(exc)
                record("ISSUE_EXCEPTION", errorType=type(exc).__name__)
                raise
            finally:
                record("ISSUE_END")
                f.clock.on_now = previous_observer
                record("OBSERVER_RESTORED")
                # Cleanup never signals transaction_reached or starts a writer.
                if thread is not None and thread.ident is not None:
                    record("WRITER_JOIN_BEGIN", timeoutSeconds=10, threadAlive=thread.is_alive())
                    thread.join(10)
                    record("WRITER_JOIN_END", threadAlive=thread.is_alive())
                else:
                    record("WRITER_JOIN_NOT_STARTED")
            self.assertTrue(transaction_reached.is_set(), "target evidence transaction was not observed")
            self.assertIsNotNone(thread)
            self.assertEqual(sum(row["phase"] == "WRITER_STARTED" for row in timeline), 1)
            self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
            self.assertIn("grant", issued, issued); self.assertTrue(observations)
            self.assertEqual(issued["sendPermission"], "NONE")
            self.assertFalse(issued["recordReplay"])
            self.assertTrue(attempted.is_set()); self.assertTrue(finished.is_set())
            self.assertEqual(len([r for r in f.records() if r["recordKind"] == "GenerationDispatchGrant"]), 1)
            record("AFTER_WRITER_PREPARE_BEGIN")
            after = f.dispatch.boundary.prepare(f.prepare_command())
            evidence["afterWriterPrepare"] = after
            record("AFTER_WRITER_PREPARE_RETURNED")
            self.assertIn("code", after)
            evidence["methodOutcome"] = "ASSERTIONS_COMPLETED"
        except BaseException as exc:
            primary_error = exc
            evidence["testException"] = exception_value(exc)
            evidence["methodOutcome"] = "EXCEPTION_OR_ASSERTION"
            record("TEST_METHOD_EXCEPTION", errorType=type(exc).__name__)
            raise
        finally:
            record("TEST_METHOD_FINALLY")
            try:
                evidence.update(transactionReached=transaction_reached.is_set(),
                    writerStartClaimed=start_claimed, attempted=attempted.is_set(), finished=finished.is_set(),
                    errors=list(errors), observations=deepcopy(observations), timeline=list(timeline),
                    resourcesBeforeFixtureCleanup=resources(),
                    writerObservations=deepcopy(f.dispatch.coordination.observations) if f is not None else "NOT_OBSERVED")
                export_evidence("source_writer_excluded_through_commit", evidence)
            except BaseException as exc:
                evidence["exportErrors"].append(exception_value(exc))
                print("TEST_EVIDENCE_EXPORT_FAILED", repr(evidence), file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if primary_error is None:
                    raise
                primary_error.add_note("Evidence export also failed; see TEST_EVIDENCE_EXPORT_FAILED stderr.")

    def test_removed_real_writer_hook_and_domain_loss_refuse_before_issue(self):
        f = BindingFixture(self)
        repository = f.assembly.project_context._ProjectPublicBoundary__service.repository
        installed = repository.archive_project
        repository.archive_project = type(repository).archive_project.__get__(repository)
        denied = f.dispatch.boundary.prepare(f.prepare_command())
        self.assertEqual(denied["code"], "CURRENTNESS_FENCE_UNAVAILABLE")
        repository.archive_project = installed
        original_path = repository.database_path
        repository.database_path = f.queue_path
        changed_path = f.dispatch.boundary.prepare(f.prepare_command())
        self.assertEqual(changed_path["code"], "CURRENTNESS_FENCE_UNAVAILABLE")
        repository.database_path = original_path
        root = f.dispatch.source.root
        original_reader = root.project_reader
        root.project_reader = object()
        changed_reader = f.dispatch.boundary.prepare(f.prepare_command())
        self.assertEqual(changed_reader["code"], "CURRENTNESS_FENCE_UNAVAILABLE")
        root.project_reader = original_reader
        from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
        with self.assertRaises(Exception):
            LifecycleAssembly.sqlite(f.root / "lifecycle.sqlite3", initialize_or_upgrade=True)
        f.domain.close()
        denied_closed = f.dispatch.boundary.prepare(f.prepare_command())
        self.assertEqual(denied_closed["code"], "CURRENTNESS_FENCE_UNAVAILABLE")
        export_evidence("real_writer_coverage_missing", {"missingHook": denied,
            "changedStoragePath": changed_path, "changedFormalReader": changed_reader, "closedDomain": denied_closed})

    def test_input_script_and_m6_original_writers_invalidate_their_selectors(self):
        f = BindingFixture(self); before = revisions(f)
        original_records = f.records()
        new_input = f.boundary.create_method_aware_input_plan({**f.scope,
            "executionMethodPlanVersionRef": f.plan["executionMethodPlanVersionRef"],
            "assetBindings": [f.binding(f.asset)], "idempotencyKey": "test-pkg2-input-successor"})
        after_input = revisions(f)
        self.assertGreater(after_input["CURRENT_INPUT_PLAN"], before["CURRENT_INPUT_PLAN"])
        self.assertIn("code", f.dispatch.boundary.prepare(f.prepare_command()))
        old_script = f.seed["boundScript"]["scriptVersion"]
        content = {key: deepcopy(old_script[key]) for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
        content["scenes"][0]["productionNotes"].append("TEST_ONLY revised script observation")
        version = f.assembly.script_studio.create_version({**{k:f.scope[k] for k in ("workspaceRef", "projectRef", "seriesRef", "episodeRef")},
            "scriptRef": f.seed["boundScript"]["script"]["scriptRef"], "baseScriptVersionRef": old_script["scriptVersionRef"],
            "changeKind": "manual-edit", "content": content})
        f.assembly.script_studio.confirm_version({**{k:f.scope[k] for k in ("workspaceRef", "seriesRef", "episodeRef")},
            "scriptRef": version["script"]["scriptRef"], "scriptVersionRef": version["scriptVersion"]["scriptVersionRef"],
            "expectedScriptVersion": version["script"]["version"], "humanConfirmed": True})
        after_script = revisions(f)
        self.assertGreater(after_script["CURRENT_CONFIRMED_SCRIPT"], after_input["CURRENT_CONFIRMED_SCRIPT"])
        m6 = advance_native_m6(f.seed, f.scope["workspaceRef"])
        after_m6 = revisions(f)
        self.assertGreater(after_m6["ACTIVE_M6_BINDING"], after_script["ACTIVE_M6_BINDING"])
        self.assertEqual(f.records()[:len(original_records)], original_records)
        self.assertEqual(f.jobs(), [])
        export_evidence("input_script_m6_writer_changes", {"before": before, "afterInput": after_input,
            "afterScript": after_script, "afterM6": after_m6, "newInputPlan": new_input, "newM6": m6,
            "historyBefore": original_records, "historyAfter": f.records(), "observations": f.dispatch.coordination.observations})

    def test_canonical_registration_joins_actual_participants_and_rolls_back_failure(self):
        from tests.unit.test_canonical_registration import registration_command, subject_from_preflight, ExactSubjectAuthority
        f = BindingFixture(self); before = revisions(f)
        boundary = f.assembly.canonical_registration
        command = registration_command(); command["workspaceRef"] = f.scope["workspaceRef"]
        command["registrationKey"] = "test-pkg2-other-canonical"; command["idempotencyKey"] = "test-pkg2-register"
        preflight = boundary.preflight(command)
        service = boundary._CanonicalRegistrationPublicBoundary__service
        service.acceptance_authority = ExactSubjectAuthority(subject_from_preflight(preflight))
        original_fault = service._fault_hook
        phases = []
        def fail(point):
            phases.append(point)
            if point == "before-registration-receipt": raise RuntimeError("TEST_ONLY before receipt failure")
        service._fault_hook = fail
        # The accepted callback point name is asserted by the original service;
        # the successful case below still uses its original authority/write path.
        try:
            with self.assertRaises(Exception): boundary.register(command)
        finally: service._fault_hook = original_fault
        self.assertIn("before-registration-receipt", phases)
        after_failure = revisions(f)
        self.assertEqual(after_failure, before)
        successful = boundary.register(command)
        after = revisions(f)
        self.assertGreater(after["CURRENT_PROJECT"], before["CURRENT_PROJECT"])
        self.assertGreater(after["CURRENT_EPISODE"], before["CURRENT_EPISODE"])
        self.assertGreater(after["CURRENT_CONFIRMED_SCRIPT"], before["CURRENT_CONFIRMED_SCRIPT"])
        export_evidence("canonical_composite_rollback", {"before": before, "afterRollback": after_failure,
            "afterCommit": after, "result": successful, "faultPhases": phases,
            "observations": f.dispatch.coordination.observations})

    def test_source_commit_unknown_invalidates_and_poison_cannot_be_read_back_away(self):
        import sqlite3
        from unittest.mock import patch
        from services.v5_core_os.project_engine.foundation import SqliteProjectAdapter
        f = BindingFixture(self); before = revisions(f)
        original_connect = sqlite3.connect
        observations = []
        class Connection:
            def __init__(self, inner): object.__setattr__(self, "inner", inner)
            def __getattr__(self, name): return getattr(self.inner, name)
            def __setattr__(self, name, value): setattr(self.inner, name, value)
            def commit(self):
                changes = self.inner.total_changes
                self.inner.commit()
                if changes:
                    observations.append({"actualCommitReturned": True, "changes": changes})
                    raise OSError("TEST_ONLY source commit receipt loss")
        def connect(path, *args, **kwargs):
            inner = original_connect(path, *args, **kwargs)
            return Connection(inner) if str(path) == str(f.root / "lifecycle.sqlite3") else inner
        with patch.object(sqlite3, "connect", connect):
            with self.assertRaises(Exception):
                f.assembly.project_context.archive_project(f.scope["workspaceRef"], f.scope["projectRef"])
        self.assertTrue(observations)
        after = {kind: f.dispatch.coordination._counters[(f.scope["workspaceRef"], owner, kind, f.scope[scope_field])]
            for kind, (owner, scope_field) in c.SELECTORS.items()}
        self.assertGreater(after["CURRENT_PROJECT"], before["CURRENT_PROJECT"])
        self.assertIn(f.scope["workspaceRef"], f.dispatch.coordination._poisoned)
        denied = f.dispatch.boundary.prepare(f.prepare_command())
        self.assertEqual(denied["code"], "CURRENTNESS_FENCE_UNAVAILABLE")
        f.domain.close()
        repository = SqliteProjectAdapter(f.root / "lifecycle.sqlite3")
        restored = repository.get_project(f.scope["workspaceRef"], f.scope["projectRef"])
        self.assertEqual(restored.status, "archived")
        export_evidence("source_unknown_poison", {"before": before, "afterUnknown": after,
            "commitObservations": observations, "denied": denied, "reopenedProjectStatus": restored.status,
            "domainRemainsPoisoned": f.scope["workspaceRef"] in f.dispatch.coordination._poisoned})
