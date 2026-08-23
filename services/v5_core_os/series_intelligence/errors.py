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


class M6BaselineNotAvailableError(SeriesIntelligenceError):
    code = "m6_baseline_not_available"


class M6BaselineStaleError(SeriesIntelligenceError):
    code = "m6_baseline_stale"


class M6LineageMismatchError(SeriesIntelligenceError):
    code = "m6_lineage_mismatch"


class M6ConsumerAuthorityUnavailableError(SeriesIntelligenceError):
    code = "m6_consumer_authority_unavailable"


class M6EpisodeMappingUnavailableError(SeriesIntelligenceError):
    code = "m6_episode_mapping_unavailable"
