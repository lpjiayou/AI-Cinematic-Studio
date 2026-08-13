"""Stable internal errors for bounded M6 Series Intelligence."""


class SeriesIntelligenceError(ValueError):
    code = "invalid_request"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class AuthorityUnavailableError(SeriesIntelligenceError):
    code = "authority_unavailable"


class ScopeMismatchError(SeriesIntelligenceError):
    code = "scope_mismatch"


class RecordNotFoundError(SeriesIntelligenceError):
    code = "not_found"


class DuplicateRecordError(SeriesIntelligenceError):
    code = "duplicate_record"


class VersionConflictError(SeriesIntelligenceError):
    code = "version_conflict"


class IdempotencyConflictError(SeriesIntelligenceError):
    code = "idempotency_conflict"


class ConfirmationRequiredError(SeriesIntelligenceError):
    code = "confirmation_required"


class StaleSourceError(SeriesIntelligenceError):
    code = "stale_source"


class InvalidReferenceError(SeriesIntelligenceError):
    code = "invalid_reference"


class IdentityBindingDeniedError(SeriesIntelligenceError):
    code = "identity_binding_denied"
