"""Immutable records returned by the V5 Project-Asset Relationship Engine."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectAssetRelationship:
    """An immutable record that a Project uses an Asset.

    The two identifiers are opaque references. This relationship does not
    express ownership, rights, permission, or a selected Asset version.
    """

    project_id: str
    asset_id: str
