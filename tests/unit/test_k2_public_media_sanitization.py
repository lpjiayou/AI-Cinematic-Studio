import unittest

from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)


class ReturningOperation:
    def __init__(self, response):
        self.response = response

    def command(self, command):
        del command
        return self.response

    def query(self, workspace_ref, run_ref):
        del workspace_ref, run_ref
        return self.response


class K2PublicMediaSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.response = {
            "state": "REAL_VIDEO_PLAN_READY",
            "storageKey": "private/top-level.mp4",
            "candidate": {
                "candidateRef": "candidate-1",
                "internalPath": "/private/candidate.mp4",
                "artifactStorageKey": "private/candidate.mp4",
                "nested": [
                    {
                        "finalStorageKey": "private/final.mp4",
                        "candidateStorageKeys": ["private/part.mp4"],
                        "payloadDigest": "1" * 64,
                    }
                ],
            },
        }
        self.operation = ReturningOperation(self.response)
        self.boundary = object.__new__(EpisodeProductionPublicBoundary)
        setattr(
            self.boundary,
            "_EpisodeProductionPublicBoundary__real_media_revision",
            type(
                "RealMediaRevision",
                (),
                {
                    "plan_images": self.operation.command,
                    "select_and_admit_images": self.operation.command,
                    "record_real_image_candidates": self.operation.command,
                    "admit_real_images": self.operation.command,
                    "admit_real_image_successor": self.operation.command,
                    "plan_videos": self.operation.command,
                    "record_real_video_candidates": self.operation.command,
                    "admit_real_videos": self.operation.command,
                    "get_revision_bundle": self.operation.query,
                },
            )(),
        )
        setattr(
            self.boundary,
            "_EpisodeProductionPublicBoundary__candidate_review",
            type(
                "CandidateReview",
                (),
                {
                    "record_semantic_visual_qc": self.operation.command,
                    "record_human_selection": self.operation.command,
                },
            )(),
        )
        setattr(
            self.boundary,
            "_EpisodeProductionPublicBoundary__state_projection",
            type(
                "StateProjection",
                (),
                {
                    "get_projection": ReturningOperation(
                        {
                            **self.response,
                            "rootState": {"state": "ROOTS_READY"},
                            "productionState": "REAL_VIDEO_PLAN_READY",
                            "runtimeState": {
                                "state": "SUCCEEDED",
                                "storageKey": "private/runtime.db",
                            },
                            "visualQcState": {"state": "FAIL"},
                            "activeRevision": {
                                "state": "ACTIVE",
                                "revisionRef": "revision-current",
                            },
                        }
                    ).query
                },
            )(),
        )

    def assert_sanitized(self, response):
        serialized = repr(response)
        for field in (
            "storageKey",
            "internalPath",
            "artifactStorageKey",
            "finalStorageKey",
            "candidateStorageKeys",
        ):
            self.assertNotIn(field, serialized)
        self.assertEqual(
            response["candidate"]["nested"][0]["payloadDigest"], "1" * 64
        )
        self.assertIn("storageKey", self.response)
        self.assertIn("internalPath", self.response["candidate"])

    def test_all_real_media_command_responses_strip_internal_locators(self):
        operations = (
            self.boundary.plan_real_images,
            self.boundary.select_real_images,
            self.boundary.record_real_image_candidates,
            self.boundary.admit_real_images,
            self.boundary.admit_real_image_successor,
            self.boundary.plan_real_videos,
            self.boundary.record_real_video_candidates,
            self.boundary.record_semantic_visual_qc,
            self.boundary.record_human_selection,
            self.boundary.admit_real_videos,
        )
        for operation in operations:
            with self.subTest(operation=operation.__name__):
                self.assert_sanitized(operation({"idempotencyKey": "request"}))

    def test_real_media_and_state_queries_strip_internal_locators(self):
        for operation in (
            self.boundary.get_real_media_revision,
            self.boundary.get_state_projection,
        ):
            with self.subTest(operation=operation.__name__):
                self.assert_sanitized(operation("workspace", "run"))

    def test_existing_real_media_query_is_additively_extended_with_four_axes(self):
        response = self.boundary.get_real_media_revision("workspace", "run")

        self.assertEqual(response["state"], response["productionState"])
        self.assertEqual(response["rootState"]["state"], "ROOTS_READY")
        self.assertEqual(response["runtimeState"]["state"], "SUCCEEDED")
        self.assertEqual(response["visualQcState"]["state"], "FAIL")
        self.assertEqual(
            response["activeRevision"]["revisionRef"], "revision-current"
        )
        self.assertNotIn("storageKey", response["runtimeState"])


if __name__ == "__main__":
    unittest.main()
