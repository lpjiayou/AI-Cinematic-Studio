"""In-memory M6 fact repository, operation registry and ordered outbox."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .errors import IdempotencyConflictError


class InMemorySeriesIntelligenceRepository:
    def __init__(self, *, outbox_hook: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.bibles: dict[tuple[str, ...], dict[str, Any]] = {}
        self.bible_versions: dict[tuple[str, ...], dict[str, Any]] = {}
        self.characters: dict[tuple[str, ...], dict[str, Any]] = {}
        self.character_versions: dict[tuple[str, ...], dict[str, Any]] = {}
        self.snapshots: dict[tuple[str, ...], dict[str, Any]] = {}
        self.active_snapshots: dict[tuple[str, ...], str] = {}
        self.operations: dict[tuple[tuple[str, ...], str], tuple[str, Any]] = {}
        self.outbox: list[dict[str, Any]] = []
        self._outbox_hook = outbox_hook

    def capture(self) -> dict[str, Any]:
        return deepcopy({
            "bibles": self.bibles,
            "bible_versions": self.bible_versions,
            "characters": self.characters,
            "character_versions": self.character_versions,
            "snapshots": self.snapshots,
            "active_snapshots": self.active_snapshots,
            "operations": self.operations,
            "outbox": self.outbox,
        })

    def restore(self, snapshot: dict[str, Any]) -> None:
        for name, value in deepcopy(snapshot).items():
            setattr(self, name, value)

    def replay(self, scope_key: tuple[str, ...], key: str, payload_digest: str) -> Any | None:
        existing = self.operations.get((scope_key, key))
        if existing is None:
            return None
        if existing[0] != payload_digest:
            raise IdempotencyConflictError()
        return deepcopy(existing[1])

    def record_operation(
        self, scope_key: tuple[str, ...], key: str, payload_digest: str, result: Any
    ) -> Any:
        self.operations[(scope_key, key)] = (payload_digest, deepcopy(result))
        return deepcopy(result)

    def append_event(self, event: dict[str, Any]) -> None:
        self.outbox.append(deepcopy(event))
        if self._outbox_hook is not None:
            self._outbox_hook(deepcopy(event))

    def diagnostic(self) -> dict[str, int]:
        return {
            "bibleCount": len(self.bibles),
            "bibleVersionCount": len(self.bible_versions),
            "characterCount": len(self.characters),
            "characterVersionCount": len(self.character_versions),
            "snapshotCount": len(self.snapshots),
            "activeSnapshotCount": len(self.active_snapshots),
            "operationCount": len(self.operations),
            "outboxCount": len(self.outbox),
        }
