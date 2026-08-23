import unittest

from services.v5_core_os.episode_production.media_candidate_review import (
    CandidateNotSelectableError,
    VerifiedMediaSelection,
)
from services.v5_core_os.episode_production.real_media_revision import (
    RealVideoCandidateRejectedError,
)
from tests.unit.test_episode_production_k2 import WORKSPACE
from tests.unit import test_k2_real_image_selection as image_selection


class VideoCandidateEvidence:
    def __init__(self):
        self.tamper_after_recording = False

    def resolve_candidates(
        self,
        workspace_ref,
        production_run_ref,
        real_video_plan_ref,
        expected_requests,
    ):
        del real_video_plan_ref
        candidates = []
        for request in expected_requests:
            ordinal = request["ordinal"]
            candidates.append(
                {
                    "candidateRef": f"m11-candidate-{ordinal}",
                    "candidateVersion": 1,
                    "ordinal": ordinal,
                    "slotRef": request["creativeShotVersionRef"],
                    "sourceRequestRef": request["generationRequestRef"],
                    "sourceRequestDigest": request["payloadDigest"],
                    "artifactRef": f"v4-artifact:{ordinal}",
                    "artifactDigest": (
                        "9" * 64
                        if self.tamper_after_recording and ordinal == 1
                        else str(ordinal) * 64
                    ),
                    "artifactByteSize": 10_000 + ordinal,
                    "storageKey": f"jobs/shot-{ordinal}/attempt-1.mp4",
                    "provenance": "SELF_HOSTED_AI_GENERATED",
                    "technicalChecks": [
                        {"check": "request-digest", "passed": True},
                        {"check": "artifact-sha256", "passed": True},
                        {"check": "media-probe", "passed": True},
                    ],
                }
            )
        return {
            "handoff": {
                "schemaVersion": "v4.k2-real-video-candidate-handoff.v1",
                "workspaceRef": workspace_ref,
                "productionRunRef": production_run_ref,
                "candidateCount": 4,
                "payloadDigest": "f" * 64,
            },
            "candidates": candidates,
        }


class SelectionAuthority:
    def verify(self, *, subject, approval_ref, decision):
        values = {
            "authority_ref": "approval-authority-k2-test",
            "approval_ref": approval_ref,
            "actor_ref": "human-reviewer-k2-test",
            "actor_kind": "HUMAN",
            "decision": decision,
            "authority_decision_ref": f"authority-{approval_ref}",
            "decided_at": "2026-08-24T00:00:00Z",
            "subject_digest": subject.subject_digest,
        }
        values["authority_decision_digest"] = (
            VerifiedMediaSelection.expected_decision_digest(**values)
        )
        return VerifiedMediaSelection.create(**values)


class K2RealVideoSelectionTests(unittest.TestCase):
    def setUp(self):
        image_selection.K2RealImageSelectionTests.setUp(self)
        self.boundary.select_real_images(
            image_selection.K2RealImageSelectionTests.selection_command(self)
        )
        self.plan = self.boundary.plan_real_videos(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-plan-for-selection-v1",
            }
        )
        self.revision = self.boundary._EpisodeProductionPublicBoundary__real_media_revision
        self.video_candidate_evidence = VideoCandidateEvidence()
        self.revision.video_candidate_evidence = self.video_candidate_evidence
        self.revision.candidate_review.selection_authority = SelectionAuthority()

    def tearDown(self):
        image_selection.K2RealImageSelectionTests.tearDown(self)

    def record_candidates(self):
        return self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-candidate-handoff-v1",
            }
        )

    def visual_qc(self, validation, ordinal, result="PASS"):
        return self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"m11-visual-qc-{ordinal}-v1",
                "technicalValidationRef": validation["technicalValidationRef"],
                "technicalValidationVersion": 1,
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": f"m11-visual-qc-{ordinal}-v1",
                "visualQcVersion": 1,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": f"m11-review-frame-{ordinal}",
                        "evidenceDigest": str(ordinal) * 64,
                    }
                ],
                "supersedesVisualQc": None,
                "checks": {
                    name: {"result": result, "note": ""}
                    for name in (
                        "identity",
                        "wardrobe",
                        "location",
                        "action",
                        "prop",
                        "motion",
                    )
                },
                "result": result,
            }
        )["semanticVisualQc"]

    @staticmethod
    def selection_request(qc, ordinal):
        return {
            "visualQcRef": qc["visualQcRef"],
            "visualQcVersion": 1,
            "visualQcDigest": qc["payloadDigest"],
            "selectionRef": f"m11-selection-{ordinal}-v1",
            "selectionVersion": 1,
            "approvalRef": f"m11-approval-{ordinal}-v1",
        }

    def test_four_exact_pass_candidates_admit_as_successor_asset_versions(self):
        recorded = self.record_candidates()
        self.assertEqual(recorded["state"], "REAL_VIDEO_PLAN_READY")
        self.assertEqual(len(recorded["technicalValidations"]), 4)
        selections = []
        for ordinal, validation in enumerate(
            recorded["technicalValidations"], start=1
        ):
            qc = self.visual_qc(validation, ordinal)
            selections.append(self.selection_request(qc, ordinal))
        admitted = self.revision.admit_real_videos(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-admit-four-v1",
                "selections": selections,
            }
        )
        self.assertEqual(admitted["state"], "REAL_VIDEO_READY")
        self.assertEqual(len(admitted["assetVersions"]), 4)
        self.assertEqual(
            [item["ordinal"] for item in admitted["assetVersions"]],
            [1, 2, 3, 4],
        )
        self.assertTrue(
            all(item["version"] == 2 for item in admitted["assetVersions"])
        )
        self.assertTrue(
            all(item["supersedesAssetVersionRef"] for item in admitted["assetVersions"])
        )
        selection_records = self.revision.evidence.list_records(
            WORKSPACE,
            self.run["productionRunRef"],
            record_kind="HumanSelectionDecision",
        )
        self.assertEqual(len(selection_records), 8)
        self.assertEqual(
            sum(
                item["recordRef"].startswith("m11-selection-")
                for item in selection_records
            ),
            4,
        )
        replay = self.revision.admit_real_videos(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-admit-four-v1",
                "selections": selections,
            }
        )
        self.assertTrue(replay["idempotentReplay"])
        projection = self.revision.get_revision_bundle(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(projection["state"], "REAL_VIDEO_READY")
        self.assertEqual(len(projection["videoAssetVersions"]), 4)
        self.assertFalse(projection["publicationAllowed"] if "publicationAllowed" in projection else False)

    def test_semantic_qc_fail_cannot_select_or_advance_production(self):
        recorded = self.record_candidates()
        qc = self.visual_qc(recorded["technicalValidations"][0], 1, result="FAIL")
        with self.assertRaises(CandidateNotSelectableError):
            self.revision.candidate_review.prepare_human_selection_record(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m11-failed-selection-v1",
                    **self.selection_request(qc, 1),
                    "decision": "SELECTED",
                }
            )
        self.assertEqual(
            self.boundary.get_run(WORKSPACE, self.run["productionRunRef"])["state"],
            "REAL_VIDEO_PLAN_READY",
        )
        projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(len(projection["candidateLifecycle"]["candidates"]), 4)
        failed = next(
            item
            for item in projection["candidateLifecycle"]["candidates"]
            if item["candidateRef"] == "m11-candidate-1"
        )
        self.assertEqual(failed["visualQcState"], "SEMANTIC_QC_FAILED")

    def test_changed_runtime_bytes_fail_before_any_video_admission_append(self):
        recorded = self.record_candidates()
        selections = []
        for ordinal, validation in enumerate(
            recorded["technicalValidations"], start=1
        ):
            qc = self.visual_qc(validation, ordinal)
            selections.append(self.selection_request(qc, ordinal))
        before = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.video_candidate_evidence.tamper_after_recording = True

        with self.assertRaises(RealVideoCandidateRejectedError):
            self.revision.admit_real_videos(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m11-admit-tampered-v1",
                    "selections": selections,
                }
            )

        after = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(after, before)
        self.assertEqual(
            self.revision.evidence.current_state(
                WORKSPACE, self.run["productionRunRef"]
            ),
            "REAL_VIDEO_PLAN_READY",
        )


if __name__ == "__main__":
    unittest.main()
