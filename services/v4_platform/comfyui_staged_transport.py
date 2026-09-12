"""Opt-in staged ComfyUI HTTP client, with no default runtime connection.

Protocol checked against ComfyUI commit
a7b1d39d342d102f305797fb5ba12dc304d9c1f5 (server.py / execution.py).
Only POST /prompt, GET /history/<exact UUID>, and GET /view are implemented.
HTTPConnection has no environment proxy, redirect or request retry machinery.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import http.client
import ipaddress
import json
import math
import os
import re
import threading
import time
import weakref
from typing import Any, Mapping
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from .generation_dispatch_transport import (_canonical, _exact, _ref, _sha, digest,
    CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED, REQUEST_BYTES_COMMITTED,
    RESPONSE_RECEIVED, SUBMISSION_OUTCOME_UNKNOWN)
from .generation_dispatch_live_contracts import (LIVE_REQUEST_SCHEMA,
    NOT_STARTED, ZERO_BYTES_PROVEN, MAY_HAVE_BEEN_SENT, LOCAL_WRITE_COMPLETE,
    LiveGenerationDispatchTransportError, LiveTransportReadResult,
    make_live_transport_submission, make_live_transport_result,
    validate_live_transport_request, validate_live_transport_submission,
    validate_prompt_id, _component, _subfolder)

_BINDING_KEY = object()
_MAX_JSON_BYTES = 2 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_SEQUENCE_BYTES = 128 * 1024 * 1024
_MAX_REQUEST_BYTES = 2 * 1024 * 1024
_MAX_HISTORY_READS = 2048
_READ_BLOCK = 64 * 1024
_POLICY = {"maxPromptSubmissions": 1, "postRetryAllowed": False,
           "redirectAllowed": False, "fallbackAllowed": False}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("bounded transport deadline expired")
    return remaining


def _json(raw: bytes) -> dict:
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = child
        return value
    def constant(_):
        raise ValueError("non-finite JSON number")
    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                       parse_constant=constant)
    if type(value) is not dict:
        raise ValueError("protocol body is not an object")
    _canonical(value)
    return value


class _DeadlineResponseReader:
    """Bound each status/header byte, not merely each blocking socket recv.

    BufferedReader.readline() can be kept alive indefinitely by a peer dripping
    bytes faster than the socket inactivity timeout. Parsing one buffered byte
    at a time here preserves the absolute deadline even in that case.
    """
    def __init__(self, stream, sock, deadline):
        self.stream, self.sock, self.deadline = stream, sock, deadline
        self.header_bytes = self.header_lines = 0

    def _timeout(self):
        self.sock.settimeout(_remaining(self.deadline))

    def readline(self, limit=-1):
        self.header_lines += 1
        if self.header_lines > 64:
            raise ValueError("response header count exceeded")
        maximum = min(limit if limit >= 0 else 8192, 8192)
        line = bytearray()
        while len(line) < maximum:
            self._timeout()
            byte = self.stream.read1(1)
            if not byte:
                return bytes(line)
            line.extend(byte)
            self.header_bytes += 1
            if self.header_bytes > 32768:
                raise ValueError("response header bytes exceeded")
            if byte == b"\n":
                return bytes(line)
        raise ValueError("response header line exceeded")

    def read1(self, size=-1):
        self._timeout()
        return self.stream.read1(size)

    def read(self, size=-1):
        # No unbounded response-body read is permitted by the client.
        if size < 0:
            raise ValueError("unbounded response read forbidden")
        self._timeout()
        return self.stream.read1(size)

    def flush(self):
        # HTTPResponse.close() flushes a still-attached response reader.
        self.stream.flush()

    def close(self):
        self.stream.close()


class _DeadlineHTTPResponse(http.client.HTTPResponse):
    def __init__(self, sock, *, deadline, **kwargs):
        super().__init__(sock, **kwargs)
        self._deadline_socket = sock
        self.fp = _DeadlineResponseReader(self.fp, sock, deadline)


class _TrustedStagedBinding:
    __slots__ = ("endpoint", "host", "port", "scheme", "pins", "timeouts", "_key")

    def __init__(self, key, *, endpoint, host, port, scheme, pins, timeouts):
        if key is not _BINDING_KEY:
            raise ValueError("staged binding requires trusted internal assembly")
        self._key = key
        self.endpoint, self.host, self.port, self.scheme = endpoint, host, port, scheme
        self.pins, self.timeouts = deepcopy(pins), deepcopy(timeouts)


def _bind_staged_transport(endpoint_url: str, *, execution_config: Mapping[str, Any],
        runtime_binding: Mapping[str, Any], backend_decision: Mapping[str, Any]) -> "ComfyUIStagedTransport":
    """Internal assembly only, after the existing trusted readers validate originals.

    Pins are checked again against the request re-read inside L2. This constructor
    is not an approval resolver, a public endpoint selector or a config writer.
    Literal addresses avoid unbounded DNS in the initial write window.
    """
    if type(endpoint_url) is not str:
        raise ValueError("missing trusted endpoint")
    parsed = urlsplit(endpoint_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path != "/"
            or parsed.port is None or not 1 <= parsed.port <= 65535):
        raise ValueError("endpoint is not canonical")
    ip = ipaddress.ip_address(parsed.hostname)
    host = str(ip)
    canonical = f"{parsed.scheme}://{'[' + host + ']' if ip.version == 6 else host}:{parsed.port}/"
    if endpoint_url != canonical:
        raise ValueError("endpoint is not canonical")
    config, runtime, backend = deepcopy(dict(execution_config)), deepcopy(dict(runtime_binding)), deepcopy(dict(backend_decision))
    if (config.get("schemaVersion") != "v5.generation-dispatch-execution-config.v1"
            or config.get("baseUrlDigest") != digest(endpoint_url)
            or _canonical(config.get("transportPolicy")) != _canonical(_POLICY)
            or config.get("coordinationMode") != "SINGLE_HOST_SINGLE_CONTROL_PROCESS"):
        raise ValueError("approved execution configuration binding mismatch")
    _exact(runtime, {"instanceRef", "processIdentityDigest", "attestationFileSha256"})
    _ref(runtime["instanceRef"]); _sha(runtime["processIdentityDigest"]); _sha(runtime["attestationFileSha256"])
    from .backend_registry import validate_decision
    backend = validate_decision(backend)
    if config.get("backendRef") != backend["backendRef"]:
        raise ValueError("approved backend binding mismatch")
    if backend["endpointClass"] == "TEST_ONLY_LOOPBACK":
        if host != "127.0.0.1" or parsed.scheme != "http" or parsed.port == 8188:
            raise ValueError("test endpoint is not an isolated loopback target")
    timeouts = {n: config.get(n) for n in ("connectionTimeoutMs", "requestTimeoutMs", "historyTimeoutMs", "postprocessTimeoutMs")}
    if any(type(v) is not int or v < 1 for v in timeouts.values()) or timeouts["connectionTimeoutMs"] > timeouts["requestTimeoutMs"]:
        raise ValueError("approved timeout binding mismatch")
    pins = {"endpointDigest": digest(endpoint_url), "executionConfigDigest": digest(config),
        "runtimeBindingDigest": digest(runtime), "backendDecisionDigest": digest(backend)}
    binding = _TrustedStagedBinding(_BINDING_KEY, endpoint=endpoint_url, host=host,
        port=parsed.port, scheme=parsed.scheme, pins=pins, timeouts=timeouts)
    return ComfyUIStagedTransport(binding)


class _Exchange:
    __slots__ = ("owner", "request", "body", "correlation", "pid", "thread_id", "lock",
        "spent", "read_started", "connection", "submission", "write_state", "provider_prompt_id",
        "deadline", "request_deadline", "response_deadline", "history_deadline", "postprocess_deadline", "send_authority", "__weakref__")

    def __init__(self, owner, request, body, correlation, deadline, send_deadline=None):
        self.owner, self.request, self.body, self.correlation = owner, request, body, correlation
        self.pid, self.thread_id = os.getpid(), threading.get_ident()
        self.lock = threading.Lock()
        self.spent, self.read_started = False, False
        self.connection, self.submission, self.provider_prompt_id = None, None, None
        self.write_state = NOT_STARTED
        self.send_authority = None
        started = time.monotonic()
        self.deadline = deadline
        self.response_deadline = min(deadline, started + request["requestTimeoutMs"] / 1000)
        self.request_deadline = min(self.response_deadline,
            self.response_deadline if send_deadline is None else send_deadline)
        self.history_deadline = min(deadline, self.response_deadline + request["historyTimeoutMs"] / 1000)
        self.postprocess_deadline = min(deadline, self.history_deadline + request["postprocessTimeoutMs"] / 1000)

    def __copy__(self):
        raise TypeError("staged exchanges cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("staged exchanges cannot be copied")

    def __reduce__(self):
        raise TypeError("staged exchanges cannot be serialized")


class ComfyUIStagedTransport:
    """Explicit internal live implementation; construction and open are inert."""
    __slots__ = ("_binding", "_pid", "_exchanges")

    def __init__(self, binding: _TrustedStagedBinding):
        if type(binding) is not _TrustedStagedBinding or binding._key is not _BINDING_KEY:
            raise ValueError("staged transport is disabled without trusted internal binding")
        self._binding, self._pid = binding, os.getpid()
        self._exchanges = weakref.WeakSet()

    def open_exchange(self, request: Mapping[str, Any], *, deadline_monotonic: float,
                      send_deadline_monotonic: float | None = None) -> _Exchange:
        request = validate_live_transport_request(request)
        if (type(deadline_monotonic) not in {int, float} or not math.isfinite(deadline_monotonic)
                or os.getpid() != self._pid or any(request[n] != v for n, v in self._binding.pins.items())
                or any(request[n] != v for n, v in self._binding.timeouts.items())):
            raise ValueError("live request trusted binding mismatch")
        _remaining(deadline_monotonic)
        if send_deadline_monotonic is not None:
            if type(send_deadline_monotonic) not in {int, float} or not math.isfinite(send_deadline_monotonic):
                raise ValueError("invalid in-process send deadline")
            _remaining(send_deadline_monotonic)
        correlation = {"requestDigest": request["payloadDigest"],
            "generationDispatchGrantRef": request["generationDispatchGrantRef"],
            "generationDispatchGrantDigest": request["generationDispatchGrantDigest"],
            "mediaJobRef": request["mediaJobRef"], "attemptRef": request["attemptRef"]}
        body = _canonical({"prompt": request["workflow"],
            "client_id": "acs-" + request["payloadDigest"],
            "extra_data": {"acs_dispatch": correlation}})
        if len(body) > _MAX_REQUEST_BYTES or digest(_json(body)["prompt"]) != request["workflowDigest"]:
            raise ValueError("encoded workflow mismatch or body too large")
        from .generation_dispatch_a14b_exact import EXACT_REQUEST_SCHEMA
        if request["schemaVersion"] == EXACT_REQUEST_SCHEMA:
            from .generation_dispatch_live_result import encoder_tool_identity
            # Local material verification precedes the network request budget.
            # The original absolute execution/send deadlines are NOT restarted.
            if encoder_tool_identity() != request["postprocessBinding"]["toolIdentity"]:
                raise ValueError("encoding tool changed before initial request")
            _remaining(deadline_monotonic)
            if send_deadline_monotonic is not None:
                _remaining(send_deadline_monotonic)
        exchange = _Exchange(self, request, body, correlation, deadline_monotonic, send_deadline_monotonic)
        self._exchanges.add(exchange)
        return exchange

    def _check(self, exchange: _Exchange) -> None:
        if (type(exchange) is not _Exchange or exchange.owner is not self
                or exchange not in self._exchanges
                or exchange.pid != os.getpid() or self._pid != os.getpid()
                or exchange.thread_id != threading.get_ident()):
            raise ValueError("foreign or reconstructed staged exchange")

    def _authorize_exchange(self, exchange: _Exchange, validator) -> None:
        """V5-owned, process-local spent Capability/gate validation callback.

        The callback is supplied by trusted composition, never a request field.
        It must verify the original continuation and the currently-held L2 lease.
        """
        self._check(exchange)
        with exchange.lock:
            if exchange.spent or exchange.send_authority is not None or not callable(validator):
                raise ValueError("staged exchange cannot be authorized")
            exchange.send_authority = validator

    def _connection(self, deadline: float, connection_timeout_ms: int):
        timeout = min(_remaining(deadline), connection_timeout_ms / 1000)
        cls = http.client.HTTPSConnection if self._binding.scheme == "https" else http.client.HTTPConnection
        connection = cls(self._binding.host, self._binding.port, timeout=timeout)
        # An absent socket must fail, never silently reconnect through send().
        connection.auto_open = 0
        return connection

    @staticmethod
    def _timeout(connection, deadline):
        remaining = _remaining(deadline)
        if connection.sock is None:
            raise ConnectionError("connection disappeared")
        connection.sock.settimeout(remaining)

    def commit_request_once(self, exchange: _Exchange) -> dict:
        self._check(exchange)
        with exchange.lock:
            if exchange.spent:
                raise ValueError("staged exchange has already been spent")
            # Never restore this flag, including on connection failures.
            exchange.spent = True
        try:
            if exchange.send_authority is None:
                raise ValueError("missing original send capability")
            authority, exchange.send_authority = exchange.send_authority, None
            authority("CONNECT")
            request = validate_live_transport_request(exchange.request)
            expected_body = _canonical({"prompt": request["workflow"],
                "client_id": "acs-" + request["payloadDigest"],
                "extra_data": {"acs_dispatch": exchange.correlation}})
            if (exchange.body != expected_body or any(request[n] != v for n, v in self._binding.pins.items())
                    or any(request[n] != v for n, v in self._binding.timeouts.items())):
                raise ValueError("staged exchange request changed before commit")
            _remaining(exchange.request_deadline)
            connection = self._connection(exchange.request_deadline, exchange.request["connectionTimeoutMs"])
            exchange.connection = connection
            connection.connect()
            self._timeout(connection, exchange.request_deadline)
            authority("WRITE")
            self._timeout(connection, exchange.request_deadline)
            connection.putrequest("POST", "/prompt", skip_accept_encoding=True)
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(exchange.body)))
            connection.putheader("Connection", "close")
            # First possible request bytes: mark conservatively BEFORE sendall.
            exchange.write_state = MAY_HAVE_BEEN_SENT
            connection.endheaders()
            self._timeout(connection, exchange.request_deadline)
            connection.send(exchange.body)
            exchange.write_state = LOCAL_WRITE_COMPLETE
            _remaining(exchange.request_deadline)
            exchange.submission = make_live_transport_submission(request=exchange.request,
                transport_submission_ref="local-submission-" + uuid4().hex, committed_at=_now())
            return deepcopy(exchange.submission)
        except Exception as exc:
            if exchange.connection is not None:
                exchange.connection.close()
            if exchange.write_state == NOT_STARTED:
                exchange.write_state = ZERO_BYTES_PROVEN
                raise LiveGenerationDispatchTransportError("LIVE_CONNECT_OR_DEADLINE_FAILED",
                    REQUEST_BYTES_NOT_COMMITTED, request_write_state=ZERO_BYTES_PROVEN) from None
            raise LiveGenerationDispatchTransportError("LIVE_SUBMISSION_OUTCOME_UNKNOWN",
                SUBMISSION_OUTCOME_UNKNOWN, request_write_state=exchange.write_state,
                submission=exchange.submission) from None

    def _read_body(self, connection, *, deadline: float, max_bytes: int,
                   expected_media_type: str) -> tuple[int, bytes]:
        self._timeout(connection, deadline)
        connection.response_class = lambda sock, **kwargs: _DeadlineHTTPResponse(
            sock, deadline=deadline, **kwargs)
        response = connection.getresponse()
        try:
            # 3xx, 429 and 5xx are terminal observations, never retry instructions.
            if response.status != 200:
                return response.status, b""
            lengths = response.headers.get_all("Content-Length", [])
            if (len(lengths) != 1 or re.fullmatch(r"[0-9]+", lengths[0]) is None
                    or response.headers.get("Transfer-Encoding") is not None
                    or response.headers.get("Content-Encoding", "identity") != "identity"
                    or response.headers.get_content_type() != expected_media_type):
                raise ValueError("unbounded or unsupported response framing")
            length = int(lengths[0])
            if length < 1 or length > max_bytes:
                raise ValueError("response body size exceeded")
            chunks, count = [], 0
            while count < length:
                # HTTPResponse owns the socket after Connection: close headers.
                _remaining(deadline)
                sock = connection.sock
                if sock is None:
                    sock = response._deadline_socket
                if sock is None:
                    raise ConnectionError("response socket unavailable")
                sock.settimeout(_remaining(deadline))
                chunk = response.read1(min(_READ_BLOCK, length - count))
                if not chunk:
                    raise ValueError("truncated response body")
                chunks.append(chunk); count += len(chunk)
            _remaining(deadline)
            return response.status, b"".join(chunks)
        finally:
            response.close()

    def _get(self, path: str, *, deadline: float, max_bytes: int, media_type: str) -> bytes:
        connection = self._connection(deadline, self._binding.timeouts["connectionTimeoutMs"])
        try:
            connection.connect()
            self._timeout(connection, deadline)
            connection.putrequest("GET", path, skip_accept_encoding=True)
            connection.putheader("Connection", "close")
            connection.endheaders()
            status, body = self._read_body(connection, deadline=deadline, max_bytes=max_bytes,
                                            expected_media_type=media_type)
            if status != 200:
                raise ValueError("non-success read-only response")
            return body
        finally:
            connection.close()

    def _history(self, exchange: _Exchange) -> dict:
        prompt_id = validate_prompt_id(exchange.provider_prompt_id)
        for _ in range(_MAX_HISTORY_READS):
            history = _json(self._get("/history/" + prompt_id, deadline=exchange.history_deadline,
                max_bytes=_MAX_JSON_BYTES, media_type="application/json"))
            if not history:
                time.sleep(min(0.05, _remaining(exchange.history_deadline)))
                continue
            _exact(history, {prompt_id})
            record = history[prompt_id]
            if type(record) is not dict or not {"prompt", "outputs", "status"} <= set(record) or set(record) - {"prompt", "outputs", "status", "meta"}:
                raise ValueError("invalid history record")
            prompt = record["prompt"]
            if (type(prompt) is not list or len(prompt) != 5 or prompt[1] != prompt_id
                    or type(prompt[0]) not in {int, float} or digest(prompt[2]) != exchange.request["workflowDigest"]
                    or type(prompt[3]) is not dict
                    or prompt[3].get("acs_dispatch") != exchange.correlation
                    or prompt[3].get("client_id") != "acs-" + exchange.request["payloadDigest"]
                    or prompt[4] != [exchange.request["outputBinding"]["nodeId"]]):
                raise ValueError("history request lineage mismatch")
            status = _exact(record["status"], {"status_str", "completed", "messages"})
            if type(status["completed"]) is not bool or type(status["messages"]) is not list:
                raise ValueError("invalid history status")
            if status["status_str"] == "error":
                raise ValueError("provider execution failed")
            if status["status_str"] != "success":
                raise ValueError("unknown history status")
            if not status["completed"]:
                time.sleep(min(0.05, _remaining(exchange.history_deadline)))
                continue
            return record
        raise TimeoutError("history read bound exhausted")

    def _artifacts(self, exchange: _Exchange, history: dict) -> tuple[list, tuple[bytes, ...]]:
        output = exchange.request["outputBinding"]
        outputs = _exact(history["outputs"], {output["nodeId"]})
        node = _exact(outputs[output["nodeId"]], {output["outputKey"]})
        descriptors = node[output["outputKey"]]
        if type(descriptors) is not list or len(descriptors) != output["frameCount"]:
            raise ValueError("native output count mismatch")
        native, blobs, total, seen, previous_counter = [], [], 0, set(), None
        for index, descriptor in enumerate(descriptors):
            _exact(descriptor, {"filename", "subfolder", "type"})
            _component(descriptor["filename"]); _subfolder(descriptor["subfolder"])
            extension = ".png" if output["mediaType"] == "image/png" else ".mp4"
            if (descriptor["type"] != "output" or descriptor["subfolder"] != output["subfolder"]
                    or not descriptor["filename"].startswith(output["filenamePrefix"] + "_")
                    or not descriptor["filename"].endswith(extension)
                    or descriptor["filename"] in seen):
                raise ValueError("native output locator mismatch")
            seen.add(descriptor["filename"])
            if output["mediaType"] == "image/png":
                match = re.fullmatch(re.escape(output["filenamePrefix"]) + r"_([0-9]{5,})_\.png", descriptor["filename"])
                if match is None:
                    raise ValueError("native frame filename does not match pinned SaveImage sequence")
                counter = int(match.group(1))
                if previous_counter is not None and counter != previous_counter + 1:
                    raise ValueError("native frame sequence is reordered or incomplete")
                previous_counter = counter
            data = self._get("/view?" + urlencode(descriptor), deadline=exchange.history_deadline,
                max_bytes=min(_MAX_ARTIFACT_BYTES, _MAX_SEQUENCE_BYTES - total), media_type=output["mediaType"])
            total += len(data)
            if output["mediaType"] == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("native output is not PNG")
            native.append({"index": index, "nodeId": output["nodeId"], **descriptor,
                "mediaType": output["mediaType"], "byteSize": len(data), "sha256": sha256(data).hexdigest()})
            blobs.append(data)
        return native, tuple(blobs)

    def read_result(self, exchange: _Exchange, submission: Mapping[str, Any]) -> LiveTransportReadResult:
        self._check(exchange)
        with exchange.lock:
            if exchange.read_started or not exchange.spent or exchange.submission is None:
                raise ValueError("staged result collection is unavailable")
            bound = validate_live_transport_submission(submission)
            if bound != exchange.submission:
                raise ValueError("foreign local submission")
            exchange.read_started = True
        try:
            status, body = self._read_body(exchange.connection, deadline=exchange.response_deadline,
                max_bytes=_MAX_JSON_BYTES, expected_media_type="application/json")
            exchange.connection.close()
            if status != 200:
                raise ValueError("unproven provider acceptance")
            receipt = _exact(_json(body), {"prompt_id", "number", "node_errors"})
            if type(receipt["number"]) not in {int, float} or receipt["node_errors"] != {}:
                raise ValueError("invalid provider acceptance receipt")
            exchange.provider_prompt_id = validate_prompt_id(receipt["prompt_id"])
            # Phase caps only shrink; the absolute L2-derived ceiling never moves.
            exchange.history_deadline = min(exchange.history_deadline,
                time.monotonic() + exchange.request["historyTimeoutMs"] / 1000)
            history = self._history(exchange)
            native, blobs = self._artifacts(exchange, history)
            derivation = None
            exchange.postprocess_deadline = min(exchange.postprocess_deadline,
                time.monotonic() + exchange.request["postprocessTimeoutMs"] / 1000)
            if exchange.request["outputBinding"]["mediaType"] == "image/png":
                from .generation_dispatch_live_result import process_native_frames
                final_bytes, derivation = process_native_frames(blobs, native, exchange.request,
                    deadline_monotonic=exchange.postprocess_deadline)
                frames = blobs
            else:
                final_bytes, frames = blobs[0], ()
            _remaining(exchange.postprocess_deadline)
            result = make_live_transport_result(request=exchange.request, submission=bound,
                outcome="SUCCEEDED", phase=RESPONSE_RECEIVED, request_write_state=LOCAL_WRITE_COMPLETE,
                provider_prompt_id=exchange.provider_prompt_id, artifact_digest=sha256(final_bytes).hexdigest(),
                failure_code=None, received_at=_now(), native_artifacts=native, derivation=derivation)
            return LiveTransportReadResult(request=exchange.request, submission=bound, receipt=result,
                artifact_bytes=final_bytes, native_frames=frames, deadline_monotonic=exchange.postprocess_deadline)
        except Exception:
            raise LiveGenerationDispatchTransportError("LIVE_RESULT_OUTCOME_UNKNOWN",
                SUBMISSION_OUTCOME_UNKNOWN, request_write_state=LOCAL_WRITE_COMPLETE,
                submission=bound, provider_prompt_id=exchange.provider_prompt_id) from None
        finally:
            if exchange.connection is not None:
                exchange.connection.close()


def is_trusted_staged_transport(value: Any) -> bool:
    return (type(value) is ComfyUIStagedTransport and type(value._binding) is _TrustedStagedBinding
            and value._binding._key is _BINDING_KEY and value._pid == os.getpid())
