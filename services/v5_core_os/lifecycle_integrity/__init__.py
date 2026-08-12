"""Accepted bounded V5 lifecycle integrity composition boundary."""

from .contracts import (
    AssemblyState,
    BackendKind,
    LeaseState,
    LifecycleAssemblyIdentity,
    LifecycleLeaseView,
    LifecycleOperation,
)
from .errors import (
    AssemblyPoisonedError,
    LeaseRejectedError,
    LifecycleIntegrityError,
    LifecycleRollbackError,
)
from .in_memory import InMemoryLifecycleState


def __getattr__(name: str):
    if name == "LifecycleAssembly":
        from .composition import LifecycleAssembly

        return LifecycleAssembly
    raise AttributeError(name)


__all__ = [
    "AssemblyPoisonedError",
    "AssemblyState",
    "BackendKind",
    "InMemoryLifecycleState",
    "LeaseRejectedError",
    "LeaseState",
    "LifecycleAssembly",
    "LifecycleAssemblyIdentity",
    "LifecycleIntegrityError",
    "LifecycleLeaseView",
    "LifecycleOperation",
    "LifecycleRollbackError",
]
