"""Dependency-free in-memory foundation for the V5 Identity Engine MVP."""

from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Optional, Tuple

from .errors import (
    DuplicateIdentityError,
    DuplicateOwnershipReferenceError,
    DuplicateWorkspaceError,
    IdentityNotFoundError,
    OwnershipReferenceNotFoundError,
    ValidationError,
    WorkspaceNotFoundError,
)
from .models import Identity, OwnershipReference, Workspace

Clock = Callable[[], datetime]
OwnershipKey = Tuple[str, str]

MAX_IDENTIFIER_LENGTH = 128
MAX_DISPLAY_NAME_LENGTH = 200


class IdentityEngine:
    """Create and query identities, workspaces, and ownership references.

    State is intentionally process-local. The engine exposes no persistence,
    transport, identity-provider, or access-decision behavior.
    """

    def __init__(self, *, clock: Optional[Clock] = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._identities: Dict[str, Identity] = {}
        self._workspaces: Dict[str, Workspace] = {}
        self._ownership_references: Dict[OwnershipKey, OwnershipReference] = {}
        self._lock = RLock()

    def create_identity(self, *, identity_id: str, display_name: str) -> Identity:
        """Create an identity and return its immutable record."""

        normalized_id = self._identifier(identity_id, "identity_id")
        normalized_name = self._display_name(display_name)

        with self._lock:
            if normalized_id in self._identities:
                raise DuplicateIdentityError(
                    "Identity already exists: {}".format(normalized_id)
                )

            identity = Identity(
                identity_id=normalized_id,
                display_name=normalized_name,
                created_at=self._timestamp(),
            )
            self._identities[normalized_id] = identity
            return identity

    def get_identity(self, identity_id: str) -> Identity:
        """Return an identity by its opaque identifier."""

        normalized_id = self._identifier(identity_id, "identity_id")
        with self._lock:
            try:
                return self._identities[normalized_id]
            except KeyError as error:
                raise IdentityNotFoundError(
                    "Identity not found: {}".format(normalized_id)
                ) from error

    def create_workspace(
        self,
        *,
        workspace_id: str,
        display_name: str,
    ) -> Workspace:
        """Create a workspace and return its immutable record."""

        normalized_id = self._identifier(workspace_id, "workspace_id")
        normalized_name = self._display_name(display_name)

        with self._lock:
            if normalized_id in self._workspaces:
                raise DuplicateWorkspaceError(
                    "Workspace already exists: {}".format(normalized_id)
                )

            workspace = Workspace(
                workspace_id=normalized_id,
                display_name=normalized_name,
                created_at=self._timestamp(),
            )
            self._workspaces[normalized_id] = workspace
            return workspace

    def get_workspace(self, workspace_id: str) -> Workspace:
        """Return a workspace by its opaque identifier."""

        normalized_id = self._identifier(workspace_id, "workspace_id")
        with self._lock:
            try:
                return self._workspaces[normalized_id]
            except KeyError as error:
                raise WorkspaceNotFoundError(
                    "Workspace not found: {}".format(normalized_id)
                ) from error

    def create_ownership_reference(
        self,
        *,
        identity_id: str,
        workspace_id: str,
    ) -> OwnershipReference:
        """Associate an existing identity with an existing workspace.

        The Identity-to-Workspace pair is the reference key. The association
        is referential only and has no access-decision effect.
        """

        normalized_identity_id = self._identifier(identity_id, "identity_id")
        normalized_workspace_id = self._identifier(workspace_id, "workspace_id")
        key = (normalized_identity_id, normalized_workspace_id)

        with self._lock:
            if normalized_identity_id not in self._identities:
                raise IdentityNotFoundError(
                    "Identity not found: {}".format(normalized_identity_id)
                )
            if normalized_workspace_id not in self._workspaces:
                raise WorkspaceNotFoundError(
                    "Workspace not found: {}".format(normalized_workspace_id)
                )
            if key in self._ownership_references:
                raise DuplicateOwnershipReferenceError(
                    "Ownership reference already exists for the supplied pair"
                )

            reference = OwnershipReference(
                identity_id=normalized_identity_id,
                workspace_id=normalized_workspace_id,
                created_at=self._timestamp(),
            )
            self._ownership_references[key] = reference
            return reference

    def get_ownership_reference(
        self,
        *,
        identity_id: str,
        workspace_id: str,
    ) -> OwnershipReference:
        """Return an ownership reference by its Identity-to-Workspace pair."""

        normalized_identity_id = self._identifier(identity_id, "identity_id")
        normalized_workspace_id = self._identifier(workspace_id, "workspace_id")
        key = (normalized_identity_id, normalized_workspace_id)

        with self._lock:
            try:
                return self._ownership_references[key]
            except KeyError as error:
                raise OwnershipReferenceNotFoundError(
                    "Ownership reference not found for the supplied pair"
                ) from error

    def _timestamp(self) -> datetime:
        timestamp = self._clock()
        if not isinstance(timestamp, datetime):
            raise ValidationError("clock must return a datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValidationError("clock must return a timezone-aware datetime")
        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _identifier(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError("{} must be a string".format(field_name))
        if not value or value != value.strip():
            raise ValidationError(
                "{} must be non-empty and contain no surrounding whitespace".format(
                    field_name
                )
            )
        if len(value) > MAX_IDENTIFIER_LENGTH:
            raise ValidationError(
                "{} must not exceed {} characters".format(
                    field_name,
                    MAX_IDENTIFIER_LENGTH,
                )
            )
        if not value.isprintable() or any(character.isspace() for character in value):
            raise ValidationError(
                "{} must contain printable, non-whitespace characters only".format(
                    field_name
                )
            )
        return value

    @staticmethod
    def _display_name(value: str) -> str:
        if not isinstance(value, str):
            raise ValidationError("display_name must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValidationError("display_name must not be empty")
        if len(normalized) > MAX_DISPLAY_NAME_LENGTH:
            raise ValidationError(
                "display_name must not exceed {} characters".format(
                    MAX_DISPLAY_NAME_LENGTH
                )
            )
        if not normalized.isprintable():
            raise ValidationError(
                "display_name must contain only printable characters"
            )
        return normalized
