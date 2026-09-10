"""Actual original SQLite and InMemory transactions, concurrency and replay."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import sqlite3
from threading import Barrier, Event
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.evidence import EvidenceRecord, GateAppend, EvidenceFact, SqliteEpisodeProductionEvidenceAdapter
from services.v5_core_os.episode_production.generation_dispatch_public import GenerationDispatchPublicBoundary
from tests.support.generation_dispatch_fixtures import Fixture, fault_at, synthetic_consumption, save_evidence, TransactionObservation, NOW, START, END, TEST_SCOPE


class GenerationDispatchJournalTests(unittest.TestCase):
    def test_f01_expiry_after_real_begin_rolls_back_first_issue(self):
        x = Fixture(self)
        command = x.command()
        before = {"records": x.records(), "tokens": x.snapshot()}
        observation = TransactionObservation(x, advance_at="BEGIN_COMPLETED")
        with observation.observe():
            result = x.public.issue(command)
        x.reopen()
        after = {"records": x.records(), "tokens": x.snapshot(),
            "slot": x.repo.get_record(TEST_SCOPE["workspaceRef"], TEST_SCOPE["productionRunRef"], c.grant_ref(x.package["plan"]), 1)}
        save_evidence("f01_T1_begin_expiry.json", {"before": before, "result": result,
            "events": observation.events, "reopenedAfter": after})
        reads = [e for e in observation.events if e["phase"] == "CLOCK_READ"]
        self.assertEqual([e["value"] for e in reads[:2]], [NOW, NOW])
        self.assertTrue(all(not e["inTransaction"] for e in reads[:2]))
        self.assertTrue(any(e["phase"] == "BEGIN_COMPLETED" and e["inTransaction"] for e in observation.events))
        self.assertEqual(result.get("code"), "OUTSIDE_VALIDITY_WINDOW", result)
        self.assertEqual(result["writesCommitted"], 0)
        self.assertEqual(result["sendPermission"], "NONE")
        self.assertEqual(after["records"], before["records"])
        self.assertEqual(after["tokens"], before["tokens"])
        self.assertIsNone(after["slot"])
        self.assertTrue(any(e["phase"] == "ROLLBACK_COMPLETED" for e in observation.events))
        self.assertFalse(any(e["phase"] == "COMMIT_CALLED" for e in observation.events))

    def test_f01_expiry_after_insert_preserves_reopened_history_and_tokens(self):
        x = Fixture(self)
        payload = {"test": "pre-existing synthetic Candidate"}
        x.repo.append_record(EvidenceRecord(TEST_SCOPE["workspaceRef"], TEST_SCOPE["productionRunRef"],
            "Candidate", "test-f01-old-candidate", 1, "test-f01-old-key", c.digest(payload),
            START, payload, c.digest(payload)))
        command = x.command()
        before = {"records": x.records(), "tokens": x.snapshot(),
            "state": x.repo.current_state(TEST_SCOPE["workspaceRef"], TEST_SCOPE["productionRunRef"])}
        observation = TransactionObservation(x, advance_at="INSERT_COMPLETED")
        with observation.observe():
            result = x.public.issue(command)
        x.reopen()
        after = {"records": x.records(), "tokens": x.snapshot(),
            "state": x.repo.current_state(TEST_SCOPE["workspaceRef"], TEST_SCOPE["productionRunRef"])}
        save_evidence("f01_T2_insert_expiry.json", {"before": before, "result": result,
            "events": observation.events, "reopenedAfter": after})
        self.assertEqual(result["code"], "OUTSIDE_VALIDITY_WINDOW", result)
        self.assertEqual(result["writesCommitted"], 0)
        self.assertEqual(result["sendPermission"], "NONE")
        self.assertEqual(after, before)
        events = observation.events
        insert = next(i for i, e in enumerate(events) if e["phase"] == "INSERT_COMPLETED")
        self.assertTrue(events[insert]["inTransaction"])
        self.assertEqual(events[insert]["recordKind"], "GenerationDispatchGrant")
        self.assertEqual([e["phase"] for e in events[insert:]],
            ["INSERT_COMPLETED", "CLOCK_ADVANCED", "DECODE_COMPLETED", "CLOCK_READ", "ROLLBACK_CALLED", "ROLLBACK_COMPLETED"])
        self.assertEqual(events[insert + 3]["value"], END)
        self.assertTrue(events[insert + 3]["inTransaction"])
        self.assertEqual([e["value"] for e in events if e["phase"] == "CLOCK_READ"][:2], [NOW, NOW])

    def test_f01_valid_final_clock_preserves_sealed_record_and_commits_once(self):
        proofs = []
        for initial, final in ((NOW, NOW), (START, START), (NOW, "2030-01-01T00:59:59.999999Z")):
            with self.subTest(initial=initial, final=final):
                x = Fixture(self)
                x.clock.value = initial
                command = x.command()
                before = {"records": x.records(), "tokens": x.snapshot()}
                observation = TransactionObservation(x, advance_at="INSERT_COMPLETED", value=final)
                with observation.observe():
                    result = x.public.issue(command)
                x.reopen()
                after = {"records": x.records(), "tokens": x.snapshot()}
                proofs.append({"initial": initial, "final": final, "before": before,
                    "events": observation.events, "result": result, "reopenedAfter": after})
                save_evidence("f01_T3_valid.json", proofs)
                self.assertIn("grant", result, result)
                self.assertFalse(result["recordReplay"])
                self.assertEqual(result["sendPermission"], "NONE")
                self.assertEqual(len(after["records"]), 1)
                grant, record = result["grant"], after["records"][0]
                self.assertEqual(record["payload"], grant)
                self.assertEqual(grant["createdAt"], initial)
                self.assertEqual(record["createdAt"], initial)
                self.assertLessEqual(c.utc(grant["approval"]["decidedAt"]), c.utc(initial))
                inserts = [e for e in observation.events if e["phase"] == "INSERT_COMPLETED"]
                self.assertEqual(len(inserts), 1)
                self.assertEqual((inserts[0]["createdAt"], inserts[0]["recordRef"], inserts[0]["payloadDigest"]),
                    (grant["createdAt"], grant["generationDispatchGrantRef"], grant["payloadDigest"]))
                events = observation.events
                commit = next(i for i, e in enumerate(events) if e["phase"] == "COMMIT_CALLED")
                self.assertEqual([e["phase"] for e in events[commit - 2:commit + 2]],
                    ["DECODE_COMPLETED", "CLOCK_READ", "COMMIT_CALLED", "COMMIT_COMPLETED"])
                self.assertTrue(events[commit - 1]["inTransaction"])
                self.assertEqual(events[commit - 1]["value"], final)
                self.assertEqual(sum(e["phase"] == "COMMIT_COMPLETED" for e in events), 1)

    def test_f01_transaction_clock_boundaries_and_unavailability_reject(self):
        proofs = []
        cases = [("before_not_before", "2029-12-31T23:59:59.999999Z", None, "OUTSIDE_VALIDITY_WINDOW"),
            ("not_before_but_before_created", START, None, "OUTSIDE_VALIDITY_WINDOW"),
            ("expires_at", END, None, "OUTSIDE_VALIDITY_WINDOW"),
            ("clock_regression", "2030-01-01T00:00:09.999999Z", None, "OUTSIDE_VALIDITY_WINDOW"),
            ("regression_after_second_read", NOW, None, "OUTSIDE_VALIDITY_WINDOW"),
            ("unparseable", "not-a-time", None, "INVALID_CLOSED_SCHEMA"),
            ("missing_reading", None, None, "INVALID_CLOSED_SCHEMA"),
            ("unavailable", NOW, RuntimeError("test trusted clock unavailable"), "CURRENTNESS_FENCE_UNAVAILABLE")]
        for name, value, error, expected in cases:
            with self.subTest(case=name):
                x = Fixture(self)
                command = x.command()
                before = {"records": x.records(), "tokens": x.snapshot()}
                if name == "regression_after_second_read":
                    x.clock.sequence = [NOW, "2030-01-01T00:00:20.000000Z"]
                observation = TransactionObservation(x, advance_at="INSERT_COMPLETED", value=value, clock_error=error)
                with observation.observe():
                    result = x.public.issue(command)
                x.reopen()
                after = {"records": x.records(), "tokens": x.snapshot()}
                proofs.append({"case": name, "before": before, "events": observation.events,
                    "result": result, "reopenedAfter": after})
                save_evidence("f01_T4_clock_rejections.json", proofs)
                self.assertEqual(result["code"], expected, result)
                self.assertEqual(result["writesCommitted"], 0)
                self.assertEqual(result["sendPermission"], "NONE")
                self.assertEqual(after, before)
                events = observation.events
                at = next(i for i, e in enumerate(events) if e["phase"] == "INSERT_COMPLETED")
                self.assertEqual(sum(e["phase"] == "INSERT_COMPLETED" for e in events), 1)
                self.assertTrue(any(e["phase"] in ("CLOCK_READ", "CLOCK_RAISED") and e["inTransaction"] for e in events[at:]))
                self.assertTrue(any(e["phase"] == "ROLLBACK_COMPLETED" and not e["inTransaction"] for e in events[at:]))
                self.assertFalse(any(e["phase"] == "COMMIT_CALLED" for e in events))

    def test_f01_expired_replay_and_revoke_do_not_reapply_first_issue_check(self):
        x = Fixture(self)
        command = x.command()
        issued = x.public.issue(command)
        self.assertIn("grant", issued, issued)
        x.reopen()
        x.clock.value = END
        before = {"records": x.records(), "tokens": x.snapshot()}
        replay_observation = TransactionObservation(x)
        with replay_observation.observe():
            replay = x.public.issue(command)
        after_replay = {"records": x.records(), "tokens": x.snapshot()}
        self.assertEqual(replay["grant"], issued["grant"])
        self.assertTrue(replay["recordReplay"])
        self.assertEqual(replay["eligibility"], "EXPIRED")
        self.assertEqual(after_replay, before)
        self.assertFalse(any(e["phase"] in ("BEGIN_COMPLETED", "INSERT_COMPLETED", "COMMIT_CALLED") for e in replay_observation.events))
        # Storage replay remains historical, even with a check that would reject
        # a first append. Neither replay is a new authorization decision.
        storage_checks = []
        class RejectFirstAppend:
            def validate_before_commit(self):
                storage_checks.append("called")
                raise c.DispatchError("OUTSIDE_VALIDITY_WINDOW")
        row = before["records"][0]
        record = EvidenceRecord(**{k: row[k] for k in EvidenceRecord.__dataclass_fields__})
        stored, replayed = x.repo.append_records((record,), grant_issue_validity=RejectFirstAppend())
        self.assertTrue(replayed)
        self.assertEqual(stored, before["records"])
        self.assertEqual(storage_checks, [])
        revocation = x.revoke_command(issued["grant"])
        revoke_observation = TransactionObservation(x)
        with revoke_observation.observe():
            revoked = x.public.revoke(revocation)
        x.reopen()
        after_revoke = {"records": x.records(), "tokens": x.snapshot()}
        save_evidence("f01_T5_history.json", {"before": before, "issued": issued,
            "replay": replay, "replayEvents": replay_observation.events, "afterReplay": after_replay,
            "storageReplay": replayed, "storageValidationCalls": len(storage_checks),
            "revoked": revoked, "revokeEvents": revoke_observation.events, "reopenedAfter": after_revoke})
        self.assertEqual(revoked["terminal"]["kind"], "REVOKED", revoked)
        self.assertEqual(revoked["sendPermission"], "NONE")
        self.assertEqual(len(after_revoke["records"]), 2)
        self.assertEqual(after_revoke["records"][0], before["records"][0])
        self.assertFalse(any(e["phase"] == "CLOCK_READ" and e["inTransaction"] for e in revoke_observation.events))

    def test_f01_rollback_uncertainty_never_claims_zero_writes(self):
        proofs = []
        for phase in ("before", "after"):
            with self.subTest(phase=phase):
                x = Fixture(self)
                command = x.command()
                before = {"records": x.records(), "tokens": x.snapshot()}
                observation = TransactionObservation(x, advance_at="INSERT_COMPLETED", rollback_fault=phase)
                with observation.observe():
                    result = x.public.issue(command)
                x.reopen()
                after = {"records": x.records(), "tokens": x.snapshot()}
                proofs.append({"fault": phase, "before": before, "events": observation.events,
                    "result": result, "reopenedAfter": after})
                save_evidence("f01_T6_rollback_unknown.json", proofs)
                self.assertEqual(result["code"], "COMMIT_OUTCOME_UNKNOWN", result)
                self.assertNotIn("writesCommitted", result)
                self.assertEqual(result["sendPermission"], "NONE")
                self.assertEqual(after, before)
                self.assertTrue(any(e["phase"] == "ROLLBACK_RAISED" for e in observation.events))

    def test_f01_close_uncertainty_preserves_indeterminate_result(self):
        proofs = []
        for final in (NOW, END):
            with self.subTest(final=final):
                x = Fixture(self)
                command = x.command()
                before = {"records": x.records(), "tokens": x.snapshot()}
                observation = TransactionObservation(x, advance_at="INSERT_COMPLETED", value=final, close_fault=True)
                with observation.observe():
                    result = x.public.issue(command)
                x.reopen()
                after = {"records": x.records(), "tokens": x.snapshot()}
                proofs.append({"final": final, "before": before, "events": observation.events,
                    "result": result, "reopenedAfter": after})
                save_evidence("f01_T6_close_unknown.json", proofs)
                self.assertEqual(result["code"], "COMMIT_OUTCOME_UNKNOWN", result)
                self.assertNotIn("writesCommitted", result)
                self.assertEqual(result["sendPermission"], "NONE")
                if final == NOW:
                    self.assertEqual(len(after["records"]), 1)
                else:
                    self.assertEqual(after, before)

    def test_f01_inmemory_check_runs_under_lock_and_matches_sqlite_rejection(self):
        proofs = []
        for memory in (True, False):
            x = Fixture(self, memory=memory)
            command = x.command()
            before = {"records": x.records(), "tokens": x.snapshot()}
            x.clock.sequence = [NOW, NOW, END]
            if memory:
                events = []
                original = x.clock.now
                def now():
                    value = original()
                    events.append({"phase": "CLOCK_READ", "value": value, "appendLockHeld": x.repo._lock._is_owned()})
                    return value
                with patch.object(x.clock, "now", side_effect=now):
                    result = x.public.issue(command)
                self.assertEqual([e["appendLockHeld"] for e in events], [False, False, True])
            else:
                observation = TransactionObservation(x)
                with observation.observe():
                    result = x.public.issue(command)
                events = observation.events
                x.reopen()
            after = {"records": x.records(), "tokens": x.snapshot()}
            proofs.append({"adapter": "InMemory" if memory else "SQLite", "before": before,
                "events": events, "result": result, "after": after})
            save_evidence("f01_T6_adapter_parity.json", proofs)
            self.assertEqual(result["code"], "OUTSIDE_VALIDITY_WINDOW", result)
            self.assertEqual(after, before)
        self.assertEqual(proofs[0]["result"], proofs[1]["result"])

    def test_f01_adapter_without_validity_capability_has_no_unchecked_fallback(self):
        x = Fixture(self)
        command = x.command()
        before = {"records": x.records(), "tokens": x.snapshot()}
        legacy_body_calls = []
        original = x.repo.append_records
        def legacy(records, *, expected_record_journal_head=None,
                   expected_workspace_record_journal_head=None, expected_evidence_revision_token=None):
            legacy_body_calls.append("called")
            return original(records, expected_record_journal_head=expected_record_journal_head,
                expected_workspace_record_journal_head=expected_workspace_record_journal_head,
                expected_evidence_revision_token=expected_evidence_revision_token)
        with patch.object(x.repo, "append_records", side_effect=legacy) as append:
            result = x.public.issue(command)
        x.reopen()
        after = {"records": x.records(), "tokens": x.snapshot()}
        save_evidence("f01_T6_unsupported_adapter.json", {"before": before, "result": result,
            "appendAttempts": append.call_count, "legacyBodyCalls": len(legacy_body_calls), "reopenedAfter": after})
        self.assertEqual(result["code"], "PERSISTENCE_UNAVAILABLE", result)
        self.assertEqual(result["writesCommitted"], 0)
        self.assertEqual(result["sendPermission"], "NONE")
        self.assertEqual(append.call_count, 1)
        self.assertEqual(legacy_body_calls, [])
        self.assertEqual(after, before)

    def test_issue_reopen_exact_replay_preserves_original_time_and_digest(self):
        x = Fixture(self)
        command = x.command()
        issued = x.public.issue(command)
        self.assertIn("grant", issued, issued)
        self.assertFalse(issued["recordReplay"])
        record = x.records()[0]
        self.assertEqual(record["createdAt"], issued["grant"]["createdAt"])
        self.assertEqual(record["payload"]["issuanceEvidence"]["snapshotTokens"], command["snapshotTokens"])
        x.reopen()
        x.clock.value = END
        replay = x.public.issue(command)
        self.assertTrue(replay["recordReplay"], replay)
        self.assertEqual(replay["grant"], issued["grant"])
        self.assertEqual(replay["eligibility"], "EXPIRED")
        self.assertEqual(x.records(), [record])
        save_evidence("restart_replay.json", {"command": command, "initial": issued, "reopenedReplay": replay, "records": x.records()})

    def test_inmemory_and_sqlite_return_same_grant_contract(self):
        values = []
        for memory in (True, False):
            x = Fixture(self, memory=memory)
            result = x.public.issue(x.command())
            self.assertIn("grant", result, result)
            self.assertEqual(x.repo.current_state(TEST_SCOPE["workspaceRef"], TEST_SCOPE["productionRunRef"]), "ROOTS_READY")
            values.append(result)
        self.assertEqual(values[0], values[1])

    def test_same_key_changed_meaning_and_other_key_same_slot(self):
        x = Fixture(self)
        command = x.command()
        issued = x.public.issue(command)
        self.assertIn("grant", issued, issued)
        changed = {**command, "expectedApprovedPlanDigest": "f" * 64}
        self.assertEqual(x.public.issue(changed)["code"], "IDEMPOTENCY_CONFLICT")
        result = x.public.issue(x.command("test-another-key"))
        self.assertEqual(result["code"], "GRANT_SUBJECT_ALREADY_RECORDED")
        self.assertEqual(len(x.records()), 1)
        self.assertEqual(x.records()[0]["recordVersion"], 1)

    def test_each_snapshot_token_is_independently_required(self):
        for token in c.TOKEN_FIELDS:
            x = Fixture(self)
            command = x.command()
            command["snapshotTokens"][token] = "f" * 64
            with self.subTest(token=token):
                self.assertEqual(x.public.issue(command)["code"], "SNAPSHOT_CHANGED")
                self.assertEqual(x.records(), [])

    def test_original_transaction_cas_catches_intervening_record_workspace_and_gate(self):
        proofs = []
        for mode in ("record", "workspace", "revision"):
            x = Fixture(self)
            command = x.command()
            def intervene():
                x.readers.source_hook = None
                if mode == "revision":
                    payload = {"test": "legacy-gate"}
                    x.repo.append_gate(GateAppend(TEST_SCOPE["workspaceRef"], TEST_SCOPE["productionRunRef"], "test-existing-gate", "test-gate-key",
                        "a" * 64, "b" * 64, "ROOTS_READY", "AUTHORITY_READY", START,
                        (EvidenceFact("TestFact", "test-fact", 1, payload, c.digest(payload)),)))
                else:
                    run = "test-other-run" if mode == "workspace" else TEST_SCOPE["productionRunRef"]
                    payload = {"test": mode}
                    x.repo.append_record(EvidenceRecord(TEST_SCOPE["workspaceRef"], run, "Candidate", "test-intervening", 1,
                        "test-intervening-key", c.digest(payload), START, payload, c.digest(payload)))
            x.readers.source_hook = intervene
            result = x.public.issue(command)
            with self.subTest(mode=mode):
                self.assertEqual(result["code"], "SNAPSHOT_CHANGED", result)
                self.assertFalse(any(r["recordKind"] == "GenerationDispatchGrant" for r in x.records()))
            proofs.append({"mode": mode, "before": command["snapshotTokens"], "after": x.snapshot(), "result": result})
        save_evidence("three_transaction_cas.json", proofs)

    def test_actual_precommit_failures_roll_back_and_postcommit_loss_is_indeterminate(self):
        proofs = []
        for phase in ("after_insert", "before_commit", "after_commit"):
            x = Fixture(self)
            command = x.command()
            before = x.snapshot()
            with fault_at(x.repo, phase):
                result = x.public.issue(command)
            x.reopen()
            after = x.records()
            with self.subTest(phase=phase):
                if phase == "after_commit":
                    self.assertEqual(result["code"], "COMMIT_OUTCOME_UNKNOWN", result)
                    self.assertNotIn("writesCommitted", result)
                    self.assertEqual(len(after), 1)
                    self.assertTrue(x.public.issue(command)["recordReplay"])
                else:
                    self.assertEqual(result["code"], "PERSISTENCE_UNAVAILABLE", result)
                    self.assertEqual(result["writesCommitted"], 0)
                    self.assertEqual(after, [])
                    self.assertEqual(x.snapshot(), before)
                self.assertEqual(result["sendPermission"], "NONE")
            proofs.append({"phase": phase, "before": before, "result": result, "reopenedRecords": after, "afterTokens": x.snapshot()})
        save_evidence("commit_faults.json", proofs)

    def test_validity_and_trusted_commit_time_boundaries(self):
        for value, expected in (("2029-12-31T23:59:59.999999Z", "OUTSIDE_VALIDITY_WINDOW"), (END, "OUTSIDE_VALIDITY_WINDOW"), (START, None)):
            x = Fixture(self)
            x.clock.value = value
            result = x.public.issue(x.command())
            with self.subTest(value=value):
                if expected:
                    self.assertEqual(result["code"], expected)
                    self.assertEqual(x.records(), [])
                else:
                    self.assertEqual(result["grant"]["createdAt"], START)
                    self.assertEqual(x.records()[0]["createdAt"], START)
        x = Fixture(self)
        x.clock.sequence = [NOW, END]
        self.assertEqual(x.public.issue(x.command())["code"], "OUTSIDE_VALIDITY_WINDOW")
        self.assertEqual(x.records(), [])

    def test_inspect_eligibility_never_updates_history(self):
        x = Fixture(self)
        issued = x.public.issue(x.command())
        self.assertIn("grant", issued, issued)
        before = x.records()
        cases = [("clock", "2029-12-31T23:59:59.999999Z", "NOT_YET_VALID"), ("clock", END, "EXPIRED"),
            ("source", True, "SOURCE_CHANGED"), ("backend", True, "CONFIG_CHANGED"), ("runtime", True, "CONFIG_CHANGED"),
            ("cost", True, "CONFIG_CHANGED"), ("approval", True, "APPROVAL_UNAVAILABLE"), ("fence", True, "FENCE_UNAVAILABLE")]
        for kind, value, eligibility in cases:
            x.clock.value, x.readers.failure, x.originals.failure, x.fence.available = NOW, None, False, True
            if kind == "clock": x.clock.value = value
            elif kind == "approval": x.originals.failure = True
            elif kind == "fence": x.fence.available = False
            else: x.readers.failure = kind
            result = x.public.inspect(x.inspect_command())
            with self.subTest(kind=kind, value=value):
                self.assertEqual(result["eligibility"], eligibility, result)
                self.assertEqual(result["grant"], issued["grant"])
                self.assertEqual(x.records(), before)
        x.service.coordination = None
        self.assertEqual(x.public.inspect(x.inspect_command())["grant"], issued["grant"])

    def test_revoke_expired_stale_grant_independent_approval_and_restart_replay(self):
        x = Fixture(self)
        issued = x.public.issue(x.command())
        grant = issued["grant"]
        command = x.revoke_command(grant)
        x.clock.value = END
        x.readers.failure = "source"
        x.approval_path.unlink()
        revoked = x.public.revoke(command)
        self.assertIn("terminal", revoked, revoked)
        self.assertFalse(revoked["recordReplay"])
        self.assertEqual(x.public.inspect(x.inspect_command())["eligibility"], "REVOKED")
        x.reopen()
        replay = x.public.revoke(command)
        self.assertEqual(replay["terminal"], revoked["terminal"])
        self.assertTrue(replay["recordReplay"])
        self.assertEqual(x.records()[0]["payload"], grant)
        self.assertEqual(len(x.records()), 2)
        self.assertEqual(x.public.revoke({**command, "idempotencyKey": "test-other-revoke"})["code"], "ALREADY_REVOKED")
        self.assertEqual(x.public.revoke({**command, "authorityDecisionRef": "test-other-decision"})["code"], "IDEMPOTENCY_CONFLICT")
        save_evidence("revocation_replay.json", {"issue": issued, "revoke": revoked, "restartReplay": replay, "records": x.records()})

    def test_revoke_requires_own_approval_cas_and_rejects_preloaded_consumption(self):
        x = Fixture(self)
        grant = x.public.issue(x.command())["grant"]
        command = x.revoke_command(grant)
        original = x.service.revocation_reader
        x.service.revocation_reader = x.approval_reader
        self.assertEqual(x.public.revoke(command)["code"], "APPROVAL_UNAVAILABLE")
        x.service.revocation_reader = original
        for token in c.TOKEN_FIELDS:
            bad = deepcopy(command)
            bad["snapshotTokens"][token] = "f" * 64
            self.assertEqual(x.public.revoke(bad)["code"], "SNAPSHOT_CHANGED")
        x.repo.append_record(synthetic_consumption(x, grant))
        before = x.records()
        self.assertEqual(x.public.revoke(command)["code"], "ALREADY_CONSUMED")
        self.assertEqual(x.public.inspect(x.inspect_command())["eligibility"], "CONSUMED")
        self.assertEqual(x.records(), before)

    def test_two_sqlite_instances_concurrent_issue_and_revoke(self):
        proofs = []
        for action, same_key in (("ISSUE", True), ("ISSUE", False), ("REVOKE", True), ("REVOKE", False)):
            x = Fixture(self)
            if action == "ISSUE": command = x.command()
            else: command = x.revoke_command(x.public.issue(x.command())["grant"])
            second = SqliteEpisodeProductionEvidenceAdapter(x.path, initialize_if_missing=False)
            other = GenerationDispatchPublicBoundary(x.make_service(second))
            commands = [deepcopy(command), deepcopy(command)]
            if not same_key: commands[1]["idempotencyKey"] += "-other"
            barrier = Barrier(2)
            def invoke(index):
                barrier.wait(timeout=5)
                return getattr((x.public, other)[index], action.lower())(commands[index])
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(invoke, (0, 1)))
            successes = [r for r in results if "code" not in r]
            with self.subTest(action=action, same_key=same_key):
                self.assertEqual(len(successes), 2 if same_key else 1, results)
                self.assertEqual(sum(not r["recordReplay"] for r in successes), 1)
                self.assertEqual(len(x.records()), 1 if action == "ISSUE" else 2)
                if not same_key:
                    self.assertEqual(next(r["code"] for r in results if "code" in r), "GRANT_SUBJECT_ALREADY_RECORDED" if action == "ISSUE" else "ALREADY_REVOKED")
            proofs.append({"action": action, "sameKey": same_key, "results": results, "records": x.records()})
        save_evidence("two_connection_concurrency.json", proofs)

    def test_source_mutation_waits_for_gate_and_changed_source_rejects_first_issue(self):
        x = Fixture(self)
        x.readers.package["plan"]["subject"]["manifestDigest"] = "f" * 64
        self.assertEqual(x.public.issue(x.command())["code"], "SOURCE_CHANGED")
        self.assertEqual(x.records(), [])
        x.readers.package = deepcopy(x.package)
        entered, writer_started, writer_done = Event(), Event(), Event()
        def read_hook():
            x.readers.source_hook = None
            entered.set()
            self.assertTrue(writer_started.wait(5))
            self.assertFalse(writer_done.is_set())
        def mutate():
            self.assertTrue(entered.wait(5))
            writer_started.set()
            with x.fence.critical_section(TEST_SCOPE["workspaceRef"]):
                x.readers.package["plan"]["subject"]["manifestDigest"] = "e" * 64
                writer_done.set()
        x.readers.source_hook = read_hook
        with ThreadPoolExecutor(max_workers=2) as executor:
            writer = executor.submit(mutate)
            result = x.public.issue(x.command())
            writer.result(timeout=5)
        self.assertIn("grant", result, result)
        self.assertTrue(writer_done.is_set())
        self.assertEqual(x.public.inspect(x.inspect_command())["eligibility"], "SOURCE_CHANGED")

    def test_revoke_commit_failure_and_lost_receipt_have_distinct_results(self):
        proofs = []
        for phase in ("before_commit", "after_commit"):
            x = Fixture(self)
            grant = x.public.issue(x.command())["grant"]
            command = x.revoke_command(grant)
            before = x.records()
            with fault_at(x.repo, phase):
                result = x.public.revoke(command)
            x.reopen()
            if phase == "before_commit":
                self.assertEqual(result["code"], "PERSISTENCE_UNAVAILABLE", result)
                self.assertEqual(result["writesCommitted"], 0)
                self.assertEqual(x.records(), before)
            else:
                self.assertEqual(result["code"], "COMMIT_OUTCOME_UNKNOWN", result)
                self.assertNotIn("writesCommitted", result)
                self.assertEqual(len(x.records()), 2)
                self.assertTrue(x.public.revoke(command)["recordReplay"])
            proofs.append({"phase": phase, "before": before, "result": result, "reopenedRecords": x.records()})
        save_evidence("revocation_commit_faults.json", proofs)


if __name__ == "__main__":
    unittest.main()
