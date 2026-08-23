"""Dependency-free in-memory Project-Asset relationship foundation."""

from threading import RLock
from typing import Dict, Sequence, Tuple

from .errors import DuplicateProjectAssetRelationshipError, ValidationError
from .models import ProjectAssetRelationship

RelationshipKey = Tuple[str, str]


class ProjectAssetRelationshipEngine:
    """Attach and query process-local Project-to-Asset use relationships.

    Project and Asset identifiers remain opaque. This engine records only
    that a Project uses an Asset; it does not resolve either reference or
    infer ownership, rights, permission, or version selection.
    """

    def __init__(self) -> None:
        self._relationships: Dict[
            RelationshipKey,
            ProjectAssetRelationship,
        ] = {}
        self._lock = RLock()

    def attach_asset(
        self,
        *,
        project_id: str,
        asset_id: str,
    ) -> ProjectAssetRelationship:
        """Record that an opaque Project reference uses an Asset reference."""

        normalized_project_id = self._identifier(project_id, "project_id")
        normalized_asset_id = self._identifier(asset_id, "asset_id")
        key = (normalized_project_id, normalized_asset_id)

        with self._lock:
            if key in self._relationships:
                raise DuplicateProjectAssetRelationshipError(
                    "Project-Asset relationship already exists"
                )

            relationship = ProjectAssetRelationship(
                project_id=normalized_project_id,
                asset_id=normalized_asset_id,
            )
            self._relationships[key] = relationship
            return relationship

    def list_project_assets(
        self,
        project_id: str,
    ) -> Sequence[ProjectAssetRelationship]:
        """Return a snapshot of use relationships for one Project reference."""

        normalized_project_id = self._identifier(project_id, "project_id")
        with self._lock:
            return tuple(
                relationship
                for relationship in self._relationships.values()
                if relationship.project_id == normalized_project_id
            )

    def list_asset_projects(
        self,
        asset_id: str,
    ) -> Sequence[ProjectAssetRelationship]:
        """Return a snapshot of use relationships for one Asset reference."""

        normalized_asset_id = self._identifier(asset_id, "asset_id")
        with self._lock:
            return tuple(
                relationship
                for relationship in self._relationships.values()
                if relationship.asset_id == normalized_asset_id
            )

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
        if not value.isprintable() or any(character.isspace() for character in value):
            raise ValidationError(
                "{} must contain printable, non-whitespace characters only".format(
                    field_name
                )
            )
        return value
