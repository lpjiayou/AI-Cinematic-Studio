"""Deterministic fixed-byte WAV adapter for M12 contract tests only."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Mapping
import wave


def _fixed_wav_bytes() -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(48_000)
        writer.writeframes(b"\x00\x00" * 4_800)
    return output.getvalue()


FIXED_WAV_BYTES = _fixed_wav_bytes()


class FixedWavTtsAdapter:
    """Test-only substitute for the absent Piper runtime boundary."""

    adapter_identity = "v4.local-piper-tts.v1"
    provenance = "LOCAL_EVIDENCE"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, request: Mapping[str, Any], candidate_path: Path) -> Path:
        self.calls.append(dict(request))
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_bytes(FIXED_WAV_BYTES)
        return candidate_path
