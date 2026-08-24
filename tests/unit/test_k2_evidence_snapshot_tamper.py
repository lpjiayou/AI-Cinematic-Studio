import tempfile
import unittest
from pathlib import Path

from services.v5_core_os.episode_production.evidence import (
    EvidenceFact,
    EvidenceRecord,
    EvidenceSnapshot,
    GateAppend,
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
    _snapshot_revision_token,
)
from services.v5_core_os.episode_production.foundation import (
    RepositoryUnavailableError,
    _digest,
)
from services.v5_core_os.episode_production.media_candidate_review import (
    K2MediaCandidateReviewService,
)
from services.v5_core_os.episode_production.state_projection import (
    K2ProductionStateProjectionService,
)


WORKSPACE = "workspace-evidence-snapshot-tamper"
RUN = "episode-production-run-evidence-snapshot-tamper"


class RootService:
    def get_run(self, workspace_ref, production_run_ref):
        return {
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "state": "ROOTS_READY",
            "payloadDigest": "1" * 64,
            "version": 1,
        }


def candidate_record() -> EvidenceRecord:
    payload = {
        "candidateRef": "candidate-snapshot-tamper-v1",
        "revisionRef": "real-video-plan-snapshot-tamper-v1",
        "mediaKind": "VIDEO",
        "publicationAllowed": False,
    }
    return EvidenceRecord(
        workspaceRef=WORKSPACE,
        productionRunRef=RUN,
        recordKind="Candidate",
        recordRef=payload["candidateRef"],
        recordVersion=1,
        idempotencyKey="candidate-snapshot-tamper-v1",
        requestDigest=_digest({"operation": "candidate-snapshot-tamper-v1"}),
        createdAt="2026-08-25T00:00:00Z",
        payload=payload,
        payloadDigest=_digest(payload),
    )


def authority_gate() -> GateAppend:
    payload = {
        "authorityRef": "authority-snapshot-tamper-v1",
        "publicationAllowed": False,
    }
    return GateAppend(
        workspaceRef=WORKSPACE,
        productionRunRef=RUN,
        gateName="AUTHORITY_SNAPSHOT_TAMPER_TEST",
        idempotencyKey="authority-snapshot-tamper-v1",
        rootPayloadDigest="2" * 64,
        requestDigest=_digest({"operation": "authority-snapshot-tamper-v1"}),
        fromState="ROOTS_READY",
        toState="AUTHORITY_READY",
        createdAt="2026-08-25T00:00:01Z",
        facts=(
            EvidenceFact(
                factKind="AuthoritySnapshot",
                factRef="authority-snapshot-tamper-v1",
                factVersion=1,
                payload=payload,
                payloadDigest=_digest(payload),
            ),
        ),
    )


def script_gate() -> GateAppend:
    payload = {
        "scriptRef": "script-snapshot-tamper-v1",
        "publicationAllowed": False,
    }
    return GateAppend(
        workspaceRef=WORKSPACE,
        productionRunRef=RUN,
        gateName="SCRIPT_SNAPSHOT_TAMPER_TEST",
        idempotencyKey="script-snapshot-tamper-v1",
        rootPayloadDigest="3" * 64,
        requestDigest=_digest({"operation": "script-snapshot-tamper-v1"}),
        fromState="AUTHORITY_READY",
        toState="SCRIPT_VALIDATED",
        createdAt="2026-08-25T00:00:02Z",
        facts=(
            EvidenceFact(
                factKind="ScriptSnapshot",
                factRef="script-snapshot-tamper-v1",
                factVersion=1,
                payload=payload,
                payloadDigest=_digest(payload),
            ),
        ),
    )


class EvidenceSnapshotTamperMixin:
    def repository(self):
        raise NotImplementedError

    @staticmethod
    def projection(repository):
        root = RootService()
        candidates = K2MediaCandidateReviewService(
            root,
            repository,
            clock=lambda: "2026-08-25T00:00:02Z",
        )
        return K2ProductionStateProjectionService(root, repository, candidates)

    def test_record_payload_mutation_with_unchanged_token_fails_closed(self):
        repository = self.repository()
        repository.append_record(candidate_record())
        snapshot = repository.read_snapshot(WORKSPACE, RUN)
        token = snapshot.revisionToken
        snapshot.records[0]["payload"]["revisionRef"] = "tampered-revision"

        self.assertEqual(snapshot.revisionToken, token)
        with self.assertRaises(RepositoryUnavailableError):
            self.projection(repository).get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=snapshot,
            )

        fresh = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(fresh.revisionToken, token)
        self.assertEqual(
            fresh.records[0]["payload"]["revisionRef"],
            "real-video-plan-snapshot-tamper-v1",
        )

    def test_gate_fact_payload_mutation_with_unchanged_token_fails_closed(self):
        repository = self.repository()
        repository.append_gate(authority_gate())
        snapshot = repository.read_snapshot(WORKSPACE, RUN)
        token = snapshot.revisionToken
        snapshot.gates[0]["facts"][0]["payload"]["authorityRef"] = (
            "tampered-authority"
        )

        self.assertEqual(snapshot.revisionToken, token)
        with self.assertRaises(RepositoryUnavailableError):
            self.projection(repository).get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=snapshot,
            )

        fresh = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(fresh.revisionToken, token)
        self.assertEqual(
            fresh.gates[0]["facts"][0]["payload"]["authorityRef"],
            "authority-snapshot-tamper-v1",
        )

    def test_record_request_digest_mutation_with_unchanged_token_fails_closed(self):
        repository = self.repository()
        repository.append_record(candidate_record())
        snapshot = repository.read_snapshot(WORKSPACE, RUN)
        token = snapshot.revisionToken
        snapshot.records[0]["requestDigest"] = "f" * 64

        self.assertEqual(snapshot.revisionToken, token)
        with self.assertRaises(RepositoryUnavailableError):
            self.projection(repository).get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=snapshot,
            )

        fresh = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(fresh.revisionToken, token)
        self.assertNotEqual(fresh.records[0]["requestDigest"], "f" * 64)

    def test_gate_created_at_mutation_with_unchanged_token_fails_closed(self):
        repository = self.repository()
        repository.append_gate(authority_gate())
        snapshot = repository.read_snapshot(WORKSPACE, RUN)
        token = snapshot.revisionToken
        snapshot.gates[0]["createdAt"] = "2026-08-25T00:00:59Z"

        self.assertEqual(snapshot.revisionToken, token)
        with self.assertRaises(RepositoryUnavailableError):
            self.projection(repository).get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=snapshot,
            )

        fresh = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(fresh.revisionToken, token)
        self.assertEqual(
            fresh.gates[0]["createdAt"],
            "2026-08-25T00:00:01Z",
        )

    def test_record_idempotency_key_mutation_with_unchanged_token_fails_closed(self):
        repository = self.repository()
        repository.append_record(candidate_record())
        snapshot = repository.read_snapshot(WORKSPACE, RUN)
        token = snapshot.revisionToken
        snapshot.records[0]["idempotencyKey"] = "changed-candidate-operation"

        self.assertEqual(snapshot.revisionToken, token)
        with self.assertRaises(RepositoryUnavailableError):
            self.projection(repository).get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=snapshot,
            )

        fresh = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(fresh.revisionToken, token)
        self.assertEqual(
            fresh.records[0]["idempotencyKey"],
            "candidate-snapshot-tamper-v1",
        )

    def test_gate_idempotency_key_mutation_with_unchanged_token_fails_closed(self):
        repository = self.repository()
        repository.append_gate(authority_gate())
        snapshot = repository.read_snapshot(WORKSPACE, RUN)
        token = snapshot.revisionToken
        snapshot.gates[0]["idempotencyKey"] = "changed-authority-operation"

        self.assertEqual(snapshot.revisionToken, token)
        with self.assertRaises(RepositoryUnavailableError):
            self.projection(repository).get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=snapshot,
            )

        fresh = repository.read_snapshot(WORKSPACE, RUN)
        self.assertEqual(fresh.revisionToken, token)
        self.assertEqual(
            fresh.gates[0]["idempotencyKey"],
            "authority-snapshot-tamper-v1",
        )

    def test_resigned_duplicate_gate_idempotency_key_fails_closed(self):
        repository = self.repository()
        repository.append_gate(authority_gate())
        repository.append_gate(script_gate())
        snapshot = repository.read_snapshot(WORKSPACE, RUN)
        snapshot.gates[1]["idempotencyKey"] = snapshot.gates[0][
            "idempotencyKey"
        ]
        resigned = EvidenceSnapshot(
            snapshot.workspaceRef,
            snapshot.productionRunRef,
            snapshot.currentState,
            snapshot.gates,
            snapshot.records,
            _snapshot_revision_token(
                snapshot.workspaceRef,
                snapshot.productionRunRef,
                snapshot.currentState,
                snapshot.gates,
                snapshot.records,
            ),
        )

        with self.assertRaises(RepositoryUnavailableError):
            self.projection(repository).get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=resigned,
            )

        fresh = repository.read_snapshot(WORKSPACE, RUN)
        self.assertNotEqual(
            fresh.gates[0]["idempotencyKey"],
            fresh.gates[1]["idempotencyKey"],
        )


class InMemoryEvidenceSnapshotTamperTests(
    EvidenceSnapshotTamperMixin, unittest.TestCase
):
    def repository(self):
        return InMemoryEpisodeProductionEvidenceAdapter()


class SqliteEvidenceSnapshotTamperTests(
    EvidenceSnapshotTamperMixin, unittest.TestCase
):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "evidence.sqlite3"

    def tearDown(self):
        self.directory.cleanup()

    def repository(self):
        return SqliteEpisodeProductionEvidenceAdapter(
            self.path,
            initialize_if_missing=True,
        )


if __name__ == "__main__":
    unittest.main()
