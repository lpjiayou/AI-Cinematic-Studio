"""Provider-neutral contracts for the bounded lifecycle integrity assembly."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BackendKind(str, Enum):
    IN_MEMORY = "in-memory"


class LeaseState(str, Enum):
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled-back"
    POISONED = "poisoned"


class AssemblyState(str, Enum):
    READY = "ready"
    POISONED = "poisoned"
    CLOSED = "closed"


class LifecycleOperation(str, Enum):
    CREATE_PROJECT = "create-project"
    CREATE_SCRIPT_VERSION = "create-script-version"
    DELETE_EPISODE = "delete-episode"
    DELETE_SERIES = "delete-series"


@dataclass(frozen=True, slots=True)
class LifecycleAssemblyIdentity:
    assembly_ref: str
    backend_kind: BackendKind
    storage_identity: str


@dataclass(frozen=True, slots=True)
class LifecycleLeaseView:
    issuer_ref: str
    assembly_identity: LifecycleAssemblyIdentity
    nonce: str
    owner_thread_id: int
    workspace_ref: str
    operation: LifecycleOperation
    state: LeaseState
