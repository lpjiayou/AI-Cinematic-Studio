"""Contract for the retired M003 process-local Asset Registry."""

import unittest

from services.v5_core_os.asset_registry import (
    AssetRegistry,
    AssetRegistryDeprecatedError,
    AssetRegistryError,
)


class AssetRegistryRetirementContractTests(unittest.TestCase):
    def test_package_remains_importable_but_all_authority_operations_fail_closed(self):
        registry = AssetRegistry()
        for operation in (
            lambda: registry.create_asset(
                asset_id="asset-contract", asset_type="image", version_id="v1"
            ),
            lambda: registry.get_asset("asset-contract"),
            registry.list_assets,
        ):
            with self.assertRaises(AssetRegistryDeprecatedError):
                operation()

    def test_deprecation_error_preserves_package_error_hierarchy(self):
        self.assertTrue(issubclass(AssetRegistryDeprecatedError, AssetRegistryError))


if __name__ == "__main__":
    unittest.main()
