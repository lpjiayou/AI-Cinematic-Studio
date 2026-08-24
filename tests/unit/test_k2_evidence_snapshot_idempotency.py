import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.v5_core_os.episode_production.evidence import (
    EvidenceFact,
    EvidenceRecord,
    GateAppend,
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    _digest,
)


WORKSPACE = "workspace-evidence-snapshot"
RUN = "episode-production-run-evidence-snapshot"


def record(*, key="candidate-operation-v1", artifact="1" * 64):
    payload = {
        "schemaVersion": "test.candidate.v1",
        "candidateRef": "candidate-snapshot-v1",
        "artifactDigest": artifact,
        "publicationAllowed": False,
    }
    payload_digest = _digest(payload)
    payload["payloadDigest"] = payload_digest
    return EvidenceRecord(
        WORKSPACE,
        RUN,
        "Candidate",
        "candidate-snapshot-v1",
        1,
        key,
        _digest(
            {
                "recordKind": "Candidate",
                "recordRef": "candidate-snapshot-v1",
                "recordVersion": 1,
                "payloadDigest": payload_digest,
            }
        ),
        "2026-08-24T00:00:00Z",
        payload,
        payload_digest,
    )


def second_record(*, artifact="2" * 64):
    payload = {
        "schemaVersion": "test.technical-validation.v1",
        "candidateRef": "candidate-snapshot-v1",
        "artifactDigest": artifact,
        "publicationAllowed": False,
    }
    payload_digest = _digest(payload)
    payload["payloadDigest"] = payload_digest
    return EvidenceRecord(
        WORKSPACE,
        RUN,
        "TechnicalValidation",
        "technical-snapshot-v1",
        1,
        "candidate-operation-v1-child-validation",
        _digest(
            {
                "recordKind": "TechnicalValidation",
                "recordRef": "technical-snapshot-v1",
                "recordVersion": 1,
                "payloadDigest": payload_digest,
            }
        ),
        "2026-08-24T00:00:00Z",
        payload,
        payload_digest,
    )


def gate():
    payload = {
        "schemaVersion": "test.authority.v1",
        "authorityRef": "authority-snapshot-v1",
    }
    payload_digest = _digest(payload)
    payload["payloadDigest"] = payload_digest
    request_digest = _digest({"gate": "authority-snapshot-v1"})
    return GateAppend(
        WORKSPACE,
        RUN,
        "AUTHORITY_SNAPSHOT_TEST",
        "authority-snapshot-gate-v1",
        "a" * 64,
        request_digest,
        "ROOTS_READY",
        "AUTHORITY_READY",
        "2026-08-24T00:00:01Z",
        (
            EvidenceFact(
                "AuthoritySnapshot",
                "authority-snapshot-v1",
                1,
                payload,
                payload_digest,
            ),
        ),
    )


class EvidenceSnapshotIdempotencyMixin:
    def repository(self):
        raise NotImplementedError

    def test_snapshot_seals_gates_state_and_records_at_one_revision(self):
        repository = self.repository()
        repository.append_record(record())
        before = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(before.currentState, "ROOTS_READY")
        self.assertEqual(len(before.records), 1)
        self.assertEqual(len(before.gates), 0)

        repository.append_gate(gate())
        after = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(after.currentState, "AUTHORITY_READY")
        self.assertEqual(len(after.records), 1)
        self.assertEqual(len(after.gates), 1)
        self.assertNotEqual(before.revisionToken, after.revisionToken)
        self.assertEqual(before.currentState, "ROOTS_READY")
        self.assertEqual(len(before.gates), 0)

    def test_concurrent_exact_append_has_one_winner_and_one_replay(self):
        repository = self.repository()
        item = record()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: repository.append_record(item), range(2)))
        self.assertEqual(sorted(replayed for _, replayed in results), [False, True])
        self.assertEqual(len(repository.list_records(WORKSPACE, RUN)), 1)

    def test_same_key_changed_payload_conflicts_and_lookup_returns_winner(self):
        repository = self.repository()
        winner, replayed = repository.append_record(record())
        self.assertFalse(replayed)
        changed = record(artifact="2" * 64)
        with self.assertRaises(IdempotencyConflictError):
            repository.append_record(changed)
        self.assertEqual(
            repository.get_record_by_idempotency_key(
                WORKSPACE, RUN, "candidate-operation-v1"
            ),
            winner,
        )

    def test_exact_supplied_batch_replays_and_changed_member_conflicts(self):
        # The repository guarantees atomicity and exact replay for the records
        # supplied to this call.  Typed services, not this generic primitive,
        # own and verify their closed-world operation membership.
        repository = self.repository()
        first_batch, replayed = repository.append_records(
            (record(), second_record())
        )
        self.assertFalse(replayed)
        replay, replayed = repository.append_records(
            (record(), second_record())
        )
        self.assertTrue(replayed)
        self.assertEqual(replay, first_batch)

        with self.assertRaises(IdempotencyConflictError):
            repository.append_records(
                (record(), second_record(artifact="3" * 64))
            )

    def test_concurrent_exact_batch_has_one_winner_and_one_replay(self):
        repository = self.repository()
        batch = (record(), second_record())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(lambda _: repository.append_records(batch), range(2))
            )
        self.assertEqual(sorted(replayed for _, replayed in results), [False, True])
        self.assertEqual(len(repository.list_records(WORKSPACE, RUN)), 2)


class InMemoryEvidenceSnapshotIdempotencyTests(
    EvidenceSnapshotIdempotencyMixin, unittest.TestCase
):
    def repository(self):
        return InMemoryEpisodeProductionEvidenceAdapter()


class SqliteEvidenceSnapshotIdempotencyTests(
    EvidenceSnapshotIdempotencyMixin, unittest.TestCase
):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "evidence.sqlite3"

    def tearDown(self):
        self.directory.cleanup()

    def repository(self):
        return SqliteEpisodeProductionEvidenceAdapter(
            self.path, initialize_if_missing=True
        )

    def test_restart_replays_exact_record_and_snapshot_token(self):
        first = self.repository()
        stored, replayed = first.append_records((record(), second_record()))
        self.assertFalse(replayed)
        first_snapshot = first.read_snapshot(WORKSPACE, RUN)

        restarted = SqliteEpisodeProductionEvidenceAdapter(
            self.path, initialize_if_missing=False
        )
        replay, replayed = restarted.append_records((record(), second_record()))
        self.assertTrue(replayed)
        self.assertEqual(replay, stored)
        self.assertEqual(
            restarted.read_snapshot(WORKSPACE, RUN).revisionToken,
            first_snapshot.revisionToken,
        )


if __name__ == "__main__":
    unittest.main()
