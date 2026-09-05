"""Bounded, standards-compliant JSON handling for Creator public HTTP."""

from __future__ import annotations

import json
import math
from typing import Any


MAX_PUBLIC_JSON_DEPTH = 64
MAX_PUBLIC_JSON_NUMBER_TOKEN_CHARS = 128

PUBLIC_JSON_DECODE_ERRORS = (
    UnicodeDecodeError,
    json.JSONDecodeError,
    ValueError,
    OverflowError,
    RecursionError,
)

PUBLIC_JSON_ENCODE_ERRORS = (
    TypeError,
    ValueError,
    OverflowError,
    RecursionError,
)


def _validate_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False

    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_PUBLIC_JSON_DEPTH:
                raise ValueError("public JSON exceeds maximum depth")
        elif character in "]}":
            depth -= 1


def _parse_int(token: str) -> int:
    if len(token) > MAX_PUBLIC_JSON_NUMBER_TOKEN_CHARS:
        raise ValueError("public JSON integer token is too long")
    return int(token)


def _parse_float(token: str) -> float:
    if len(token) > MAX_PUBLIC_JSON_NUMBER_TOKEN_CHARS:
        raise ValueError("public JSON float token is too long")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("public JSON float must be finite")
    return value


def _reject_constant(_token: str) -> None:
    raise ValueError("public JSON constants must use the standard grammar")


def load_public_json(raw: bytes) -> Any:
    """Decode one bounded public request without recursive pre-validation."""

    text = raw.decode("utf-8")
    _validate_depth(text)
    return json.loads(
        text,
        parse_constant=_reject_constant,
        parse_int=_parse_int,
        parse_float=_parse_float,
    )


def dump_public_json(value: Any) -> bytes:
    """Serialize one public response using only standard JSON numbers."""

    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
