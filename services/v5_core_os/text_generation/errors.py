"""Safe V5 errors for the Text Generation capability boundary."""

from __future__ import annotations


_SAFE_CATEGORIES = frozenset(
    {
        "credential_missing",
        "fake_exhausted",
        "internal_adapter_error",
        "invalid_generation_command",
        "invalid_generation_purpose",
        "network_error",
        "provider_empty_content",
        "provider_http_error",
        "provider_invalid_json",
        "provider_timeout",
    }
)


def _safe_category(value: object, fallback: str) -> str:
    safe_fallback = (
        fallback
        if type(fallback) is str and fallback in _SAFE_CATEGORIES
        else "internal_adapter_error"
    )
    if type(value) is str and value in _SAFE_CATEGORIES:
        return value
    return safe_fallback


def _safe_status(value: object) -> int | None:
    if type(value) is int and 100 <= value <= 599:
        return value
    return None


class TextGenerationCapabilityError(RuntimeError):
    """Stable error that exposes only safe V5 diagnostics."""

    code = "text_generation_unavailable"
    category = "internal_adapter_error"

    def __init__(
        self,
        *,
        category: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(self.code)
        self.category = _safe_category(category, type(self).category)
        self.status = _safe_status(status)


class TextGenerationConfigurationError(TextGenerationCapabilityError):
    """The V5 capability has no usable configured execution provider."""

    code = "text_generation_not_configured"
    category = "credential_missing"


class TextGenerationTimeoutError(TextGenerationCapabilityError):
    """The lower execution boundary did not complete within its V5 policy."""

    code = "text_generation_timeout"
    category = "provider_timeout"


class TextGenerationUnavailableError(TextGenerationCapabilityError):
    """The lower execution boundary could not return usable candidate text."""

    code = "text_generation_unavailable"
    category = "network_error"
