import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    V4CompositionExecutor,
)
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_in_memory_boundary,
    create_local_development_boundary,
)
from services.v5_core_os.episode_production.media_candidate_review import (
    RejectingMediaSelectionApprovalAuthority,
    VerifiedMediaSelection,
)
from services.v5_core_os.episode_production.foundation import (
    RepositoryUnavailableError,
)
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    g2_command,
    g3_command,
    g4_command,
    g5_command,
    g6_preview_command,
    k2_identity_authority,
    run_command,
    seed_k2_roots,
)


def _digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


class StubRealImageCandidateEvidence:
    def __init__(self) -> None:
        self.calls = 0
        self.generation = 1

    @staticmethod
    def candidate_ref(ordinal: int) -> str:
        return f"m10-reviewed-candidate-{ordinal}"

    def content_digest(self, ordinal: int) -> str:
        return _digest(
            f"m10-candidate-content-{ordinal}-generation-{self.generation}"
        )

    def resolve_candidates(
        self,
        workspace_ref,
        production_run_ref,
        real_image_plan_ref,
        expected_requests,
    ):
        self.calls += 1
        return {
            "candidateEvidenceRef": (
                f"candidate-evidence-test-v{self.generation}"
            ),
            "candidateEvidenceDigest": _digest(
                f"candidate-evidence-{self.generation}"
            ),
            "artifactStoreRef": "artifact-store-test-v1",
            "modelSetDigest": _digest("model-set"),
            "adapterIdentity": "v4.comfyui.pinned-image-evidence.v1",
            "candidates": [
                {
                    "candidateRef": self.candidate_ref(request["ordinal"]),
                    "ordinal": request["ordinal"],
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestDigest": request["payloadDigest"],
                    "creativeShotVersionRef": request[
                        "creativeShotVersionRef"
                    ],
                    "workflowDigest": _digest(
                        f"workflow-{request['ordinal']}"
                    ),
                    "artifact": {
                        "storageKey": (
                            f"m10/shot-{request['ordinal']:02d}.png"
                        ),
                        "sha256": self.content_digest(request["ordinal"]),
                        "byteSize": 10_000 + request["ordinal"],
                        "width": request["parameters"]["width"],
                        "height": request["parameters"]["height"],
                        "mediaType": "image/png",
                    },
                    "state": "TECHNICALLY_VERIFIED",
                    "provenance": "SELF_HOSTED_AI_GENERATED",
                    "gpuUsed": True,
                    "publicationAllowed": False,
                }
                for request in expected_requests
            ],
            "publicationAllowed": False,
        }


class SelectionAuthority:
    def verify(self, *, subject, approval_ref, decision):
        values = {
            "authority_ref": "approval-authority-k2-image-test",
            "approval_ref": approval_ref,
            "actor_ref": "human-reviewer-k2-image-test",
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


class K2RealImageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(self.assembly, self.project, self.series)
        artifact_root = Path(self.directory.name) / "artifacts"
        execution = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            DeterministicLocalFfmpegAdapter(),
            artifact_root,
            ref_factory=self.refs,
            clock=lambda: "2026-08-23T08:00:00Z",
        )
        self.candidate_evidence = StubRealImageCandidateEvidence()
        boundary_factory = getattr(
            self, "_episode_production_boundary_factory", create_in_memory_boundary
        )
        self.boundary = boundary_factory(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            real_image_candidate_evidence=self.candidate_evidence,
            media_execution=execution,
            composition_execution=V4CompositionExecutor.from_artifact_root(
                artifact_root
            ),
            ref_factory=self.refs,
            clock=lambda: "2026-08-23T08:00:00Z",
        )
        self.run = self.boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        self.boundary.authorize_and_lock(g2_command(self.run))
        self.boundary.compile_shot_graph(g3_command(self.run))
        self.boundary.resolve_assets(g4_command(self.run))
        self.boundary.execute_media(g5_command(self.run))
        self.boundary.compose_and_qc(g6_preview_command(self.run))
        self.plan = self.boundary.plan_real_images(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-image-plan-selection-tests",
            }
        )
        self.revision = (
            self.boundary._EpisodeProductionPublicBoundary__real_media_revision
        )
        self.revision.candidate_review.selection_authority = SelectionAuthority()
        self.recorded = self.boundary.record_real_image_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-image-candidate-handoff-tests",
            }
        )
        self.qcs = [
            K2RealImageSelectionTests.visual_qc(self, validation, ordinal)
            for ordinal, validation in enumerate(
                self.recorded["technicalValidations"], start=1
            )
        ]

    def tearDown(self):
        self.directory.cleanup()

    def visual_qc(self, validation, ordinal):
        return self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"m10-visual-qc-{ordinal}-v1",
                "technicalValidationRef": validation[
                    "technicalValidationRef"
                ],
                "technicalValidationVersion": 1,
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": f"m10-visual-qc-{ordinal}-v1",
                "visualQcVersion": 1,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": f"m10-review-frame-{ordinal}",
                        "evidenceDigest": str(ordinal) * 64,
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

    def selection_command(self):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
            "idempotencyKey": "m10-four-image-selection-v1",
            "selections": [
                {
                    "visualQcRef": qc["visualQcRef"],
                    "visualQcVersion": qc["visualQcVersion"],
                    "visualQcDigest": qc["payloadDigest"],
                    "selectionRef": f"m10-selection-{ordinal}-v1",
                    "selectionVersion": 1,
                    "approvalRef": f"m10-approval-{ordinal}-v1",
                }
                for ordinal, qc in enumerate(self.qcs, start=1)
            ],
        }

    def _prepare_successor_command(self, suffix):
        baseline = self.boundary.select_real_images(self.selection_command())
        self.candidate_evidence.generation = 2
        successor_candidates = self.boundary.record_real_image_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"m10-successor-handoff-{suffix}",
            }
        )
        validation = successor_candidates["technicalValidations"][0]
        qc = self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": f"m10-successor-qc-{suffix}",
                "technicalValidationRef": validation[
                    "technicalValidationRef"
                ],
                "technicalValidationVersion": validation[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": f"m10-successor-qc-{suffix}",
                "visualQcVersion": 1,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": f"m10-successor-frame-{suffix}",
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
        return baseline, {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
            "idempotencyKey": f"m10-successor-admission-{suffix}",
            "selection": {
                "visualQcRef": qc["visualQcRef"],
                "visualQcVersion": qc["visualQcVersion"],
                "visualQcDigest": qc["payloadDigest"],
                "selectionRef": f"m10-successor-selection-{suffix}",
                "selectionVersion": 1,
                "approvalRef": f"m10-successor-approval-{suffix}",
            },
        }

    def _assert_concurrent_exact_successor_replays_complete_batch(self, suffix):
        _, command = self._prepare_successor_command(suffix)
        evidence = self.revision.evidence
        original_append_records = evidence.append_records
        append_barrier = Barrier(2)

        def interleaved_append(records, **kwargs):
            if len(records) == 3:
                append_barrier.wait(timeout=10)
            return original_append_records(records, **kwargs)

        evidence.append_records = interleaved_append
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda _: self.boundary.admit_real_image_successor(
                            command
                        ),
                        range(2),
                    )
                )
        finally:
            evidence.append_records = original_append_records

        self.assertEqual(
            sorted(item["idempotentReplay"] for item in results),
            [False, True],
        )
        self.assertEqual(results[0]["humanSelection"], results[1]["humanSelection"])
        self.assertEqual(results[0]["assetAdmission"], results[1]["assetAdmission"])
        self.assertEqual(results[0]["assetVersion"], results[1]["assetVersion"])
        selection = results[0]["humanSelection"]
        admission = results[0]["assetAdmission"]
        asset = results[0]["assetVersion"]
        selection_records = [
            item
            for item in evidence.list_records(
                WORKSPACE,
                self.run["productionRunRef"],
                record_kind="HumanSelectionDecision",
            )
            if item["idempotencyKey"] == command["idempotencyKey"]
        ]
        admission_records = [
            item
            for item in evidence.list_records(
                WORKSPACE,
                self.run["productionRunRef"],
                record_kind="AssetAdmission",
            )
            if item["payload"].get("selectionRef")
            == selection["selectionRef"]
            and item["payload"].get("selectionDigest")
            == selection["payloadDigest"]
        ]
        asset_records = [
            item
            for item in evidence.list_records(
                WORKSPACE,
                self.run["productionRunRef"],
                record_kind="AssetVersion",
            )
            if item["recordRef"] == admission["assetVersionRef"]
            and item["payloadDigest"] == admission["assetVersionDigest"]
        ]
        self.assertEqual(
            (len(selection_records), len(admission_records), len(asset_records)),
            (1, 1, 1),
        )
        self.assertEqual(
            {
                field: asset_records[0]["payload"][field]
                for field in (
                    "assetVersionRef",
                    "version",
                    "sha256",
                    "payloadDigest",
                )
            },
            {
                field: asset[field]
                for field in (
                    "assetVersionRef",
                    "version",
                    "sha256",
                    "payloadDigest",
                )
            },
        )

    def test_concurrent_exact_successor_replays_one_complete_three_record_batch(self):
        self._assert_concurrent_exact_successor_replays_complete_batch("memory")

    def test_records_exact_human_selections_and_four_immutable_assets(self):
        result = self.boundary.select_real_images(self.selection_command())
        self.assertEqual(result["state"], "REAL_IMAGE_READY")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(len(result["candidates"]), 4)
        self.assertEqual(len(result["selectionDecisions"]), 4)
        self.assertEqual(len(result["assetVersions"]), 4)
        self.assertEqual(
            [item["ordinal"] for item in result["assetVersions"]],
            [1, 2, 3, 4],
        )
        for decision, asset in zip(
            result["selectionDecisions"], result["assetVersions"]
        ):
            self.assertEqual(decision["actorKind"], "HUMAN")
            self.assertEqual(decision["decision"], "SELECTED")
            self.assertEqual(
                asset["humanSelectionDigest"],
                decision["payloadDigest"],
            )
            self.assertTrue(asset["immutable"])
            self.assertEqual(asset["state"], "REGISTERED")
            self.assertFalse(asset["publicationAllowed"])
        self.assertEqual(
            result["realImageAdmissionManifest"]["admittedCount"], 4
        )
        self.assertNotIn(
            "internalPath", json.dumps(result, ensure_ascii=False)
        )
        projected = self.boundary.get_run(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(projected["state"], "REAL_IMAGE_READY")
        self.assertEqual(
            projected["completedGates"][-1], "M10_REAL_IMAGE_ADMISSION"
        )
        restored = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(
            restored["realImagePlan"]["payloadDigest"],
            self.plan["realImagePlan"]["payloadDigest"],
        )
        self.assertEqual(restored["assetVersions"], result["assetVersions"])

    def test_exact_replay_does_not_reopen_candidate_evidence(self):
        first = self.boundary.select_real_images(self.selection_command())
        replay = self.boundary.select_real_images(self.selection_command())
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["assetVersions"], first["assetVersions"])
        self.assertEqual(self.candidate_evidence.calls, 2)

    def test_candidate_handoff_key_pins_complete_batch_and_replays_exactly(self):
        replay = self.boundary.record_real_image_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-image-candidate-handoff-tests",
            }
        )
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["candidates"], self.recorded["candidates"])

        self.candidate_evidence.generation = 2
        with self.assertRaises(EpisodeProductionPublicError) as conflict:
            self.boundary.record_real_image_candidates(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m10-image-candidate-handoff-tests",
                }
            )
        self.assertEqual(
            (conflict.exception.status, conflict.exception.code),
            (409, "idempotency_conflict"),
        )

    def test_candidate_handoff_rejects_incomplete_typed_batch_readback(self):
        evidence = self.revision.evidence
        original_append_records = evidence.append_records

        def incomplete_readback(records, **kwargs):
            stored, replayed = original_append_records(records, **kwargs)
            if len(records) == 8:
                return stored[:-1], replayed
            return stored, replayed

        evidence.append_records = incomplete_readback
        try:
            with self.assertRaises(RepositoryUnavailableError):
                self.revision.record_real_image_candidates(
                    {
                        "workspaceRef": WORKSPACE,
                        "productionRunRef": self.run["productionRunRef"],
                        "idempotencyKey": "m10-image-candidate-handoff-tests",
                    }
                )
        finally:
            evidence.append_records = original_append_records

    def test_image_admission_replay_rejects_incomplete_typed_bundle(self):
        command = self.selection_command()
        self.boundary.select_real_images(command)
        original_bundle = self.revision._admission_bundle

        def incomplete_bundle(gate, **kwargs):
            bundle = original_bundle(gate, **kwargs)
            bundle["assetAdmissions"] = bundle["assetAdmissions"][:-1]
            return bundle

        self.revision._admission_bundle = incomplete_bundle
        try:
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                self.boundary.select_real_images(command)
        finally:
            self.revision._admission_bundle = original_bundle
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (503, "episode_production_unavailable"),
        )

    def test_rejects_one_changed_candidate_digest_atomically(self):
        command = self.selection_command()
        command["selections"][2]["visualQcDigest"] = _digest(
            "not-the-reviewed-candidate"
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.select_real_images(command)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "stale_input"),
        )
        self.assertEqual(
            self.boundary.get_run(
                WORKSPACE, self.run["productionRunRef"]
            )["state"],
            "REAL_IMAGE_PLAN_READY",
        )

    def test_rejects_partial_selection_before_candidate_evidence(self):
        command = self.selection_command()
        command["selections"].pop()
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.select_real_images(command)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "invalid_request"),
        )
        self.assertEqual(self.candidate_evidence.calls, 1)

    def test_post_baseline_candidate_revision_admits_one_successor_without_state_rewind(self):
        baseline = self.boundary.select_real_images(self.selection_command())
        predecessor = baseline["assetVersions"][0]
        self.candidate_evidence.generation = 2
        successor_candidates = self.boundary.record_real_image_candidates(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-image-candidate-handoff-successor-v2",
            }
        )
        validation = successor_candidates["technicalValidations"][0]
        qc = self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-successor-visual-qc-1-v1",
                "technicalValidationRef": validation[
                    "technicalValidationRef"
                ],
                "technicalValidationVersion": validation[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": "m10-successor-visual-qc-1-v1",
                "visualQcVersion": 1,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": "m10-successor-review-frame-1",
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
        successor_command = {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
            "idempotencyKey": "m10-image-successor-admission-v2",
            "selection": {
                "visualQcRef": qc["visualQcRef"],
                "visualQcVersion": qc["visualQcVersion"],
                "visualQcDigest": qc["payloadDigest"],
                "selectionRef": "m10-successor-selection-1-v1",
                "selectionVersion": 1,
                "approvalRef": "m10-successor-approval-1-v1",
            },
        }
        admitted = self.boundary.admit_real_image_successor(successor_command)
        self.assertEqual(admitted["state"], "REAL_IMAGE_READY")
        self.assertEqual(admitted["assetVersion"]["version"], 2)
        self.assertEqual(
            admitted["assetVersion"]["supersedesAssetVersionRef"],
            predecessor["assetVersionRef"],
        )
        self.assertNotEqual(
            admitted["assetVersion"]["revisionRef"],
            self.plan["realImagePlan"]["realImagePlanRef"],
        )
        projection = self.revision.state_projection.get_projection(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(
            projection["productionState"], "REAL_IMAGE_READY"
        )
        self.assertEqual(len(projection["candidates"]), 4)

        duplicate = json.loads(json.dumps(successor_command))
        duplicate["idempotencyKey"] = "m10-image-successor-duplicate-v2"
        duplicate["selection"]["selectionRef"] = (
            "m10-successor-selection-duplicate-v1"
        )
        with self.assertRaises(EpisodeProductionPublicError) as conflict:
            self.boundary.admit_real_image_successor(duplicate)
        self.assertEqual(
            (conflict.exception.status, conflict.exception.code),
            (409, "idempotency_conflict"),
        )

        self.revision.candidate_review.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
                "idempotencyKey": "m10-successor-visual-qc-1-v2",
                "technicalValidationRef": validation[
                    "technicalValidationRef"
                ],
                "technicalValidationVersion": validation[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": "m10-successor-visual-qc-1-v2",
                "visualQcVersion": 2,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": "m10-successor-review-frame-1-v2",
                        "evidenceDigest": "9" * 64,
                    }
                ],
                "supersedesVisualQc": {
                    "visualQcRef": qc["visualQcRef"],
                    "visualQcVersion": qc["visualQcVersion"],
                    "visualQcDigest": qc["payloadDigest"],
                    "staleReason": "newer canonical review",
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
        self.revision.candidate_review.selection_authority = (
            RejectingMediaSelectionApprovalAuthority()
        )
        replay = self.boundary.admit_real_image_successor(successor_command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["assetVersion"], admitted["assetVersion"])

    def test_intervening_candidate_append_cannot_partially_admit_assets(self):
        review = self.revision.candidate_review
        delegate = SelectionAuthority()
        injected = False

        class InterleavingAuthority:
            def verify(inner_self, *, subject, approval_ref, decision):
                nonlocal injected
                if not injected:
                    injected = True
                    review.register_candidate(
                        {
                            "workspaceRef": WORKSPACE,
                            "productionRunRef": self.run[
                                "productionRunRef"
                            ],
                            "idempotencyKey": "m10-intervening-candidate-v1",
                            "candidateRef": "m10-intervening-candidate-v1",
                            "candidateVersion": 1,
                            "revisionRef": "m10-intervening-revision-v1",
                            "mediaKind": "IMAGE",
                            "slotRef": "intervening-shot-slot",
                            "sourceRequestRef": "intervening-request-v1",
                            "sourceRequestDigest": "a" * 64,
                            "artifactRef": "intervening-artifact-v1",
                            "artifactDigest": "b" * 64,
                            "artifactByteSize": 1234,
                            "sourceAssetVersions": [],
                            "provenance": "SELF_HOSTED_AI_GENERATED",
                        }
                    )
                return delegate.verify(
                    subject=subject,
                    approval_ref=approval_ref,
                    decision=decision,
                )

        review.selection_authority = InterleavingAuthority()
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.select_real_images(self.selection_command())
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "stale_input"),
        )
        for kind in (
            "HumanSelectionDecision",
            "AssetAdmission",
            "AssetVersion",
        ):
            self.assertEqual(
                self.revision.evidence.list_records(
                    WORKSPACE,
                    self.run["productionRunRef"],
                    record_kind=kind,
                ),
                [],
            )
        self.assertEqual(
            self.revision.evidence.current_state(
                WORKSPACE, self.run["productionRunRef"]
            ),
            "REAL_IMAGE_PLAN_READY",
        )


class K2RealImageSuccessorSqliteConcurrencyTests(unittest.TestCase):
    def test_concurrent_exact_successor_replays_one_complete_three_record_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            database_root = Path(directory)

            def sqlite_boundary(**kwargs):
                return create_local_development_boundary(
                    database_root / "episode-production.sqlite3",
                    evidence_database_path=(
                        database_root / "episode-production-evidence.sqlite3"
                    ),
                    production_policy_database_path=(
                        database_root / "production-policy.sqlite3"
                    ),
                    provider_experiment_database_path=(
                        database_root / "provider-experiments.sqlite3"
                    ),
                    **kwargs,
                )

            fixture = K2RealImageSelectionTests(
                "test_concurrent_exact_successor_replays_one_complete_three_record_batch"
            )
            with patch(
                f"{__name__}.create_in_memory_boundary",
                side_effect=sqlite_boundary,
            ):
                fixture.setUp()
            try:
                fixture._assert_concurrent_exact_successor_replays_complete_batch(
                    "sqlite"
                )
            finally:
                fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
