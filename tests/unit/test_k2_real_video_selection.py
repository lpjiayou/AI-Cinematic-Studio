import unittest
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from services.v5_core_os.episode_production import create_local_development_boundary
from services.v5_core_os.episode_production.media_candidate_review import (
    CandidateNotSelectableError,
    VerifiedMediaSelection,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
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
            request_version = request.get("version", 1)
            successor_digest = sha256(
                f"{ordinal}:{request['payloadDigest']}".encode("utf-8")
            ).hexdigest()
            candidates.append(
                {
                    "candidateRef": (
                        f"m11-candidate-{ordinal}"
                        if request_version == 1
                        else f"m11-candidate-{ordinal}-v{request_version}"
                    ),
                    "candidateVersion": 1,
                    "ordinal": ordinal,
                    "slotRef": request["creativeShotVersionRef"],
                    "sourceRequestRef": request["generationRequestRef"],
                    "sourceRequestDigest": request["payloadDigest"],
                    "artifactRef": f"v4-artifact:{ordinal}",
                    "artifactDigest": (
                        "9" * 64
                        if self.tamper_after_recording and ordinal == 1
                        else (
                            str(ordinal) * 64
                            if request_version == 1
                            else successor_digest
                        )
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

    def admit_video_handoff(self, recorded, *, prefix):
        selections = []
        ordinal_by_slot = {
            item["creativeShotVersionRef"]: item["ordinal"]
            for item in self.boundary.get_real_media_revision(
                WORKSPACE, self.run["productionRunRef"]
            )["videoGenerationRequests"]
        }
        for validation in recorded["technicalValidations"]:
            candidate = next(
                item
                for item in recorded["candidates"]
                if item["candidateRef"] == validation["candidateRef"]
            )
            ordinal = ordinal_by_slot[candidate["slotRef"]]
            qc = self.revision.candidate_review.record_semantic_visual_qc(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": f"{prefix}-qc-{ordinal}",
                    "technicalValidationRef": validation[
                        "technicalValidationRef"
                    ],
                    "technicalValidationVersion": validation[
                        "technicalValidationVersion"
                    ],
                    "technicalValidationDigest": validation["payloadDigest"],
                    "visualQcRef": f"{prefix}-qc-{ordinal}",
                    "visualQcVersion": 1,
                    "reviewerRef": "reviewer-project-lead",
                    "reviewProfile": "k2-semantic-visual-qc-v1",
                    "evidence": [
                        {
                            "evidenceRef": f"{prefix}-frame-{ordinal}",
                            "evidenceDigest": sha256(
                                f"{prefix}:{ordinal}".encode("utf-8")
                            ).hexdigest(),
                        }
                    ],
                    "supersedesVisualQc": None,
                    "checks": {
                        name: {"result": "PASS", "note": ""}
                        for name in (
                            "identity",
                            "wardrobe",
                            "location",
                            "action",
                            "prop",
                            "motion",
                        )
                    },
                    "result": "PASS",
                }
            )["semanticVisualQc"]
            selections.append(
                {
                    "visualQcRef": qc["visualQcRef"],
                    "visualQcVersion": qc["visualQcVersion"],
                    "visualQcDigest": qc["payloadDigest"],
                    "selectionRef": f"{prefix}-selection-{ordinal}",
                    "selectionVersion": 1,
                    "approvalRef": f"{prefix}-approval-{ordinal}",
                }
            )
        return self.revision.admit_real_videos(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"{prefix}-admit",
                "selections": selections,
            }
        )

    def admit_shot_one_image_successor(self, *, prefix):
        self.candidate_evidence.generation += 1
        image_successors = self.boundary.record_real_image_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"{prefix}-image-handoff",
            }
        )
        validation = image_successors["technicalValidations"][0]
        qc = self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"{prefix}-image-qc",
                "technicalValidationRef": validation["technicalValidationRef"],
                "technicalValidationVersion": validation[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": f"{prefix}-image-qc",
                "visualQcVersion": 1,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": f"{prefix}-image-frame",
                        "evidenceDigest": sha256(prefix.encode("utf-8")).hexdigest(),
                    }
                ],
                "supersedesVisualQc": None,
                "checks": {
                    name: {"result": "PASS", "note": ""}
                    for name in (
                        "identity",
                        "wardrobe",
                        "location",
                        "action",
                        "prop",
                        "motion",
                    )
                },
                "result": "PASS",
            }
        )["semanticVisualQc"]
        return self.boundary.admit_real_image_successor(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"{prefix}-image-admit",
                "selection": {
                    "visualQcRef": qc["visualQcRef"],
                    "visualQcVersion": qc["visualQcVersion"],
                    "visualQcDigest": qc["payloadDigest"],
                    "selectionRef": f"{prefix}-image-selection",
                    "selectionVersion": 1,
                    "approvalRef": f"{prefix}-image-approval",
                },
            }
        )

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

    def reseal_committed_record(self, record_ref, mutate):
        """Simulate semantically corrupted but digest-consistent storage."""

        evidence = self.revision.evidence
        current = next(
            item
            for item in evidence.list_records(
                WORKSPACE, self.run["productionRunRef"]
            )
            if item["recordRef"] == record_ref
        )
        payload = deepcopy(current["payload"])
        payload.pop("payloadDigest", None)
        mutate(payload)
        payload_digest = _digest(payload)
        payload["payloadDigest"] = payload_digest
        request_digest = _digest(
            {
                "recordKind": current["recordKind"],
                "recordRef": current["recordRef"],
                "recordVersion": current["recordVersion"],
                "payloadDigest": payload_digest,
            }
        )
        if hasattr(evidence, "_records"):
            key = (
                WORKSPACE,
                self.run["productionRunRef"],
                current["recordRef"],
                current["recordVersion"],
            )
            with evidence._lock:
                evidence._records[key] = replace(
                    evidence._records[key],
                    payload=payload,
                    payloadDigest=payload_digest,
                    requestDigest=request_digest,
                )
            return
        with sqlite3.connect(evidence.database_path) as connection:
            connection.execute(
                "UPDATE v5_episode_production_records "
                "SET payload_json=?, payload_digest=?, request_digest=? "
                "WHERE workspace_ref=? AND production_run_ref=? "
                "AND record_ref=? AND record_version=?",
                (
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload_digest,
                    request_digest,
                    WORKSPACE,
                    self.run["productionRunRef"],
                    current["recordRef"],
                    current["recordVersion"],
                ),
            )

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
        self.assertEqual(len(projection["videoAssetAdmissions"]), 4)
        self.assertEqual(len(projection["videoAssetVersions"]), 4)
        self.assertFalse(projection["publicationAllowed"] if "publicationAllowed" in projection else False)

    def test_post_ready_image_successor_reuses_three_video_chains_and_activates_one(self):
        baseline_handoff = self.record_candidates()
        baseline = self.admit_video_handoff(
            baseline_handoff, prefix="m11-baseline-ready"
        )
        self.assertEqual(baseline["state"], "REAL_VIDEO_READY")
        baseline_by_ordinal = {
            item["ordinal"]: item for item in baseline["assetVersions"]
        }
        before_records = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )

        image = self.admit_shot_one_image_successor(
            prefix="m11-post-ready-image-v2"
        )
        self.assertEqual(image["assetVersion"]["version"], 2)
        self.assertEqual(
            self.revision.evidence.current_state(
                WORKSPACE, self.run["productionRunRef"]
            ),
            "REAL_VIDEO_READY",
        )

        blocked = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(blocked["videoLineageState"]["state"], "STALE_BLOCKED")
        self.assertEqual(blocked["videoAssetVersions"], [])
        self.assertEqual(blocked["videoAssetAdmissions"], [])
        self.assertEqual(len(blocked["activeVideoAdmission"]["assetAdmissions"]), 4)
        self.assertEqual(len(blocked["activeVideoAdmission"]["assetVersions"]), 4)
        blocked_projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(blocked_projection["activeRevision"]["mediaKind"], "VIDEO")
        self.assertEqual(
            blocked_projection["activeRevision"]["state"], "STALE_BLOCKED"
        )
        self.assertEqual(
            blocked_projection["activeRevision"]["activationManifestDigest"],
            blocked["activeVideoAdmission"]["realVideoAdmissionManifest"][
                "payloadDigest"
            ],
        )

        successor_handoff = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-post-ready-video-handoff-v2",
            }
        )
        self.assertEqual(len(successor_handoff["candidates"]), 1)
        self.assertEqual(len(successor_handoff["technicalValidations"]), 1)
        candidate = successor_handoff["candidates"][0]
        self.assertEqual(candidate["slotRef"], baseline_by_ordinal[1]["creativeShotVersionRef"])
        self.assertEqual(candidate["consumedGenerationRequest"]["version"], 2)
        self.assertEqual(
            candidate["consumedGenerationRequest"][
                "supersedesGenerationRequestVersionRef"
            ],
            self.plan["generationRequests"][0]["generationRequestVersionRef"],
        )
        self.assertEqual(
            candidate["consumedRealVideoRevision"]["generationRequestCount"], 4
        )
        after_handoff_records = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(
            sum(item["recordKind"] == "Candidate" for item in after_handoff_records),
            sum(item["recordKind"] == "Candidate" for item in before_records) + 5,
        )
        self.assertEqual(
            sum(
                item["recordKind"] == "TechnicalValidation"
                for item in after_handoff_records
            ),
            sum(
                item["recordKind"] == "TechnicalValidation"
                for item in before_records
            )
            + 5,
        )

        successor = self.admit_video_handoff(
            successor_handoff, prefix="m11-post-ready-video-v2"
        )
        self.assertEqual(successor["state"], "REAL_VIDEO_READY")
        self.assertEqual(len(successor["assetAdmissions"]), 4)
        self.assertEqual(len(successor["assetVersions"]), 4)
        successor_by_ordinal = {
            item["ordinal"]: item for item in successor["assetVersions"]
        }
        self.assertNotEqual(
            successor_by_ordinal[1]["assetVersionRef"],
            baseline_by_ordinal[1]["assetVersionRef"],
        )
        self.assertEqual(
            successor_by_ordinal[1]["supersedesAssetVersionRef"],
            baseline_by_ordinal[1]["assetVersionRef"],
        )
        for ordinal in (2, 3, 4):
            self.assertEqual(
                successor_by_ordinal[ordinal]["assetVersionRef"],
                baseline_by_ordinal[ordinal]["assetVersionRef"],
            )
        self.assertEqual(successor["realVideoAdmissionManifest"]["newAdmissionCount"], 1)
        self.assertEqual(successor["realVideoAdmissionManifest"]["reusedAdmissionCount"], 3)
        current_bundle = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(current_bundle["videoLineageState"]["state"], "CURRENT")
        self.assertEqual(len(current_bundle["videoAssetAdmissions"]), 4)
        current_projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(current_projection["activeRevision"]["mediaKind"], "VIDEO")
        self.assertEqual(current_projection["activeRevision"]["state"], "ACTIVE")
        self.assertEqual(
            current_projection["activeRevision"]["activationManifestDigest"],
            successor["realVideoAdmissionManifest"]["payloadDigest"],
        )
        selection_record = self.revision.evidence.get_record(
            WORKSPACE,
            self.run["productionRunRef"],
            successor["assetAdmissions"][0]["selectionRef"],
            successor["assetAdmissions"][0]["selectionVersion"],
        )
        selection = selection_record["payload"]
        replay = self.revision.admit_real_videos(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-post-ready-video-v2-admit",
                "selections": [
                    {
                        "visualQcRef": selection["visualQcRef"],
                        "visualQcVersion": selection["visualQcVersion"],
                        "visualQcDigest": selection["visualQcDigest"],
                        "selectionRef": selection["selectionRef"],
                        "selectionVersion": selection["selectionVersion"],
                        "approvalRef": selection["approvalRef"],
                    }
                ],
            }
        )
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["realVideoAdmissionManifest"], successor["realVideoAdmissionManifest"])
        self.assertEqual(replay["assetAdmissions"], successor["assetAdmissions"])
        self.assertEqual(replay["assetVersions"], successor["assetVersions"])
        before_conflicts = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        with self.assertRaises(IdempotencyConflictError):
            self.revision.admit_real_videos(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m11-post-ready-video-v2-admit",
                    "selections": [
                        {
                            "visualQcRef": selection["visualQcRef"],
                            "visualQcVersion": selection["visualQcVersion"],
                            "visualQcDigest": selection["visualQcDigest"],
                            "selectionRef": selection["selectionRef"],
                            "selectionVersion": selection["selectionVersion"],
                            "approvalRef": "changed-approval-ref",
                        }
                    ],
                }
            )
        with self.assertRaises(IdempotencyConflictError):
            self.revision.admit_real_videos(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m11-post-ready-video-v2-different-key",
                    "selections": [
                        {
                            "visualQcRef": selection["visualQcRef"],
                            "visualQcVersion": selection["visualQcVersion"],
                            "visualQcDigest": selection["visualQcDigest"],
                            "selectionRef": selection["selectionRef"],
                            "selectionVersion": selection["selectionVersion"],
                            "approvalRef": selection["approvalRef"],
                        }
                    ],
                }
            )
        self.assertEqual(
            self.revision.evidence.list_records(
                WORKSPACE, self.run["productionRunRef"]
            ),
            before_conflicts,
        )
        final_records = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(
            sum(item["recordKind"] == "AssetVersion" for item in final_records),
            sum(item["recordKind"] == "AssetVersion" for item in after_handoff_records)
            + 1,
        )
        self.assertEqual(
            self.revision.evidence.current_state(
                WORKSPACE, self.run["productionRunRef"]
            ),
            "REAL_VIDEO_READY",
        )

    def test_post_ready_video_request_v3_immediately_supersedes_persisted_v2(self):
        K2RealVideoSelectionTests.test_post_ready_image_successor_reuses_three_video_chains_and_activates_one(
            self
        )
        active_v2 = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        active_v2_internal = self.revision.get_revision_bundle(
            WORKSPACE, self.run["productionRunRef"]
        )
        request_v2 = active_v2["videoGenerationRequests"][0]
        asset_v2 = active_v2["videoAssetVersions"][0]
        activation_v2 = deepcopy(
            active_v2_internal["realVideoAdmissionManifest"]
        )
        admissions_v2 = deepcopy(active_v2_internal["videoAssetAdmissions"])
        assets_v2 = deepcopy(active_v2_internal["videoAssetVersions"])
        selection_v2_record = self.revision.evidence.get_record(
            WORKSPACE,
            self.run["productionRunRef"],
            admissions_v2[0]["selectionRef"],
            admissions_v2[0]["selectionVersion"],
        )
        selection_v2 = selection_v2_record["payload"]

        image_v3 = self.admit_shot_one_image_successor(
            prefix="m11-post-ready-image-v3"
        )
        self.assertEqual(image_v3["assetVersion"]["version"], 3)
        handoff_v3 = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-post-ready-video-handoff-v3",
            }
        )
        self.assertEqual(len(handoff_v3["candidates"]), 1)
        request_v3 = handoff_v3["candidates"][0]["consumedGenerationRequest"]
        revision_v3 = handoff_v3["candidates"][0]["consumedRealVideoRevision"]
        self.assertEqual(request_v3["version"], 3)
        self.assertEqual(
            request_v3["supersedesGenerationRequestVersionRef"],
            request_v2["generationRequestVersionRef"],
        )
        self.assertEqual(
            request_v3["supersedesGenerationRequestDigest"],
            request_v2["payloadDigest"],
        )
        self.assertEqual(revision_v3["version"], 3)
        self.assertEqual(
            revision_v3["supersedesRealVideoRevisionRef"],
            active_v2["realVideoRevision"]["realVideoRevisionRef"],
        )
        self.assertEqual(
            revision_v3["supersedesRealVideoRevisionDigest"],
            active_v2["realVideoRevision"]["payloadDigest"],
        )

        restart = getattr(self, "_restart_episode_production_boundary", None)
        if restart is not None:
            restarted = restart()
            restarted_revision = (
                restarted._EpisodeProductionPublicBoundary__real_media_revision
            )
            restarted_revision.video_candidate_evidence = self.video_candidate_evidence
            restarted_revision.candidate_review.selection_authority = SelectionAuthority()
            self.boundary = restarted
            self.revision = restarted_revision
            persisted = self.boundary.get_real_media_revision(
                WORKSPACE, self.run["productionRunRef"]
            )
            self.assertEqual(persisted["videoGenerationRequests"][0], request_v3)
            self.assertEqual(persisted["realVideoRevision"], revision_v3)

        activated_v3 = self.admit_video_handoff(
            handoff_v3, prefix="m11-post-ready-video-v3"
        )
        self.assertEqual(activated_v3["state"], "REAL_VIDEO_READY")
        self.assertEqual(
            activated_v3["assetVersions"][0]["supersedesAssetVersionRef"],
            asset_v2["assetVersionRef"],
        )
        self.assertEqual(
            activated_v3["realVideoAdmissionManifest"]["newAdmissionCount"], 1
        )
        historical_v2_replay = self.revision.admit_real_videos(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-post-ready-video-v2-admit",
                "selections": [
                    {
                        "visualQcRef": selection_v2["visualQcRef"],
                        "visualQcVersion": selection_v2["visualQcVersion"],
                        "visualQcDigest": selection_v2["visualQcDigest"],
                        "selectionRef": selection_v2["selectionRef"],
                        "selectionVersion": selection_v2["selectionVersion"],
                        "approvalRef": selection_v2["approvalRef"],
                    }
                ],
            }
        )
        self.assertTrue(historical_v2_replay["idempotentReplay"])
        self.assertEqual(
            historical_v2_replay["realVideoAdmissionManifest"], activation_v2
        )
        self.assertEqual(historical_v2_replay["assetAdmissions"], admissions_v2)
        self.assertEqual(historical_v2_replay["assetVersions"], assets_v2)

    def test_post_ready_successor_cas_failure_leaves_no_partial_activation(self):
        baseline_handoff = self.record_candidates()
        self.admit_video_handoff(baseline_handoff, prefix="m11-cas-baseline")
        self.admit_shot_one_image_successor(prefix="m11-cas-image-v2")
        successor_handoff = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-cas-video-handoff-v2",
            }
        )
        validation = successor_handoff["technicalValidations"][0]
        qc = self.visual_qc(validation, 1)
        selection = self.selection_request(qc, 1)
        selection["selectionRef"] = "m11-cas-successor-selection"
        selection["approvalRef"] = "m11-cas-successor-approval"
        before = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        original_append = self.revision.evidence.append_records
        injected = False

        def interleaving_append(records, *, expected_record_journal_head=None):
            nonlocal injected
            if not injected:
                injected = True
                intervening = self.revision.candidate_review.prepare_candidate_record(
                    {
                        "workspaceRef": WORKSPACE,
                        "productionRunRef": self.run["productionRunRef"],
                        "idempotencyKey": "m11-cas-intervening-candidate",
                        "candidateRef": "m11-cas-intervening-candidate",
                        "candidateVersion": 1,
                        "revisionRef": "m11-cas-intervening-image-revision",
                        "mediaKind": "IMAGE",
                        "slotRef": "m11-cas-intervening-image-slot",
                        "sourceRequestRef": "m11-cas-intervening-image-request",
                        "sourceRequestDigest": "a" * 64,
                        "artifactRef": "m11-cas-intervening-image-artifact",
                        "artifactDigest": "b" * 64,
                        "artifactByteSize": 1,
                        "sourceAssetVersions": [],
                        "provenance": "LOCAL_EVIDENCE",
                    }
                )
                original_append((intervening,))
            return original_append(
                records,
                expected_record_journal_head=expected_record_journal_head,
            )

        self.revision.evidence.append_records = interleaving_append
        try:
            with self.assertRaises(StaleInputError):
                self.revision.admit_real_videos(
                    {
                        "workspaceRef": WORKSPACE,
                        "productionRunRef": self.run["productionRunRef"],
                        "idempotencyKey": "m11-cas-successor-admit",
                        "selections": [selection],
                    }
                )
        finally:
            self.revision.evidence.append_records = original_append
        after = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(
            [
                item["recordKind"]
                for item in after
                if item.get("idempotencyKey") == "m11-cas-successor-admit"
            ],
            [],
        )
        self.assertFalse(
            any(
                isinstance(item.get("payload"), dict)
                and item["payload"].get("operationIdempotencyKey")
                == "m11-cas-successor-admit"
                for item in after
            )
        )
        self.assertEqual(
            self.revision.evidence.current_state(
                WORKSPACE, self.run["productionRunRef"]
            ),
            "REAL_VIDEO_READY",
        )

    def test_post_ready_same_key_true_concurrency_replays_exact_batch(self):
        baseline_handoff = self.record_candidates()
        self.admit_video_handoff(
            baseline_handoff, prefix="m11-concurrent-baseline"
        )
        self.admit_shot_one_image_successor(prefix="m11-concurrent-image-v2")
        successor_handoff = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-concurrent-handoff-v2",
            }
        )
        qc = self.visual_qc(successor_handoff["technicalValidations"][0], 1)
        selection = self.selection_request(qc, 1)
        selection["selectionRef"] = "m11-concurrent-selection-v2"
        selection["approvalRef"] = "m11-concurrent-approval-v2"
        command = {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
            "idempotencyKey": "m11-concurrent-admit-v2",
            "selections": [selection],
        }
        original_append = self.revision.evidence.append_records
        append_barrier = threading.Barrier(2, timeout=20)

        def synchronized_append(records, *, expected_record_journal_head=None):
            if any(
                item.payload.get("schemaVersion")
                == "v5.k2-real-video-batch-activation.v2"
                for item in records
            ):
                append_barrier.wait()
            return original_append(
                records,
                expected_record_journal_head=expected_record_journal_head,
            )

        self.revision.evidence.append_records = synchronized_append
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(self.revision.admit_real_videos, command)
                    for _ in range(2)
                ]
                results = [item.result(timeout=60) for item in futures]
        finally:
            self.revision.evidence.append_records = original_append
        self.assertEqual(
            {item["idempotentReplay"] for item in results}, {False, True}
        )
        for field in (
            "realVideoAdmissionManifest",
            "assetAdmissions",
            "assetVersions",
            "state",
            "publicationAllowed",
        ):
            self.assertEqual(results[0][field], results[1][field])
        records = self.revision.evidence.list_records(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(
            sum(
                item.get("idempotencyKey") == "m11-concurrent-admit-v2"
                for item in records
            ),
            1,
        )
        self.assertEqual(
            sum(
                isinstance(item.get("payload"), dict)
                and item["payload"].get("operationIdempotencyKey")
                == "m11-concurrent-admit-v2"
                for item in records
            ),
            1,
        )

    def test_committed_activation_extra_field_fails_closed(self):
        baseline_handoff = self.record_candidates()
        self.admit_video_handoff(
            baseline_handoff, prefix="m11-corrupt-fields-baseline"
        )
        self.admit_shot_one_image_successor(
            prefix="m11-corrupt-fields-image-v2"
        )
        successor_handoff = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-corrupt-fields-handoff-v2",
            }
        )
        activated = self.admit_video_handoff(
            successor_handoff, prefix="m11-corrupt-fields-video-v2"
        )
        self.reseal_committed_record(
            activated["realVideoAdmissionManifest"]["admissionRef"],
            lambda payload: payload.__setitem__("unexpectedField", True),
        )
        with self.assertRaises(RepositoryUnavailableError):
            self.revision.get_revision_bundle(
                WORKSPACE, self.run["productionRunRef"]
            )

    def test_committed_reused_slot_substitution_fails_closed(self):
        baseline_handoff = self.record_candidates()
        self.admit_video_handoff(
            baseline_handoff, prefix="m11-corrupt-reused-baseline"
        )
        self.admit_shot_one_image_successor(
            prefix="m11-corrupt-reused-image-v2"
        )
        successor_handoff = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-corrupt-reused-handoff-v2",
            }
        )
        activated = self.admit_video_handoff(
            successor_handoff, prefix="m11-corrupt-reused-video-v2"
        )

        def substitute_reused(payload):
            reused = next(
                item
                for item in payload["slotActivations"]
                if item["activationSource"] == "REUSED_CURRENT"
            )
            reused["candidateDigest"] = "e" * 64

        self.reseal_committed_record(
            activated["realVideoAdmissionManifest"]["admissionRef"],
            substitute_reused,
        )
        with self.assertRaises(RepositoryUnavailableError):
            self.revision.get_video_activation_projection(
                WORKSPACE, self.run["productionRunRef"]
            )

    def test_committed_successor_revision_array_corruption_fails_closed(self):
        baseline_handoff = self.record_candidates()
        self.admit_video_handoff(
            baseline_handoff, prefix="m11-corrupt-revision-baseline"
        )
        self.admit_shot_one_image_successor(
            prefix="m11-corrupt-revision-image-v2"
        )
        successor_handoff = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-corrupt-revision-handoff-v2",
            }
        )

        def corrupt_revision(payload):
            revision = deepcopy(payload["consumedRealVideoRevision"])
            revision.pop("payloadDigest", None)
            revision["changedSlotRefs"] = []
            revision["payloadDigest"] = _digest(revision)
            payload["consumedRealVideoRevision"] = revision

        self.reseal_committed_record(
            successor_handoff["candidates"][0]["candidateRef"],
            corrupt_revision,
        )
        with self.assertRaises(RepositoryUnavailableError):
            self.revision.get_revision_bundle(
                WORKSPACE, self.run["productionRunRef"]
            )

    def test_post_ready_same_request_new_bytes_stale_then_activate_one_slot(self):
        baseline_handoff = self.record_candidates()
        baseline = self.admit_video_handoff(
            baseline_handoff, prefix="m11-same-request-baseline"
        )
        baseline_assets = {
            item["ordinal"]: item for item in baseline["assetVersions"]
        }
        self.video_candidate_evidence.tamper_after_recording = True
        replacement_handoff = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-same-request-replacement-handoff",
            }
        )
        self.assertEqual(len(replacement_handoff["candidates"]), 1)
        self.assertEqual(len(replacement_handoff["technicalValidations"]), 1)
        self.assertEqual(len(replacement_handoff["reusedCandidates"]), 3)
        replacement = replacement_handoff["candidates"][0]
        self.assertEqual(
            replacement["sourceRequestDigest"],
            self.plan["generationRequests"][0]["payloadDigest"],
        )
        self.assertNotIn("consumedGenerationRequest", replacement)
        stale = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(stale["videoLineageState"]["state"], "STALE_BLOCKED")
        self.assertEqual(stale["videoAssetVersions"], [])
        stale_projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(
            stale_projection["activeRevision"]["state"], "STALE_BLOCKED"
        )

        activated = self.admit_video_handoff(
            replacement_handoff, prefix="m11-same-request-replacement"
        )
        self.assertEqual(activated["state"], "REAL_VIDEO_READY")
        self.assertEqual(
            activated["realVideoAdmissionManifest"]["newAdmissionCount"], 1
        )
        self.assertEqual(
            activated["assetVersions"][0]["supersedesAssetVersionRef"],
            baseline_assets[1]["assetVersionRef"],
        )
        for ordinal in (2, 3, 4):
            self.assertEqual(
                activated["assetVersions"][ordinal - 1]["assetVersionRef"],
                baseline_assets[ordinal]["assetVersionRef"],
            )
        current = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(current["videoLineageState"]["state"], "CURRENT")
        self.assertEqual(len(current["videoAssetVersions"]), 4)

    def test_post_ready_superseding_qc_fail_blocks_current_asset_projection(self):
        baseline_handoff = self.record_candidates()
        admitted = self.admit_video_handoff(
            baseline_handoff, prefix="m11-post-ready-qc-baseline"
        )
        first_asset = admitted["assetVersions"][0]
        prior_qc_record = self.revision.evidence.get_record(
            WORKSPACE,
            self.run["productionRunRef"],
            first_asset["semanticVisualQcRef"],
            1,
        )
        prior_qc = prior_qc_record["payload"]
        self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-post-ready-qc-fail-v2",
                "technicalValidationRef": prior_qc["technicalValidationRef"],
                "technicalValidationVersion": prior_qc[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": prior_qc[
                    "technicalValidationDigest"
                ],
                "visualQcRef": "m11-post-ready-qc-fail-v2",
                "visualQcVersion": 2,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": "m11-post-ready-qc-fail-frame-v2",
                        "evidenceDigest": "d" * 64,
                    }
                ],
                "supersedesVisualQc": {
                    "visualQcRef": prior_qc_record["recordRef"],
                    "visualQcVersion": prior_qc_record["recordVersion"],
                    "visualQcDigest": prior_qc_record["payloadDigest"],
                    "staleReason": "new semantic evidence failed",
                },
                "checks": {
                    name: {"result": "FAIL", "note": "new evidence"}
                    for name in (
                        "identity",
                        "wardrobe",
                        "location",
                        "action",
                        "prop",
                        "motion",
                    )
                },
                "result": "FAIL",
            }
        )
        self.assertEqual(
            self.revision.evidence.current_state(
                WORKSPACE, self.run["productionRunRef"]
            ),
            "REAL_VIDEO_READY",
        )
        blocked = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(blocked["videoLineageState"]["state"], "STALE_BLOCKED")
        self.assertEqual(blocked["videoAssetAdmissions"], [])
        self.assertEqual(blocked["videoAssetVersions"], [])
        self.assertEqual(len(blocked["activeVideoAdmission"]["assetVersions"]), 4)
        projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(projection["activeRevision"]["state"], "STALE_BLOCKED")

    def test_candidate_handoff_key_pins_complete_batch_and_replays_exactly(self):
        first = self.record_candidates()
        replay = self.record_candidates()
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["candidates"], first["candidates"])

        self.video_candidate_evidence.tamper_after_recording = True
        with self.assertRaises(IdempotencyConflictError):
            self.record_candidates()

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

    def test_changed_handoff_appends_only_changed_slot_and_stales_old_qc(self):
        first = self.record_candidates()
        old_qc = self.visual_qc(first["technicalValidations"][0], 1)
        self.video_candidate_evidence.tamper_after_recording = True
        successor = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-candidate-handoff-successor-v2",
            }
        )

        successor_revisions = {
            item["revisionRef"] for item in successor["candidates"]
        }
        self.assertEqual(len(successor_revisions), 1)
        successor_revision = next(iter(successor_revisions))
        self.assertEqual(
            successor_revision, self.plan["realVideoPlan"]["realVideoPlanRef"]
        )
        self.assertEqual(len(successor["candidates"]), 1)
        self.assertEqual(len(successor["technicalValidations"]), 1)
        self.assertEqual(len(successor["reusedCandidates"]), 3)
        self.assertTrue(
            all(item.get("sourceCandidateRef") for item in successor["candidates"])
        )
        with self.assertRaises(CandidateNotSelectableError):
            self.revision.candidate_review.prepare_human_selection_record(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m11-stale-old-qc-selection-v1",
                    **self.selection_request(old_qc, 1),
                    "decision": "SELECTED",
                }
            )
        projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(
            projection["activeRevision"]["revisionRef"], successor_revision
        )
        self.assertEqual(len(projection["candidates"]), 4)
        self.assertEqual(projection["visualQcState"]["state"], "NOT_RECORDED")

    def test_image_successor_stales_old_video_and_derives_admissible_request_set(self):
        first = self.record_candidates()
        old_qcs = [
            self.visual_qc(validation, ordinal)
            for ordinal, validation in enumerate(
                first["technicalValidations"], start=1
            )
        ]

        # Admit only the Shot 01 image v2.  Production remains on the one-time
        # M11 plan; the old Shot 01 VIDEO lineage must immediately become stale.
        self.candidate_evidence.generation = 2
        image_successors = self.boundary.record_real_image_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-image-handoff-for-m11-successor-v2",
            }
        )
        image_validation = image_successors["technicalValidations"][0]
        image_qc = self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-image-qc-for-m11-successor-v2",
                "technicalValidationRef": image_validation[
                    "technicalValidationRef"
                ],
                "technicalValidationVersion": image_validation[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": image_validation["payloadDigest"],
                "visualQcRef": "m10-image-qc-for-m11-successor-v2",
                "visualQcVersion": 1,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": "m10-image-frame-for-m11-successor-v2",
                        "evidenceDigest": "8" * 64,
                    }
                ],
                "supersedesVisualQc": None,
                "checks": {
                    name: {"result": "PASS", "note": ""}
                    for name in (
                        "identity",
                        "wardrobe",
                        "location",
                        "action",
                        "prop",
                        "motion",
                    )
                },
                "result": "PASS",
            }
        )["semanticVisualQc"]
        image_admission = self.boundary.admit_real_image_successor(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-image-admit-for-m11-successor-v2",
                "selection": {
                    "visualQcRef": image_qc["visualQcRef"],
                    "visualQcVersion": image_qc["visualQcVersion"],
                    "visualQcDigest": image_qc["payloadDigest"],
                    "selectionRef": "m10-image-select-for-m11-successor-v2",
                    "selectionVersion": 1,
                    "approvalRef": "m10-image-approval-for-m11-successor-v2",
                },
            }
        )
        self.assertEqual(image_admission["assetVersion"]["version"], 2)

        stale_projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        full_lifecycle = self.revision.candidate_review.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        stale_shot = next(
            item
            for item in full_lifecycle["candidates"]
            if item["candidateRef"] == "m11-candidate-1"
        )
        self.assertEqual(stale_shot["visualQcState"], "STALE")
        self.assertNotEqual(stale_projection["visualQcState"]["state"], "PASS")
        with self.assertRaises(CandidateNotSelectableError):
            self.revision.candidate_review.prepare_human_selection_record(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m11-old-video-selection-after-image-v2",
                    **self.selection_request(old_qcs[0], 1),
                    "decision": "SELECTED",
                }
            )

        revision = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertTrue(revision["realVideoRevision"]["isSuccessor"])
        successor_request = revision["videoGenerationRequests"][0]
        self.assertEqual(successor_request["version"], 2)
        self.assertEqual(
            successor_request["sourceImageAssetVersionRef"],
            image_admission["assetVersion"]["assetVersionRef"],
        )
        self.assertEqual(
            revision["videoGenerationRequests"][1:],
            self.plan["generationRequests"][1:],
        )
        restart = getattr(self, "_restart_episode_production_boundary", None)
        if restart is not None:
            restarted = restart()
            restarted_revision = (
                restarted._EpisodeProductionPublicBoundary__real_media_revision
            )
            restarted_revision.video_candidate_evidence = (
                self.video_candidate_evidence
            )
            restarted_revision.candidate_review.selection_authority = (
                SelectionAuthority()
            )
            self.assertEqual(
                restarted.get_real_media_revision(
                    WORKSPACE, self.run["productionRunRef"]
                )["videoGenerationRequests"],
                revision["videoGenerationRequests"],
            )
            self.boundary = restarted
            self.revision = restarted_revision

        successor = self.revision.record_real_video_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-video-handoff-after-image-v2",
            }
        )
        self.assertEqual(len(successor["candidates"]), 1)
        self.assertEqual(len(successor["technicalValidations"]), 1)
        self.assertEqual(len(successor["reusedCandidates"]), 3)
        self.assertEqual(
            len({item["revisionRef"] for item in successor["candidates"]}), 1
        )
        successor_selections = []
        for ordinal, validation in enumerate(
            successor["technicalValidations"], start=1
        ):
            qc = self.revision.candidate_review.record_semantic_visual_qc(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": f"m11-successor-qc-{ordinal}-v1",
                    "technicalValidationRef": validation[
                        "technicalValidationRef"
                    ],
                    "technicalValidationVersion": validation[
                        "technicalValidationVersion"
                    ],
                    "technicalValidationDigest": validation["payloadDigest"],
                    "visualQcRef": f"m11-successor-qc-{ordinal}-v1",
                    "visualQcVersion": 1,
                    "reviewerRef": "reviewer-project-lead",
                    "reviewProfile": "k2-semantic-visual-qc-v1",
                    "evidence": [
                        {
                            "evidenceRef": f"m11-successor-frame-{ordinal}",
                            "evidenceDigest": str(ordinal + 4) * 64,
                        }
                    ],
                    "supersedesVisualQc": None,
                    "checks": {
                        name: {"result": "PASS", "note": ""}
                        for name in (
                            "identity",
                            "wardrobe",
                            "location",
                            "action",
                            "prop",
                            "motion",
                        )
                    },
                    "result": "PASS",
                }
            )["semanticVisualQc"]
            successor_selections.append(
                {
                    "visualQcRef": qc["visualQcRef"],
                    "visualQcVersion": qc["visualQcVersion"],
                    "visualQcDigest": qc["payloadDigest"],
                    "selectionRef": f"m11-successor-selection-{ordinal}",
                    "selectionVersion": 1,
                    "approvalRef": f"m11-successor-approval-{ordinal}",
                }
            )
        successor_selections.extend(
            self.selection_request(old_qcs[ordinal - 1], ordinal)
            for ordinal in (2, 3, 4)
        )
        admitted = self.revision.admit_real_videos(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m11-admit-current-four-after-image-v2",
                "selections": successor_selections,
            }
        )
        self.assertEqual(admitted["state"], "REAL_VIDEO_READY")
        self.assertEqual(len(admitted["assetVersions"]), 4)
        self.assertEqual(
            admitted["assetVersions"][0]["sourceImageAssetVersionRef"],
            image_admission["assetVersion"]["assetVersionRef"],
        )


class K2RealVideoSuccessorSqliteTests(unittest.TestCase):
    """Run the source-successor chain against the durable evidence adapter."""

    record_candidates = K2RealVideoSelectionTests.record_candidates
    visual_qc = K2RealVideoSelectionTests.visual_qc
    selection_request = staticmethod(K2RealVideoSelectionTests.selection_request)
    reseal_committed_record = K2RealVideoSelectionTests.reseal_committed_record
    admit_video_handoff = K2RealVideoSelectionTests.admit_video_handoff
    admit_shot_one_image_successor = (
        K2RealVideoSelectionTests.admit_shot_one_image_successor
    )

    def setUp(self):
        def factory(**kwargs):
            root = Path(self.directory.name)
            self._sqlite_boundary_kwargs = dict(kwargs)
            return create_local_development_boundary(
                root / "episode-production.sqlite3",
                evidence_database_path=root / "episode-evidence.sqlite3",
                production_policy_database_path=root / "production-policy.sqlite3",
                provider_experiment_database_path=root / "provider-experiments.sqlite3",
                **kwargs,
            )

        def restart():
            root = Path(self.directory.name)
            return create_local_development_boundary(
                root / "episode-production.sqlite3",
                evidence_database_path=root / "episode-evidence.sqlite3",
                production_policy_database_path=root / "production-policy.sqlite3",
                provider_experiment_database_path=root / "provider-experiments.sqlite3",
                initialize_if_missing=False,
                **self._sqlite_boundary_kwargs,
            )

        self._episode_production_boundary_factory = factory
        self._restart_episode_production_boundary = restart
        K2RealVideoSelectionTests.setUp(self)

    def tearDown(self):
        K2RealVideoSelectionTests.tearDown(self)

    def test_image_successor_chain_is_durable_and_admissible(self):
        K2RealVideoSelectionTests.test_image_successor_stales_old_video_and_derives_admissible_request_set(
            self
        )

    def test_post_ready_v2_to_v3_chain_survives_restart(self):
        K2RealVideoSelectionTests.test_post_ready_video_request_v3_immediately_supersedes_persisted_v2(
            self
        )

    def test_post_ready_same_request_replacement_is_durable(self):
        K2RealVideoSelectionTests.test_post_ready_same_request_new_bytes_stale_then_activate_one_slot(
            self
        )

    def test_post_ready_superseding_qc_fail_is_durable_and_blocks_current(self):
        K2RealVideoSelectionTests.test_post_ready_superseding_qc_fail_blocks_current_asset_projection(
            self
        )

    def test_post_ready_same_key_true_concurrency_replays_exact_batch(self):
        K2RealVideoSelectionTests.test_post_ready_same_key_true_concurrency_replays_exact_batch(
            self
        )

    def test_committed_activation_extra_field_fails_closed(self):
        K2RealVideoSelectionTests.test_committed_activation_extra_field_fails_closed(
            self
        )

    def test_committed_reused_slot_substitution_fails_closed(self):
        K2RealVideoSelectionTests.test_committed_reused_slot_substitution_fails_closed(
            self
        )

    def test_committed_successor_revision_array_corruption_fails_closed(self):
        K2RealVideoSelectionTests.test_committed_successor_revision_array_corruption_fails_closed(
            self
        )


if __name__ == "__main__":
    unittest.main()
