"""Unit tests for the V5 Core OS Project Engine."""

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from services.v5_core_os.project_engine import (
    DuplicateProjectError,
    InvalidProjectLifecycleTransitionError,
    Project,
    ProjectEngine,
    ProjectLifecycleState,
    ProjectNotFoundError,
    ValidationError,
)


class ProjectEngineUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(
            2026,
            8,
            6,
            21,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        )
        self.engine = ProjectEngine(clock=lambda: self.now)

    def create_project(self, project_id: str = "project-primary") -> Project:
        return self.engine.create_project(
            project_id=project_id,
            workspace_id="workspace-reference",
            owner_identity_id="identity-owner-reference",
        )

    def test_create_project_preserves_references_and_starts_active(self) -> None:
        project = self.create_project()

        self.assertEqual("project-primary", project.project_id)
        self.assertEqual("workspace-reference", project.workspace_id)
        self.assertEqual("identity-owner-reference", project.owner_identity_id)
        self.assertIs(ProjectLifecycleState.ACTIVE, project.lifecycle_state)
        self.assertEqual(self.now.astimezone(timezone.utc), project.created_at)
        self.assertEqual(project.created_at, project.updated_at)

    def test_query_returns_created_project(self) -> None:
        created = self.create_project()

        self.assertEqual(created, self.engine.get_project("project-primary"))

    def test_list_is_empty_before_creation(self) -> None:
        self.assertEqual(0, len(self.engine.list_projects()))

    def test_list_contains_created_projects_without_order_assumption(self) -> None:
        self.create_project("project-first")
        self.create_project("project-second")

        project_ids = {project.project_id for project in self.engine.list_projects()}

        self.assertEqual({"project-first", "project-second"}, project_ids)

    def test_list_returns_a_snapshot(self) -> None:
        self.create_project("project-first")
        snapshot = self.engine.list_projects()

        self.create_project("project-second")

        self.assertEqual({"project-first"}, {project.project_id for project in snapshot})

    def test_duplicate_project_identifier_is_rejected(self) -> None:
        self.create_project()

        with self.assertRaises(DuplicateProjectError):
            self.create_project()

    def test_query_missing_project_is_rejected(self) -> None:
        with self.assertRaises(ProjectNotFoundError):
            self.engine.get_project("project-missing")

    def test_archive_moves_active_project_to_archived(self) -> None:
        created_at = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
        archived_at = datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc)
        moments = iter((created_at, archived_at))
        engine = ProjectEngine(clock=lambda: next(moments))
        active = engine.create_project(
            project_id="project-lifecycle",
            workspace_id="workspace-reference",
            owner_identity_id="identity-owner-reference",
        )

        archived = engine.archive_project("project-lifecycle")

        self.assertIs(ProjectLifecycleState.ACTIVE, active.lifecycle_state)
        self.assertIs(ProjectLifecycleState.ARCHIVED, archived.lifecycle_state)
        self.assertEqual(active.created_at, archived.created_at)
        self.assertEqual(archived_at, archived.updated_at)
        self.assertEqual(archived, engine.get_project("project-lifecycle"))

    def test_archiving_an_archived_project_is_rejected(self) -> None:
        self.create_project()
        self.engine.archive_project("project-primary")

        with self.assertRaises(InvalidProjectLifecycleTransitionError):
            self.engine.archive_project("project-primary")

    def test_archiving_a_missing_project_is_rejected(self) -> None:
        with self.assertRaises(ProjectNotFoundError):
            self.engine.archive_project("project-missing")

    def test_identifiers_reject_invalid_values(self) -> None:
        invalid_values = ("", "   ", " padded ", "with space", "line\nbreak", None)
        fields = ("project_id", "workspace_id", "owner_identity_id")

        for field in fields:
            for invalid_value in invalid_values:
                values = {
                    "project_id": "project-valid",
                    "workspace_id": "workspace-valid",
                    "owner_identity_id": "identity-valid",
                }
                values[field] = invalid_value
                with self.subTest(field=field, invalid_value=invalid_value):
                    with self.assertRaises(ValidationError):
                        self.engine.create_project(**values)  # type: ignore[arg-type]

    def test_returned_project_is_immutable(self) -> None:
        project = self.create_project()

        with self.assertRaises(FrozenInstanceError):
            project.workspace_id = "workspace-changed"  # type: ignore[misc]

    def test_clock_must_return_datetime(self) -> None:
        engine = ProjectEngine(clock=lambda: "not-a-datetime")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            engine.create_project(
                project_id="project-valid",
                workspace_id="workspace-valid",
                owner_identity_id="identity-valid",
            )

    def test_clock_must_return_timezone_aware_datetime(self) -> None:
        engine = ProjectEngine(clock=lambda: datetime(2026, 8, 6, 12, 0))

        with self.assertRaises(ValidationError):
            engine.create_project(
                project_id="project-valid",
                workspace_id="workspace-valid",
                owner_identity_id="identity-valid",
            )

    def test_engine_instances_keep_isolated_state(self) -> None:
        first = ProjectEngine()
        second = ProjectEngine()
        first.create_project(
            project_id="project-isolated",
            workspace_id="workspace-reference",
            owner_identity_id="identity-owner-reference",
        )

        with self.assertRaises(ProjectNotFoundError):
            second.get_project("project-isolated")


if __name__ == "__main__":
    unittest.main()
