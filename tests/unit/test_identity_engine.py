"""Unit tests for the V5 Core OS Identity Engine."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from services.v5_core_os.identity_engine import (
    DuplicateIdentityError,
    DuplicateOwnershipReferenceError,
    DuplicateWorkspaceError,
    IdentityEngine,
    IdentityNotFoundError,
    OwnershipReferenceNotFoundError,
    ValidationError,
    WorkspaceNotFoundError,
)


class IdentityEngineUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(
            2026,
            8,
            6,
            20,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        )
        self.engine = IdentityEngine(clock=lambda: self.now)

    def test_create_and_query_identity(self) -> None:
        created = self.engine.create_identity(
            identity_id="identity-operator",
            display_name="  Studio Operator  ",
        )

        self.assertEqual("identity-operator", created.identity_id)
        self.assertEqual("Studio Operator", created.display_name)
        self.assertEqual(self.now.astimezone(timezone.utc), created.created_at)
        self.assertEqual(created, self.engine.get_identity(created.identity_id))

    def test_identity_identifier_must_be_unique(self) -> None:
        self.engine.create_identity(identity_id="identity-fixed", display_name="First")

        with self.assertRaises(DuplicateIdentityError):
            self.engine.create_identity(
                identity_id="identity-fixed",
                display_name="Second",
            )

    def test_create_and_query_workspace(self) -> None:
        created = self.engine.create_workspace(
            workspace_id="workspace-primary",
            display_name="  Primary Workspace  ",
        )

        self.assertEqual("workspace-primary", created.workspace_id)
        self.assertEqual("Primary Workspace", created.display_name)
        self.assertEqual(self.now.astimezone(timezone.utc), created.created_at)
        self.assertEqual(created, self.engine.get_workspace(created.workspace_id))

    def test_workspace_identifier_must_be_unique(self) -> None:
        self.engine.create_workspace(workspace_id="workspace-fixed", display_name="First")

        with self.assertRaises(DuplicateWorkspaceError):
            self.engine.create_workspace(
                workspace_id="workspace-fixed",
                display_name="Second",
            )

    def test_create_and_query_ownership_reference(self) -> None:
        self.engine.create_identity(identity_id="identity-owner", display_name="Owner")
        self.engine.create_workspace(
            workspace_id="workspace-owned",
            display_name="Workspace",
        )

        reference = self.engine.create_ownership_reference(
            identity_id="identity-owner",
            workspace_id="workspace-owned",
        )

        self.assertEqual("identity-owner", reference.identity_id)
        self.assertEqual("workspace-owned", reference.workspace_id)
        self.assertEqual(self.now.astimezone(timezone.utc), reference.created_at)
        self.assertEqual(
            reference,
            self.engine.get_ownership_reference(
                identity_id="identity-owner",
                workspace_id="workspace-owned",
            ),
        )

    def test_duplicate_ownership_pair_is_rejected(self) -> None:
        self.engine.create_identity(identity_id="identity-owner", display_name="Owner")
        self.engine.create_workspace(
            workspace_id="workspace-owned",
            display_name="Workspace",
        )
        self.engine.create_ownership_reference(
            identity_id="identity-owner",
            workspace_id="workspace-owned",
        )

        with self.assertRaises(DuplicateOwnershipReferenceError):
            self.engine.create_ownership_reference(
                identity_id="identity-owner",
                workspace_id="workspace-owned",
            )

    def test_ownership_reference_requires_existing_identity(self) -> None:
        self.engine.create_workspace(
            workspace_id="workspace-existing",
            display_name="Workspace",
        )

        with self.assertRaises(IdentityNotFoundError):
            self.engine.create_ownership_reference(
                identity_id="identity-missing",
                workspace_id="workspace-existing",
            )

    def test_ownership_reference_requires_existing_workspace(self) -> None:
        self.engine.create_identity(
            identity_id="identity-existing",
            display_name="Owner",
        )

        with self.assertRaises(WorkspaceNotFoundError):
            self.engine.create_ownership_reference(
                identity_id="identity-existing",
                workspace_id="workspace-missing",
            )

    def test_queries_report_missing_records(self) -> None:
        with self.assertRaises(IdentityNotFoundError):
            self.engine.get_identity("identity-missing")
        with self.assertRaises(WorkspaceNotFoundError):
            self.engine.get_workspace("workspace-missing")
        with self.assertRaises(OwnershipReferenceNotFoundError):
            self.engine.get_ownership_reference(
                identity_id="identity-missing",
                workspace_id="workspace-missing",
            )

    def test_identifiers_reject_invalid_or_oversized_values(self) -> None:
        invalid_identifiers = ("", "   ", " identity-padded ", "with space", "x" * 129)

        for invalid_identifier in invalid_identifiers:
            with self.subTest(invalid_identifier=invalid_identifier):
                with self.assertRaises(ValidationError):
                    self.engine.create_identity(
                        identity_id=invalid_identifier,
                        display_name="Owner",
                    )

        with self.assertRaises(ValidationError):
            self.engine.create_workspace(  # type: ignore[arg-type]
                workspace_id=None,
                display_name="Workspace",
            )

    def test_display_names_reject_invalid_or_oversized_values(self) -> None:
        invalid_names = ("", "   ", "Line\nBreak", "x" * 201, None)

        for invalid_name in invalid_names:
            with self.subTest(invalid_name=invalid_name):
                with self.assertRaises(ValidationError):
                    self.engine.create_identity(  # type: ignore[arg-type]
                        identity_id="identity-valid",
                        display_name=invalid_name,
                    )

    def test_all_returned_records_are_immutable(self) -> None:
        identity = self.engine.create_identity(
            identity_id="identity-owner",
            display_name="Owner",
        )
        workspace = self.engine.create_workspace(
            workspace_id="workspace-owned",
            display_name="Workspace",
        )
        reference = self.engine.create_ownership_reference(
            identity_id=identity.identity_id,
            workspace_id=workspace.workspace_id,
        )

        with self.assertRaises(FrozenInstanceError):
            identity.display_name = "Changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            workspace.display_name = "Changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            reference.workspace_id = "Changed"  # type: ignore[misc]

    def test_clock_must_return_timezone_aware_datetime(self) -> None:
        engine = IdentityEngine(clock=lambda: datetime(2026, 8, 6, 12, 0))

        with self.assertRaises(ValidationError):
            engine.create_identity(identity_id="identity-owner", display_name="Owner")

    def test_clock_must_return_datetime(self) -> None:
        engine = IdentityEngine(clock=lambda: "not-a-datetime")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            engine.create_workspace(
                workspace_id="workspace-owned",
                display_name="Workspace",
            )

    def test_engine_instances_keep_isolated_state(self) -> None:
        first = IdentityEngine()
        second = IdentityEngine()
        first.create_identity(identity_id="identity-isolated", display_name="Owner")

        with self.assertRaises(IdentityNotFoundError):
            second.get_identity("identity-isolated")

    def test_concurrent_duplicate_identity_creation_has_one_winner(self) -> None:
        def create_identity() -> str:
            try:
                self.engine.create_identity(
                    identity_id="identity-concurrent",
                    display_name="Owner",
                )
                return "created"
            except DuplicateIdentityError:
                return "duplicate"

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: create_identity(), range(8)))

        self.assertEqual(1, results.count("created"))
        self.assertEqual(7, results.count("duplicate"))


if __name__ == "__main__":
    unittest.main()
