"""Unit tests for the V5 Core OS Asset Registry."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from services.v5_core_os.asset_registry import (
    Asset,
    AssetNotFoundError,
    AssetRegistry,
    AssetType,
    DuplicateAssetError,
    ValidationError,
)


class AssetRegistryUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(
            2026,
            8,
            6,
            21,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        )
        self.registry = AssetRegistry(clock=lambda: self.now)

    def create_asset(
        self,
        asset_id: str = "asset-primary",
        asset_type: AssetType = AssetType.IMAGE,
        version_id: str = "version-initial",
    ) -> Asset:
        return self.registry.create_asset(
            asset_id=asset_id,
            asset_type=asset_type,
            version_id=version_id,
        )

    def test_create_asset_preserves_identity_type_and_utc_time(self) -> None:
        asset = self.create_asset()

        self.assertEqual("asset-primary", asset.asset_id)
        self.assertIs(AssetType.IMAGE, asset.asset_type)
        self.assertEqual(self.now.astimezone(timezone.utc), asset.created_at)

    def test_create_asset_registers_an_initial_version(self) -> None:
        asset = self.create_asset()

        self.assertEqual("version-initial", asset.initial_version.version_id)
        self.assertEqual(asset.asset_id, asset.initial_version.asset_id)
        self.assertEqual(asset.created_at, asset.initial_version.registered_at)

    def test_query_returns_created_asset(self) -> None:
        created = self.create_asset()

        self.assertEqual(created, self.registry.get_asset("asset-primary"))

    def test_list_is_empty_before_creation(self) -> None:
        self.assertEqual(0, len(self.registry.list_assets()))

    def test_list_contains_created_assets_without_order_assumption(self) -> None:
        self.create_asset("asset-first", AssetType.VIDEO, "version-first")
        self.create_asset("asset-second", AssetType.AUDIO, "version-second")

        asset_ids = {asset.asset_id for asset in self.registry.list_assets()}

        self.assertEqual({"asset-first", "asset-second"}, asset_ids)

    def test_list_returns_a_snapshot(self) -> None:
        self.create_asset("asset-first", version_id="version-first")
        snapshot = self.registry.list_assets()

        self.create_asset("asset-second", version_id="version-second")

        self.assertEqual({"asset-first"}, {asset.asset_id for asset in snapshot})

    def test_duplicate_asset_identifier_is_rejected(self) -> None:
        self.create_asset()

        with self.assertRaises(DuplicateAssetError):
            self.create_asset()

    def test_duplicate_identifier_is_rejected_even_if_other_values_change(self) -> None:
        self.create_asset()

        with self.assertRaises(DuplicateAssetError):
            self.create_asset(
                asset_type=AssetType.TEXT,
                version_id="version-different",
            )

    def test_query_missing_asset_is_rejected(self) -> None:
        with self.assertRaises(AssetNotFoundError):
            self.registry.get_asset("asset-missing")

    def test_asset_and_version_identifiers_reject_invalid_values(self) -> None:
        invalid_values = (
            "",
            "   ",
            " padded ",
            "with space",
            "line\nbreak",
            "x" * 129,
            None,
        )

        for field in ("asset_id", "version_id"):
            for invalid_value in invalid_values:
                values = {
                    "asset_id": "asset-valid",
                    "asset_type": AssetType.IMAGE,
                    "version_id": "version-valid",
                }
                values[field] = invalid_value
                with self.subTest(field=field, invalid_value=invalid_value):
                    with self.assertRaises(ValidationError):
                        self.registry.create_asset(**values)  # type: ignore[arg-type]

    def test_asset_type_must_use_the_public_classification(self) -> None:
        for invalid_type in ("image", None, object()):
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(ValidationError):
                    self.registry.create_asset(
                        asset_id="asset-valid",
                        asset_type=invalid_type,  # type: ignore[arg-type]
                        version_id="version-valid",
                    )

    def test_broad_asset_types_are_preserved(self) -> None:
        sample_types = (
            AssetType.IMAGE,
            AssetType.VIDEO,
            AssetType.AUDIO,
            AssetType.TEXT,
            AssetType.OTHER,
        )

        for index, asset_type in enumerate(sample_types):
            with self.subTest(asset_type=asset_type):
                asset = self.create_asset(
                    asset_id="asset-{}".format(index),
                    asset_type=asset_type,
                    version_id="version-{}".format(index),
                )
                self.assertIs(asset_type, asset.asset_type)

    def test_returned_asset_and_initial_version_are_immutable(self) -> None:
        asset = self.create_asset()

        with self.assertRaises(FrozenInstanceError):
            asset.asset_type = AssetType.TEXT  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            asset.initial_version.version_id = "changed"  # type: ignore[misc]

    def test_clock_must_return_datetime(self) -> None:
        registry = AssetRegistry(clock=lambda: "not-a-datetime")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            registry.create_asset(
                asset_id="asset-valid",
                asset_type=AssetType.IMAGE,
                version_id="version-valid",
            )

    def test_clock_must_return_timezone_aware_datetime(self) -> None:
        registry = AssetRegistry(clock=lambda: datetime(2026, 8, 6, 12, 0))

        with self.assertRaises(ValidationError):
            registry.create_asset(
                asset_id="asset-valid",
                asset_type=AssetType.IMAGE,
                version_id="version-valid",
            )

    def test_registry_instances_keep_isolated_state(self) -> None:
        first = AssetRegistry()
        second = AssetRegistry()
        first.create_asset(
            asset_id="asset-isolated",
            asset_type=AssetType.IMAGE,
            version_id="version-isolated",
        )

        with self.assertRaises(AssetNotFoundError):
            second.get_asset("asset-isolated")

    def test_concurrent_duplicate_asset_creation_has_one_winner(self) -> None:
        def create_asset() -> str:
            try:
                self.registry.create_asset(
                    asset_id="asset-concurrent",
                    asset_type=AssetType.IMAGE,
                    version_id="version-concurrent",
                )
                return "created"
            except DuplicateAssetError:
                return "duplicate"

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: create_asset(), range(8)))

        self.assertEqual(1, results.count("created"))
        self.assertEqual(7, results.count("duplicate"))


if __name__ == "__main__":
    unittest.main()
