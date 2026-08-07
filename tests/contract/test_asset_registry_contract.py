"""V5-internal Asset Registry package contract tests for ACS-P1-004."""

import unittest

from services.v5_core_os.asset_registry import (
    Asset,
    AssetNotFoundError,
    AssetRegistry,
    AssetRegistryError,
    AssetType,
    AssetVersion,
    DuplicateAssetError,
    ValidationError,
)


class AssetRegistryPackageContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AssetRegistry()

    def create_asset(self, asset_id: str = "asset-contract") -> Asset:
        return self.registry.create_asset(
            asset_id=asset_id,
            asset_type=AssetType.IMAGE,
            version_id="{}-initial".format(asset_id),
        )

    def test_create_and_query_contract(self) -> None:
        created = self.create_asset()

        self.assertIsInstance(created, Asset)
        self.assertEqual("asset-contract", created.asset_id)
        self.assertEqual(created, self.registry.get_asset("asset-contract"))
        self.assertEqual(0, created.created_at.utcoffset().total_seconds())

    def test_list_contract_exposes_created_assets(self) -> None:
        self.create_asset("asset-first")
        self.create_asset("asset-second")

        asset_ids = {asset.asset_id for asset in self.registry.list_assets()}

        self.assertEqual({"asset-first", "asset-second"}, asset_ids)

    def test_asset_type_contract_preserves_the_supplied_type(self) -> None:
        created = self.registry.create_asset(
            asset_id="asset-text",
            asset_type=AssetType.TEXT,
            version_id="version-text",
        )

        self.assertIs(AssetType.TEXT, created.asset_type)

    def test_initial_version_contract_preserves_opaque_identity(self) -> None:
        created = self.registry.create_asset(
            asset_id="asset-versioned",
            asset_type=AssetType.VIDEO,
            version_id="opaque-version-token",
        )

        self.assertIsInstance(created.initial_version, AssetVersion)
        self.assertEqual("opaque-version-token", created.initial_version.version_id)
        self.assertEqual(created.asset_id, created.initial_version.asset_id)

    def test_duplicate_not_found_and_validation_contract(self) -> None:
        self.create_asset()

        with self.assertRaises(DuplicateAssetError):
            self.create_asset()
        with self.assertRaises(AssetNotFoundError):
            self.registry.get_asset("asset-missing")
        with self.assertRaises(ValidationError):
            self.registry.create_asset(
                asset_id="",
                asset_type=AssetType.IMAGE,
                version_id="version-valid",
            )

    def test_error_hierarchy_contract(self) -> None:
        public_errors = (
            AssetNotFoundError,
            DuplicateAssetError,
            ValidationError,
        )

        for error_type in public_errors:
            with self.subTest(error_type=error_type.__name__):
                self.assertTrue(issubclass(error_type, AssetRegistryError))


if __name__ == "__main__":
    unittest.main()
