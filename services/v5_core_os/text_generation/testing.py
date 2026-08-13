"""Test-only deterministic V5 Text Generation capability."""

from __future__ import annotations

from collections.abc import Sequence

from .contracts import TextGenerationCommand
from .errors import TextGenerationUnavailableError


class FakeTextGenerationCapability:
    """Record V5 commands and return deterministic outcomes for tests."""

    def __init__(self, outcomes: Sequence[str | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.commands: list[TextGenerationCommand] = []

    def generate(self, command: TextGenerationCommand) -> str:
        self.commands.append(command)
        if not self._outcomes:
            raise TextGenerationUnavailableError(category="fake_exhausted") from None
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
