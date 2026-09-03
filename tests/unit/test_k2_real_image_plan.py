import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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
from tests.support.legacy_k2_history import seed_legacy_g4, seed_legacy_g5


class K2RealImagePlanTests(unittest.TestCase):
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
            clock=lambda: "2026-08-23T01:00:00Z",
        )
        self.boundary = create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            media_execution=execution,
            composition_execution=V4CompositionExecutor.from_artifact_root(
                artifact_root
            ),
            ref_factory=self.refs,
            clock=lambda: "2026-08-23T01:00:00Z",
        )
        self.run = self.boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        self.boundary.authorize_and_lock(g2_command(self.run))
        self.boundary.compile_shot_graph(g3_command(self.run))
        seed_legacy_g4(self.boundary, g4_command(self.run))
        seed_legacy_g5(self.boundary, g5_command(self.run))
        self.boundary.compose_and_qc(g6_preview_command(self.run))

    def tearDown(self):
        self.directory.cleanup()

    def command(self, **extra):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
            "idempotencyKey": "k2-m10-real-image-plan-v1",
            **extra,
        }

    def test_plans_four_two_identity_shot_images_without_admission(self):
        result = self.boundary.plan_real_images(self.command())
        self.assertEqual(result["state"], "REAL_IMAGE_PLAN_READY")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(len(result["generationRequests"]), 4)
        self.assertEqual(
            [item["ordinal"] for item in result["generationRequests"]],
            [1, 2, 3, 4],
        )
        for request in result["generationRequests"]:
            self.assertEqual(request["mediaKind"], "image")
            self.assertEqual(request["mediaType"], "image/png")
            self.assertEqual(len(request["identityInputs"]), 2)
            self.assertEqual(
                {item["scriptCharacterName"] for item in request["identityInputs"]},
                {"林澈", "顾言"},
            )
            self.assertEqual(
                {item["referenceMediaType"] for item in request["identityInputs"]},
                {"image", "identity-direction"},
            )
            self.assertTrue(
                all(
                    len(item["referenceContentDigest"]) == 64
                    for item in request["identityInputs"]
                )
            )
            self.assertEqual(
                request["capabilityVerificationState"],
                "PENDING_LIVE_PREFLIGHT",
            )
            self.assertEqual(
                request["executionAuthorizationState"], "NOT_GRANTED_BY_PLAN"
            )
            self.assertTrue(request["selectionRequired"])
            self.assertFalse(request["publicationAllowed"])
            self.assertNotIn("path", json.dumps(request, ensure_ascii=False).lower())

        plan = result["realImagePlan"]
        self.assertEqual(plan["expectedRequestCount"], 4)
        self.assertEqual(plan["requiredIdentityInputsPerRequest"], 2)
        self.assertEqual(plan["candidateSelectionState"], "NOT_STARTED")
        self.assertEqual(plan["assetAdmissionState"], "NOT_STARTED")
        self.assertFalse(plan["publicationAllowed"])
        self.assertNotIn("candidate", result)
        self.assertNotIn("assetVersions", result)
        projected = self.boundary.get_run(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(projected["state"], "REAL_IMAGE_PLAN_READY")
        self.assertEqual(projected["completedGates"][-1], "M10_REAL_IMAGE_PLAN")

    def test_replay_and_projection_are_stable(self):
        first = self.boundary.plan_real_images(self.command())
        replay = self.boundary.plan_real_images(self.command())
        projected = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["realImagePlan"], first["realImagePlan"])
        self.assertEqual(projected["realImagePlan"], first["realImagePlan"])
        self.assertEqual(
            projected["generationRequests"], first["generationRequests"]
        )
        self.assertEqual(projected["state"], "REAL_IMAGE_PLAN_READY")
        self.assertEqual(projected["productionState"], projected["state"])
        self.assertEqual(projected["visualQcState"]["state"], "NOT_RECORDED")

    def test_concurrent_exact_plan_returns_committed_winner_as_replay(self):
        revision = (
            self.boundary._EpisodeProductionPublicBoundary__real_media_revision
        )
        original_append = revision.evidence.append_gate
        barrier = Barrier(2)

        def append_after_both_planned(gate):
            barrier.wait(timeout=5)
            return original_append(gate)

        revision.evidence.append_gate = append_after_both_planned
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(lambda _: self.boundary.plan_real_images(self.command()), range(2))
            )
        self.assertEqual(
            sorted(item["idempotentReplay"] for item in results),
            [False, True],
        )
        self.assertEqual(results[0]["realImagePlan"], results[1]["realImagePlan"])
        self.assertEqual(
            results[0]["generationRequests"], results[1]["generationRequests"]
        )

    def test_public_command_is_closed_world_and_cannot_supply_paths(self):
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.plan_real_images(
                self.command(identityImagePath="/tmp/injected.png")
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "invalid_request"),
        )
        self.assertEqual(
            self.boundary.get_run(
                WORKSPACE, self.run["productionRunRef"]
            )["state"],
            "QC_READY",
        )


if __name__ == "__main__":
    unittest.main()
