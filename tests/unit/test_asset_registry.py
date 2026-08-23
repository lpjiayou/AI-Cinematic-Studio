"""The retired process-local registry must never become a second authority."""

import unittest

from services.v5_core_os.asset_registry import (
    AssetRegistry,
    AssetRegistryDeprecatedError,
    AssetType,
)


class AssetRegistryRetirementTests(unittest.TestCase):
    def setUp(self):
        self.registry = AssetRegistry()

    def test_create_fails_closed_and_points_to_canonical_authority(self):
        with self.assertRaises(AssetRegistryDeprecatedError) as caught:
            self.registry.create_asset(
                asset_id="asset-island",
                asset_type=AssetType.IMAGE,
                version_id="version-island",
            )
        self.assertIn("CanonicalAssetVersionAuthority", str(caught.exception))

    def test_reads_do_not_expose_process_local_state(self):
        with self.assertRaises(AssetRegistryDeprecatedError):
            self.registry.get_asset("asset-island")
        with self.assertRaises(AssetRegistryDeprecatedError):
            self.registry.list_assets()

    def test_two_instances_cannot_create_divergent_asset_histories(self):
        for registry in (AssetRegistry(), AssetRegistry()):
            with self.assertRaises(AssetRegistryDeprecatedError):
                registry.create_asset(
                    asset_id="asset-same",
                    asset_type=AssetType.VIDEO,
                    version_id="version-different",
                )


if __name__ == "__main__":
    unittest.main()
