"""Errors exposed by the V5 Core OS Identity Engine."""


class IdentityEngineError(Exception):
    """Base error for all Identity Engine failures."""


class ValidationError(IdentityEngineError, ValueError):
    """Raised when a caller supplies invalid input."""


class DuplicateIdentityError(IdentityEngineError):
    """Raised when an identity identifier is already registered."""


class IdentityNotFoundError(IdentityEngineError, LookupError):
    """Raised when an identity cannot be found."""


class DuplicateWorkspaceError(IdentityEngineError):
    """Raised when a workspace identifier is already registered."""


class WorkspaceNotFoundError(IdentityEngineError, LookupError):
    """Raised when a workspace cannot be found."""


class DuplicateOwnershipReferenceError(IdentityEngineError):
    """Raised when an Identity-to-Workspace association already exists."""


class OwnershipReferenceNotFoundError(IdentityEngineError, LookupError):
    """Raised when an ownership reference cannot be found."""
