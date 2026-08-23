"""Errors exposed by the V5 Core OS Project Engine."""


class ProjectEngineError(Exception):
    """Base error for all Project Engine failures."""


class ValidationError(ProjectEngineError, ValueError):
    """Raised when a caller supplies invalid input."""


class DuplicateProjectError(ProjectEngineError):
    """Raised when a project identifier is already registered."""


class ProjectNotFoundError(ProjectEngineError, LookupError):
    """Raised when a project cannot be found."""


class InvalidProjectLifecycleTransitionError(ProjectEngineError):
    """Raised when a requested project lifecycle change is not allowed."""
