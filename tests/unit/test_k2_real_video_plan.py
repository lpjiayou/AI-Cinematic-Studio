import json
import unittest

from services.v5_core_os.episode_production import EpisodeProductionPublicError
from tests.unit.test_episode_production_k2 import WORKSPACE
from tests.unit import test_k2_real_image_selection as image_selection
from tests.unit import test_k2_real_image_plan as image_plan


class K2RealVideoPlanTests(unittest.TestCase):
    def setUp(self):
        image_selection.K2RealImageSelectionTests.setUp(self)
        self.image_admission = self.boundary.select_real_images(
            image_selection.K2RealImageSelectionTests.selection_command(self)
        )

    def tearDown(self):
        image_selection.K2RealImageSelectionTests.tearDown(self)

    def command(self, **extra):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": self.run["productionRunRef"],
            "idempotencyKey": "m11-four-shot-video-plan-v1",
            **extra,
        }

    def test_derives_four_exact_start_image_bound_video_requests(self):
        result = self.boundary.plan_real_videos(self.command())
        self.assertEqual(result["state"], "REAL_VIDEO_PLAN_READY")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(len(result["generationRequests"]), 4)
        self.assertEqual(
            [
                item["parameters"]["durationFrames"]
                for item in result["generationRequests"]
            ],
            [168, 168, 192, 192],
        )
        admitted_by_ordinal = {
            item["ordinal"]: item
            for item in self.image_admission["assetVersions"]
        }
        for request in result["generationRequests"]:
            source = admitted_by_ordinal[request["ordinal"]]
            self.assertEqual(request["mediaKind"], "video")
            self.assertEqual(request["mediaType"], "video/mp4")
            self.assertEqual(
                request["sourceImageAssetVersionRef"],
                source["assetVersionRef"],
            )
            self.assertEqual(
                request["sourceImageAssetVersionDigest"],
                source["payloadDigest"],
            )
            self.assertEqual(
                request["sourceImageContentDigest"], source["sha256"]
            )
            self.assertEqual(
                request["startImageBindingState"],
                "EXACT_ASSET_VERSION_BOUND",
            )
            self.assertEqual(
                (request["parameters"]["width"], request["parameters"]["height"]),
                (640, 352),
            )
            self.assertEqual(request["parameters"]["frameRate"], 24)
            self.assertEqual(
                request["executionMode"], "INTERNAL_SELF_HOSTED"
            )
            self.assertEqual(
                request["rightsState"], "NOT_REQUIRED_INTERNAL"
            )
            self.assertEqual(
                request["providerPolicyState"],
                "NOT_REQUIRED_SELF_HOSTED",
            )
            self.assertEqual(
                request["budgetAuthorityState"], "NOT_REQUIRED_INTERNAL"
            )
            self.assertTrue(request["selectionRequired"])
            self.assertFalse(request["publicationAllowed"])
        plan = result["realVideoPlan"]
        self.assertEqual(plan["frameCounts"], [168, 168, 192, 192])
        self.assertEqual(plan["totalFrames"], 720)
        self.assertEqual(plan["frameRate"], 24)
        self.assertEqual(
            plan["sourceImageAssetVersionDigests"],
            [
                item["payloadDigest"]
                for item in self.image_admission["assetVersions"]
            ],
        )
        self.assertEqual(plan["candidateSelectionState"], "NOT_STARTED")
        self.assertEqual(plan["assetAdmissionState"], "NOT_STARTED")
        self.assertFalse(plan["publicationAllowed"])
        public_json = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("internalPath", public_json)
        self.assertNotIn("/data/", public_json)
        projected = self.boundary.get_run(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(projected["state"], "REAL_VIDEO_PLAN_READY")
        self.assertEqual(
            projected["completedGates"][-1], "M11_REAL_VIDEO_PLAN"
        )

    def test_replay_and_combined_revision_projection_are_stable(self):
        first = self.boundary.plan_real_videos(self.command())
        replay = self.boundary.plan_real_videos(self.command())
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["realVideoPlan"], first["realVideoPlan"])
        restored = self.boundary.get_real_media_revision(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(restored["state"], "REAL_VIDEO_PLAN_READY")
        self.assertEqual(
            restored["realVideoPlan"], first["realVideoPlan"]
        )
        self.assertEqual(
            restored["videoGenerationRequests"],
            first["generationRequests"],
        )
        self.assertEqual(len(restored["assetVersions"]), 4)

    def test_public_command_rejects_client_paths_and_provider_claims(self):
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.plan_real_videos(
                self.command(
                    startImagePath="/tmp/injected.png",
                    providerId="client-selected-provider",
                )
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "invalid_request"),
        )
        self.assertEqual(
            self.boundary.get_run(
                WORKSPACE, self.run["productionRunRef"]
            )["state"],
            "REAL_IMAGE_READY",
        )


class K2RealVideoPlanPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        image_plan.K2RealImagePlanTests.setUp(self)

    def tearDown(self):
        image_plan.K2RealImagePlanTests.tearDown(self)

    def test_cannot_plan_video_before_exact_image_admission(self):
        self.boundary.plan_real_images(
            image_plan.K2RealImagePlanTests.command(self)
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.plan_real_videos(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": self.run["productionRunRef"],
                    "idempotencyKey": "m11-before-image-admission",
                }
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "upstream_not_confirmed"),
        )
        self.assertEqual(
            self.boundary.get_run(
                WORKSPACE, self.run["productionRunRef"]
            )["state"],
            "REAL_IMAGE_PLAN_READY",
        )


if __name__ == "__main__":
    unittest.main()
