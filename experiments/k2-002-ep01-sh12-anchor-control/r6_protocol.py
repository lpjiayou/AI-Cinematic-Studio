#!/usr/bin/env python3
"""ComfyUI request lifecycle with UUID correlation and exact history binding."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import quote, urlsplit


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _pointer_token(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def json_pointer_diff(expected: Any, actual: Any, pointer: str = "") -> list[dict[str, Any]]:
    if type(expected) is not type(actual):
        return [{"pointer": pointer or "/", "kind": "type", "expected": type(expected).__name__, "actual": type(actual).__name__}]
    if isinstance(expected, Mapping):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(expected) | set(actual), key=str):
            child = f"{pointer}/{_pointer_token(key)}"
            if key not in expected:
                rows.append({"pointer": child, "kind": "unexpected", "actual": actual[key]})
            elif key not in actual:
                rows.append({"pointer": child, "kind": "missing", "expected": expected[key]})
            else:
                rows.extend(json_pointer_diff(expected[key], actual[key], child))
        return rows
    if isinstance(expected, list):
        rows = []
        for index in range(max(len(expected), len(actual))):
            child = f"{pointer}/{index}"
            if index >= len(expected):
                rows.append({"pointer": child, "kind": "unexpected", "actual": actual[index]})
            elif index >= len(actual):
                rows.append({"pointer": child, "kind": "missing", "expected": expected[index]})
            else:
                rows.extend(json_pointer_diff(expected[index], actual[index], child))
        return rows
    return [] if expected == actual else [{"pointer": pointer or "/", "kind": "value", "expected": expected, "actual": actual}]


class ProtocolError(RuntimeError):
    def __init__(self, code: str, message: str, details: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: Mapping[str, Any]


class Adapter(Protocol):
    async def connect_ws(self, client_id: str) -> Mapping[str, Any]: ...
    async def receive_ws(self, timeout_seconds: float) -> Mapping[str, Any] | None: ...
    async def request_json(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> HttpResult: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class AttemptIds:
    attempt_id: str
    prompt_id: str
    client_id: str
    correlation_id: str

    @classmethod
    def fresh(cls) -> "AttemptIds":
        values = [str(uuid.uuid4()) for _ in range(4)]
        if len(set(values)) != 4:
            raise ProtocolError("UUID_COLLISION", "UUIDv4 identifiers were not unique")
        return cls(*values)


@dataclass(frozen=True)
class BoundHistory:
    prompt_id: str
    submitted_workflow_sha256: str
    history_workflow_sha256: str
    history_entry_sha256: str
    output_records: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class LifecycleResult:
    ids: AttemptIds
    request: Mapping[str, Any]
    response: Mapping[str, Any]
    response_status: int
    history_pending_count: int
    websocket_events: tuple[Mapping[str, Any], ...]
    queue_snapshots: tuple[Mapping[str, Any], ...]
    history: BoundHistory
    prompt_post_count: int
    automatic_retry_count: int


def dry_run_report(api_prompt: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate/hash an API prompt without creating execute identifiers."""
    if not api_prompt:
        raise ProtocolError("EMPTY_API_PROMPT", "dry-run API prompt must not be empty")
    return {
        "mode": "DRY_RUN",
        "executeIdentifiersCreated": False,
        "promptPostCount": 0,
        "apiPromptCanonicalSha256": canonical_sha256(api_prompt),
    }


def compensation_gate(r5_consumed_lock: Path, complete_output_candidates: list[Path]) -> Mapping[str, Any]:
    """Read-only R6 gate: an existing non-empty R5 output blocks compensation."""
    if not r5_consumed_lock.is_file():
        raise ProtocolError("R5_LOCK_MISSING", "R5 consumed-attempt lock is missing")
    before = hashlib.sha256(r5_consumed_lock.read_bytes()).hexdigest()
    complete = [str(path) for path in complete_output_candidates if path.is_file() and path.stat().st_size > 0]
    after = hashlib.sha256(r5_consumed_lock.read_bytes()).hexdigest()
    if before != after:
        raise ProtocolError("R5_LOCK_MUTATED", "read-only gate changed the R5 consumed-attempt lock")
    return {
        "r5AttemptLockPreserved": True,
        "r5RunBudgetConsumed": True,
        "r5CompleteOutputs": complete,
        "r6CompensationAllowed": not complete,
        "r6MaxPromptPosts": 1,
    }


def _exclusive_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_json(path: Path, value: object) -> None:
    _exclusive_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n")


def _queue_prompt_ids(queue: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    result: list[set[str]] = []
    for key in ("queue_running", "queue_pending"):
        rows = queue.get(key)
        if not isinstance(rows, list):
            raise ProtocolError("QUEUE_SCHEMA_ERROR", f"{key} is not a list")
        values: set[str] = set()
        for row in rows:
            if isinstance(row, list) and len(row) > 1 and isinstance(row[1], str):
                values.add(row[1])
        result.append(values)
    return result[0], result[1]


def _collect_outputs(value: Any) -> tuple[Mapping[str, Any], ...]:
    found: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if {"filename", "subfolder", "type"}.issubset(value):
            found.append(dict(value))
        for child in value.values():
            found.extend(_collect_outputs(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_collect_outputs(child))
    return tuple(found)


def bind_history(
    history: Mapping[str, Any],
    ids: AttemptIds,
    experiment_id: str,
    submitted_api_prompt: Mapping[str, Any],
) -> BoundHistory:
    entry = history.get(ids.prompt_id)
    if not isinstance(entry, Mapping):
        raise ProtocolError("HISTORY_PENDING", "history entry is not available")
    queue_tuple = entry.get("prompt")
    if not isinstance(queue_tuple, list) or len(queue_tuple) < 4:
        raise ProtocolError("HISTORY_SCHEMA_PARSE_ERROR", "history prompt tuple must contain indexes 1, 2 and 3")
    history_prompt_id = queue_tuple[1]
    history_api_prompt = queue_tuple[2]
    history_extra_data = queue_tuple[3]
    if history_prompt_id != ids.prompt_id:
        raise ProtocolError("HISTORY_MISMATCH", "history prompt_id differs", {"pointer": "/prompt/1", "expected": ids.prompt_id, "actual": history_prompt_id})
    if not isinstance(history_api_prompt, Mapping):
        raise ProtocolError("HISTORY_SCHEMA_PARSE_ERROR", "history API prompt at index 2 is not an object")
    if not isinstance(history_extra_data, Mapping):
        raise ProtocolError("HISTORY_SCHEMA_PARSE_ERROR", "history extra_data at index 3 is not an object")
    expected_extra = {
        "client_id": ids.client_id,
        "k2_attempt_id": ids.attempt_id,
        "k2_correlation_id": ids.correlation_id,
        "k2_experiment_id": experiment_id,
    }
    extra_diff = [
        {"pointer": f"/prompt/3/{key}", "expected": value, "actual": history_extra_data.get(key)}
        for key, value in expected_extra.items()
        if history_extra_data.get(key) != value
    ]
    if extra_diff:
        raise ProtocolError("HISTORY_MISMATCH", "history correlation fields differ", extra_diff)
    workflow_diff = json_pointer_diff(submitted_api_prompt, history_api_prompt)
    if workflow_diff:
        raise ProtocolError("WORKFLOW_CANONICALIZATION_MISMATCH", "history API prompt differs from submitted API prompt", workflow_diff)
    return BoundHistory(
        prompt_id=ids.prompt_id,
        submitted_workflow_sha256=canonical_sha256(submitted_api_prompt),
        history_workflow_sha256=canonical_sha256(history_api_prompt),
        history_entry_sha256=canonical_sha256(entry),
        output_records=_collect_outputs(entry.get("outputs")),
    )


class ComfyLifecycle:
    def __init__(self, adapter: Adapter, *, timeout_seconds: float = 120.0, poll_seconds: float = 0.1, evidence_dir: Path | None = None) -> None:
        self.adapter = adapter
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self.evidence_dir = evidence_dir
        self.prompt_posts = 0

    async def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> HttpResult:
        if method == "POST" and path == "/prompt":
            if self.prompt_posts != 0:
                raise ProtocolError("POST_BUDGET_EXCEEDED", "a second POST /prompt is forbidden")
            self.prompt_posts += 1
        return await self.adapter.request_json(method, path, payload)

    async def cancel_targeted(self, prompt_id: str) -> Mapping[str, Any]:
        before = await self._request("GET", "/queue")
        running, pending = _queue_prompt_ids(before.body)
        if prompt_id not in running | pending:
            return {"promptId": prompt_id, "action": "ALREADY_ABSENT", "confirmedAbsent": True}
        response = await self._request("POST", f"/api/jobs/{quote(prompt_id, safe='')}/cancel", {})
        after = await self._request("GET", "/queue")
        running_after, pending_after = _queue_prompt_ids(after.body)
        if prompt_id in running_after | pending_after:
            raise ProtocolError("TARGETED_CANCEL_FAILED", "prompt_id remained in queue after targeted cancel")
        return {"promptId": prompt_id, "action": "TARGETED_JOB_CANCEL", "status": response.status, "confirmedAbsent": True}

    async def run(self, api_prompt: Mapping[str, Any], *, experiment_id: str, authority_state: str = "TECHNICAL_EVIDENCE_ONLY") -> LifecycleResult:
        ids = AttemptIds.fresh()
        extra_data = {
            "k2_experiment_id": experiment_id,
            "k2_attempt_id": ids.attempt_id,
            "k2_correlation_id": ids.correlation_id,
            "k2_workflow_canonical_sha256": canonical_sha256(api_prompt),
            "k2_authority_state": authority_state,
        }
        submitted_request = {
            "prompt": api_prompt,
            "prompt_id": ids.prompt_id,
            "client_id": ids.client_id,
            "extra_data": extra_data,
        }
        if self.evidence_dir is not None:
            _write_json(self.evidence_dir / "SUBMITTED_REQUEST.json", submitted_request)
            _exclusive_write(self.evidence_dir / "SUBMITTED_API_PROMPT.json", canonical_bytes(api_prompt))
            _exclusive_write(self.evidence_dir / "SUBMITTED_API_PROMPT_CANONICAL.sha256", (canonical_sha256(api_prompt) + "\n").encode("ascii"))

        events: list[Mapping[str, Any]] = []
        queues: list[Mapping[str, Any]] = []
        initial = await self.adapter.connect_ws(ids.client_id)
        if initial.get("type") != "status" or not isinstance(initial.get("data"), Mapping) or initial["data"].get("sid") != ids.client_id:
            raise ProtocolError("WEBSOCKET_SESSION_MISMATCH", "WebSocket initial sid does not match client_id", initial)

        post: HttpResult | None = None
        started = time.monotonic()
        pending_count = 0
        terminal = False
        history_value: Mapping[str, Any] | None = None
        try:
            post = await self._request("POST", "/prompt", submitted_request)
            if self.evidence_dir is not None:
                _write_json(self.evidence_dir / "POST_RESPONSE.json", {"httpStatus": post.status, "body": post.body})
            if post.status != 200:
                raise ProtocolError("PROMPT_REJECTED", "POST /prompt did not return HTTP 200", {"status": post.status, "body": post.body})
            if post.body.get("prompt_id") != ids.prompt_id:
                raise ProtocolError("PROMPT_ID_RESPONSE_MISMATCH", "response.prompt_id differs from submitted prompt_id", {"expected": ids.prompt_id, "actual": post.body.get("prompt_id")})
            node_errors = post.body.get("node_errors")
            if node_errors:
                raise ProtocolError("NODE_ERRORS", "POST /prompt returned blocking node_errors", node_errors)

            # Capture the accepted-but-not-yet-terminal state explicitly.  An
            # empty history response here is expected and must not be treated
            # as a binding failure.
            first_history = await self._request("GET", f"/history/{quote(ids.prompt_id, safe='')}")
            if first_history.body.get(ids.prompt_id):
                history_value = first_history.body
            else:
                pending_count += 1
            first_queue = await self._request("GET", "/queue")
            _queue_prompt_ids(first_queue.body)
            queues.append(first_queue.body)

            while not terminal:
                if time.monotonic() - started > self.timeout_seconds:
                    raise ProtocolError("TIMED_OUT", "prompt did not reach a matching terminal WebSocket event")
                event = await self.adapter.receive_ws(self.poll_seconds)
                if event is not None:
                    events.append(event)
                    event_type = event.get("type")
                    data = event.get("data")
                    if isinstance(data, Mapping) and data.get("prompt_id") == ids.prompt_id:
                        if event_type in {"execution_error", "execution_interrupted"}:
                            raise ProtocolError(event_type.upper(), "ComfyUI reported a matching terminal error", event)
                        if event_type == "executing" and data.get("node") is None:
                            terminal = True
                history_result = await self._request("GET", f"/history/{quote(ids.prompt_id, safe='')}")
                if not history_result.body.get(ids.prompt_id):
                    pending_count += 1
                else:
                    history_value = history_result.body
                queue_result = await self._request("GET", "/queue")
                _queue_prompt_ids(queue_result.body)
                queues.append(queue_result.body)

            history_deadline = time.monotonic() + min(10.0, self.timeout_seconds)
            while history_value is None or not history_value.get(ids.prompt_id):
                if time.monotonic() >= history_deadline:
                    raise ProtocolError("HISTORY_TIMEOUT", "terminal event arrived but history did not become available")
                await asyncio.sleep(self.poll_seconds)
                result = await self._request("GET", f"/history/{quote(ids.prompt_id, safe='')}")
                if result.body.get(ids.prompt_id):
                    history_value = result.body
                else:
                    pending_count += 1
            bound = bind_history(history_value, ids, experiment_id, api_prompt)
        except Exception:
            if post is not None and post.status == 200:
                try:
                    await self.cancel_targeted(ids.prompt_id)
                except Exception:
                    pass
            raise
        finally:
            if self.evidence_dir is not None:
                _exclusive_write(self.evidence_dir / "WEBSOCKET_EVENTS.jsonl", b"".join(canonical_bytes(row) + b"\n" for row in events))
                _write_json(self.evidence_dir / "QUEUE_SNAPSHOTS.json", queues)
                if history_value is not None:
                    _write_json(self.evidence_dir / "HISTORY.json", history_value)
            await self.adapter.close()
        if post is None:  # defensive; the successful path always assigns it
            raise ProtocolError("POST_RESPONSE_MISSING", "POST /prompt returned no response object")
        return LifecycleResult(ids, submitted_request, post.body, post.status, pending_count, tuple(events), tuple(queues), bound, self.prompt_posts, 0)


class AiohttpAdapter:
    """Live loopback adapter; aiohttp is imported lazily from the ComfyUI venv."""

    def __init__(self, base_url: str) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None or parsed.path not in {"", "/"}:
            raise ProtocolError("UNSAFE_ENDPOINT", "ComfyUI endpoint must be exact IPv4 loopback")
        try:
            import aiohttp  # type: ignore
        except ImportError as exc:
            raise ProtocolError("AIOHTTP_UNAVAILABLE", "run live protocol with the existing ComfyUI venv") from exc
        self.aiohttp = aiohttp
        self.base_url = base_url.rstrip("/")
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35), trust_env=False)
        self.ws = None

    async def connect_ws(self, client_id: str) -> Mapping[str, Any]:
        ws_url = self.base_url.replace("http://", "ws://", 1) + f"/ws?clientId={quote(client_id, safe='')}"
        self.ws = await self.session.ws_connect(ws_url, autoping=True, max_msg_size=16_000_000)
        message = await self.ws.receive(timeout=10)
        if message.type != self.aiohttp.WSMsgType.TEXT:
            raise ProtocolError("WEBSOCKET_INITIAL_MESSAGE", "initial WebSocket message was not JSON text")
        value = json.loads(message.data)
        if not isinstance(value, Mapping):
            raise ProtocolError("WEBSOCKET_INITIAL_MESSAGE", "initial WebSocket JSON was not an object")
        return value

    async def receive_ws(self, timeout_seconds: float) -> Mapping[str, Any] | None:
        if self.ws is None:
            raise ProtocolError("WEBSOCKET_NOT_CONNECTED", "WebSocket must connect before POST")
        try:
            message = await self.ws.receive(timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return None
        if message.type == self.aiohttp.WSMsgType.TEXT:
            value = json.loads(message.data)
            return value if isinstance(value, Mapping) else None
        if message.type in {self.aiohttp.WSMsgType.CLOSED, self.aiohttp.WSMsgType.ERROR}:
            raise ProtocolError("WEBSOCKET_CLOSED", "WebSocket closed before terminal event")
        return None

    async def request_json(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> HttpResult:
        async with self.session.request(method, self.base_url + path, json=payload, allow_redirects=False) as response:
            raw = await response.read()
            if len(raw) > 16_000_000:
                raise ProtocolError("RESPONSE_TOO_LARGE", "ComfyUI response exceeded 16 MB")
            value = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(value, Mapping):
                raise ProtocolError("RESPONSE_SCHEMA", "ComfyUI response was not an object")
            return HttpResult(response.status, value)

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
        await self.session.close()
