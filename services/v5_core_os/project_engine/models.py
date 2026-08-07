"""Immutable records returned by the V5 Core OS Project Engine."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ProjectLifecycleState(Enum):
    """Minimal lifecycle states supported by ACS-P1-003.

    ACTIVE means only that the project has not been archived. It assigns no
    broader operational or execution semantics.
    """

    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Project:
    """An immutable Project Engine record.

    workspace_id and owner_identity_id jointly preserve an opaque owner
    reference context. They do not grant access or establish authoritative
    ownership, and this package does not resolve their external existence.
    """

    project_id: str
    workspace_id: str
    owner_identity_id: str
    lifecycle_state: ProjectLifecycleState
    created_at: datetime
    updated_at: datetime
