"""Provider-neutral synchronous text generation boundary.

Provider-specific request details remain inside adapters. Application callers
receive only text or stable boundary errors; credentials and raw responses are
never included in those errors.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
from typing import Mapping, Protocol, Sequence
from urllib import error, request


class TextProviderError(RuntimeError):
    """Base error carrying only safe provider diagnostics."""

    category = "internal_adapter_error"

    def __init__(
        self,
        message: str,
        *,
        category: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category or type(self).category
        self.status = status


class ProviderConfigurationError(TextProviderError):
    """The selected provider cannot be configured from the environment."""

    category = "credential_missing"


class ProviderTimeoutError(TextProviderError):
    """The provider did not respond before the configured timeout."""

    category = "provider_timeout"


class ProviderUnavailableError(TextProviderError):
    """The provider rejected or could not complete the request."""

    category = "network_error"


class ProviderMalformedResponseError(TextProviderError):
    """The provider response did not contain usable generated text."""

    category = "provider_invalid_json"


@dataclass(frozen=True)
class TextMessage:
    role: str
    content: str


@dataclass(frozen=True)
class TextGenerationRequest:
    messages: tuple[TextMessage, ...]
    response_format: str = "json_object"
    max_tokens: int = 6000
    temperature: float = 0.4
    timeout_seconds: float = 35.0


class TextProvider(Protocol):
    def generate(self, generation_request: TextGenerationRequest) -> str:
        """Return generated text without exposing provider-specific metadata."""


@dataclass(frozen=True)
class DeepSeekTextProvider:
    """Replaceable DeepSeek adapter using the current Chat Completions API."""

    api_key: str
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ProviderConfigurationError("provider credential is required")
        if not self.model.strip():
            raise ProviderConfigurationError("text model is required")
        if self.base_url.rstrip("/") != "https://api.deepseek.com":
            raise ProviderConfigurationError("unsupported provider endpoint")

    def generate(self, generation_request: TextGenerationRequest) -> str:
        if generation_request.response_format != "json_object":
            raise ProviderConfigurationError("unsupported response format")

        payload = {
            "model": self.model,
            "messages": [
                {"role": item.role, "content": item.content}
                for item in generation_request.messages
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": generation_request.max_tokens,
            "temperature": generation_request.temperature,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        provider_request = request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with request.urlopen(
                provider_request,
                timeout=generation_request.timeout_seconds,
            ) as response:
                raw_body = response.read(2_000_001)
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderTimeoutError("provider timeout") from exc
        except error.HTTPError as exc:
            raise ProviderUnavailableError(
                "provider request failed",
                category="provider_http_error",
                status=exc.code,
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderTimeoutError("provider timeout") from exc
            raise ProviderUnavailableError(
                "provider unavailable",
                category="network_error",
            ) from exc

        if len(raw_body) > 2_000_000:
            raise ProviderMalformedResponseError(
                "provider response exceeded limit",
                category="provider_invalid_json",
            )
        try:
            response_payload = json.loads(raw_body.decode("utf-8"))
            choice = response_payload["choices"][0]
            content = choice["message"]["content"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ProviderMalformedResponseError(
                "provider response was malformed",
                category="provider_invalid_json",
            ) from exc
        if choice.get("finish_reason") == "length":
            raise ProviderMalformedResponseError(
                "provider response was truncated",
                category="provider_invalid_json",
            )
        if not isinstance(content, str) or not content.strip():
            raise ProviderMalformedResponseError(
                "provider response was empty",
                category="provider_empty_content",
            )
        return content.strip()


class FakeTextProvider:
    """Deterministic provider for tests and local browser evidence only."""

    def __init__(self, outcomes: Sequence[str | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[TextGenerationRequest] = []

    def generate(self, generation_request: TextGenerationRequest) -> str:
        self.requests.append(generation_request)
        if not self._outcomes:
            raise ProviderUnavailableError("fake provider exhausted")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def create_text_provider_from_environment(
    environ: Mapping[str, str] | None = None,
) -> TextProvider:
    """Build the configured adapter without exposing secrets to the caller."""

    values = os.environ if environ is None else environ
    provider_name = values.get("TEXT_PROVIDER", "deepseek").strip().lower()
    model = values.get("TEXT_MODEL", "deepseek-v4-pro").strip()
    api_key = values.get("PROVIDER_API_KEY", "").strip()
    if provider_name != "deepseek":
        raise ProviderConfigurationError("unsupported text provider")
    if not api_key:
        raise ProviderConfigurationError("provider credential is required")
    return DeepSeekTextProvider(api_key=api_key, model=model)
