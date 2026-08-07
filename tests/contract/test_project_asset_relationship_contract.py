"""V5-internal package contract tests for Project-Asset relationships."""

import unittest

from services.v5_core_os.project_asset_relationship import (
    DuplicateProjectAssetRelationshipError,
    ProjectAssetRelationship,
    ProjectAssetRelationshipEngine,
    ProjectAssetRelationshipError,
    ValidationError,
)


class ProjectAssetRelationshipPackageContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ProjectAssetRelationshipEngine()

    def test_attach_contract_returns_a_relationship(self) -> None:
        relationship = self.engine.attach_asset(
            project_id="project-contract",
            asset_id="asset-contract",
        )

        self.assertIsInstance(relationship, ProjectAssetRelationship)
        self.assertEqual("project-contract", relationship.project_id)
        self.assertEqual("asset-contract", relationship.asset_id)

    def test_list_project_assets_contract(self) -> None:
        self.engine.attach_asset(
            project_id="project-contract",
            asset_id="asset-first",
        )
        self.engine.attach_asset(
            project_id="project-contract",
            asset_id="asset-second",
        )

        asset_ids = {
            relationship.asset_id
            for relationship in self.engine.list_project_assets("project-contract")
        }

        self.assertEqual({"asset-first", "asset-second"}, asset_ids)

    def test_list_asset_projects_contract(self) -> None:
        self.engine.attach_asset(
            project_id="project-first",
            asset_id="asset-contract",
        )
        self.engine.attach_asset(
            project_id="project-second",
            asset_id="asset-contract",
        )

        project_ids = {
            relationship.project_id
            for relationship in self.engine.list_asset_projects("asset-contract")
        }

        self.assertEqual({"project-first", "project-second"}, project_ids)

    def test_duplicate_relationship_contract(self) -> None:
        self.engine.attach_asset(
            project_id="project-contract",
            asset_id="asset-contract",
        )

        with self.assertRaises(DuplicateProjectAssetRelationshipError):
            self.engine.attach_asset(
                project_id="project-contract",
                asset_id="asset-contract",
            )

    def test_empty_query_contract(self) -> None:
        self.assertEqual(
            0,
            len(self.engine.list_project_assets("project-without-assets")),
        )
        self.assertEqual(
            0,
            len(self.engine.list_asset_projects("asset-without-projects")),
        )

    def test_error_hierarchy_and_validation_contract(self) -> None:
        self.assertTrue(
            issubclass(
                DuplicateProjectAssetRelationshipError,
                ProjectAssetRelationshipError,
            )
        )
        self.assertTrue(issubclass(ValidationError, ProjectAssetRelationshipError))
        self.assertTrue(issubclass(ValidationError, ValueError))

        with self.assertRaises(ValidationError):
            self.engine.attach_asset(
                project_id="",
                asset_id="asset-contract",
            )


if __name__ == "__main__":
    unittest.main()
