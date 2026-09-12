"""TEST_ONLY fixture-owned sockets. No connection to an existing service.

Synthetic protocol data is not SH09 workflow or runtime evidence. The fixture
binds port zero, retains listener ownership, and reports every observed request.
"""
from __future__ import annotations

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from services.v4_platform.backend_registry import digest
from services.v4_platform.comfyui_staged_transport import _bind_staged_transport
from services.v4_platform.generation_dispatch_live_contracts import make_live_transport_request
from tests.support.generation_dispatch_fixtures import make_package

PROMPT_ID = "12345678-1234-1234-1234-123456789abc"
SYNTHETIC_MP4_BYTES = b"synthetic-protocol-payload-not-media-verification"


def authorize_test_exchange(transport, exchange):
    """Protocol-only test double, not a real V5 Capability or runtime grant."""
    phases = iter(("CONNECT", "WRITE"))
    def test_authority(phase):
        if (transport._binding.host != "127.0.0.1" or transport._binding.port == 8188
                or exchange.request["workspaceRef"] != "test-workspace" or phase != next(phases, None)):
            raise ValueError("non-test target in synthetic authorization")
    transport._authorize_exchange(exchange, test_authority)
    return exchange


class LoopbackComfyUI:
    TEST_ONLY = True

    def __init__(self, *, status=200, receipt_raw=None, response_delay=0.0,
                 truncate=False, pending_reads=0, history_mutation=None, frames=None,
                 redirect_url=None, content_length=None, block_response=False, drip_headers=False,
                 scenario=None, header_line_bytes=0, header_count=0):
        self.status, self.receipt_raw, self.response_delay = status, receipt_raw, response_delay
        self.truncate, self.pending_reads, self.history_mutation = truncate, pending_reads, history_mutation
        self.frames = tuple(frames) if frames is not None else None
        self.redirect_url, self.content_length = redirect_url, content_length
        self.block_response, self.release_response = block_response, threading.Event()
        self.drip_headers, self.dripped_bytes = drip_headers, 0
        self.scenario = scenario
        self.header_line_bytes, self.header_count = header_line_bytes, header_count
        self.post_count = self.complete_post_count = self.history_count = self.view_count = 0
        self.body = None
        self.paths, self.responses = [], []
        self.lock, self.accepted = threading.Lock(), threading.Event()
        self.server = self.thread = None

    def __enter__(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def reply(self, status, data, media_type="application/json", *, truncate=False):
                with fixture.lock:
                    fixture.responses.append({"method": self.command, "path": self.path, "status": status})
                self.send_response(status)
                self.send_header("Content-Type", media_type)
                self.send_header("Content-Length", str(fixture.content_length if fixture.content_length is not None else len(data)))
                self.send_header("Connection", "close")
                if fixture.redirect_url:
                    self.send_header("Location", fixture.redirect_url)
                for index in range(fixture.header_count):
                    self.send_header("X-Test-Only-" + str(index), "a" * fixture.header_line_bytes)
                self.end_headers()
                try:
                    self.wfile.write(data[:max(1, len(data) // 2)] if truncate else data)
                    self.wfile.flush()
                except (ConnectionError, OSError):
                    pass
                self.close_connection = True

            def do_POST(self):
                with fixture.lock:
                    fixture.paths.append(("POST", self.path))
                    fixture.post_count += 1
                length = int(self.headers.get("Content-Length", 0))
                self.connection.settimeout(2)
                try:
                    raw = self.rfile.read(length)
                except OSError:
                    return
                if len(raw) != length:
                    return
                with fixture.lock:
                    fixture.complete_post_count += 1
                    fixture.body = json.loads(raw)
                fixture.accepted.set()
                if fixture.block_response:
                    fixture.release_response.wait(timeout=3)
                if fixture.response_delay:
                    time.sleep(fixture.response_delay)
                if fixture.drip_headers:
                    with fixture.lock:
                        fixture.responses.append({"method": "POST", "path": self.path, "status": 200,
                            "delivery": "DRIPPED_INCOMPLETE_HEADERS"})
                    try:
                        for byte in b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}":
                            self.connection.sendall(bytes([byte]))
                            fixture.dripped_bytes += 1
                            if fixture.release_response.wait(timeout=0.02):
                                break
                    except OSError:
                        pass
                    self.close_connection = True
                    return
                receipt = fixture.receipt_raw if fixture.receipt_raw is not None else json.dumps({
                    "prompt_id": PROMPT_ID, "number": 1, "node_errors": {}}).encode()
                self.reply(fixture.status, receipt, truncate=fixture.truncate)

            def do_GET(self):
                parsed = urlsplit(self.path)
                with fixture.lock:
                    fixture.paths.append(("GET", self.path))
                if parsed.path == "/history/" + PROMPT_ID:
                    with fixture.lock:
                        fixture.history_count += 1
                        count = fixture.history_count
                    if count <= fixture.pending_reads:
                        self.reply(200, b"{}")
                        return
                    native_count = len(fixture.frames) if fixture.frames is not None else 1
                    suffix = "png" if fixture.frames is not None else "mp4"
                    body = fixture.body
                    graph_prefix = body["prompt"]["16"]["inputs"]["filename_prefix"]
                    subfolder, _, filename_prefix = graph_prefix.rpartition("/")
                    descriptors = [{"filename": f"{filename_prefix}_{i:05d}_.{suffix}", "subfolder": subfolder, "type": "output"}
                                   for i in range(native_count)]
                    history = {PROMPT_ID: {"prompt": [1, PROMPT_ID, body["prompt"],
                        {**body["extra_data"], "client_id": body["client_id"], "create_time": 1}, ["16"]],
                        "outputs": {"16": {"images": descriptors}},
                        "status": {"status_str": "success", "completed": True, "messages": []}}}
                    if fixture.history_mutation:
                        fixture.history_mutation(history)
                    self.reply(200, json.dumps(history).encode())
                elif parsed.path == "/view":
                    with fixture.lock:
                        fixture.view_count += 1
                    query = parse_qs(parsed.query)
                    index = int(re.search(r"_([0-9]+)_\.(?:png|mp4)$", query["filename"][0]).group(1))
                    raw = fixture.frames[index] if fixture.frames is not None else SYNTHETIC_MP4_BYTES
                    self.reply(200, raw, "image/png" if fixture.frames is not None else "video/mp4")
                else:
                    self.reply(404, b"{}")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        # server_close joins all bounded handler threads, including slow peers.
        self.server.daemon_threads = False
        if self.server.server_port == 8188:
            self.server.server_close()
            raise RuntimeError("forbidden fixture port allocation")
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/"
        self.thread = threading.Thread(target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01}, name="test-only-comfyui-loopback", daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.release_response.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("fixture listener cleanup failed")
        evidence = {
            "schemaVersion": "v4.test-only-loopback-wire-evidence.v1",
            "classification": "TEST_ONLY_LOOPBACK_MOCK_NO_LIVE_COMFYUI_SUBMISSION",
            "host": "127.0.0.1", "port": self.server.server_port, "processId": os.getpid(),
            "fixtureRef": "test-loopback-" + uuid4().hex,
            "scenario": self.scenario or {"responseStatus": self.status,
                "pendingHistoryReads": self.pending_reads, "responseDelaySeconds": self.response_delay,
                "dripHeaders": self.drip_headers, "nativeFrames": len(self.frames) if self.frames is not None else 0,
                "headerLineBytes": self.header_line_bytes, "headerCount": self.header_count,
                "mutatedHistory": self.history_mutation is not None, "truncatedReceipt": self.truncate,
                "redirectResponse": self.redirect_url is not None},
            "postCount": self.post_count, "completePostCount": self.complete_post_count,
            "historyGetCount": self.history_count, "viewGetCount": self.view_count,
            "requests": [{"method": method, "path": path} for method, path in self.paths],
            "responses": self.responses, "listenerStopped": True,
            "listenerSocketClosed": self.server.fileno() == -1,
            # socketserver uses a non-iterable _NoThreads sentinel until the
            # first request; server_close has joined the real list otherwise.
            "requestThreadsStopped": (not isinstance(self.server._threads, list)
                or not any(t.is_alive() for t in self.server._threads)),
            "realComfyUIConnections": 0, "realPromptSubmissions": 0,
            "gpuExecutions": 0, "formalDatabaseAccesses": 0, "paidOperations": 0}
        location = os.environ.get("PKG3_TEST_EVIDENCE_DIR")
        if location:
            root = Path(location).resolve()
            root.mkdir(parents=True, exist_ok=True)
            (root / (evidence["fixtureRef"] + ".json")).write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("TRANSPORT_LOOPBACK_EVIDENCE=" + json.dumps(evidence, sort_keys=True), flush=True)


def make_loopback_client(endpoint, *, native_frames=False, request_timeout_ms=1000,
                         history_timeout_ms=1000, postprocess_timeout_ms=1000):
    package, _ = make_package()
    config = deepcopy(package["materials"]["executionConfig"])
    config.update(baseUrlDigest=digest(endpoint), requestTimeoutMs=request_timeout_ms,
        historyTimeoutMs=history_timeout_ms, postprocessTimeoutMs=postprocess_timeout_ms)
    backend = deepcopy(package["plan"]["executionBinding"]["backendDecision"])
    backend["endpointClass"] = "TEST_ONLY_LOOPBACK"
    runtime = deepcopy(package["plan"]["executionBinding"]["runtimeBinding"])
    transport = _bind_staged_transport(endpoint, execution_config=config,
        runtime_binding=runtime, backend_decision=backend)
    workflow = {"16": {"class_type": "SaveImage" if native_frames else "SaveVideo",
        "inputs": {"filename_prefix": "test_only/test_output"}}}
    request = make_live_transport_request(workspace_ref="test-workspace", production_run_ref="test-run",
        worker_ref="test-worker", generation_dispatch_grant_ref="test-grant",
        generation_dispatch_grant_digest=digest("test-grant"), media_job_ref="test-job", attempt_ref="test-attempt",
        generation_request_ref="test-request", generation_request_digest=digest("test-request"),
        execution_envelope_digest=digest("test-envelope"), workflow_digest=digest(workflow),
        output_constraints=package["plan"]["subject"]["outputConstraints"], workflow=workflow,
        connection_timeout_ms=config["connectionTimeoutMs"], request_timeout_ms=request_timeout_ms,
        history_timeout_ms=history_timeout_ms, postprocess_timeout_ms=postprocess_timeout_ms,
        transport_policy=config["transportPolicy"], endpoint_digest=digest(endpoint),
        execution_config_digest=digest(config), runtime_binding_digest=digest(runtime),
        backend_decision_digest=digest(backend), output_binding={"nodeId": "16", "outputKey": "images",
            "mediaType": "image/png" if native_frames else "video/mp4", "frameCount": 49 if native_frames else 1,
            "filenamePrefix": "test_output", "subfolder": "test_only"},
        postprocess_binding={"profileId": "ACS-SPIKE0-POST-49TO48-24FPS-R1", "keepIndices": list(range(48)),
            "dropIndices": [48], "frameRate": 24} if native_frames else None)
    return transport, request
