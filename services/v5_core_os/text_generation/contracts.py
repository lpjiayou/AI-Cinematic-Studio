"""Application-facing contracts for the V5 Text Generation capability."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class TextGenerationPurpose(str, Enum):
    """Closed set of accepted V5 text-generation execution purposes."""

    AI_DIRECTOR_CANDIDATE = "ai-director-candidate"
    SCRIPT_CANDIDATE = "script-candidate"
    SCRIPT_SCENE_REWRITE = "script-scene-rewrite"
    SERIES_PLAN_CANDIDATE = "series-plan-candidate"


@dataclass(frozen=True)
class TextGenerationMessage:
    """Provider-neutral message owned by the V5 Application-facing boundary."""

    role: str
    content: str


@dataclass(frozen=True)
class TextGenerationCommand:
    """V5 intent that cannot override lower-layer execution policy."""

    purpose: TextGenerationPurpose
    messages: tuple[TextGenerationMessage, ...]


class TextGenerationCapability(Protocol):
    """Stable capability consumed by Creator Application services."""

    def generate(self, command: TextGenerationCommand) -> str:
        """Return unconfirmed candidate text for local Application validation."""
