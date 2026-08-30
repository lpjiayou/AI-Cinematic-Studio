from dataclasses import replace
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.v5_core_os.episode_production.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EvidenceFact,
    EvidenceRecord,
    GateAppend,
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
    InvalidStateTransitionError,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
)


WORKSPACE = "workspace-k2-records"
RUN = "episode-production-run-k2-records"
OTHER_RUN = "episode-production-run-k2-records-other"


def record(
    *,
    version=1,
    key="visual-qc-shot-0001-v1",
    decision="PASS",
    run=RUN,
):
    payload = {
        "schemaVersion": "v5.semantic-visual-qc-decision.v1",
        "candidateRef": "candidate-shot-0001-v1",
        "candidateDigest": "1" * 64,
        "artifactDigest": "2" * 64,
        "decision": decision,
        "publicationAllowed": False,
    }
    return EvidenceRecord(
        workspaceRef=WORKSPACE,
        productionRunRef=run,
        recordKind="SemanticVisualQCDecision",
        recordRef="visual-qc-decision-shot-0001",
        recordVersion=version,
        idempotencyKey=key,
        requestDigest=_digest({"version": version, "decision": decision}),
        createdAt=f"2026-08-23T12:00:{version:02d}Z",
        payload=payload,
        payloadDigest=_digest(payload),
    )


def gate(*, name="atomic-admission", key="atomic-admission-v1"):
    payload = {
        "schemaVersion": "v5.test-atomic-admission.v1",
        "publicationAllowed": False,
    }
    payload_digest = _digest(payload)
    return GateAppend(
        workspaceRef=WORKSPACE,
        productionRunRef=RUN,
        gateName=name,
        idempotencyKey=key,
        rootPayloadDigest="a" * 64,
        requestDigest=_digest(
            {"gateName": name, "key": key, "payloadDigest": payload_digest}
        ),
        fromState="ROOTS_READY",
        toState="AUTHORITY_READY",
        createdAt="2026-08-24T00:00:00Z",
        facts=(
            EvidenceFact(
                factKind="AtomicAdmissionManifest",
                factRef=f"{name}-manifest",
                factVersion=1,
                payload=payload,
                payloadDigest=payload_digest,
            ),
        ),
    )


class AppendOnlyEvidenceRecordMixin:
    def repository(self):
        raise NotImplementedError

    def test_record_is_append_only_idempotent_and_does_not_advance_state(self):
        repository = self.repository()
        first, replayed = repository.append_record(record())
        replay, was_replayed = repository.append_record(record())

        self.assertFalse(replayed)
        self.assertTrue(was_replayed)
        self.assertEqual(replay, first)
        self.assertEqual(repository.current_state(WORKSPACE, RUN), "ROOTS_READY")
        self.assertEqual(
            repository.list_records(
                WORKSPACE, RUN, record_kind="SemanticVisualQCDecision"
            ),
            [first],
        )

    def test_versions_are_ordered_and_idempotency_conflicts_fail_closed(self):
        repository = self.repository()
        first = record()
        second = record(version=2, key="visual-qc-shot-0001-v2", decision="FAIL")
        repository.append_record(first)
        repository.append_record(second)
        self.assertEqual(
            [item["recordVersion"] for item in repository.list_records(WORKSPACE, RUN)],
            [1, 2],
        )
        changed = EvidenceRecord(
            workspaceRef=first.workspaceRef,
            productionRunRef=first.productionRunRef,
            recordKind=first.recordKind,
            recordRef=first.recordRef,
            recordVersion=first.recordVersion,
            idempotencyKey=first.idempotencyKey,
            requestDigest="f" * 64,
            createdAt=first.createdAt,
            payload=first.payload,
            payloadDigest=first.payloadDigest,
        )
        with self.assertRaises(IdempotencyConflictError):
            repository.append_record(changed)

    def test_records_and_gate_append_or_replay_as_one_unit(self):
        repository = self.repository()
        expected_head = repository.record_journal_head(WORKSPACE, RUN)
        stored_records, stored_gate, replayed = repository.append_records_and_gate(
            (record(),),
            gate(),
            expected_record_journal_head=expected_head,
        )
        self.assertFalse(replayed)
        self.assertEqual(len(stored_records), 1)
        self.assertEqual(stored_gate["toState"], "AUTHORITY_READY")
        replay_records, replay_gate, was_replayed = (
            repository.append_records_and_gate(
                (record(),),
                gate(),
                # An exact replay remains valid with the head observed by the
                # original request, even though that request advanced it.
                expected_record_journal_head=expected_head,
            )
        )
        self.assertTrue(was_replayed)
        self.assertEqual(replay_records, stored_records)
        self.assertEqual(replay_gate, stored_gate)

    def test_gate_failure_rolls_back_all_new_records(self):
        repository = self.repository()
        repository.append_gate(gate(name="already-advanced", key="advance-v1"))
        with self.assertRaises(InvalidStateTransitionError):
            repository.append_records_and_gate(
                (record(),), gate(name="stale-admission", key="stale-v1")
            )
        self.assertEqual(repository.list_records(WORKSPACE, RUN), [])
        self.assertIsNone(repository.get_gate(WORKSPACE, RUN, "stale-admission"))

    def test_record_journal_head_is_opaque_and_changes_after_append(self):
        repository = self.repository()
        empty_head = repository.record_journal_head(WORKSPACE, RUN)
        self.assertEqual(len(empty_head), 64)
        self.assertTrue(all(character in "0123456789abcdef" for character in empty_head))

        repository.append_record(record())
        populated_head = repository.record_journal_head(WORKSPACE, RUN)
        self.assertEqual(len(populated_head), 64)
        self.assertNotEqual(populated_head, empty_head)

    def test_append_records_cas_rejects_intervening_append(self):
        repository = self.repository()
        expected_head = repository.record_journal_head(WORKSPACE, RUN)
        concurrent = record()
        repository.append_record(concurrent)

        with self.assertRaises(StaleInputError):
            repository.append_records(
                (
                    record(
                        version=2,
                        key="visual-qc-shot-0001-v2",
                        decision="FAIL",
                    ),
                ),
                expected_record_journal_head=expected_head,
            )

        self.assertEqual(
            [item["recordVersion"] for item in repository.list_records(WORKSPACE, RUN)],
            [1],
        )

    def test_append_records_exact_replay_accepts_original_head(self):
        repository = self.repository()
        expected_head = repository.record_journal_head(WORKSPACE, RUN)
        expected_workspace_head = repository.workspace_record_journal_head(
            WORKSPACE
        )
        expected_revision = repository.read_snapshot(
            WORKSPACE, RUN
        ).revisionToken
        stored, replayed = repository.append_records(
            (record(),),
            expected_record_journal_head=expected_head,
            expected_workspace_record_journal_head=expected_workspace_head,
            expected_evidence_revision_token=expected_revision,
        )
        replay, was_replayed = repository.append_records(
            (record(),),
            expected_record_journal_head=expected_head,
            expected_workspace_record_journal_head=expected_workspace_head,
            expected_evidence_revision_token=expected_revision,
        )
        self.assertFalse(replayed)
        self.assertTrue(was_replayed)
        self.assertEqual(replay, stored)

    def test_composite_cas_rejects_same_run_gate_append(self):
        repository = self.repository()
        expected_workspace_head = repository.workspace_record_journal_head(
            WORKSPACE
        )
        expected_revision = repository.read_snapshot(
            WORKSPACE, RUN
        ).revisionToken
        repository.append_gate(gate())

        with self.assertRaises(StaleInputError):
            repository.append_records(
                (record(),),
                expected_workspace_record_journal_head=expected_workspace_head,
                expected_evidence_revision_token=expected_revision,
            )

        self.assertEqual(repository.list_records(WORKSPACE, RUN), [])

    def test_composite_cas_rejects_other_run_record_append(self):
        repository = self.repository()
        expected_workspace_head = repository.workspace_record_journal_head(
            WORKSPACE
        )
        expected_revision = repository.read_snapshot(
            WORKSPACE, RUN
        ).revisionToken
        repository.append_record(record(run=OTHER_RUN))

        # The current-run snapshot is unchanged; the workspace head is the
        # independent CAS component that detects this cross-run write.
        self.assertEqual(
            repository.read_snapshot(WORKSPACE, RUN).revisionToken,
            expected_revision,
        )
        with self.assertRaises(StaleInputError):
            repository.append_records(
                (record(),),
                expected_workspace_record_journal_head=expected_workspace_head,
                expected_evidence_revision_token=expected_revision,
            )

        self.assertEqual(repository.list_records(WORKSPACE, RUN), [])
        self.assertEqual(len(repository.list_records(WORKSPACE, OTHER_RUN)), 1)

    def test_append_records_and_gate_cas_rolls_back_on_intervening_append(self):
        repository = self.repository()
        expected_head = repository.record_journal_head(WORKSPACE, RUN)
        repository.append_record(record())

        with self.assertRaises(StaleInputError):
            repository.append_records_and_gate(
                (
                    record(
                        version=2,
                        key="visual-qc-shot-0001-v2",
                        decision="FAIL",
                    ),
                ),
                gate(),
                expected_record_journal_head=expected_head,
            )

        self.assertEqual(
            [item["recordVersion"] for item in repository.list_records(WORKSPACE, RUN)],
            [1],
        )
        self.assertIsNone(repository.get_gate(WORKSPACE, RUN, "atomic-admission"))
        self.assertEqual(repository.current_state(WORKSPACE, RUN), "ROOTS_READY")

    def test_unknown_record_kind_is_rejected_fail_closed(self):
        repository = self.repository()
        unknown = replace(record(), recordKind="CallerDefinedEvidence")
        with self.assertRaises(EpisodeProductionError):
            repository.append_record(unknown)
        self.assertEqual(repository.list_records(WORKSPACE, RUN), [])


class InMemoryAppendOnlyEvidenceRecordTests(
    AppendOnlyEvidenceRecordMixin, unittest.TestCase
):
    def repository(self):
        return InMemoryEpisodeProductionEvidenceAdapter()


class SqliteAppendOnlyEvidenceRecordTests(
    AppendOnlyEvidenceRecordMixin, unittest.TestCase
):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def repository(self):
        return SqliteEpisodeProductionEvidenceAdapter(
            Path(self.temporary_directory.name) / "evidence.sqlite3",
            initialize_if_missing=True,
        )

    def legacy_v1_database(self, name="legacy.sqlite3", *, with_rows=True):
        database = Path(self.temporary_directory.name) / name
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA foreign_keys = ON")
        SqliteEpisodeProductionEvidenceAdapter._create_schema(connection)
        if with_rows:
            legacy_gate = gate()
            connection.execute(
                "INSERT INTO v5_episode_production_gates VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    legacy_gate.workspaceRef,
                    legacy_gate.productionRunRef,
                    legacy_gate.gateName,
                    legacy_gate.idempotencyKey,
                    legacy_gate.rootPayloadDigest,
                    legacy_gate.requestDigest,
                    legacy_gate.fromState,
                    legacy_gate.toState,
                    legacy_gate.createdAt,
                ),
            )
            for fact in legacy_gate.facts:
                connection.execute(
                    "INSERT INTO v5_episode_production_facts VALUES (?,?,?,?,?,?,?,?)",
                    (
                        legacy_gate.workspaceRef,
                        legacy_gate.productionRunRef,
                        legacy_gate.gateName,
                        fact.factKind,
                        fact.factRef,
                        fact.factVersion,
                        json.dumps(
                            fact.payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                        fact.payloadDigest,
                    ),
                )
            connection.execute(
                "INSERT INTO v5_episode_production_transitions VALUES (?,?,?,?,?,?,?,?)",
                (
                    legacy_gate.workspaceRef,
                    legacy_gate.productionRunRef,
                    1,
                    legacy_gate.gateName,
                    legacy_gate.fromState,
                    legacy_gate.toState,
                    legacy_gate.requestDigest,
                    legacy_gate.createdAt,
                ),
            )
        connection.execute("DROP TABLE v5_episode_production_records")
        connection.execute(
            "UPDATE v5_episode_production_evidence_schema SET schema_version=1"
        )
        connection.commit()
        connection.close()
        return database

    @staticmethod
    def legacy_rows(database):
        connection = sqlite3.connect(database)
        try:
            return {
                table: connection.execute(
                    "SELECT rowid,"
                    + ",".join(
                        SqliteEpisodeProductionEvidenceAdapter._COLUMNS[table]
                    )
                    + f" FROM {table} ORDER BY rowid"
                ).fetchall()
                for table in (
                    "v5_episode_production_gates",
                    "v5_episode_production_facts",
                    "v5_episode_production_transitions",
                )
            }
        finally:
            connection.close()

    def test_v1_database_migrates_in_place_without_changing_gate_rows(self):
        database = self.legacy_v1_database()
        accepted_rows = self.legacy_rows(database)

        repository = SqliteEpisodeProductionEvidenceAdapter(
            database, initialize_if_missing=False
        )
        self.assertEqual(repository.current_state(WORKSPACE, RUN), "AUTHORITY_READY")
        migrated_gate = repository.get_gate(WORKSPACE, RUN, "atomic-admission")
        self.assertEqual(migrated_gate["facts"][0]["factKind"], "AtomicAdmissionManifest")
        self.assertEqual(self.legacy_rows(database), accepted_rows)
        stored, _ = repository.append_record(record())
        self.assertEqual(stored["recordKind"], "SemanticVisualQCDecision")
        verify = sqlite3.connect(database)
        try:
            self.assertEqual(
                verify.execute(
                    "SELECT schema_version FROM v5_episode_production_evidence_schema"
                ).fetchone()[0],
                EVIDENCE_SCHEMA_VERSION,
            )
        finally:
            verify.close()

    def test_malformed_v1_schema_is_rejected_without_partial_migration(self):
        database = self.legacy_v1_database("malformed.sqlite3")
        accepted_rows = self.legacy_rows(database)
        connection = sqlite3.connect(database)
        connection.execute(
            "ALTER TABLE v5_episode_production_gates ADD COLUMN unexpected TEXT"
        )
        connection.commit()
        connection.close()

        with self.assertRaises(RepositoryUnavailableError):
            SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=False
            )

        verify = sqlite3.connect(database)
        try:
            tables = {
                row[0]
                for row in verify.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertNotIn("v5_episode_production_records", tables)
            self.assertEqual(
                verify.execute(
                    "SELECT schema_version FROM v5_episode_production_evidence_schema"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(self.legacy_rows(database), accepted_rows)
        finally:
            verify.close()

    def test_v1_payload_digest_failure_is_rejected_before_migration(self):
        database = self.legacy_v1_database("invalid-payload.sqlite3")
        connection = sqlite3.connect(database)
        connection.execute(
            "UPDATE v5_episode_production_facts SET payload_json=?",
            (json.dumps({"publicationAllowed": True}),),
        )
        connection.commit()
        connection.close()
        corrupted_rows = self.legacy_rows(database)

        with self.assertRaises(RepositoryUnavailableError):
            SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=False
            )

        verify = sqlite3.connect(database)
        try:
            tables = {
                row[0]
                for row in verify.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertNotIn("v5_episode_production_records", tables)
            self.assertEqual(
                verify.execute(
                    "SELECT schema_version FROM v5_episode_production_evidence_schema"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(self.legacy_rows(database), corrupted_rows)
        finally:
            verify.close()

    def test_v1_migration_fault_rolls_back_schema_marker_and_rows(self):
        database = self.legacy_v1_database("migration-fault.sqlite3")
        accepted_rows = self.legacy_rows(database)
        migrate = SqliteEpisodeProductionEvidenceAdapter._migrate_v1_to_v2

        def migrate_then_fail(connection):
            migrate(connection)
            raise sqlite3.OperationalError("injected post-migration fault")

        with patch.object(
            SqliteEpisodeProductionEvidenceAdapter,
            "_migrate_v1_to_v2",
            side_effect=migrate_then_fail,
        ):
            with self.assertRaises(RepositoryUnavailableError):
                SqliteEpisodeProductionEvidenceAdapter(
                    database, initialize_if_missing=False
                )

        verify = sqlite3.connect(database)
        try:
            tables = {
                row[0]
                for row in verify.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertNotIn("v5_episode_production_records", tables)
            self.assertEqual(
                verify.execute(
                    "SELECT schema_version FROM v5_episode_production_evidence_schema"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(self.legacy_rows(database), accepted_rows)
        finally:
            verify.close()

    def test_record_payload_tampering_is_detected_on_restart_read(self):
        repository = self.repository()
        repository.append_record(record())
        connection = sqlite3.connect(repository.database_path)
        connection.execute(
            "UPDATE v5_episode_production_records SET payload_json=?",
            (json.dumps({"decision": "PASS"}),),
        )
        connection.commit()
        connection.close()
        with self.assertRaises(RepositoryUnavailableError):
            repository.list_records(WORKSPACE, RUN)

    def test_unknown_durable_record_kind_is_rejected_on_restart(self):
        repository = self.repository()
        repository.append_record(record())
        connection = sqlite3.connect(repository.database_path)
        connection.execute(
            "UPDATE v5_episode_production_records SET record_kind=?",
            ("CallerDefinedEvidence",),
        )
        connection.commit()
        connection.close()

        with self.assertRaises(RepositoryUnavailableError):
            SqliteEpisodeProductionEvidenceAdapter(
                repository.database_path,
                initialize_if_missing=False,
            )

    def test_sqlite_fault_after_record_insert_rolls_back_gate_and_records(self):
        repository = self.repository()
        connection = sqlite3.connect(repository.database_path)
        connection.execute(
            "CREATE TRIGGER reject_atomic_gate BEFORE INSERT ON "
            "v5_episode_production_gates BEGIN "
            "SELECT RAISE(ABORT, 'fault injection'); END"
        )
        connection.commit()
        connection.close()
        with self.assertRaises(IdempotencyConflictError):
            repository.append_records_and_gate((record(),), gate())
        self.assertEqual(repository.list_records(WORKSPACE, RUN), [])
        self.assertIsNone(repository.get_gate(WORKSPACE, RUN, "atomic-admission"))
        self.assertEqual(repository.current_state(WORKSPACE, RUN), "ROOTS_READY")


if __name__ == "__main__":
    unittest.main()
