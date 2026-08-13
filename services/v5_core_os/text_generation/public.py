"""V5-owned Application boundary that maps text-generation intent to V4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from services.v4_platform import (
    ProviderConfigurationError,
    ProviderTimeoutError,
    TextGenerationRequest as V4TextGenerationRequest,
    TextMessage as V4TextMessage,
    TextProvider,
    TextProviderError,
    create_text_provider_from_environment,
)

from .contracts import (
    TextGenerationCommand,
    TextGenerationMessage,
    TextGenerationPurpose,
)
from .errors import (
    TextGenerationConfigurationError,
    TextGenerationTimeoutError,
    TextGenerationUnavailableError,
)


@dataclass(frozen=True)
class _ExecutionProfile:
    response_format: str
    max_tokens: int
    temperature: float
    timeout_seconds: float


_EXECUTION_PROFILES = {
    TextGenerationPurpose.AI_DIRECTOR_CANDIDATE: _ExecutionProfile(
        "json_object", 6_000, 0.4, 35.0
    ),
    TextGenerationPurpose.SCRIPT_CANDIDATE: _ExecutionProfile(
        "json_object", 8_000, 0.35, 45.0
    ),
    TextGenerationPurpose.SCRIPT_SCENE_REWRITE: _ExecutionProfile(
        "json_object", 3_500, 0.35, 45.0
    ),
    TextGenerationPurpose.SERIES_PLAN_CANDIDATE: _ExecutionProfile(
        "json_object", 16_000, 0.3, 90.0
    ),
}


class TextGenerationPublicBoundary:
    """The only V5 text-generation surface available to Creator Application."""

    def __init__(self, provider: TextProvider) -> None:
        self.__provider = provider

    def generate(self, command: TextGenerationCommand) -> str:
        if type(command) is not TextGenerationCommand:
            raise TextGenerationConfigurationError(
                category="invalid_generation_command"
            ) from None
        if type(command.purpose) is not TextGenerationPurpose:
            raise TextGenerationConfigurationError(
                category="invalid_generation_purpose"
            ) from None
        if type(command.messages) is not tuple or any(
            type(message) is not TextGenerationMessage
            or type(message.role) is not str
            or type(message.content) is not str
            for message in command.messages
        ):
            raise TextGenerationConfigurationError(
                category="invalid_generation_command"
            ) from None
        profile = _EXECUTION_PROFILES[command.purpose]

        generation_request = V4TextGenerationRequest(
            messages=tuple(
                V4TextMessage(role=message.role, content=message.content)
                for message in command.messages
            ),
            response_format=profile.response_format,
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
            timeout_seconds=profile.timeout_seconds,
        )
        try:
            return self.__provider.generate(generation_request)
        except ProviderConfigurationError as exc:
            safe_error = TextGenerationConfigurationError(
                category=exc.category,
                status=exc.status,
            )
        except ProviderTimeoutError as exc:
            safe_error = TextGenerationTimeoutError(
                category=exc.category,
                status=exc.status,
            )
        except TextProviderError as exc:
            safe_error = TextGenerationUnavailableError(
                category=exc.category,
                status=exc.status,
            )
        # Raise outside the V4 exception handler so even programmatic inspection of
        # __context__ cannot reach a lower-layer exception containing raw details.
        raise safe_error from None


class _UnconfiguredTextGenerationCapability:
    """Fail-closed capability used when server-side configuration is unavailable."""

    def generate(self, command: TextGenerationCommand) -> str:
        raise TextGenerationConfigurationError() from None


def create_unconfigured_text_generation_capability():
    """Create a safe capability that fails only when generation is requested."""

    return _UnconfiguredTextGenerationCapability()


def create_text_generation_capability_from_environment(
    environ: Mapping[str, str] | None = None,
):
    """Compose the V5 boundary without exposing V4 providers or configuration errors."""

    try:
        provider = create_text_provider_from_environment(environ)
    except ProviderConfigurationError:
        return create_unconfigured_text_generation_capability()
    return TextGenerationPublicBoundary(provider)
