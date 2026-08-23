"""V5-internal package surface for the Identity Engine MVP."""

from .engine import IdentityEngine
from .errors import (
    DuplicateIdentityError,
    DuplicateOwnershipReferenceError,
    DuplicateWorkspaceError,
    IdentityEngineError,
    IdentityNotFoundError,
    OwnershipReferenceNotFoundError,
    ValidationError,
    WorkspaceNotFoundError,
)
from .models import Identity, OwnershipReference, Workspace

__all__ = [
    "DuplicateIdentityError",
    "DuplicateOwnershipReferenceError",
    "DuplicateWorkspaceError",
    "Identity",
    "IdentityEngine",
    "IdentityEngineError",
    "IdentityNotFoundError",
    "OwnershipReference",
    "OwnershipReferenceNotFoundError",
    "ValidationError",
    "Workspace",
    "WorkspaceNotFoundError",
]
