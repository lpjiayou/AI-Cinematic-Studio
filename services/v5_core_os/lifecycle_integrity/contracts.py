"""Provider-neutral contracts for the bounded lifecycle integrity assembly."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BackendKind(str, Enum):
    IN_MEMORY = "in-memory"
    SQLITE_LOCAL = "sqlite-local-development"


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
    CREATE_SERIES = "create-series"
    CONFIRM_CREATIVE_PLAN = "confirm-creative-plan"
    CREATE_EPISODE = "create-episode"
    CREATE_PROJECT = "create-project"
    ARCHIVE_PROJECT = "archive-project"
    CREATE_SCRIPT_VERSION = "create-script-version"
    CONFIRM_SCRIPT_VERSION = "confirm-script-version"
    CREATE_SERIES_PLAN = "create-series-plan"
    APPEND_SERIES_PLAN_VERSION = "append-series-plan-version"
    CONFIRM_SERIES_PLAN_VERSION = "confirm-series-plan-version"
    CREATE_SERIES_BIBLE_VERSION = "create-series-bible-version"
    SUBMIT_SERIES_BIBLE_CANDIDATE = "submit-series-bible-candidate"
    CONFIRM_SERIES_BIBLE_VERSION = "confirm-series-bible-version"
    CREATE_CHARACTER_CONTINUITY_VERSION = "create-character-continuity-version"
    SUBMIT_CHARACTER_CONTINUITY_CANDIDATE = "submit-character-continuity-candidate"
    CONFIRM_CHARACTER_CONTINUITY_VERSION = "confirm-character-continuity-version"
    ACTIVATE_M6_BASELINE = "activate-m6-baseline"
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
