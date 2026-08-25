import copy
from hashlib import sha256
import json
import unittest

import services.v5_core_os.episode_production as episode_production_package
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    StaticIdentityReferenceAuthority,
    create_in_memory_boundary,
)
from services.v5_core_os.episode_production import dynamic_media_revision
from services.v5_core_os.episode_production.foundation import _digest
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    g3_command,
    g6_finalize_command,
    seed_k2_roots,
)
from tests.unit.test_k2_002_shot_profile_v2 import (
    PortraitProjectBoundary,
    _activate_k2_002_roots,
    _reseal,
    ep01_shot_budgets,
)


FIXED_BLOCKERS = {
    "M10_CANONICAL_APPEND_NOT_IMPLEMENTED",
    "K2_002_REGISTRATION_PROVENANCE_NOT_VERIFIED_BY_PREFLIGHT",
    "SCRIPT_OWNER_ACCEPTANCE_NOT_VERIFIED_BY_PREFLIGHT",
    "SHOT_PLAN_APPROVAL_NOT_VERIFIED",
    "CAMERA_CONTRACT_NOT_READY",
    "INPUT_ASSET_ADMISSION_NOT_VERIFIED",
    "RIGHTS_AUTHORITY_NOT_VERIFIED",
    "PROVIDER_POLICY_NOT_VERIFIED",
    "BUDGET_AUTHORITY_NOT_VERIFIED",
    "RUNTIME_CAPABILITY_NOT_VERIFIED",
}


def _k2_002_identity_authority():
    def reference(character_ref, media_type):
        return {
            "referenceRef": f"identity-reference-{character_ref}",
            "referenceVersionRef": (
                f"identity-reference-version-{character_ref}-1"
            ),
            "contentDigest": sha256(
                f"{character_ref}:local-reference:v1".encode()
            ).hexdigest(),
            "mediaType": media_type,
            "rightsState": "LOCAL_EVIDENCE_ONLY",
            "provenance": "LOCAL_EVIDENCE",
            "approvalRef": f"local-evidence-approval-{character_ref}",
        }

    return StaticIdentityReferenceAuthority(
        {
            "character-lin": reference("character-lin", "image/png"),
            "character-gu": reference("character-gu", "identity-direction"),
        }
    )


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


class K2DynamicMediaPreflightTests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            generated,
        ) = seed_k2_roots(with_m6_authority=True)
        self.generated = _activate_k2_002_roots(
            self.assembly,
            self.project,
            self.series,
            self.episode,
            generated,
        )
        self.boundary = self._boundary()
        self.run = self.boundary.create_run(
            self._run_command("k2-002-image-preflight")
        )
        self.boundary.authorize_and_lock(self._authority_command(self.run))
        compiled = self.boundary.compile_shot_graph(g3_command(self.run))
        self.draft = compiled["shotPlanDraft"]
        self.creative_shots = compiled["creativeShotDrafts"]

    def _boundary(self):
        return create_in_memory_boundary(
            project_boundary=PortraitProjectBoundary(
                self.assembly.project_context
            ),
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=_k2_002_identity_authority(),
            ref_factory=self.refs,
            clock=lambda: "2026-08-25T00:00:00Z",
        )

    def _run_command(self, idempotency_key, *, shot_budgets=None):
        return {
            "workspaceRef": WORKSPACE,
            "projectRef": self.project["projectRef"],
            "seriesRef": self.series["seriesRef"],
            "episodeRef": self.episode["episodeRef"],
            "idempotencyKey": idempotency_key,
            "shotBudgets": (
                ep01_shot_budgets(self.generated["scriptVersion"])
                if shot_budgets is None
                else shot_budgets
            ),
        }

    @staticmethod
    def _authority_command(run):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": run["productionRunRef"],
            "idempotencyKey": f"authority-{run['productionRunRef']}",
            "characterMappings": [
                {
                    "scriptCharacterName": "沈知微",
                    "characterRef": "character-lin",
                },
                {
                    "scriptCharacterName": "裴昀",
                    "characterRef": "character-gu",
                },
            ],
        }

    def _preflight(self):
        return self.boundary.preflight_dynamic_real_media_plan(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": self.run["productionRunRef"],
            }
        )

    def test_module_exports_only_the_non_executable_preflight_service(self):
        self.assertEqual(
            dynamic_media_revision.__all__,
            [
                "DYNAMIC_MEDIA_PREFLIGHT_SCHEMA_VERSION",
                "K2DynamicMediaPreflightService",
            ],
        )
        self.assertIs(
            episode_production_package.K2DynamicMediaPreflightService,
            dynamic_media_revision.K2DynamicMediaPreflightService,
        )
        self.assertEqual(
            episode_production_package.DYNAMIC_MEDIA_PREFLIGHT_SCHEMA_VERSION,
            dynamic_media_revision.DYNAMIC_MEDIA_PREFLIGHT_SCHEMA_VERSION,
        )
        for removed in (
            "K2DynamicMediaPlanBuilder",
            "DYNAMIC_REAL_IMAGE_CAPABILITY",
            "DYNAMIC_REAL_VIDEO_CAPABILITY",
            "DYNAMIC_REAL_VIDEO_REQUEST_SCHEMA_VERSION",
            "validate_dynamic_plan_request_set",
        ):
            self.assertFalse(hasattr(dynamic_media_revision, removed))
            self.assertFalse(hasattr(episode_production_package, removed))

    def test_current_image_preflight_is_deterministic_zero_write_and_blocked(self):
        run_before = self.boundary.get_run(
            WORKSPACE, self.run["productionRunRef"]
        )
        draft_before = self.boundary.get_shot_graph_bundle(
            WORKSPACE, self.run["productionRunRef"]
        )
        evidence = (
            self.boundary._EpisodeProductionPublicBoundary__shot_graph.evidence
        )
        evidence_before = evidence.read_snapshot(
            WORKSPACE, self.run["productionRunRef"]
        )
        first = self._preflight()
        replay = self._preflight()
        run_after = self.boundary.get_run(
            WORKSPACE, self.run["productionRunRef"]
        )
        draft_after = self.boundary.get_shot_graph_bundle(
            WORKSPACE, self.run["productionRunRef"]
        )
        evidence_after = evidence.read_snapshot(
            WORKSPACE, self.run["productionRunRef"]
        )

        self.assertEqual(replay, first)
        self.assertEqual(run_after, run_before)
        self.assertEqual(draft_after, draft_before)
        self.assertEqual(evidence_after, evidence_before)
        self.assertEqual(
            first["schemaVersion"], "v5.k2-dynamic-image-preflight.v1"
        )
        self.assertEqual(first["expectedShotCount"], 12)
        self.assertEqual(len(first["imageRequestPreviews"]), 12)
        self.assertEqual(
            first["imagePlanPreview"]["expectedRequestPreviewCount"], 12
        )
        self.assertEqual(
            first["imagePlanPreview"]["slotOrdinals"], list(range(1, 13))
        )
        self.assertEqual(
            first["shotPlanInputAuthority"],
            "LOCAL_STRUCTURAL_REPRESENTATION / NOT APPROVED INPUT AUTHORITY",
        )
        self.assertEqual(
            first["observedCurrentFacts"]["scriptOwnerAcceptance"],
            "NOT_VERIFIED_BY_PREFLIGHT",
        )
        self.assertEqual(
            first["observedCurrentFacts"]["shotPlanApproval"],
            "NOT_VERIFIED_BY_PREFLIGHT",
        )
        self.assertEqual(
            first["observedCurrentFacts"]["cameraContract"], "NOT_READY"
        )
        self.assertEqual(first["videoPlanState"], "OUT_OF_SCOPE_NOT_BUILT")
        self.assertEqual(first["audioPlanState"], "OUT_OF_SCOPE_NOT_BUILT")

        mappings = [item for item in _walk(first) if isinstance(item, dict)]
        self.assertTrue(
            all(item["dispatchAllowed"] is False for item in mappings if "dispatchAllowed" in item)
        )
        self.assertTrue(
            all(
                item["candidateAdmissionAllowed"] is False
                for item in mappings
                if "candidateAdmissionAllowed" in item
            )
        )
        self.assertTrue(
            all(
                item["publicationAllowed"] is False
                for item in mappings
                if "publicationAllowed" in item
            )
        )
        self.assertTrue(
            all(
                item["executionAuthorizationState"]
                == "PREFLIGHT_ONLY_NOT_AUTHORIZED"
                for item in mappings
                if "executionAuthorizationState" in item
            )
        )

        blocker_types = {
            item["blockerType"] for item in first["dispatchBlockers"]
        }
        self.assertTrue(FIXED_BLOCKERS <= blocker_types)
        self.assertEqual(
            sum(
                item["blockerType"] == "POSTPROCESS_REQUIREMENT_NOT_READY"
                for item in first["dispatchBlockers"]
            ),
            9,
        )
        self.assertEqual(
            first["payloadDigest"],
            _digest(
                {
                    key: value
                    for key, value in first.items()
                    if key != "payloadDigest"
                }
            ),
        )

    def test_preview_preserves_none_body_face_and_mixed_without_provider_claims(self):
        preflight = self._preflight()
        requests = preflight["imageRequestPreviews"]
        self.assertEqual(requests[0]["visibleIdentityMode"], "NONE")
        self.assertEqual(requests[4]["visibleIdentityMode"], "BODY_ONLY")
        self.assertEqual(requests[3]["visibleIdentityMode"], "FACE_LOCK")
        self.assertEqual(requests[9]["visibleIdentityMode"], "MIXED")
        self.assertEqual(
            [item["bindingMode"] for item in requests[9]["identityInputs"]],
            ["FACE_LOCK", "BODY_ONLY"],
        )
        self.assertIn("identityLockRef", requests[9]["identityInputs"][0])
        self.assertNotIn("identityLockRef", requests[9]["identityInputs"][1])
        self.assertEqual(
            requests[9]["dialogueRequirement"],
            {
                "speaker": None,
                "text": "一次克制吸气，无台词。",
                "sourceMode": "SFX_OR_SILENCE",
            },
        )
        self.assertEqual(requests[9]["dialogueSyncMode"], "NONE")

        serialized = json.dumps(preflight, ensure_ascii=False)
        for forbidden in (
            "adapterCapability",
            "providerPolicyState",
            "budgetAuthorityState",
            "rightsState",
            "NOT_REQUIRED_INTERNAL",
            "NOT_REQUIRED_SELF_HOSTED",
            "generationRequestRef",
            "realVideoPlan",
            "video/mp4",
            "ExecutableShotGraph",
            "executableShotGraph",
            "CreativeShotVersion",
            "creativeShotVersion",
            "cameraInstruction",
            "SHOTS_COMPILED",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(
            all(
                request["shotPlanDraftDigest"]
                == preflight["shotPlanDraftDigest"]
                for request in requests
            )
        )

    def test_shot_plan_draft_is_rejected_by_every_legacy_mutation_entry(self):
        run_before = self.boundary.get_run(
            WORKSPACE, self.run["productionRunRef"]
        )
        draft_before = self.boundary.get_shot_graph_bundle(
            WORKSPACE, self.run["productionRunRef"]
        )
        evidence = (
            self.boundary._EpisodeProductionPublicBoundary__shot_graph.evidence
        )
        evidence_before = evidence.read_snapshot(
            WORKSPACE, self.run["productionRunRef"]
        )
        scope = {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
        }
        operations = (
            (
                self.boundary.resolve_assets,
                {**scope, "idempotencyKey": "blocked-v2-assets"},
            ),
            (
                self.boundary.execute_media,
                {**scope, "idempotencyKey": "blocked-v2-media"},
            ),
            (
                self.boundary.compose_and_qc,
                {**scope, "idempotencyKey": "blocked-v2-compose"},
            ),
            (
                self.boundary.approve_and_finalize,
                {
                    **g6_finalize_command(self.run),
                    "idempotencyKey": "blocked-v2-finalize",
                },
            ),
            (
                self.boundary.run_provider_experiment,
                {
                    **scope,
                    "idempotencyKey": "blocked-v2-provider",
                    "sourceGenerationRequestRef": "blocked-request",
                    "providerCapabilityRef": "blocked-capability",
                },
            ),
            (
                self.boundary.plan_real_images,
                {**scope, "idempotencyKey": "blocked-v2-image-plan"},
            ),
            (
                self.boundary.record_real_image_candidates,
                {**scope, "idempotencyKey": "blocked-v2-image-candidates"},
            ),
            (
                self.boundary.admit_real_images,
                {
                    **scope,
                    "idempotencyKey": "blocked-v2-image-admission",
                    "selections": [],
                },
            ),
            (
                self.boundary.select_real_images,
                {
                    **scope,
                    "idempotencyKey": "blocked-v2-image-selection-alias",
                    "selections": [],
                },
            ),
            (
                self.boundary.admit_real_image_successor,
                {
                    **scope,
                    "idempotencyKey": "blocked-v2-image-successor",
                    "selection": {},
                },
            ),
            (
                self.boundary.plan_real_videos,
                {**scope, "idempotencyKey": "blocked-v2-video-plan"},
            ),
            (
                self.boundary.record_real_video_candidates,
                {**scope, "idempotencyKey": "blocked-v2-video-candidates"},
            ),
            (
                self.boundary.admit_real_videos,
                {
                    **scope,
                    "idempotencyKey": "blocked-v2-video-admission",
                    "selections": [],
                },
            ),
            (
                self.boundary.record_semantic_visual_qc,
                {
                    **scope,
                    "idempotencyKey": "blocked-v2-semantic-qc",
                    "technicalValidationRef": "blocked-validation",
                    "technicalValidationVersion": 1,
                    "technicalValidationDigest": "0" * 64,
                    "visualQcRef": "blocked-qc",
                    "visualQcVersion": 1,
                    "reviewerRef": "blocked-reviewer",
                    "reviewProfile": "k2-semantic-visual-qc-v1",
                    "evidence": [],
                    "supersedesVisualQc": None,
                    "checks": {},
                    "result": "FAIL",
                },
            ),
            (
                self.boundary.record_human_selection,
                {
                    **scope,
                    "idempotencyKey": "blocked-v2-human-selection",
                    "visualQcRef": "blocked-qc",
                    "visualQcVersion": 1,
                    "visualQcDigest": "0" * 64,
                    "selectionRef": "blocked-selection",
                    "selectionVersion": 1,
                    "approvalRef": "blocked-approval",
                    "decision": "REJECTED",
                },
            ),
        )

        for operation, command in operations:
            with self.subTest(operation=operation.__name__), self.assertRaises(
                EpisodeProductionPublicError
            ) as caught:
                operation(command)
            self.assertEqual(
                (caught.exception.status, caught.exception.code),
                (409, "execution_not_authorized"),
                operation.__name__,
            )

        self.assertEqual(
            self.boundary.get_run(WORKSPACE, self.run["productionRunRef"]),
            run_before,
        )
        self.assertEqual(
            self.boundary.get_shot_graph_bundle(
                WORKSPACE, self.run["productionRunRef"]
            ),
            draft_before,
        )
        self.assertEqual(
            evidence.read_snapshot(WORKSPACE, self.run["productionRunRef"]),
            evidence_before,
        )

    def test_preflight_rejects_client_authority_payloads(self):
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.preflight_dynamic_real_media_plan(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "shotPlanDraft": self.draft,
                }
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "invalid_request"),
        )

    def test_internal_preview_rejects_resealed_draft_authority_injections_zero_write(self):
        service = self.boundary._EpisodeProductionPublicBoundary__shot_graph
        verified = service.verify_shot_plan_draft_current(
            WORKSPACE, self.run["productionRunRef"]
        )
        evidence_before = service.evidence.read_snapshot(
            WORKSPACE, self.run["productionRunRef"]
        )

        output_camera = copy.deepcopy(self.draft)
        output_camera["output"]["cameraInstruction"] = "fabricated"
        output_camera = _reseal(output_camera)
        publication = copy.deepcopy(self.draft)
        publication["publicationAllowed"] = True
        publication = _reseal(publication)
        creative_camera = copy.deepcopy(self.creative_shots)
        creative_camera[0]["cameraInstruction"] = "fabricated"
        creative_camera[0] = _reseal(creative_camera[0])

        cases = (
            (output_camera, self.creative_shots),
            (publication, self.creative_shots),
            (self.draft, creative_camera),
        )
        for draft, creative_shots in cases:
            with self.subTest(draft=draft is not self.draft), self.assertRaises(
                Exception
            ):
                dynamic_media_revision._build_image_preview(
                    workspace_ref=WORKSPACE,
                    production_run_ref=self.run["productionRunRef"],
                    draft=draft,
                    creative_shot_drafts=creative_shots,
                    identity_lock=verified["identityLock"],
                )

        self.assertEqual(
            service.evidence.read_snapshot(
                WORKSPACE, self.run["productionRunRef"]
            ),
            evidence_before,
        )

    def test_face_lock_rejects_non_image_identity_reference(self):
        budgets = ep01_shot_budgets(self.generated["scriptVersion"])
        budgets[8]["visibleIdentityBindings"] = [
            {"characterName": "裴昀", "bindingMode": "FACE_LOCK"}
        ]
        boundary = self._boundary()
        run = boundary.create_run(
            self._run_command(
                "k2-002-non-image-face-lock",
                shot_budgets=budgets,
            )
        )
        boundary.authorize_and_lock(self._authority_command(run))
        boundary.compile_shot_graph(g3_command(run))
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.preflight_dynamic_real_media_plan(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": run["productionRunRef"],
                }
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "invalid_request"),
        )


if __name__ == "__main__":
    unittest.main()
