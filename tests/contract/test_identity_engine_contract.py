"""V5-internal package contract tests scoped to ACS-P1-002."""

import unittest

from services.v5_core_os.identity_engine import (
    DuplicateIdentityError,
    DuplicateOwnershipReferenceError,
    DuplicateWorkspaceError,
    Identity,
    IdentityEngine,
    IdentityEngineError,
    IdentityNotFoundError,
    OwnershipReference,
    OwnershipReferenceNotFoundError,
    ValidationError,
    Workspace,
    WorkspaceNotFoundError,
)


class IdentityEnginePackageContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = IdentityEngine()

    def test_identity_create_query_contract(self) -> None:
        created = self.engine.create_identity(
            identity_id="identity-contract",
            display_name="Internal Operator",
        )

        self.assertIsInstance(created, Identity)
        self.assertEqual("identity-contract", created.identity_id)
        self.assertEqual(created, self.engine.get_identity("identity-contract"))
        self.assertEqual(0, created.created_at.utcoffset().total_seconds())

    def test_workspace_create_query_contract(self) -> None:
        created = self.engine.create_workspace(
            workspace_id="workspace-contract",
            display_name="Internal Workspace",
        )

        self.assertIsInstance(created, Workspace)
        self.assertEqual("workspace-contract", created.workspace_id)
        self.assertEqual(created, self.engine.get_workspace("workspace-contract"))
        self.assertEqual(0, created.created_at.utcoffset().total_seconds())

    def test_ownership_reference_create_query_contract(self) -> None:
        self.engine.create_identity(identity_id="identity-owner", display_name="Owner")
        self.engine.create_workspace(
            workspace_id="workspace-owned",
            display_name="Workspace",
        )

        created = self.engine.create_ownership_reference(
            identity_id="identity-owner",
            workspace_id="workspace-owned",
        )

        self.assertIsInstance(created, OwnershipReference)
        self.assertEqual("identity-owner", created.identity_id)
        self.assertEqual("workspace-owned", created.workspace_id)
        self.assertEqual(
            created,
            self.engine.get_ownership_reference(
                identity_id="identity-owner",
                workspace_id="workspace-owned",
            ),
        )

    def test_duplicate_contract(self) -> None:
        self.engine.create_identity(identity_id="identity-owner", display_name="Owner")
        self.engine.create_workspace(
            workspace_id="workspace-owned",
            display_name="Workspace",
        )
        self.engine.create_ownership_reference(
            identity_id="identity-owner",
            workspace_id="workspace-owned",
        )

        with self.assertRaises(DuplicateIdentityError):
            self.engine.create_identity(
                identity_id="identity-owner",
                display_name="Owner",
            )
        with self.assertRaises(DuplicateWorkspaceError):
            self.engine.create_workspace(
                workspace_id="workspace-owned",
                display_name="Workspace",
            )
        with self.assertRaises(DuplicateOwnershipReferenceError):
            self.engine.create_ownership_reference(
                identity_id="identity-owner",
                workspace_id="workspace-owned",
            )

    def test_not_found_contract(self) -> None:
        with self.assertRaises(IdentityNotFoundError):
            self.engine.get_identity("identity-missing")
        with self.assertRaises(WorkspaceNotFoundError):
            self.engine.get_workspace("workspace-missing")
        with self.assertRaises(OwnershipReferenceNotFoundError):
            self.engine.get_ownership_reference(
                identity_id="identity-missing",
                workspace_id="workspace-missing",
            )

    def test_error_hierarchy_contract(self) -> None:
        public_errors = (
            DuplicateIdentityError,
            DuplicateOwnershipReferenceError,
            DuplicateWorkspaceError,
            IdentityNotFoundError,
            OwnershipReferenceNotFoundError,
            ValidationError,
            WorkspaceNotFoundError,
        )

        for error_type in public_errors:
            with self.subTest(error_type=error_type.__name__):
                self.assertTrue(issubclass(error_type, IdentityEngineError))


if __name__ == "__main__":
    unittest.main()
