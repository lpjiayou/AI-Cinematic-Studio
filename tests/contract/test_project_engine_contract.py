"""V5-internal Project Engine package contract tests for ACS-P1-003."""

import unittest

from services.v5_core_os.project_engine import (
    DuplicateProjectError,
    InvalidProjectLifecycleTransitionError,
    Project,
    ProjectEngine,
    ProjectEngineError,
    ProjectLifecycleState,
    ProjectNotFoundError,
    ValidationError,
)


class ProjectEnginePackageContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ProjectEngine()

    def create_project(self, project_id: str = "project-contract") -> Project:
        return self.engine.create_project(
            project_id=project_id,
            workspace_id="workspace-contract",
            owner_identity_id="identity-owner-contract",
        )

    def test_create_and_query_contract(self) -> None:
        created = self.create_project()

        self.assertIsInstance(created, Project)
        self.assertEqual("project-contract", created.project_id)
        self.assertEqual(created, self.engine.get_project("project-contract"))
        self.assertIs(ProjectLifecycleState.ACTIVE, created.lifecycle_state)
        self.assertEqual(0, created.created_at.utcoffset().total_seconds())

    def test_list_contract_exposes_created_projects(self) -> None:
        self.create_project("project-first")
        self.create_project("project-second")

        project_ids = {project.project_id for project in self.engine.list_projects()}

        self.assertEqual({"project-first", "project-second"}, project_ids)

    def test_workspace_and_owner_reference_contract(self) -> None:
        created = self.create_project()

        self.assertEqual("workspace-contract", created.workspace_id)
        self.assertEqual("identity-owner-contract", created.owner_identity_id)

    def test_lifecycle_contract(self) -> None:
        self.create_project()

        archived = self.engine.archive_project("project-contract")

        self.assertIs(ProjectLifecycleState.ARCHIVED, archived.lifecycle_state)
        with self.assertRaises(InvalidProjectLifecycleTransitionError):
            self.engine.archive_project("project-contract")

    def test_duplicate_not_found_and_validation_contract(self) -> None:
        self.create_project()

        with self.assertRaises(DuplicateProjectError):
            self.create_project()
        with self.assertRaises(ProjectNotFoundError):
            self.engine.get_project("project-missing")
        with self.assertRaises(ValidationError):
            self.engine.create_project(
                project_id="",
                workspace_id="workspace-contract",
                owner_identity_id="identity-owner-contract",
            )

    def test_error_hierarchy_contract(self) -> None:
        public_errors = (
            DuplicateProjectError,
            InvalidProjectLifecycleTransitionError,
            ProjectNotFoundError,
            ValidationError,
        )

        for error_type in public_errors:
            with self.subTest(error_type=error_type.__name__):
                self.assertTrue(issubclass(error_type, ProjectEngineError))


if __name__ == "__main__":
    unittest.main()
