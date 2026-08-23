import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    V4CompositionExecutor,
)
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_in_memory_boundary,
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

    @staticmethod
    def candidate_ref(ordinal: int) -> str:
        return f"m10-reviewed-candidate-{ordinal}"

    @staticmethod
    def content_digest(ordinal: int) -> str:
        return _digest(f"m10-candidate-content-{ordinal}")

    def resolve_candidates(
        self,
        workspace_ref,
        production_run_ref,
        real_image_plan_ref,
        expected_requests,
    ):
        self.calls += 1
        return {
            "candidateEvidenceRef": "candidate-evidence-test-v1",
            "candidateEvidenceDigest": _digest("candidate-evidence"),
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
        self.boundary = create_in_memory_boundary(
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

    def tearDown(self):
        self.directory.cleanup()

    def selection_command(self):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
            "idempotencyKey": "m10-four-image-selection-v1",
            "actorRef": "authenticated-creator-credential",
            "selections": [
                {
                    "generationRequestRef": request[
                        "generationRequestRef"
                    ],
                    "candidateRef": self.candidate_evidence.candidate_ref(
                        request["ordinal"]
                    ),
                    "candidateContentDigest": (
                        self.candidate_evidence.content_digest(
                            request["ordinal"]
                        )
                    ),
                }
                for request in reversed(self.plan["generationRequests"])
            ],
        }

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
            self.assertEqual(
                decision["actorRef"], "authenticated-creator-credential"
            )
            self.assertEqual(decision["decision"], "SELECT")
            self.assertEqual(
                asset["selectionDecisionDigest"],
                decision["payloadDigest"],
            )
            self.assertTrue(asset["immutable"])
            self.assertEqual(asset["state"], "REGISTERED")
            self.assertEqual(asset["rightsState"], "NOT_REQUIRED_INTERNAL")
            self.assertEqual(
                asset["providerPolicyState"],
                "NOT_REQUIRED_SELF_HOSTED",
            )
            self.assertEqual(
                asset["budgetAuthorityState"], "NOT_REQUIRED_INTERNAL"
            )
            self.assertFalse(asset["publicationAllowed"])
        self.assertEqual(
            result["realImageAdmissionManifest"]["summary"],
            {
                "technicallyVerifiedCandidates": 4,
                "humanSelections": 4,
                "registeredImageAssets": 4,
                "failed": 0,
            },
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
        self.assertEqual(self.candidate_evidence.calls, 1)

    def test_rejects_one_changed_candidate_digest_atomically(self):
        command = self.selection_command()
        command["selections"][2]["candidateContentDigest"] = _digest(
            "not-the-reviewed-candidate"
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.select_real_images(command)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (422, "real_image_candidate_evidence_rejected"),
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
        self.assertEqual(self.candidate_evidence.calls, 0)


if __name__ == "__main__":
    unittest.main()
