import tempfile
import unittest
from pathlib import Path

from services.v5_core_os.episode_production.evidence import (
    EvidenceFact,
    GateAppend,
    InMemoryEpisodeProductionEvidenceAdapter,
    InvalidStateTransitionError,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import _digest


WORKSPACE = "workspace-k2-real-revision"
RUN = "episode-production-run-k2-real-revision"
ROOT_DIGEST = "1" * 64

BASE_PATH = (
    "ROOTS_READY",
    "AUTHORITY_READY",
    "SCRIPT_VALIDATED",
    "SHOTS_COMPILED",
    "ASSETS_READY",
    "MEDIA_READY",
    "PREVIEW_READY",
    "QC_READY",
)
REVISION_PATH = (
    "QC_READY",
    "REAL_IMAGE_PLAN_READY",
    "REAL_IMAGE_READY",
    "REAL_VIDEO_PLAN_READY",
    "REAL_VIDEO_READY",
    "REAL_PREVIEW_READY",
    "REAL_QC_READY",
    "APPROVAL_READY",
    "MASTER_READY",
)


def gate(from_state, to_state, ordinal):
    payload = {
        "schemaVersion": "test.k2-evidence.v1",
        "ordinal": ordinal,
        "fromState": from_state,
        "toState": to_state,
        "publicationAllowed": False,
    }
    fact = EvidenceFact(
        factKind=f"test-fact-{ordinal}",
        factRef=f"test-fact-ref-{ordinal}",
        factVersion=1,
        payload=payload,
        payloadDigest=_digest(payload),
    )
    return GateAppend(
        workspaceRef=WORKSPACE,
        productionRunRef=RUN,
        gateName=f"TEST_GATE_{ordinal}",
        idempotencyKey=f"test-gate-{ordinal}",
        rootPayloadDigest=ROOT_DIGEST,
        requestDigest=_digest(
            {
                "ordinal": ordinal,
                "fromState": from_state,
                "toState": to_state,
            }
        ),
        fromState=from_state,
        toState=to_state,
        createdAt=f"2026-08-23T00:00:{ordinal:02d}Z",
        facts=(fact,),
    )


class K2RealMediaStateGraphMixin:
    def adapter(self):
        raise NotImplementedError

    @staticmethod
    def append_path(repository, path, *, first_ordinal=1):
        for ordinal, (from_state, to_state) in enumerate(
            zip(path, path[1:]), start=first_ordinal
        ):
            repository.append_gate(gate(from_state, to_state, ordinal))

    def test_legacy_qc_to_approval_and_master_remains_valid(self):
        repository = self.adapter()
        self.append_path(repository, BASE_PATH)
        next_ordinal = len(BASE_PATH)
        repository.append_gate(gate("QC_READY", "APPROVAL_READY", next_ordinal))
        repository.append_gate(
            gate("APPROVAL_READY", "MASTER_READY", next_ordinal + 1)
        )
        self.assertEqual(repository.current_state(WORKSPACE, RUN), "MASTER_READY")

    def test_image_first_revision_path_is_append_only_and_ordered(self):
        repository = self.adapter()
        self.append_path(repository, BASE_PATH)
        self.append_path(repository, REVISION_PATH, first_ordinal=len(BASE_PATH))
        gates = repository.list_gates(WORKSPACE, RUN)
        self.assertEqual(repository.current_state(WORKSPACE, RUN), "MASTER_READY")
        self.assertEqual(
            [item["toState"] for item in gates],
            list(BASE_PATH[1:]) + list(REVISION_PATH[1:]),
        )

    def test_revision_cannot_skip_image_admission(self):
        repository = self.adapter()
        self.append_path(repository, BASE_PATH)
        with self.assertRaises(InvalidStateTransitionError):
            repository.append_gate(
                gate("QC_READY", "REAL_IMAGE_READY", len(BASE_PATH))
            )
        self.assertEqual(repository.current_state(WORKSPACE, RUN), "QC_READY")

    def test_revision_cannot_fall_back_to_legacy_approval(self):
        repository = self.adapter()
        self.append_path(repository, BASE_PATH)
        ordinal = len(BASE_PATH)
        repository.append_gate(
            gate("QC_READY", "REAL_IMAGE_PLAN_READY", ordinal)
        )
        with self.assertRaises(InvalidStateTransitionError):
            repository.append_gate(
                gate("REAL_IMAGE_PLAN_READY", "APPROVAL_READY", ordinal + 1)
            )
        self.assertEqual(
            repository.current_state(WORKSPACE, RUN), "REAL_IMAGE_PLAN_READY"
        )


class InMemoryK2RealMediaStateGraphTests(
    K2RealMediaStateGraphMixin, unittest.TestCase
):
    def adapter(self):
        return InMemoryEpisodeProductionEvidenceAdapter()


class SqliteK2RealMediaStateGraphTests(
    K2RealMediaStateGraphMixin, unittest.TestCase
):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def adapter(self):
        return SqliteEpisodeProductionEvidenceAdapter(
            Path(self.temporary_directory.name) / "evidence.sqlite3",
            initialize_if_missing=True,
        )


if __name__ == "__main__":
    unittest.main()
