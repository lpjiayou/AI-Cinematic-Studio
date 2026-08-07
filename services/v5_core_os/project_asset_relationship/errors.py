"""Errors exposed by the V5 Project-Asset Relationship Engine."""


class ProjectAssetRelationshipError(Exception):
    """Base error for Project-Asset relationship failures."""


class ValidationError(ProjectAssetRelationshipError, ValueError):
    """Raised when a caller supplies invalid input."""


class DuplicateProjectAssetRelationshipError(ProjectAssetRelationshipError):
    """Raised when a Project-to-Asset relationship already exists."""
