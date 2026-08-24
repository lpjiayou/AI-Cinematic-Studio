import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production.evidence import (
    EvidenceFact,
    GateAppend,
    InMemoryEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.media_candidate_review import (
    ASSET_VERSION,
    K2MediaCandidateReviewService,
    _record,
)
from services.v5_core_os.episode_production.state_projection import (
    K2ProductionStateProjectionService,
)


WORKSPACE = "workspace-state-projection"
RUN = "episode-production-run-state-projection"


class RootService:
    def get_run(self, workspace_ref, production_run_ref):
        return {
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "state": "ROOTS_READY",
            "payloadDigest": "1" * 64,
            "version": 1,
        }


class RuntimeReader:
    def list_jobs(self, workspace_ref, production_run_ref):
        return [
            {"state": "SUCCEEDED"},
            {"state": "SUCCEEDED"},
            {"state": "FAILED"},
        ]


class EvidenceWithCurrentVideoPlan(InMemoryEpisodeProductionEvidenceAdapter):
    def __init__(self, revision_ref, expected_count=None):
        super().__init__()
        self.revision_ref = revision_ref
        self.expected_count = expected_count
        transitions = (
            ("ROOTS_READY", "AUTHORITY_READY"),
            ("AUTHORITY_READY", "SCRIPT_VALIDATED"),
            ("SCRIPT_VALIDATED", "SHOTS_COMPILED"),
            ("SHOTS_COMPILED", "ASSETS_READY"),
            ("ASSETS_READY", "MEDIA_READY"),
            ("MEDIA_READY", "PREVIEW_READY"),
            ("PREVIEW_READY", "QC_READY"),
            ("QC_READY", "REAL_IMAGE_PLAN_READY"),
            ("REAL_IMAGE_PLAN_READY", "REAL_IMAGE_READY"),
            ("REAL_IMAGE_READY", "REAL_VIDEO_PLAN_READY"),
        )
        for index, (from_state, to_state) in enumerate(transitions, start=1):
            is_plan = to_state == "REAL_VIDEO_PLAN_READY"
            payload = (
                {
                    "realVideoPlanRef": self.revision_ref,
                    **(
                        {"expectedRequestCount": self.expected_count}
                        if self.expected_count is not None
                        else {}
                    ),
                }
                if is_plan
                else {"transitionOrdinal": index}
            )
            self.append_gate(
                GateAppend(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    gateName=(
                        "M11_REAL_VIDEO_PLAN"
                        if is_plan
                        else f"SNAPSHOT_TEST_GATE_{index}"
                    ),
                    idempotencyKey=f"snapshot-test-gate-{index}",
                    rootPayloadDigest="7" * 64,
                    requestDigest=_digest(
                        {"transitionOrdinal": index, "payload": payload}
                    ),
                    fromState=from_state,
                    toState=to_state,
                    createdAt=f"2026-08-25T00:00:{index:02d}Z",
                    facts=(
                        EvidenceFact(
                            factKind=(
                                "RealVideoPlan"
                                if is_plan
                                else f"SnapshotTestFact:{index}"
                            ),
                            factRef=(
                                self.revision_ref
                                if is_plan
                                else f"snapshot-test-fact-{index}"
                            ),
                            factVersion=1,
                            payload=payload,
                            payloadDigest=_digest(payload),
                        ),
                    ),
                )
            )


class EvidenceWithAdmittedSuccessor(EvidenceWithCurrentVideoPlan):
    def __init__(self, plan_revision_ref, admitted_revision_ref):
        super().__init__(plan_revision_ref, expected_count=1)
        self.admitted_revision_ref = admitted_revision_ref
        payload = {"revisionRef": self.admitted_revision_ref}
        self.append_gate(
            GateAppend(
                workspaceRef=WORKSPACE,
                productionRunRef=RUN,
                gateName="M11_REAL_VIDEO_ADMISSION",
                idempotencyKey="snapshot-test-video-admission",
                rootPayloadDigest="7" * 64,
                requestDigest=_digest(payload),
                fromState="REAL_VIDEO_PLAN_READY",
                toState="REAL_VIDEO_READY",
                createdAt="2026-08-25T00:00:11Z",
                facts=(
                    EvidenceFact(
                        factKind="RealVideoAdmissionManifest",
                        factRef="manifest-successor",
                        factVersion=1,
                        payload=payload,
                        payloadDigest=_digest(payload),
                    ),
                ),
            )
        )


class CandidateProjectionWithLatestRevision:
    def __init__(
        self, latest_revision_ref, visual_result=None, admission_state="NOT_ADMITTED"
    ):
        self.latest_revision_ref = latest_revision_ref
        self.visual_result = visual_result
        self.admission_state = admission_state

    def get_projection(
        self, workspace_ref, production_run_ref, *, records=None, gates=None
    ):
        del records, gates
        return {
            "schemaVersion": "v5.k2-candidate-lifecycle-projection.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "latestCandidateRevisionRef": self.latest_revision_ref,
            "candidates": [
                {
                    "candidateRef": "candidate-successor",
                    "revisionRef": self.latest_revision_ref,
                    "technicalState": "TECHNICALLY_VERIFIED",
                    "visualQcState": (
                        "NOT_STARTED"
                        if self.visual_result is None
                        else f"SEMANTIC_QC_{self.visual_result}ED"
                    ),
                    "selectionState": "UNSELECTED",
                    "admissionState": self.admission_state,
                    **(
                        {
                            "semanticVisualQc": {
                                "visualQcRef": "qc-successor",
                                "visualQcVersion": 1,
                                "candidateRef": "candidate-successor",
                                "result": self.visual_result,
                                "payloadDigest": "7" * 64,
                            }
                        }
                        if self.visual_result is not None
                        else {}
                    ),
                }
            ],
            "assetVersions": [],
            "publicationAllowed": False,
        }


class CandidateProjectionWithOnlyImageRevision(
    CandidateProjectionWithLatestRevision
):
    def get_projection(
        self, workspace_ref, production_run_ref, *, records=None, gates=None
    ):
        projection = super().get_projection(
            workspace_ref,
            production_run_ref,
            records=records,
            gates=gates,
        )
        projection["latestCandidateRevisionRefs"] = {
            "IMAGE": self.latest_revision_ref
        }
        return projection


class ValidatedActivationReader:
    def __init__(self, revision_ref):
        self.revision_ref = revision_ref

    def get_video_activation_projection(
        self,
        workspace_ref,
        production_run_ref,
        *,
        records=None,
        gates=None,
    ):
        return {
            "manifestRef": "manifest-successor",
            "manifestDigest": "5" * 64,
            "revisionRef": self.revision_ref,
            "revisionDigest": "4" * 64,
            "candidateIdentities": [
                {
                    "slotRef": "slot-successor",
                    "candidateRef": "candidate-successor",
                    "candidateDigest": None,
                }
            ],
            "lineageCurrent": True,
            "mediaKind": "VIDEO",
        }


class K2StateProjectionTests(unittest.TestCase):
    def setUp(self):
        self.evidence = InMemoryEpisodeProductionEvidenceAdapter()
        self.root = RootService()
        self.candidates = K2MediaCandidateReviewService(
            self.root,
            self.evidence,
            clock=lambda: "2026-08-23T14:00:00Z",
        )

    def test_four_axes_are_explicit_and_runtime_cannot_impersonate_production(self):
        projection = K2ProductionStateProjectionService(
            self.root, self.evidence, self.candidates, RuntimeReader()
        ).get_projection(WORKSPACE, RUN)
        self.assertEqual(projection["rootState"]["state"], "ROOTS_READY")
        self.assertEqual(
            projection["productionProjection"]["state"], "ROOTS_READY"
        )
        self.assertEqual(projection["productionState"], projection["state"])
        self.assertEqual(projection["runtimeState"]["state"], "ATTENTION_REQUIRED")
        self.assertEqual(projection["visualQcState"]["state"], "NOT_RECORDED")
        self.assertEqual(projection["activeRevision"]["state"], "NOT_RECORDED")
        self.assertTrue(
            projection["invariants"]["runtimeDoesNotAdvanceProduction"]
        )
        self.assertFalse(projection["publicationAllowed"])

    def test_missing_runtime_reader_is_explicit_not_silently_idle(self):
        projection = K2ProductionStateProjectionService(
            self.root, self.evidence, self.candidates
        ).get_projection(WORKSPACE, RUN)
        self.assertEqual(projection["runtimeState"]["state"], "UNAVAILABLE")
        self.assertEqual(
            projection["runtimeState"]["authority"], "V4_RUNTIME_NON_CANONICAL"
        )

    @staticmethod
    def _candidate_command(revision_ref, suffix):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "idempotencyKey": f"candidate-{suffix}",
            "candidateRef": f"candidate-{suffix}",
            "candidateVersion": 1,
            "revisionRef": revision_ref,
            "mediaKind": "VIDEO",
            "slotRef": f"shot-{suffix}",
            "sourceRequestRef": f"request-{suffix}",
            "sourceRequestDigest": "2" * 64,
            "sourceAssetVersions": [
                {
                    "assetVersionRef": f"source-asset-{suffix}",
                    "assetVersionDigest": "3" * 64,
                }
            ],
            "artifactRef": f"artifact-{suffix}",
            "artifactDigest": "4" * 64,
            "artifactByteSize": 1000,
            "provenance": "SELF_HOSTED_AI_GENERATED",
        }

    def _register_candidate(self, service, evidence, revision_ref, suffix):
        asset = _record(
            workspace_ref=WORKSPACE,
            run_ref=RUN,
            kind=ASSET_VERSION,
            ref=f"source-asset-{suffix}",
            version=1,
            idempotency_key=f"source-asset-{suffix}",
            created_at="2026-08-24T00:59:00Z",
            payload={
                "schemaVersion": "v5.k2-real-image-asset-version.v1",
                "assetRef": f"source-image-{suffix}",
                "assetVersionRef": f"source-asset-{suffix}",
                "version": 1,
                "mediaKind": "image",
                "creativeShotVersionRef": f"shot-{suffix}",
                "state": "REGISTERED",
                "immutable": True,
                "publicationAllowed": False,
            },
        )
        evidence.append_record(asset)
        command = self._candidate_command(revision_ref, suffix)
        command["sourceAssetVersions"][0]["assetVersionDigest"] = asset.payloadDigest
        return service.register_candidate(command)["candidate"]

    @staticmethod
    def _record_qc(service, candidate, suffix, result):
        validation = service.record_technical_validation(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "idempotencyKey": f"technical-{suffix}",
                "candidateRef": candidate["candidateRef"],
                "candidateVersion": candidate["candidateVersion"],
                "candidateDigest": candidate["payloadDigest"],
                "technicalValidationRef": f"technical-{suffix}",
                "technicalValidationVersion": 1,
                "validatorRef": "technical-validator-v1",
                "checks": [{"check": "sha256", "passed": True}],
                "result": "PASS",
            }
        )["technicalValidation"]
        return service.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "idempotencyKey": f"qc-{suffix}",
                "technicalValidationRef": validation["technicalValidationRef"],
                "technicalValidationVersion": validation[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": f"qc-{suffix}",
                "visualQcVersion": 1,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": f"review-frame-{suffix}",
                        "evidenceDigest": "5" * 64,
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

    def test_historical_failed_revision_does_not_pollute_current_plan(self):
        current_revision = "real-video-plan-current-v2"
        evidence = EvidenceWithCurrentVideoPlan(current_revision)
        candidates = K2MediaCandidateReviewService(
            self.root,
            evidence,
            clock=lambda: "2026-08-24T01:00:00Z",
        )
        old = self._register_candidate(
            candidates, evidence, "real-video-plan-history-v1", "old"
        )
        current = self._register_candidate(
            candidates, evidence, current_revision, "current"
        )
        self._record_qc(candidates, old, "old", "FAIL")
        self._record_qc(candidates, current, "current", "PASS")

        projection = K2ProductionStateProjectionService(
            self.root, evidence, candidates
        ).get_projection(WORKSPACE, RUN)
        self.assertEqual(
            projection["activeRevision"]["revisionRef"], current_revision
        )
        self.assertEqual(projection["visualQcState"]["state"], "PASS")
        self.assertEqual(projection["visualQcState"]["candidateCount"], 1)
        self.assertEqual(projection["visualQcState"]["decisionCount"], 1)
        self.assertEqual(len(projection["candidates"]), 1)
        self.assertEqual(
            projection["candidates"][0]["candidateRef"],
            current["candidateRef"],
        )
        self.assertEqual(
            projection["candidateLifecycle"]["historicalCandidateCount"], 1
        )

    def test_frozen_snapshot_projection_is_stable_after_image_successor_append(self):
        candidate = self._register_candidate(
            self.candidates,
            self.evidence,
            "real-video-plan-frozen-snapshot-v1",
            "frozen-snapshot",
        )
        self._record_qc(
            self.candidates,
            candidate,
            "frozen-snapshot",
            "PASS",
        )
        snapshot = self.evidence.read_snapshot(WORKSPACE, RUN)
        lifecycle_before = self.candidates.get_projection(
            WORKSPACE,
            RUN,
            records=snapshot.records,
            gates=snapshot.gates,
        )
        state_service = K2ProductionStateProjectionService(
            self.root,
            self.evidence,
            self.candidates,
        )
        state_before = state_service.get_projection(
            WORKSPACE,
            RUN,
            evidence_snapshot=snapshot,
        )

        source_v1 = self.evidence.get_record(
            WORKSPACE,
            RUN,
            "source-asset-frozen-snapshot",
            1,
        )
        self.assertIsNotNone(source_v1)
        source_v2 = _record(
            workspace_ref=WORKSPACE,
            run_ref=RUN,
            kind=ASSET_VERSION,
            ref="source-asset-frozen-snapshot-v2",
            version=2,
            idempotency_key="source-asset-frozen-snapshot-v2",
            created_at="2026-08-24T01:01:00Z",
            payload={
                "schemaVersion": "v5.k2-real-image-asset-version.v1",
                "assetRef": "source-image-frozen-snapshot",
                "assetVersionRef": "source-asset-frozen-snapshot-v2",
                "version": 2,
                "mediaKind": "image",
                "creativeShotVersionRef": "shot-frozen-snapshot",
                "supersedesAssetVersionRef": source_v1["recordRef"],
                "supersedesAssetVersionDigest": source_v1["payloadDigest"],
                "state": "REGISTERED",
                "immutable": True,
                "publicationAllowed": False,
            },
        )
        self.evidence.append_record(source_v2)
        self.assertNotEqual(
            snapshot.revisionToken,
            self.evidence.read_snapshot(WORKSPACE, RUN).revisionToken,
        )

        blocked_live_read = AssertionError(
            "a frozen EvidenceSnapshot projection attempted a live V5 read"
        )
        with (
            patch.object(
                self.evidence,
                "list_records",
                side_effect=blocked_live_read,
            ),
            patch.object(
                self.evidence,
                "list_gates",
                side_effect=blocked_live_read,
            ),
            patch.object(
                self.evidence,
                "get_record",
                side_effect=blocked_live_read,
            ),
            patch.object(
                self.evidence,
                "get_gate",
                side_effect=blocked_live_read,
            ),
            patch.object(
                self.evidence,
                "current_state",
                side_effect=blocked_live_read,
            ),
        ):
            lifecycle_after = self.candidates.get_projection(
                WORKSPACE,
                RUN,
                records=snapshot.records,
                gates=snapshot.gates,
            )
            state_after = state_service.get_projection(
                WORKSPACE,
                RUN,
                evidence_snapshot=snapshot,
            )
        self.assertEqual(lifecycle_after, lifecycle_before)
        self.assertEqual(state_after, state_before)

    def test_latest_candidate_journal_lineage_precedes_one_time_plan_fact(self):
        plan_revision = "real-video-plan-original-v1"
        successor_revision = "real-video-successor-review-v2"
        evidence = EvidenceWithCurrentVideoPlan(plan_revision)
        projection = K2ProductionStateProjectionService(
            self.root,
            evidence,
            CandidateProjectionWithLatestRevision(successor_revision),
        ).get_projection(WORKSPACE, RUN)

        self.assertEqual(
            projection["activeRevision"]["revisionRef"], successor_revision
        )
        self.assertEqual(
            projection["activeRevision"]["lineageSource"],
            "CANDIDATE_JOURNAL",
        )
        self.assertEqual(
            projection["productionState"], "REAL_VIDEO_PLAN_READY"
        )

    def test_video_plan_does_not_fall_back_to_latest_image_revision(self):
        plan_revision = "real-video-plan-current-v1"
        projection = K2ProductionStateProjectionService(
            self.root,
            EvidenceWithCurrentVideoPlan(plan_revision),
            CandidateProjectionWithOnlyImageRevision(
                "real-image-plan-current-v1"
            ),
        ).get_projection(WORKSPACE, RUN)

        self.assertEqual(
            projection["activeRevision"]["revisionRef"], plan_revision
        )
        self.assertEqual(
            projection["activeRevision"]["mediaKind"], "VIDEO"
        )

    def test_admission_manifest_keeps_admitted_successor_revision_active(self):
        plan_revision = "real-video-plan-original-v1"
        successor_revision = "real-video-successor-review-v2"
        evidence = EvidenceWithAdmittedSuccessor(
            plan_revision, successor_revision
        )
        projection = K2ProductionStateProjectionService(
            self.root,
            evidence,
            CandidateProjectionWithLatestRevision(
                successor_revision,
                visual_result="PASS",
                admission_state="ADMITTED",
            ),
            None,
            ValidatedActivationReader(successor_revision),
        ).get_projection(WORKSPACE, RUN)

        self.assertEqual(
            projection["activeRevision"]["revisionRef"], successor_revision
        )
        self.assertEqual(
            projection["activeRevision"]["lineageSource"],
            "ADMISSION_MANIFEST",
        )
        self.assertEqual(
            projection["productionState"], "REAL_VIDEO_READY"
        )

    def test_partial_pass_cannot_project_complete_plan_as_visual_qc_pass(self):
        revision = "real-video-plan-four-candidates"
        evidence = EvidenceWithCurrentVideoPlan(revision, expected_count=4)
        projection = K2ProductionStateProjectionService(
            self.root,
            evidence,
            CandidateProjectionWithLatestRevision(revision, visual_result="PASS"),
        ).get_projection(WORKSPACE, RUN)

        self.assertEqual(projection["visualQcState"]["state"], "IN_PROGRESS")
        self.assertEqual(
            projection["visualQcState"]["expectedCandidateCount"], 4
        )
        self.assertEqual(projection["visualQcState"]["candidateCount"], 1)
        self.assertEqual(projection["visualQcState"]["decisionCount"], 1)

    def test_multiple_candidate_revisions_use_latest_candidate_journal_lineage(self):
        first = self._register_candidate(
            self.candidates, self.evidence, "revision-one", "one"
        )
        second = self._register_candidate(
            self.candidates, self.evidence, "revision-two", "two"
        )
        self._record_qc(self.candidates, first, "one", "PASS")
        self._record_qc(self.candidates, second, "two", "PASS")

        projection = K2ProductionStateProjectionService(
            self.root, self.evidence, self.candidates
        ).get_projection(WORKSPACE, RUN)
        self.assertEqual(projection["activeRevision"]["state"], "ACTIVE")
        self.assertEqual(
            projection["activeRevision"]["revisionRef"], "revision-two"
        )
        self.assertEqual(
            projection["activeRevision"]["lineageSource"],
            "CANDIDATE_JOURNAL",
        )
        self.assertEqual(projection["visualQcState"]["state"], "PASS")

    def test_explicit_qc_supersession_projects_only_the_applicable_decision(self):
        candidate = self._register_candidate(
            self.candidates,
            self.evidence,
            "revision-supersession",
            "superseded",
        )
        old_qc = self._record_qc(
            self.candidates, candidate, "superseded", "FAIL"
        )
        lifecycle = self.candidates.get_projection(WORKSPACE, RUN)
        technical = lifecycle["candidates"][0]["technicalValidation"]
        new_qc = self.candidates.record_semantic_visual_qc(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "idempotencyKey": "qc-superseded-v2",
                "technicalValidationRef": technical["technicalValidationRef"],
                "technicalValidationVersion": technical[
                    "technicalValidationVersion"
                ],
                "technicalValidationDigest": technical["payloadDigest"],
                "visualQcRef": "qc-superseded-v2",
                "visualQcVersion": 2,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": "review-frame-superseded-v2",
                        "evidenceDigest": "6" * 64,
                    }
                ],
                "supersedesVisualQc": {
                    "visualQcRef": old_qc["visualQcRef"],
                    "visualQcVersion": old_qc["visualQcVersion"],
                    "visualQcDigest": old_qc["payloadDigest"],
                    "staleReason": "fresh evidence for unchanged exact lineage",
                },
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

        projection = K2ProductionStateProjectionService(
            self.root, self.evidence, self.candidates
        ).get_projection(WORKSPACE, RUN)
        candidate_projection = projection["candidates"][0]
        self.assertEqual(projection["visualQcState"]["state"], "PASS")
        self.assertEqual(projection["visualQcState"]["decisionCount"], 1)
        self.assertEqual(
            candidate_projection["semanticVisualQc"]["visualQcRef"],
            new_qc["visualQcRef"],
        )
        self.assertNotEqual(
            candidate_projection["semanticVisualQc"]["payloadDigest"],
            old_qc["payloadDigest"],
        )


if __name__ == "__main__":
    unittest.main()
