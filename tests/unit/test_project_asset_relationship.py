"""Unit tests for the V5 Project-Asset Relationship Engine."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

from services.v5_core_os.project_asset_relationship import (
    DuplicateProjectAssetRelationshipError,
    ProjectAssetRelationship,
    ProjectAssetRelationshipEngine,
    ValidationError,
)


class ProjectAssetRelationshipEngineUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ProjectAssetRelationshipEngine()

    def attach(
        self,
        project_id: str = "project-primary",
        asset_id: str = "asset-primary",
    ) -> ProjectAssetRelationship:
        return self.engine.attach_asset(
            project_id=project_id,
            asset_id=asset_id,
        )

    def test_attach_preserves_the_directional_references(self) -> None:
        relationship = self.attach()

        self.assertEqual("project-primary", relationship.project_id)
        self.assertEqual("asset-primary", relationship.asset_id)

    def test_relationship_is_immutable(self) -> None:
        relationship = self.attach()

        with self.assertRaises(FrozenInstanceError):
            relationship.asset_id = "asset-changed"  # type: ignore[misc]

    def test_project_query_is_empty_without_relationships(self) -> None:
        self.assertEqual(0, len(self.engine.list_project_assets("project-empty")))

    def test_asset_query_is_empty_without_relationships(self) -> None:
        self.assertEqual(0, len(self.engine.list_asset_projects("asset-empty")))

    def test_project_query_returns_only_matching_relationships(self) -> None:
        self.attach("project-target", "asset-first")
        self.attach("project-target", "asset-second")
        self.attach("project-other", "asset-third")

        asset_ids = {
            relationship.asset_id
            for relationship in self.engine.list_project_assets("project-target")
        }

        self.assertEqual({"asset-first", "asset-second"}, asset_ids)

    def test_asset_query_returns_only_matching_relationships(self) -> None:
        self.attach("project-first", "asset-target")
        self.attach("project-second", "asset-target")
        self.attach("project-third", "asset-other")

        project_ids = {
            relationship.project_id
            for relationship in self.engine.list_asset_projects("asset-target")
        }

        self.assertEqual({"project-first", "project-second"}, project_ids)

    def test_duplicate_relationship_is_rejected_without_overwrite(self) -> None:
        created = self.attach()

        with self.assertRaises(DuplicateProjectAssetRelationshipError):
            self.attach()

        self.assertEqual(
            (created,),
            tuple(self.engine.list_project_assets("project-primary")),
        )
        self.assertEqual(
            (created,),
            tuple(self.engine.list_asset_projects("asset-primary")),
        )

    def test_distinct_pairs_support_many_to_many_relationships(self) -> None:
        pairs = {
            ("project-first", "asset-first"),
            ("project-first", "asset-second"),
            ("project-second", "asset-first"),
        }

        for project_id, asset_id in pairs:
            self.attach(project_id, asset_id)

        stored_pairs = {
            (relationship.project_id, relationship.asset_id)
            for project_id in ("project-first", "project-second")
            for relationship in self.engine.list_project_assets(project_id)
        }
        self.assertEqual(pairs, stored_pairs)

    def test_project_query_returns_a_snapshot(self) -> None:
        self.attach("project-target", "asset-first")
        snapshot = self.engine.list_project_assets("project-target")

        self.attach("project-target", "asset-second")

        self.assertEqual(
            {"asset-first"},
            {relationship.asset_id for relationship in snapshot},
        )

    def test_asset_query_returns_a_snapshot(self) -> None:
        self.attach("project-first", "asset-target")
        snapshot = self.engine.list_asset_projects("asset-target")

        self.attach("project-second", "asset-target")

        self.assertEqual(
            {"project-first"},
            {relationship.project_id for relationship in snapshot},
        )

    def test_attach_rejects_invalid_identifiers(self) -> None:
        invalid_values = ("", "   ", " padded ", "with space", "line\nbreak", None)

        for field in ("project_id", "asset_id"):
            for invalid_value in invalid_values:
                values = {
                    "project_id": "project-valid",
                    "asset_id": "asset-valid",
                }
                values[field] = invalid_value
                with self.subTest(field=field, invalid_value=invalid_value):
                    with self.assertRaises(ValidationError):
                        self.engine.attach_asset(**values)  # type: ignore[arg-type]

    def test_queries_reject_invalid_identifiers(self) -> None:
        invalid_values = ("", "   ", " padded ", "with space", "line\nbreak", None)

        for invalid_value in invalid_values:
            with self.subTest(query="project", invalid_value=invalid_value):
                with self.assertRaises(ValidationError):
                    self.engine.list_project_assets(  # type: ignore[arg-type]
                        invalid_value
                    )
            with self.subTest(query="asset", invalid_value=invalid_value):
                with self.assertRaises(ValidationError):
                    self.engine.list_asset_projects(  # type: ignore[arg-type]
                        invalid_value
                    )

    def test_engine_instances_keep_isolated_state(self) -> None:
        first = ProjectAssetRelationshipEngine()
        second = ProjectAssetRelationshipEngine()
        first.attach_asset(
            project_id="project-isolated",
            asset_id="asset-isolated",
        )

        self.assertEqual(0, len(second.list_project_assets("project-isolated")))
        self.assertEqual(0, len(second.list_asset_projects("asset-isolated")))

    def test_concurrent_duplicate_attachment_has_one_winner(self) -> None:
        def attach() -> str:
            try:
                self.attach("project-concurrent", "asset-concurrent")
                return "attached"
            except DuplicateProjectAssetRelationshipError:
                return "duplicate"

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: attach(), range(8)))

        self.assertEqual(1, results.count("attached"))
        self.assertEqual(7, results.count("duplicate"))
        self.assertEqual(
            1,
            len(self.engine.list_project_assets("project-concurrent")),
        )
        self.assertEqual(
            1,
            len(self.engine.list_asset_projects("asset-concurrent")),
        )


if __name__ == "__main__":
    unittest.main()
