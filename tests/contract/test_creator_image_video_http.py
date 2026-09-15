"""CPU loopback HTTP contracts with a deliberately test-only application boundary.

These fixtures prove routing/authentication/framing, not live GPU generation.
"""

from email.message import Message
import http.client
import json
import secrets
import socket
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.parse import urlencode

from apps.creator_workspace_mvp.image_video_http import (
    MAX_IMAGE_VIDEO_REQUEST_BYTES,
    _read_command,
)
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.server import MAX_REQUEST_BYTES, create_server
from services.v5_core_os.episode_production.generation_workspace import (
    GenerationWorkspaceError,
)
from services.v5_core_os.episode_production.generation_dispatch_contracts import DispatchError


SCOPE = {
    "workspaceRef": "workspace-http-fixture",
    "projectRef": "project-http-fixture",
    "seriesRef": "series-http-fixture",
    "episodeRef": "episode-http-fixture",
    "productionRunRef": "run-http-fixture",
}
QUERY = {key: SCOPE[key] for key in ("projectRef", "seriesRef", "episodeRef")}
COMMAND = {
    "description": "窗前人物缓缓转头，镜头保持稳定。",
    "imageBase64": "dGVzdC1vbmx5LWltYWdl",
    "imageMediaType": "image/png",
    "idempotencyKey": "image-video-http-operation",
    "expectedPolicyDigest": "a" * 64,
}
CONTENT = b"test-only-video-contract-bytes"


class TestOnlyImageVideoBoundary:
    def __init__(self):
        self.calls = []
        self.failure = None

    def _record(self, operation, scope, credential_ref, *args):
        self.calls.append((operation, scope, credential_ref, *args))
        if self.failure is not None:
            raise self.failure
        if scope != SCOPE:
            raise GenerationWorkspaceError("generation_target_not_found", 404)
        if credential_ref != "credential-image-video-fixture":
            raise GenerationWorkspaceError("generation_operation_not_authorized", 403)

    def workspace(self, scope, credential_ref):
        self._record("workspace", scope, credential_ref)
        return {"state": "READY", "generations": [], "canCreate": True}

    def create(self, scope, credential_ref, command):
        self._record("create", scope, credential_ref, command)
        return {"generationRef": "generation-http-fixture", "state": "QUEUED"}

    def get(self, scope, credential_ref, generation_ref):
        self._record("get", scope, credential_ref, generation_ref)
        return {"generationRef": generation_ref, "state": "SUCCEEDED"}

    def content(self, scope, credential_ref, generation_ref, digest):
        self._record("content", scope, credential_ref, generation_ref, digest)
        return {"mediaType": "video/mp4", "content": CONTENT}


class CreatorImageVideoHttpContractTests(unittest.TestCase):
    def setUp(self):
        self.boundary = TestOnlyImageVideoBoundary()
        self.token = secrets.token_urlsafe(32)
        auth = PublicApiAuthenticator.for_token(
            self.token, SCOPE["workspaceRef"],
            credential_ref="credential-image-video-fixture",
        )
        self.server = create_server(
            ("127.0.0.1", 0), object(), public_authenticator=auth,
            allow_internal_routes=False, generation_only=True,
            image_video_boundary=self.boundary,
        )
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)
        self.base = (
            "/creator/api/v1/episode-production-runs/"
            "run-http-fixture/image-video-generations"
        )

    def call(self, *, method="GET", query=None, body=None, suffix="", auth=True,
             headers=None, path=None):
        request_headers = dict(headers or {})
        if auth:
            request_headers["Authorization"] = "Bearer " + self.token
        if body is not None:
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        target = (path or self.base) + suffix
        if query is not None:
            target += "?" + urlencode(query)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, target, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            value = raw if response.getheader("Content-Type") == "video/mp4" else json.loads(raw)
            return response.status, dict(response.getheaders()), value
        finally:
            connection.close()

    def raw_post(self, headers, body=b""):
        connection = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=5)
        try:
            lines = [f"POST {self.base} HTTP/1.0", "Host: 127.0.0.1",
                     "Authorization: Bearer " + self.token,
                     *(f"{key}: {value}" for key, value in headers)]
            connection.sendall("\r\n".join(lines).encode("ascii") + b"\r\n\r\n" + body)
            connection.shutdown(socket.SHUT_WR)
            response = http.client.HTTPResponse(connection)
            response.begin()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_collection_get_injects_authenticated_scope_and_has_no_create(self):
        status, _, result = self.call(query=QUERY)
        self.assertEqual(status, 200)
        self.assertEqual(result, {"ok": True, "workspace": {
            "state": "READY", "generations": [], "canCreate": True,
        }})
        self.assertEqual(self.boundary.calls, [
            ("workspace", SCOPE, "credential-image-video-fixture"),
        ])

    def test_create_forwards_only_closed_command_with_original_idempotency(self):
        status, _, result = self.call(method="POST", body={**QUERY, **COMMAND})
        self.assertEqual(status, 202)
        self.assertEqual(result, {"ok": True, "generation": {
            "generationRef": "generation-http-fixture", "state": "QUEUED",
        }})
        self.assertEqual(self.boundary.calls, [
            ("create", SCOPE, "credential-image-video-fixture", COMMAND),
        ])

    def test_get_generation_and_content_keep_authenticated_credential(self):
        status, _, result = self.call(query=QUERY, suffix="/generation-http-fixture")
        self.assertEqual(status, 200)
        self.assertEqual(result["generation"]["state"], "SUCCEEDED")
        status, headers, content = self.call(
            query={**QUERY, "sha256": "b" * 64}, suffix="/generation-http-fixture/content",
        )
        self.assertEqual((status, content), (200, CONTENT))
        self.assertEqual(headers["Cache-Control"], "private, no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Content-Length"], str(len(CONTENT)))
        self.assertEqual(self.boundary.calls, [
            ("get", SCOPE, "credential-image-video-fixture", "generation-http-fixture"),
            ("content", SCOPE, "credential-image-video-fixture", "generation-http-fixture", "b" * 64),
        ])

    def test_all_resources_require_authentication_before_boundary_access(self):
        for method, suffix, query, body in (
            ("GET", "", QUERY, None),
            ("POST", "", None, {**QUERY, **COMMAND}),
            ("GET", "/generation-http-fixture", QUERY, None),
            ("GET", "/generation-http-fixture/content", {**QUERY, "sha256": "b" * 64}, None),
        ):
            with self.subTest(method=method, suffix=suffix):
                status, _, result = self.call(method=method, suffix=suffix, query=query, body=body, auth=False)
                self.assertEqual(status, 401)
                self.assertEqual(result["error"]["code"], "authentication_required")
        self.assertEqual(self.boundary.calls, [])

    def test_host_missing_binding_is_503_not_demo(self):
        self.server.RequestHandlerClass.keywords["image_video_boundary"] = None
        status, _, result = self.call(query=QUERY)
        self.assertEqual(status, 503)
        self.assertEqual(result["error"]["code"], "image_video_unavailable")
        self.assertEqual(self.boundary.calls, [])

    def test_wrong_scope_is_not_found_and_does_not_rewrite_client_scope(self):
        status, _, result = self.call(query={**QUERY, "episodeRef": "other-episode"})
        self.assertEqual(status, 404)
        self.assertEqual(result["error"]["code"], "generation_target_not_found")

    def test_client_workspace_and_unknown_query_fields_are_rejected(self):
        for key in ("workspaceRef", "credentialRef", "imagePath", "grant"):
            with self.subTest(key=key):
                self.assertEqual(self.call(query={**QUERY, key: "forged"})[0], 400)
        self.assertEqual(self.boundary.calls, [])

    def test_duplicate_missing_and_blank_query_fields_are_rejected(self):
        for query in (
            [*QUERY.items(), ("episodeRef", "second")],
            {"projectRef": QUERY["projectRef"], "seriesRef": QUERY["seriesRef"]},
            {**QUERY, "episodeRef": ""},
        ):
            with self.subTest(query=query):
                self.assertEqual(self.call(query=query)[0], 400)
        self.assertEqual(self.boundary.calls, [])

    def test_unknown_upload_fields_and_client_file_urls_are_rejected(self):
        for key in ("workspaceRef", "credentialRef", "imagePath", "imageUrl", "grant", "permissions"):
            with self.subTest(key=key):
                self.assertEqual(self.call(method="POST", body={**QUERY, **COMMAND, key: "file:///etc/passwd"})[0], 400)
        self.assertEqual(self.boundary.calls, [])

    def test_duplicate_json_key_is_rejected_before_application_call(self):
        encoded = json.dumps({**QUERY, **COMMAND}).encode()
        duplicated = encoded[:-1] + b', "description": "duplicate"}'
        self.assertEqual(self.call(method="POST", body=duplicated)[0], 400)
        self.assertEqual(self.boundary.calls, [])

    def test_non_string_upload_fields_and_non_json_constants_are_rejected(self):
        for field in (*QUERY, *COMMAND):
            with self.subTest(field=field):
                self.assertEqual(self.call(method="POST", body={**QUERY, **COMMAND, field: []})[0], 400)
        self.assertEqual(self.call(method="POST", body=b'{"description":NaN}')[0], 400)
        self.assertEqual(self.boundary.calls, [])

    def test_missing_invalid_duplicate_and_short_content_lengths_are_safe(self):
        cases = [
            [], [("Content-Length", "-1")], [("Content-Length", "abc")],
            [("Content-Length", "0")], [("Content-Length", "999999999999999999999")],
            [("Content-Length", "2"), ("Content-Length", "2")],
            [("Content-Length", "5")],
        ]
        for headers in cases:
            with self.subTest(headers=headers):
                status, result = self.raw_post([*headers, ("Content-Type", "application/json")], b"{}")
                self.assertEqual(status, 400)
                self.assertEqual(result["error"]["code"], "invalid_request")
        self.assertEqual(self.boundary.calls, [])

    def test_oversize_body_is_rejected_without_reading_upload(self):
        status, result = self.raw_post([
            ("Content-Length", str(MAX_IMAGE_VIDEO_REQUEST_BYTES + 1)),
            ("Content-Type", "application/json"),
        ])
        self.assertEqual(status, 413)
        self.assertEqual(result["error"]["code"], "payload_too_large")
        self.assertEqual(self.boundary.calls, [])

    def test_non_json_charset_content_encoding_and_transfer_encoding_are_rejected(self):
        for content_type in ("text/plain", "multipart/form-data", "application/json; charset=latin-1"):
            with self.subTest(content_type=content_type):
                self.assertEqual(self.call(method="POST", body={**QUERY, **COMMAND}, headers={"Content-Type": content_type})[0], 415)
        self.assertEqual(self.call(method="POST", body={**QUERY, **COMMAND}, headers={"Content-Encoding": "gzip"})[0], 415)
        status, result = self.raw_post([
            ("Content-Length", "2"), ("Content-Type", "application/json"),
            ("Transfer-Encoding", "chunked"),
        ], b"{}")
        self.assertEqual((status, result["error"]["code"]), (400, "invalid_request"))
        self.assertEqual(self.boundary.calls, [])

    def test_post_query_and_resource_write_are_closed(self):
        self.assertEqual(self.call(method="POST", query=QUERY, body={**QUERY, **COMMAND})[0], 400)
        self.assertEqual(self.call(method="POST", suffix="/generation-http-fixture", body={**QUERY, **COMMAND})[0], 405)
        self.assertEqual(self.call(method="DELETE", query=QUERY)[0], 405)
        self.assertEqual(self.boundary.calls, [])

    def test_invalid_run_generation_and_digest_references_are_rejected(self):
        for path in (
            self.base.replace("run-http-fixture", ".."),
            self.base.replace("run-http-fixture", "run%2Fother"),
            self.base + "/..", self.base + "/generation%5Cother",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.call(query=QUERY, path=path)[0], 400)
        self.assertEqual(self.call(query={**QUERY, "sha256": "not-a-hash"}, suffix="/generation-http-fixture/content")[0], 400)
        self.assertEqual(self.call(query=QUERY, suffix="/generation-http-fixture/extra")[0], 404)
        self.assertEqual(self.boundary.calls, [])

    def test_registered_dispatch_errors_have_stable_public_status_not_generic_value_error(self):
        for code, expected_status, expected_code in (
            ("OUTSIDE_VALIDITY_WINDOW", 409, "generation_policy_expired"),
            ("SCOPE_MISMATCH", 404, "generation_target_not_found"),
            ("APPROVAL_UNAVAILABLE", 403, "generation_operation_not_authorized"),
            ("APPROVAL_PLAN_MISMATCH", 409, "generation_binding_changed"),
            ("IDEMPOTENCY_CONFLICT", 409, "idempotency_conflict"),
            ("CONFIG_CHANGED", 503, "image_video_unavailable"),
            ("RUNTIME_CHANGED", 503, "image_video_unavailable"),
            ("PERSISTENCE_UNAVAILABLE", 503, "image_video_unavailable"),
        ):
            with self.subTest(code=code):
                self.boundary.failure = DispatchError(code)
                status, _, result = self.call(method="POST", body={**QUERY, **COMMAND})
                self.assertEqual((status, result["error"]["code"]), (expected_status, expected_code))
                self.assertNotIn(code, json.dumps(result))

    def test_application_denial_conflict_and_unavailable_preserve_public_error(self):
        for code, expected_status in (
            ("generation_operation_not_authorized", 403),
            ("idempotency_conflict", 409),
            ("image_video_unavailable", 503),
        ):
            with self.subTest(code=code):
                self.boundary.failure = GenerationWorkspaceError(code, expected_status)
                status, _, result = self.call(method="POST", body={**QUERY, **COMMAND})
                self.assertEqual(status, expected_status)
                self.assertEqual(result["error"]["code"], code)
                self.assertTrue(any("\u4e00" <= character <= "\u9fff" for character in result["error"]["message"]))

    def test_unexpected_internal_failure_has_no_private_error_details(self):
        self.boundary.failure = RuntimeError("private provider credential /private/owner/path")
        status, _, result = self.call(method="POST", body={**QUERY, **COMMAND})
        self.assertEqual(status, 503)
        self.assertEqual(result["error"]["code"], "image_video_unavailable")
        self.assertNotIn("private", json.dumps(result))

    def test_generation_only_mode_retains_original_readonly_route_and_blocks_other_writes(self):
        original = self.base.replace("/image-video-generations", "/generation")
        self.assertEqual(self.call(query=QUERY, path=original)[0], 503)
        self.assertEqual(self.call(method="POST", path="/creator/api/v1/projects", body={})[0], 403)
        internal = self.base.replace("/creator/api/v1", "/creator/internal")
        self.assertEqual(self.call(method="POST", path=internal, body={**QUERY, **COMMAND})[0], 404)
        self.assertEqual(self.boundary.calls, [])

    def test_upload_limit_does_not_expand_ordinary_json_request_limit(self):
        self.assertEqual(MAX_REQUEST_BYTES, 512_000)
        self.server.RequestHandlerClass.keywords["generation_only"] = False
        status, _, _ = self.call(method="POST", path="/creator/api/v1/projects", body=b"{}",
            headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)})
        self.assertEqual(status, 400)
        self.assertEqual(self.boundary.calls, [])


class ImageVideoBodyReaderContractTests(unittest.TestCase):
    def test_timeout_restores_socket_deadline_and_never_creates_a_job(self):
        headers = Message()
        headers["Content-Length"] = "2"
        headers["Content-Type"] = "application/json"
        connection = Mock()
        connection.gettimeout.return_value = 7
        handler = SimpleNamespace(headers=headers, connection=connection, rfile=Mock())
        handler.rfile.read.side_effect = TimeoutError("fixture-only deadline")
        with self.assertRaises(GenerationWorkspaceError) as caught:
            _read_command(handler)
        self.assertEqual((caught.exception.code, caught.exception.status), ("request_timeout", 408))
        self.assertEqual(connection.settimeout.call_args_list[0].args, (7,))
        self.assertEqual(connection.settimeout.call_args_list[-1].args, (7,))


if __name__ == "__main__":
    unittest.main()
