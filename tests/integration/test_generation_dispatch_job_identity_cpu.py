"""Two original SQLite adapters, durable replay and pre-claim refusal."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3
import unittest
from unittest.mock import patch

from services.v4_platform.generation_dispatch_jobs import internal_dispatch_key
from services.v4_platform.media_jobs import SqliteMediaJobAdapter, MediaJobError, MediaJobConflictError, InMemoryMediaJobAdapter
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_routing import GenerationDispatchRouting
from tests.support.generation_dispatch_binding_fixtures import BindingFixture, export_evidence


class GenerationDispatchJobIdentityCpuTests(unittest.TestCase):
    def test_two_real_adapters_different_caller_keys_one_uuid_and_reopen(self):
        f = BindingFixture(self)
        issued = f.issue(); self.assertIn("grant", issued, issued)
        grant = issued["grant"]
        routers = [GenerationDispatchRouting(foundation=f.dispatch.boundary._foundation,
            source_reader=f.dispatch.source, coordinator=q) for q in f.coordinators]
        barrier = Barrier(2)
        def call(index):
            barrier.wait(5)
            return f.route(grant, "test-concurrent-" + str(index), routing=routers[index])
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(call, index) for index in range(2)]
            routes = [future.result(timeout=60) for future in futures]
        jobs = f.jobs(); self.assertEqual(len(jobs), 1)
        self.assertEqual({r["queuedJobs"][0]["mediaJobRef"] for r in routes}, {jobs[0]["jobRef"]})
        self.assertEqual(jobs[0]["idempotencyKey"], internal_dispatch_key(f.scope["workspaceRef"], f.scope["productionRunRef"], grant["generationDispatchGrantRef"]))
        self.assertEqual(jobs[0]["attempts"], []); self.assertIsNone(jobs[0]["lease"])
        observations = deepcopy(f.dispatch.coordination.observations)
        f.domain.close()
        reopened = SqliteMediaJobAdapter(f.queue_path, initialize_if_missing=False)
        after = reopened.list(f.scope["workspaceRef"], f.scope["productionRunRef"])
        self.assertEqual(after, jobs)
        replay, was_replay = reopened.create({**deepcopy(jobs[0]), "jobRef": "media-job-unused-new-uuid"})
        self.assertTrue(was_replay); self.assertEqual(replay, jobs[0])
        self.assertEqual(reopened.list(f.scope["workspaceRef"], f.scope["productionRunRef"]), jobs)
        export_evidence("concurrent_queue_reopen", {"routes": routes, "beforeClose": jobs, "afterReopen": after,
            "originalCreateReplay": replay, "writerObservations": observations,
            "twoAdapterObjects": f.queues[0] is not f.queues[1]})

    def test_binding_conflict_cancellation_replay_and_original_workers_refuse(self):
        f = BindingFixture(self)
        issued = f.issue(); self.assertIn("grant", issued, issued)
        f.route(issued["grant"])
        original = f.jobs()[0]
        w, r, j = f.scope["workspaceRef"], f.scope["productionRunRef"], original["jobRef"]
        coordinator = f.coordinators[0]
        self.assertIsNone(coordinator.lease_next(w, r, "test-old-worker"))
        for operation in (lambda: coordinator.lease_job(w, r, j, "test-old-worker"),
                lambda: coordinator.run_one(w, r, j, "test-old-worker"),
                lambda: coordinator.run_leased(original, "test-old-worker")):
            with self.assertRaises(MediaJobError): operation()
        self.assertEqual(coordinator.recover_expired(w, r), [])
        self.assertEqual(f.jobs(), [original]); self.assertEqual(coordinator.adapter.generate_calls, 0)
        changed = deepcopy(original)
        for value in (changed, changed["request"], changed["executionEnvelope"]):
            value["dispatchGrantBinding"]["generationDispatchGrantDigest"] = "f" * 64
        changed["request"] = c.sealed(changed["request"])
        changed["requestDigest"] = changed["request"]["payloadDigest"]
        changed["executionEnvelope"]["generationRequestDigest"] = changed["requestDigest"]
        changed["executionEnvelope"] = c.sealed(changed["executionEnvelope"], "envelopeDigest")
        with self.assertRaises(MediaJobConflictError): f.queues[1].create(changed)
        self.assertEqual(f.jobs(), [original])
        memory = InMemoryMediaJobAdapter()
        self.assertFalse(memory.create(original)[1]); self.assertTrue(memory.create(original)[1])
        with self.assertRaises(MediaJobConflictError): memory.create(changed)
        cancelled = coordinator.cancel(w, r, j)
        self.assertEqual(cancelled["state"], "CANCELLED")
        replay = f.route(issued["grant"], "test-route-after-cancellation")
        self.assertEqual(replay["queuedJobs"][0]["queueState"], "CANCELLED")
        self.assertEqual(f.jobs(), [cancelled])
        self.assertEqual([record for record in f.records() if record["recordKind"] == "GenerationDispatchGrantTerminal"], [])
        export_evidence("worker_refusal_conflict_cancel", {"originalJob": original, "afterCancellation": cancelled,
            "replayRoute": replay, "jobsAfter": f.jobs(), "generateCalls": coordinator.adapter.generate_calls,
            "sqliteAndMemoryReplayCompared": True, "writerObservations": f.dispatch.coordination.observations})

    def test_commit_receipt_loss_poison_and_reopen_recovers_one_original_job(self):
        import json
        import sys
        import time
        import traceback
        from threading import get_ident
        from services.v4_platform.generation_dispatch_jobs import _UNCERTAIN

        f = None; primary_error = None
        timeline = []
        evidence = {"issueResult": "NOT_OBSERVED", "routeResult": "NOT_RETURNED",
            "routeException": "NOT_OBSERVED", "sameDomainNextRoute": "NOT_OBSERVED",
            "reopenedJobs": "NOT_OBSERVED", "originalCreateReplay": "NOT_OBSERVED",
            "jobsAfterReplay": "NOT_OBSERVED", "closeResult": "NOT_OBSERVED",
            "testException": "NOT_OBSERVED", "methodOutcome": "STARTED", "exportErrors": []}
        def record(phase, **facts):
            timeline.append({"phase": phase, "monotonic": time.monotonic(), "thread": get_ident(), **facts})
        def exception_value(exc):
            # Retain actual exception identities/edges without serializing objects
            # or making a cause/context cycle into a recursive JSON structure.
            nodes, seen = [], {}
            def visit(current):
                if current is None: return None
                if id(current) in seen: return seen[id(current)]
                index = len(nodes); seen[id(current)] = index
                node = {"index": index, "type": type(current).__name__, "code": getattr(current, "code", None),
                    "gateExitDiagnostics": deepcopy(list(getattr(current, "_gate_exit_diagnostics", ())))}
                nodes.append(node)
                node["cause"] = visit(current.__cause__); node["context"] = visit(current.__context__)
                return index
            visit(exc)
            text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            if f is not None: text = text.replace(str(f.root), "<PRIVATE_TEST_ROOT>")
            return {"nodes": nodes, "traceback": text}
        def resources():
            if f is None: return "NOT_OBSERVED"
            coordination = f.dispatch.coordination
            lock = coordination._locks.get(f.scope["workspaceRef"])
            return {"domain": f.domain.snapshot(), "depth": getattr(coordination._thread, "depth", 0),
                "poisoned": f.scope["workspaceRef"] in coordination._poisoned,
                "active": coordination._active, "epoch": coordination.epoch,
                "gateOwnedByCurrentThread": lock._is_owned() if lock is not None else "NOT_CREATED"}
        def after_fixture_cleanup():
            record("AFTER_ORIGINAL_FIXTURE_CLEANUPS")
            export_evidence("unknown_queue_commit_cleanup", {"resources": resources(), "timeline": list(timeline)})
        self.addCleanup(after_fixture_cleanup)
        original_connect = sqlite3.connect
        observed = {"committed": 0, "raisedAfterCommit": 0}
        class Connection:
            def __init__(self, inner): object.__setattr__(self, "inner", inner)
            def __getattr__(self, name): return getattr(self.inner, name)
            def __setattr__(self, name, value): setattr(self.inner, name, value)
            def execute(self, sql, *args):
                result = self.inner.execute(sql, *args)
                operation = sql.split()[0].upper()
                if operation in ("BEGIN", "INSERT"):
                    record("SQL_" + operation + "_RETURNED", inTransaction=self.inner.in_transaction)
                    if operation == "INSERT" and "v4_media_jobs" in sql:
                        evidence["jobPassedToActualInsert"] = json.loads(args[0][-1])
                return result
            def commit(self):
                changes = self.inner.total_changes
                record("SQLITE_COMMIT_CALL", inTransaction=self.inner.in_transaction, totalChanges=changes)
                self.inner.commit()
                record("SQLITE_COMMIT_RETURNED", inTransaction=self.inner.in_transaction, totalChanges=self.inner.total_changes)
                if changes and not observed["raisedAfterCommit"]:
                    observed["committed"] += changes; observed["raisedAfterCommit"] += 1
                    record("RECEIPT_LOSS_INJECTED_AFTER_COMMIT")
                    raise OSError("TEST_ONLY receipt lost after actual SQLite commit")
            def rollback(self):
                record("SQLITE_ROLLBACK_CALL", inTransaction=self.inner.in_transaction)
                result = self.inner.rollback()
                record("SQLITE_ROLLBACK_RETURNED", inTransaction=self.inner.in_transaction)
                return result
            def close(self):
                record("SQLITE_CLOSE_CALL", inTransaction=self.inner.in_transaction)
                result = self.inner.close(); record("SQLITE_CLOSE_RETURNED")
                return result
        def connect(path, *args, **kwargs):
            inner = original_connect(path, *args, **kwargs)
            return Connection(inner) if str(path) == str(f.queue_path) else inner
        try:
            record("FIXTURE_BEGIN"); f = BindingFixture(self); record("FIXTURE_READY")
            record("ISSUE_BEGIN"); issued = f.issue(); evidence["issueResult"] = deepcopy(issued); record("ISSUE_RETURNED")
            self.assertIn("grant", issued, issued); self.assertEqual(issued["sendPermission"], "NONE")
            before_records = f.records(); evidence["recordsBeforeRoute"] = before_records
            with patch.object(sqlite3, "connect", connect):
                with self.assertRaises(c.CommitOutcomeUnknown) as unknown:
                    record("ROUTE_BEGIN")
                    try:
                        evidence["routeResult"] = f.route(issued["grant"])
                        record("ROUTE_RETURNED")
                    except BaseException as exc:
                        evidence["routeException"] = exception_value(exc)
                        record("ROUTE_RAISED", errorType=type(exc).__name__)
                        raise
            evidence["afterUnknown"] = resources()
            self.assertIs(type(unknown.exception), c.CommitOutcomeUnknown)
            self.assertIsInstance(unknown.exception.__cause__, OSError)
            self.assertIn("receipt lost after actual SQLite commit", str(unknown.exception.__cause__))
            self.assertIs(unknown.exception.__context__, unknown.exception.__cause__)
            self.assertIsNone(unknown.exception.__cause__.__cause__)
            self.assertIsNone(unknown.exception.__cause__.__context__)
            self.assertEqual(list(unknown.exception._gate_exit_diagnostics), [{"phase": "ACKNOWLEDGE",
                "errorType": "DispatchError", "code": "CURRENTNESS_FENCE_UNAVAILABLE"}])
            self.assertEqual(observed["raisedAfterCommit"], 1)
            self.assertIn(f.scope["workspaceRef"], f.dispatch.coordination._poisoned)
            self.assertTrue(f.domain._uncertain); self.assertEqual(f.domain._entries, 0)
            self.assertEqual(f.dispatch.coordination._thread.depth, 0)
            self.assertFalse(evidence["afterUnknown"]["gateOwnedByCurrentThread"])
            with self.assertRaises(c.DispatchError) as refusal:
                record("SAME_DOMAIN_NEXT_ROUTE_BEGIN")
                try: f.route(issued["grant"], "test-no-auto-retry")
                except BaseException as exc:
                    evidence["sameDomainNextRoute"] = exception_value(exc); record("SAME_DOMAIN_NEXT_ROUTE_RAISED", errorType=type(exc).__name__)
                    raise
            self.assertEqual(refusal.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")
            observations = deepcopy(f.dispatch.coordination.observations)
            record("DOMAIN_CLOSE_BEGIN")
            try: f.domain.close()
            except BaseException as exc:
                evidence["closeResult"] = exception_value(exc); raise
            evidence["closeResult"] = "RETURNED"; record("DOMAIN_CLOSE_RETURNED")
            evidence["afterExplicitClose"] = resources()
            self.assertEqual(f.domain.state, "CLOSED_POISONED")
            markers = {p.name: p.with_name(p.name + ".dispatch-lock").read_bytes() for p in f.domain.paths}
            self.assertTrue(all(value.startswith(_UNCERTAIN) for value in markers.values()))
            evidence["markersBeforeHistory"] = {p: value.decode("ascii") for p, value in markers.items()}
            reopened = SqliteMediaJobAdapter(f.queue_path, initialize_if_missing=False)
            durable = reopened.list(f.scope["workspaceRef"], f.scope["productionRunRef"])
            evidence["reopenedJobs"] = durable; record("HISTORY_REOPEN_READ_RETURNED", jobCount=len(durable))
            self.assertEqual(len(durable), 1)
            self.assertEqual(durable[0], evidence["jobPassedToActualInsert"])
            self.assertEqual(durable[0]["idempotencyKey"], internal_dispatch_key(f.scope["workspaceRef"],
                f.scope["productionRunRef"], issued["grant"]["generationDispatchGrantRef"]))
            self.assertEqual(durable[0]["attempts"], []); self.assertIsNone(durable[0]["lease"])
            replay, repeated = reopened.create(durable[0])
            evidence.update(originalCreateReplay=replay, replayed=repeated); record("EXACT_HISTORY_REPLAY_RETURNED", replayed=repeated)
            self.assertTrue(repeated); self.assertEqual(replay, durable[0])
            after = reopened.list(f.scope["workspaceRef"], f.scope["productionRunRef"])
            evidence["jobsAfterReplay"] = after; self.assertEqual(after, durable)
            original_evidence = type(f.evidence)(f.evidence.database_path, initialize_if_missing=False)
            after_records = original_evidence.list_records(f.scope["workspaceRef"], f.scope["productionRunRef"])
            evidence["recordsAfterReopen"] = after_records
            self.assertEqual(after_records, before_records)
            self.assertEqual([r for r in after_records if r["recordKind"] == "GenerationDispatchGrantTerminal"], [])
            evidence["adapterGenerateCalls"] = [q.adapter.generate_calls for q in f.coordinators]
            self.assertEqual(evidence["adapterGenerateCalls"], [0, 0])
            after_markers = {p.name: p.with_name(p.name + ".dispatch-lock").read_bytes() for p in f.domain.paths}
            evidence["markersAfterHistory"] = {p: value.decode("ascii") for p, value in after_markers.items()}
            self.assertEqual(after_markers, markers)
            self.assertTrue(f.domain._uncertain); self.assertIn(f.scope["workspaceRef"], f.dispatch.coordination._poisoned)
            with self.assertRaises(c.DispatchError):
                with f.dispatch.coordination.critical_section(f.scope["workspaceRef"]): self.fail("history revived closed domain")
            evidence.update(observations=observations, methodOutcome="ASSERTIONS_COMPLETED")
        except BaseException as exc:
            primary_error = exc; evidence["testException"] = exception_value(exc)
            evidence["methodOutcome"] = "EXCEPTION_OR_ASSERTION"; record("TEST_EXCEPTION", errorType=type(exc).__name__)
            raise
        finally:
            record("TEST_FINALLY")
            try:
                evidence.update(actualCommitObservation=observed, timeline=list(timeline), resourcesBeforeFixtureCleanup=resources(),
                    domainPoisoned=f.scope["workspaceRef"] in f.dispatch.coordination._poisoned if f is not None else "NOT_OBSERVED",
                    observations=deepcopy(f.dispatch.coordination.observations) if f is not None else "NOT_OBSERVED")
                export_evidence("unknown_queue_commit", evidence)
            except BaseException as exc:
                evidence["exportErrors"].append(exception_value(exc))
                print("UNKNOWN_COMMIT_EVIDENCE_EXPORT_FAILED", repr(evidence), file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if primary_error is None: raise
                primary_error.add_note("Evidence export also failed; see UNKNOWN_COMMIT_EVIDENCE_EXPORT_FAILED stderr.")
