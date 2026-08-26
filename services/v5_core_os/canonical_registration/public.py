"""Creator-facing boundary for canonical registration preflight and apply."""

from __future__ import annotations

from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation
from services.v5_core_os.lifecycle_integrity.errors import LifecycleIntegrityError
from services.v5_core_os.project_engine.foundation import (
    ProjectContextError,
    ProjectDuplicateError,
    ProjectLifecycleError,
    ProjectRecordNotFoundError,
    ProjectScopeMismatchError,
)
from services.v5_core_os.script_studio.foundation import (
    DuplicateRecordError as ScriptDuplicateRecordError,
    RecordNotFoundError as ScriptRecordNotFoundError,
    RepositoryWriteError,
    ScopeMismatchError as ScriptScopeMismatchError,
    ScriptNotConfirmedError,
    ScriptStudioError,
    TrustedApprovalRequiredError,
    VersionConflictError,
)
from services.v5_core_os.series_episode.foundation import (
    DuplicateRecordError as SeriesDuplicateRecordError,
    RecordNotFoundError as SeriesRecordNotFoundError,
    ScopeMismatchError as SeriesScopeMismatchError,
    SeriesEpisodeError,
    UnconfirmedPlanError,
)

from .foundation import (
    CanonicalRegistrationConflictError,
    CanonicalRegistrationError,
    CanonicalRegistrationRepositoryError,
    CanonicalRegistrationService,
    CanonicalRegistrationUnavailableError,
    normalize_registration_command,
)


class CanonicalRegistrationPublicError(RuntimeError):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _domain_error(exc: BaseException) -> CanonicalRegistrationPublicError:
    if isinstance(exc, CanonicalRegistrationConflictError):
        return CanonicalRegistrationPublicError(exc.code, 409)
    if isinstance(exc, CanonicalRegistrationUnavailableError):
        return CanonicalRegistrationPublicError(exc.code, 503)
    if isinstance(exc, CanonicalRegistrationRepositoryError):
        return CanonicalRegistrationPublicError(exc.code, 500)
    if isinstance(exc, CanonicalRegistrationError):
        return CanonicalRegistrationPublicError(exc.code, 400)
    if isinstance(exc, TrustedApprovalRequiredError):
        return CanonicalRegistrationPublicError(exc.code, 403)
    if isinstance(exc, RepositoryWriteError):
        return CanonicalRegistrationPublicError(exc.code, 500)
    if isinstance(
        exc,
        (
            ProjectDuplicateError,
            ProjectLifecycleError,
            ScriptDuplicateRecordError,
            ScriptNotConfirmedError,
            VersionConflictError,
            SeriesDuplicateRecordError,
            UnconfirmedPlanError,
        ),
    ):
        return CanonicalRegistrationPublicError(exc.code, 409)
    if isinstance(
        exc,
        (
            ProjectRecordNotFoundError,
            ScriptRecordNotFoundError,
            SeriesRecordNotFoundError,
        ),
    ):
        return CanonicalRegistrationPublicError(exc.code, 404)
    if isinstance(
        exc,
        (
            ProjectScopeMismatchError,
            ScriptScopeMismatchError,
            SeriesScopeMismatchError,
        ),
    ):
        return CanonicalRegistrationPublicError(exc.code, 400)
    if isinstance(exc, (ProjectContextError, ScriptStudioError, SeriesEpisodeError)):
        return CanonicalRegistrationPublicError(exc.code, 400)
    if isinstance(exc, LifecycleIntegrityError):
        return CanonicalRegistrationPublicError(
            "canonical_registration_unavailable", 503
        )
    return CanonicalRegistrationPublicError("application_error", 500)


class CanonicalRegistrationPublicBoundary:
    def __init__(self, service: CanonicalRegistrationService, *, lifecycle_state) -> None:
        self.__service = service
        self.__lifecycle_state = lifecycle_state
        self.__lifecycle_assembly = None

    def _bind_lifecycle_assembly(self, assembly) -> None:
        if self.__lifecycle_assembly is not None:
            raise RuntimeError("lifecycle assembly is already bound")
        self.__lifecycle_assembly = assembly

    def _lifecycle_assembly_or_none(self):
        return self.__lifecycle_assembly

    def preflight(self, command: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self.__lifecycle_state.assert_ready()
            return self.__service.preflight(command)
        except Exception as exc:
            raise _domain_error(exc) from None

    def register(self, command: Mapping[str, Any]) -> dict[str, Any]:
        try:
            normalized = normalize_registration_command(command)
            with self.__lifecycle_state.lease(
                workspace_ref=normalized["workspaceRef"],
                operation=LifecycleOperation.CANONICAL_REGISTRATION,
            ) as lease:
                return self.__lifecycle_state.apply_mutation(
                    lease, lambda: self.__service.register(normalized)
                )
        except Exception as exc:
            raise _domain_error(exc) from None


__all__ = [
    "CanonicalRegistrationPublicBoundary",
    "CanonicalRegistrationPublicError",
]
