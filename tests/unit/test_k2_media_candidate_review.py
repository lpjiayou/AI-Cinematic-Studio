import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    StaleInputError,
)
from services.v5_core_os.episode_production.media_candidate_review import (
    ASSET_VERSION,
    CandidateLifecycleError,
    CandidateNotSelectableError,
    K2MediaCandidateReviewService,
    MediaSelectionApprovalRequiredError,
    RejectingMediaSelectionApprovalAuthority,
    VerifiedMediaSelection,
    _record,
)


WORKSPACE = "workspace-candidate-review"
RUN = "episode-production-run-candidate-review"


class RootService:
    def get_run(self, workspace_ref, production_run_ref):
        if (workspace_ref, production_run_ref) != (WORKSPACE, RUN):
            raise AssertionError("unexpected scope")
        return {
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "payloadDigest": "a" * 64,
        }


class SelectionAuthority:
    def verify(self, *, subject, approval_ref, decision):
        values = {
            "authority_ref": "approval-authority-candidate-tests",
            "approval_ref": approval_ref,
            "actor_ref": "human-candidate-reviewer",
            "actor_kind": "HUMAN",
            "decision": decision,
            "authority_decision_ref": f"authority-decision-{approval_ref}",
            "decided_at": "2026-08-24T00:00:00Z",
            "subject_digest": subject.subject_digest,
        }
        values["authority_decision_digest"] = (
            VerifiedMediaSelection.expected_decision_digest(**values)
        )
        return VerifiedMediaSelection.create(**values)


class CandidateReviewMixin:
    def evidence(self):
        raise NotImplementedError

    def seed_source_asset(self, evidence):
        source = _record(
            workspace_ref=WORKSPACE,
            run_ref=RUN,
            kind=ASSET_VERSION,
            ref="source-image-version-shot-0001-v1",
            version=1,
            idempotency_key="source-image-version-shot-0001-v1",
            created_at="2026-08-23T12:59:00Z",
            payload={
                "schemaVersion": "v5.k2-real-image-asset-version.v1",
                "assetRef": "source-image-shot-0001",
                "assetVersionRef": "source-image-version-shot-0001-v1",
                "version": 1,
                "mediaKind": "image",
                "creativeShotVersionRef": "shot-0001",
                "state": "REGISTERED",
                "immutable": True,
                "publicationAllowed": False,
            },
        )
        evidence.append_record(source)
        self.source_asset_digest = source.payloadDigest
        return source

    def service(self):
        evidence = self.evidence()
        self.seed_source_asset(evidence)
        return (
            K2MediaCandidateReviewService(
                RootService(),
                evidence,
                clock=lambda: "2026-08-23T13:00:00Z",
                selection_authority=SelectionAuthority(),
            ),
            evidence,
        )

    def candidate_command(self):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "idempotencyKey": "candidate-shot-0001-v1",
            "candidateRef": "candidate-shot-0001-v1",
            "candidateVersion": 1,
            "revisionRef": "real-video-plan-candidate-review-v1",
            "mediaKind": "VIDEO",
            "slotRef": "shot-0001",
            "sourceRequestRef": "request-shot-0001-v1",
            "sourceRequestDigest": "1" * 64,
            "artifactRef": "runtime-artifact-shot-0001-v1",
            "artifactDigest": "2" * 64,
            "artifactByteSize": 12345,
            "sourceAssetVersions": [
                {
                    "assetVersionRef": "source-image-version-shot-0001-v1",
                    "assetVersionDigest": self.source_asset_digest,
                }
            ],
            "provenance": "SELF_HOSTED_AI_GENERATED",
        }

    def record_candidate(self, service):
        return service.register_candidate(self.candidate_command())["candidate"]

    def record_validation(self, service, candidate, *, result="PASS"):
        passed = result == "PASS"
        return service.record_technical_validation(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "idempotencyKey": "technical-shot-0001-v1",
                "candidateRef": candidate["candidateRef"],
                "candidateVersion": candidate["candidateVersion"],
                "candidateDigest": candidate["payloadDigest"],
                "technicalValidationRef": "technical-shot-0001-v1",
                "technicalValidationVersion": 1,
                "validatorRef": "v4-media-artifact-verifier-v1",
                "checks": [
                    {"check": "sha256", "passed": passed},
                    {"check": "media-probe", "passed": passed},
                ],
                "result": result,
            }
        )["technicalValidation"]

    def record_qc(
        self,
        service,
        validation,
        *,
        result="PASS",
        version=1,
        supersedes=None,
    ):
        return service.record_semantic_visual_qc(
            self.qc_command(
                validation,
                result=result,
                version=version,
                supersedes=supersedes,
            )
        )["semanticVisualQc"]

    def qc_command(
        self,
        validation,
        *,
        result="PASS",
        version=1,
        supersedes=None,
    ):
        return {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "idempotencyKey": f"visual-qc-shot-0001-v{version}",
                "technicalValidationRef": validation["technicalValidationRef"],
                "technicalValidationVersion": validation["technicalValidationVersion"],
                "technicalValidationDigest": validation["payloadDigest"],
                "visualQcRef": f"visual-qc-shot-0001-v{version}",
                "visualQcVersion": version,
                "reviewerRef": "reviewer-project-lead",
                "reviewProfile": "k2-semantic-visual-qc-v1",
                "evidence": [
                    {
                        "evidenceRef": f"review-frame-shot-0001-v{version}",
                        "evidenceDigest": str(version) * 64,
                    }
                ],
                "supersedesVisualQc": supersedes,
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

    @staticmethod
    def selection_command(qc, *, decision="SELECTED", suffix="v1"):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "idempotencyKey": f"selection-shot-0001-{suffix}",
            "visualQcRef": qc["visualQcRef"],
            "visualQcVersion": qc["visualQcVersion"],
            "visualQcDigest": qc["payloadDigest"],
            "selectionRef": f"selection-shot-0001-{suffix}",
            "selectionVersion": 1,
            "approvalRef": f"approval-shot-0001-{suffix}",
            "decision": decision,
        }

    def test_selected_decision_is_sealed_but_not_written_outside_admission(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        prepared = service.prepare_human_selection_record(
            self.selection_command(qc)
        )
        self.assertEqual(prepared.payload["decision"], "SELECTED")
        self.assertEqual(prepared.payload["actorKind"], "HUMAN")
        self.assertEqual(prepared.payload["visualQcDigest"], qc["payloadDigest"])
        with self.assertRaises(CandidateLifecycleError):
            service.record_human_selection(self.selection_command(qc))
        projection = service.get_projection(WORKSPACE, RUN)
        item = projection["candidates"][0]
        self.assertEqual(item["technicalState"], "TECHNICALLY_VERIFIED")
        self.assertEqual(item["visualQcState"], "SEMANTIC_QC_PASSED")
        self.assertEqual(item["selectionState"], "UNSELECTED")
        self.assertEqual(item["admissionState"], "NOT_ADMITTED")
        self.assertEqual(
            evidence.list_records(WORKSPACE, RUN, record_kind="HumanSelectionDecision"),
            [],
        )
        self.assertEqual(evidence.current_state(WORKSPACE, RUN), "ROOTS_READY")

    def test_qc_fail_is_canonical_but_cannot_be_selected(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation, result="FAIL")
        self.assertEqual(qc["lifecycleState"], "SEMANTIC_QC_FAILED")
        with self.assertRaises(CandidateNotSelectableError):
            service.prepare_human_selection_record(self.selection_command(qc))
        projection = service.get_projection(WORKSPACE, RUN)
        self.assertEqual(
            projection["candidates"][0]["visualQcState"], "SEMANTIC_QC_FAILED"
        )
        self.assertEqual(
            len(evidence.list_records(WORKSPACE, RUN, record_kind="AssetVersion")),
            1,
        )

    def test_failed_technical_validation_cannot_reach_visual_qc(self):
        service, _ = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate, result="FAIL")
        with self.assertRaises(CandidateNotSelectableError):
            self.record_qc(service, validation)

    def test_qc_supersession_is_explicit_and_old_pass_becomes_stale(self):
        service, _ = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        first = self.record_qc(service, validation)
        second = self.record_qc(
            service,
            validation,
            result="PASS",
            version=2,
            supersedes={
                "visualQcRef": first["visualQcRef"],
                "visualQcVersion": first["visualQcVersion"],
                "visualQcDigest": first["payloadDigest"],
                "staleReason": "candidate assessment replayed under current profile",
            },
        )
        with self.assertRaises(CandidateNotSelectableError):
            service.prepare_human_selection_record(
                self.selection_command(first, suffix="old")
            )
        prepared = service.prepare_human_selection_record(
            self.selection_command(second, suffix="current")
        )
        self.assertEqual(prepared.payload["visualQcDigest"], second["payloadDigest"])
        projection = service.get_projection(WORKSPACE, RUN)
        self.assertEqual(
            projection["candidates"][0]["semanticVisualQc"]["visualQcRef"],
            second["visualQcRef"],
        )

    def test_new_candidate_for_same_slot_stales_old_qc_and_projects_media_revision(self):
        service, _ = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        old_qc = self.record_qc(service, validation)

        successor_command = dict(self.candidate_command())
        successor_command.update(
            {
                "idempotencyKey": "candidate-shot-0001-v2",
                "candidateRef": "candidate-shot-0001-v2",
                "revisionRef": "real-video-plan-candidate-review-v2",
                "artifactRef": "runtime-artifact-shot-0001-v2",
                "artifactDigest": "4" * 64,
            }
        )
        service.register_candidate(successor_command)

        with self.assertRaises(CandidateNotSelectableError):
            service.prepare_human_selection_record(
                self.selection_command(old_qc, suffix="stale-candidate")
            )
        projection = service.get_projection(WORKSPACE, RUN)
        self.assertEqual(
            projection["latestCandidateRevisionRefs"]["VIDEO"],
            successor_command["revisionRef"],
        )
        old_projection = next(
            item
            for item in projection["candidates"]
            if item["candidateRef"] == candidate["candidateRef"]
        )
        self.assertEqual(old_projection["visualQcState"], "STALE")

    def test_new_source_asset_version_stales_video_qc_without_new_candidate(self):
        service, evidence = self.service()
        source_v1 = evidence.get_record(
            WORKSPACE, RUN, "source-image-version-shot-0001-v1", 1
        )
        command = dict(self.candidate_command())
        command["sourceAssetVersions"] = [
            {
                "assetVersionRef": source_v1["recordRef"],
                "assetVersionDigest": source_v1["payloadDigest"],
            }
        ]
        candidate = service.register_candidate(command)["candidate"]
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)

        source_v2 = _record(
            workspace_ref=WORKSPACE,
            run_ref=RUN,
            kind=ASSET_VERSION,
            ref="source-image-version-shot-0001-v2",
            version=2,
            idempotency_key="source-image-version-shot-0001-v2",
            created_at="2026-08-24T00:01:00Z",
            payload={
                "assetRef": "source-image-shot-0001",
                "assetVersionRef": "source-image-version-shot-0001-v2",
                "version": 2,
                "mediaKind": "image",
                "creativeShotVersionRef": "shot-0001",
                "supersedesAssetVersionRef": source_v1["recordRef"],
                "supersedesAssetVersionDigest": source_v1["payloadDigest"],
                "state": "REGISTERED",
                "immutable": True,
                "publicationAllowed": False,
            },
        )
        evidence.append_record(source_v2)

        with self.assertRaises(CandidateNotSelectableError):
            service.prepare_human_selection_record(
                self.selection_command(qc, suffix="stale-source")
            )
        projected = service.get_projection(WORKSPACE, RUN)
        item = next(
            value
            for value in projected["candidates"]
            if value["candidateRef"] == candidate["candidateRef"]
        )
        self.assertEqual(item["applicabilityState"], "STALE")
        self.assertEqual(item["visualQcState"], "STALE")

    def test_missing_canonical_source_asset_fails_video_currentness_closed(self):
        evidence = self.evidence()
        service = K2MediaCandidateReviewService(
            RootService(),
            evidence,
            clock=lambda: "2026-08-24T00:00:00Z",
            selection_authority=SelectionAuthority(),
        )
        self.source_asset_digest = "3" * 64
        candidate = service.register_candidate(self.candidate_command())["candidate"]
        validation = self.record_validation(service, candidate)
        with self.assertRaises(StaleInputError):
            self.record_qc(service, validation)
        projected = service.get_projection(WORKSPACE, RUN)["candidates"][0]
        self.assertEqual(projected["applicabilityState"], "STALE")

    def test_visual_qc_cas_rejects_intervening_candidate_append(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        original_append = evidence.append_records
        injected = False

        def interleaving_append(
            records, *, expected_record_journal_head=None
        ):
            nonlocal injected
            if not injected:
                injected = True
                intervening = dict(self.candidate_command())
                intervening.update(
                    {
                        "idempotencyKey": "candidate-intervening-v1",
                        "candidateRef": "candidate-intervening-v1",
                        "slotRef": "shot-intervening",
                        "sourceRequestRef": "request-intervening-v1",
                        "artifactRef": "artifact-intervening-v1",
                        "artifactDigest": "6" * 64,
                    }
                )
                service.register_candidate(intervening)
            return original_append(
                records,
                expected_record_journal_head=expected_record_journal_head,
            )

        evidence.append_records = interleaving_append
        with self.assertRaises(StaleInputError):
            self.record_qc(service, validation)
        self.assertEqual(
            evidence.list_records(
                WORKSPACE, RUN, record_kind="SemanticVisualQCDecision"
            ),
            [],
        )

    def test_default_selection_authority_fails_closed(self):
        evidence = self.evidence()
        service = K2MediaCandidateReviewService(
            RootService(), evidence, clock=lambda: "2026-08-23T13:00:00Z"
        )
        self.seed_source_asset(evidence)
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        with self.assertRaises(MediaSelectionApprovalRequiredError):
            service.prepare_human_selection_record(self.selection_command(qc))

    def test_rejected_decision_is_append_only_without_admission(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        rejected = service.record_human_selection(
            self.selection_command(qc, decision="REJECTED")
        )["humanSelection"]
        self.assertEqual(rejected["decision"], "REJECTED")
        self.assertEqual(
            len(evidence.list_records(WORKSPACE, RUN, record_kind="AssetVersion")),
            1,
        )

    def test_all_stages_replay_without_duplicate_records(self):
        service, evidence = self.service()
        first = service.register_candidate(self.candidate_command())
        replay = service.register_candidate(self.candidate_command())
        self.assertFalse(first["idempotentReplay"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(len(evidence.list_records(WORKSPACE, RUN)), 2)

    def test_exact_qc_replays_after_supersession_without_revalidating_currentness(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        original_command = self.qc_command(validation)
        first = service.record_semantic_visual_qc(original_command)
        self.record_qc(
            service,
            validation,
            version=2,
            supersedes={
                "visualQcRef": first["semanticVisualQc"]["visualQcRef"],
                "visualQcVersion": first["semanticVisualQc"]["visualQcVersion"],
                "visualQcDigest": first["semanticVisualQc"]["payloadDigest"],
                "staleReason": "newer canonical review",
            },
        )
        replay = service.record_semantic_visual_qc(original_command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["semanticVisualQc"], first["semanticVisualQc"])
        self.assertEqual(
            len(
                evidence.list_records(
                    WORKSPACE, RUN, record_kind="SemanticVisualQCDecision"
                )
            ),
            2,
        )

    def test_concurrent_exact_qc_has_one_winner_and_one_replay(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        command = self.qc_command(validation)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: service.record_semantic_visual_qc(command),
                    range(2),
                )
            )
        self.assertEqual(
            sorted(item["idempotentReplay"] for item in results),
            [False, True],
        )
        self.assertEqual(
            len(
                evidence.list_records(
                    WORKSPACE, RUN, record_kind="SemanticVisualQCDecision"
                )
            ),
            1,
        )

    def test_same_qc_key_changed_payload_conflicts_after_supersession(self):
        service, _ = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        original = self.qc_command(validation)
        first = service.record_semantic_visual_qc(original)["semanticVisualQc"]
        self.record_qc(
            service,
            validation,
            version=2,
            supersedes={
                "visualQcRef": first["visualQcRef"],
                "visualQcVersion": first["visualQcVersion"],
                "visualQcDigest": first["payloadDigest"],
                "staleReason": "newer canonical review",
            },
        )
        changed = self.qc_command(validation)
        changed["evidence"] = [
            {"evidenceRef": "changed-frame", "evidenceDigest": "9" * 64}
        ]
        with self.assertRaises(IdempotencyConflictError):
            service.record_semantic_visual_qc(changed)

    def test_selection_replays_after_qc_supersession_and_authority_outage(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        command = self.selection_command(qc, decision="REJECTED")
        first = service.record_human_selection(command)
        self.record_qc(
            service,
            validation,
            version=2,
            supersedes={
                "visualQcRef": qc["visualQcRef"],
                "visualQcVersion": qc["visualQcVersion"],
                "visualQcDigest": qc["payloadDigest"],
                "staleReason": "newer canonical review",
            },
        )
        service.selection_authority = RejectingMediaSelectionApprovalAuthority()
        replay = service.record_human_selection(command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["humanSelection"], first["humanSelection"])
        self.assertEqual(
            len(
                evidence.list_records(
                    WORKSPACE, RUN, record_kind="HumanSelectionDecision"
                )
            ),
            1,
        )

    def test_concurrent_exact_rejected_selection_has_one_winner_and_one_replay(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        command = self.selection_command(qc, decision="REJECTED")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: service.record_human_selection(command),
                    range(2),
                )
            )
        self.assertEqual(
            sorted(item["idempotentReplay"] for item in results),
            [False, True],
        )
        self.assertEqual(
            len(
                evidence.list_records(
                    WORKSPACE, RUN, record_kind="HumanSelectionDecision"
                )
            ),
            1,
        )

    def test_same_candidate_qc_approval_cannot_create_second_selection_identity(self):
        service, _ = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        first = self.selection_command(qc, decision="REJECTED", suffix="first")
        service.record_human_selection(first)
        duplicate_authority = self.selection_command(
            qc, decision="REJECTED", suffix="second"
        )
        duplicate_authority["approvalRef"] = first["approvalRef"]
        with self.assertRaises(IdempotencyConflictError):
            service.record_human_selection(duplicate_authority)

    def test_selection_identity_cannot_alias_a_different_operation_key(self):
        service, evidence = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        command = self.selection_command(
            qc, decision="REJECTED", suffix="identity-key"
        )
        first = service.record_human_selection(command)

        alias = dict(command)
        alias["idempotencyKey"] = "selection-different-operation-key"
        with self.assertRaises(IdempotencyConflictError):
            service.record_human_selection(alias)

        self.assertIsNone(
            evidence.get_record_by_idempotency_key(
                WORKSPACE,
                RUN,
                alias["idempotencyKey"],
            )
        )
        self.assertEqual(
            evidence.get_record_by_idempotency_key(
                WORKSPACE,
                RUN,
                command["idempotencyKey"],
            )["payload"],
            first["humanSelection"],
        )


class InMemoryCandidateReviewTests(CandidateReviewMixin, unittest.TestCase):
    def evidence(self):
        return InMemoryEpisodeProductionEvidenceAdapter()


class SqliteCandidateReviewTests(CandidateReviewMixin, unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def evidence(self):
        return SqliteEpisodeProductionEvidenceAdapter(
            Path(self.temporary_directory.name) / "evidence.sqlite3",
            initialize_if_missing=True,
        )

    def test_restart_exact_qc_replay_uses_durable_operation_record(self):
        service, _ = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        command = self.qc_command(validation)
        first = service.record_semantic_visual_qc(command)

        restarted, evidence = self.service()
        replay = restarted.record_semantic_visual_qc(command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["semanticVisualQc"], first["semanticVisualQc"])
        self.assertEqual(
            len(
                evidence.list_records(
                    WORKSPACE, RUN, record_kind="SemanticVisualQCDecision"
                )
            ),
            1,
        )

    def test_restart_exact_selection_replay_skips_live_authority(self):
        service, _ = self.service()
        candidate = self.record_candidate(service)
        validation = self.record_validation(service, candidate)
        qc = self.record_qc(service, validation)
        command = self.selection_command(qc, decision="REJECTED")
        first = service.record_human_selection(command)

        restarted, evidence = self.service()
        restarted.selection_authority = RejectingMediaSelectionApprovalAuthority()
        replay = restarted.record_human_selection(command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["humanSelection"], first["humanSelection"])
        self.assertEqual(
            len(
                evidence.list_records(
                    WORKSPACE, RUN, record_kind="HumanSelectionDecision"
                )
            ),
            1,
        )

if __name__ == "__main__":
    unittest.main()
