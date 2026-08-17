"""Minimal V4 execution boundary for replaceable external providers."""

from .text_generation import (
    DeepSeekTextProvider,
    FakeTextProvider,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TextGenerationRequest,
    TextMessage,
    TextProvider,
    TextProviderError,
    create_text_provider_from_environment,
)
from .media_jobs import (
    ArtifactVerificationError,
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaAdapterUnavailableError,
    MediaJobCoordinator,
    MediaJobError,
    MediaJobStateError,
    SqliteMediaJobAdapter,
    probe_media,
    verify_media_against_request,
)
from .composition import CompositionExecutionError, V4CompositionExecutor

__all__ = [
    "DeepSeekTextProvider",
    "FakeTextProvider",
    "ProviderConfigurationError",
    "ProviderMalformedResponseError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "TextGenerationRequest",
    "TextMessage",
    "TextProvider",
    "TextProviderError",
    "create_text_provider_from_environment",
    "ArtifactVerificationError",
    "DeterministicLocalFfmpegAdapter",
    "InMemoryMediaJobAdapter",
    "MediaAdapterUnavailableError",
    "MediaJobCoordinator",
    "MediaJobError",
    "MediaJobStateError",
    "SqliteMediaJobAdapter",
    "probe_media",
    "verify_media_against_request",
    "CompositionExecutionError",
    "V4CompositionExecutor",
]
