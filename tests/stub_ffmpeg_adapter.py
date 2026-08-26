"""Test-only media adapter backed by deterministic golden media bytes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from services.v4_platform.media_jobs import DeterministicLocalFfmpegAdapter


class StubFfmpegAdapter:
    """Write an exact golden artifact without spawning an FFmpeg process."""

    adapter_identity = DeterministicLocalFfmpegAdapter.adapter_identity
    provenance = DeterministicLocalFfmpegAdapter.provenance

    def __init__(
        self,
        source_root: Path,
        storage_key_by_request_digest: Mapping[str, str],
    ) -> None:
        self.source_root = source_root.resolve()
        self.storage_key_by_request_digest = dict(
            storage_key_by_request_digest
        )

    def generate(
        self, request: Mapping[str, Any], candidate_path: Path
    ) -> Path:
        request_digest = request.get("payloadDigest")
        storage_key = self.storage_key_by_request_digest.get(request_digest)
        if storage_key is None:
            raise RuntimeError("golden media request is unavailable")
        source = (self.source_root / storage_key).resolve()
        if self.source_root not in source.parents or not source.is_file():
            raise RuntimeError("golden media artifact is unavailable")
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_bytes(source.read_bytes())
        return candidate_path


__all__ = ["StubFfmpegAdapter"]
