import unittest
from pathlib import Path

from apps.creator_workspace_mvp import public_contract


class CreatorPublicHttpV1ContractTests(unittest.TestCase):
    def test_every_public_route_is_versioned_and_never_internal(self):
        routes = [
            value
            for name, value in vars(public_contract).items()
            if name.endswith("_ENDPOINT") and isinstance(value, str)
        ]
        self.assertGreaterEqual(len(routes), 20)
        for route in routes:
            with self.subTest(route=route):
                self.assertTrue(route.startswith("/creator/api/v1/"))
                self.assertNotIn("/internal/", route)

    def test_capability_projection_covers_m1_through_m19_once(self):
        payload = public_contract.capability_payload()
        capabilities = payload["capabilities"]
        self.assertEqual(
            [item["id"] for item in capabilities],
            [f"M{index}" for index in range(1, 20)],
        )
        self.assertEqual(
            {item["state"] for item in capabilities[:5]},
            {"available"},
        )
        self.assertEqual(capabilities[5]["state"], "authority_required")
        self.assertEqual(
            {item["state"] for item in capabilities[6:9]},
            {"local_evidence_only"},
        )
        self.assertEqual(capabilities[9]["state"], "local_evidence_only")
        self.assertEqual(
            {item["state"] for item in capabilities[10:12]},
            {"production_policy_required"},
        )
        self.assertEqual(
            {item["state"] for item in capabilities[12:15]},
            {"local_evidence_only"},
        )
        self.assertEqual(
            {item["state"] for item in capabilities[15:]},
            {"not_open"},
        )
        self.assertTrue(all(item["publicResources"] for item in capabilities[6:15]))
        self.assertTrue(all(not item["publicResources"] for item in capabilities[15:]))

    def test_capability_payload_is_detached_from_frozen_projection(self):
        first = public_contract.capability_payload()
        first["capabilities"][0]["publicResources"].append("forged")
        second = public_contract.capability_payload()
        self.assertNotIn("forged", second["capabilities"][0]["publicResources"])

    def test_m12_m13_projection_reports_the_bridge_without_claiming_runtime(self):
        capabilities = {
            item["id"]: item
            for item in public_contract.capability_payload()["capabilities"]
        }
        allowed_states = {
            "available",
            "authority_required",
            "local_evidence_only",
            "production_policy_required",
            "not_open",
        }
        self.assertTrue(
            {item["state"] for item in capabilities.values()} <= allowed_states
        )
        self.assertEqual(capabilities["M12"]["state"], "production_policy_required")
        self.assertNotIn("M11", capabilities["M12"]["requirements"])
        self.assertIn(
            "M9_explicit_audio_requirement",
            capabilities["M12"]["requirements"],
        )
        self.assertIn(
            "M12_runtime_g0_not_complete",
            capabilities["M12"]["requirements"],
        )
        self.assertEqual(capabilities["M13"]["state"], "local_evidence_only")
        self.assertIn(
            "episode-production-runs/render-candidates",
            capabilities["M13"]["publicResources"],
        )
        self.assertIn(
            "M13_base_backend_present", capabilities["M13"]["requirements"]
        )
        self.assertIn(
            "M13_product_surface_incomplete",
            capabilities["M13"]["requirements"],
        )
        self.assertIn(
            "M13_extension_g0_not_authorized",
            capabilities["M13"]["requirements"],
        )

    def test_method_aware_resources_replace_legacy_write_projection(self):
        capabilities = {
            item["id"]: item
            for item in public_contract.capability_payload()["capabilities"]
        }
        self.assertIn(
            "episode-production-runs/execution-method-plan",
            capabilities["M8"]["publicResources"],
        )
        self.assertIn(
            "episode-production-runs/method-aware-input-plan",
            capabilities["M10"]["publicResources"],
        )
        self.assertIn(
            "episode-production-runs/method-aware-video-route",
            capabilities["M11"]["publicResources"],
        )
        self.assertIn(
            "episode-production-runs/explicit-audio-requirement-route",
            capabilities["M12"]["publicResources"],
        )
        self.assertNotIn(
            "episode-production-runs/assets",
            capabilities["M9"]["publicResources"],
        )
        self.assertNotIn(
            "episode-production-runs/media",
            capabilities["M11"]["publicResources"],
        )

    def test_m10_m11_publish_only_the_typed_media_review_chain(self):
        capabilities = {
            item["id"]: item
            for item in public_contract.capability_payload()["capabilities"]
        }
        shared_review_resources = {
            "episode-production-runs/semantic-visual-qc",
            "episode-production-runs/media-selection",
            "episode-production-runs/state-projection",
        }
        self.assertTrue(
            shared_review_resources.issubset(
                capabilities["M10"]["publicResources"]
            )
        )
        self.assertTrue(
            shared_review_resources.issubset(
                capabilities["M11"]["publicResources"]
            )
        )
        self.assertTrue(
            {
                "episode-production-runs/real-image-candidates",
                "episode-production-runs/real-image-admission",
                "episode-production-runs/real-image-successor-admission",
            }.issubset(capabilities["M10"]["publicResources"])
        )
        self.assertTrue(
            {
                "episode-production-runs/real-video-candidates",
                "episode-production-runs/real-video-admission",
            }.issubset(capabilities["M11"]["publicResources"])
        )
        self.assertFalse(
            any(
                resource.endswith("/evidence-records")
                for capability in capabilities.values()
                for resource in capability["publicResources"]
            )
        )

    def test_document_covers_control_plane_and_breaking_selection_migration(self):
        document = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "04-interface-contract"
            / "creator-public-http-v1.md"
        ).read_text(encoding="utf-8")
        for required_term in (
            "production_policy_required",
            "real-image-candidates",
            "real-image-admission",
            "real-image-successor-admission",
            "real-video-candidates",
            "semantic-visual-qc",
            "media-selection",
            "real-video-admission",
            "state-projection",
            "render-candidates",
            "M12_runtime_g0_not_complete",
            "M13_product_surface_incomplete",
            "visualQcRef",
            "approvalRef",
            "BREAKING",
            "client_workspace_scope_forbidden",
            "script-versions/reviewed-import/accept",
            "CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SHA256",
            "v5.script-acceptance.v1",
            "script_acceptance@1",
            "idempotentReplay=true",
            "canonical-registrations/preflight",
            "CREATOR_CANONICAL_TARGET_REF",
            "v5.canonical-registration.v1",
            "canonical_registration@1",
            "series_scope_required",
            "candidateRef",
            "sourceContextDigest",
            "creator.series-plan-candidate-receipt.v1",
            "raw `creativeInput`",
        ):
            with self.subTest(required_term=required_term):
                self.assertIn(required_term, document)


if __name__ == "__main__":
    unittest.main()
