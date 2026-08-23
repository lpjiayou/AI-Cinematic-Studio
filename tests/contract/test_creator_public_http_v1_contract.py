import unittest

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


if __name__ == "__main__":
    unittest.main()
