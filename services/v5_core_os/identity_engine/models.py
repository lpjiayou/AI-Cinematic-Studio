"""Immutable records returned by the V5 Core OS Identity Engine."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Identity:
    """An immutable record returned by IdentityEngine."""

    identity_id: str
    display_name: str
    created_at: datetime


@dataclass(frozen=True)
class Workspace:
    """An immutable record returned by IdentityEngine."""

    workspace_id: str
    display_name: str
    created_at: datetime


@dataclass(frozen=True)
class OwnershipReference:
    """A referential Identity-to-Workspace association.

    The association records ownership context only. It does not grant or
    evaluate access to the referenced workspace.
    """

    identity_id: str
    workspace_id: str
    created_at: datetime
