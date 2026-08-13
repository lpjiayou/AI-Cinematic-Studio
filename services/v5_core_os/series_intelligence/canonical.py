"""canonical-json-v1 used by M6-owned content digests."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any, Mapping

from .errors import SeriesIntelligenceError


def normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise SeriesIntelligenceError("canonical-json-v1 forbids floating-point values")
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = unicodedata.normalize("NFC", str(raw_key))
            if key in result:
                raise SeriesIntelligenceError("duplicate key after Unicode normalization")
            result[key] = normalize(raw_value)
        return result
    raise SeriesIntelligenceError("value is not canonical JSON")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
