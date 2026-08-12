"""Stable internal errors for the V5 lifecycle integrity boundary."""


class LifecycleIntegrityError(RuntimeError):
    """Base error; messages never expose repository internals."""

    code = "lifecycle_integrity_error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class LeaseRejectedError(LifecycleIntegrityError):
    code = "lifecycle_lease_rejected"


class AssemblyPoisonedError(LifecycleIntegrityError):
    code = "lifecycle_assembly_poisoned"


class LifecycleRollbackError(LifecycleIntegrityError):
    code = "lifecycle_rollback_failed"
