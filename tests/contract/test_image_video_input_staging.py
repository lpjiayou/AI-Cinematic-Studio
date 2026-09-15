"""Fixture-owned HTTP upload/readback contracts. Never a real GPU endpoint."""
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from tests.support.comfyui_loopback_fixtures import make_loopback_client
from tests.unit.test_image_video_materials import test_png


class InputStagingContractTests(unittest.TestCase):
    def setUp(self):
        self.paths, self.parts, self.authorized = [], {}, []
        self.mode = "ok"
        self.exists = False
        self.png = test_png()
        self.digest = sha256(self.png).hexdigest()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def send_body(self, status, value, media_type):
                self.send_response(status)
                self.send_header("Content-Type", media_type)
                self.send_header("Content-Length", str(len(value)))
                if status == 307:
                    self.send_header("Location", "/never-follow")
                self.end_headers()
                self.wfile.write(value)

            def do_POST(self):
                fixture.paths.append(("POST", self.path))
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                message = BytesParser(policy=policy.default).parsebytes(
                    ("Content-Type: " + self.headers["Content-Type"] + "\r\n\r\n").encode() + raw)
                for part in message.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    fixture.parts[name] = (part.get_filename(), part.get_payload(decode=True))
                receipt = {"name": fixture.digest + ".png", "subfolder": "acs-user-image-video", "type": "input"}
                if fixture.mode == "rename":
                    receipt["name"] = "server-renamed.png"
                if fixture.mode == "extra":
                    receipt["path"] = "/private/path"
                fixture.exists = True
                self.send_body(307 if fixture.mode == "redirect" else 503 if fixture.mode == "503" else 200,
                    json.dumps(receipt).encode(), "application/json")

            def do_GET(self):
                fixture.paths.append(("GET", self.path))
                if not fixture.exists:
                    self.send_body(404, b"missing", "text/plain")
                    return
                self.send_body(200, fixture.png[:-1] + b"x" if fixture.mode == "bad-readback" else fixture.png, "image/png")

            def log_message(self, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)
        self.transport, _ = make_loopback_client(f"http://127.0.0.1:{self.server.server_port}/")

    def upload(self):
        return self.transport.upload_input_png(self.png, self.digest,
            deadline_monotonic=time.monotonic() + 3, authorize=self.authorized.append)

    def test_fixed_multipart_target_overwrite_false_and_digest_verified_readback(self):
        result = self.upload()
        self.assertEqual(result, {"inputName": "acs-user-image-video/" + self.digest + ".png",
            "contentDigest": self.digest, "mediaType": "image/png", "byteSize": len(self.png)})
        self.assertEqual(set(self.parts), {"image", "type", "subfolder", "overwrite"})
        self.assertEqual(self.parts["image"], (self.digest + ".png", self.png))
        self.assertEqual(self.parts["overwrite"], (None, b"false"))
        self.assertEqual(self.paths[1], ("POST", "/upload/image"))
        readback = urlsplit(self.paths[2][1])
        self.assertEqual(readback.path, "/view")
        self.assertEqual(parse_qs(readback.query), {"filename": [self.digest + ".png"], "subfolder": ["acs-user-image-video"], "type": ["input"]})
        self.assertEqual(self.authorized, ["INPUT_LOOKUP", "INPUT_LOOKUP_READ", "INPUT_CONNECT",
            "INPUT_WRITE", "INPUT_VERIFY", "INPUT_VERIFIED"])
        self.assertFalse(any(path == "/prompt" for _, path in self.paths))

    def test_all_non_success_responses_fail_without_retry_redirect_or_prompt(self):
        for mode in ("redirect", "503"):
            with self.subTest(mode=mode):
                self.mode, self.paths, self.exists = mode, [], False
                with self.assertRaises(ValueError):
                    self.upload()
                self.assertEqual([method for method, _ in self.paths], ["GET", "POST"])
                self.assertEqual(self.paths[1], ("POST", "/upload/image"))

    def test_renamed_and_extra_field_receipt_reject_before_readback(self):
        for mode in ("rename", "extra"):
            with self.subTest(mode=mode):
                self.mode, self.paths, self.exists = mode, [], False
                with self.assertRaises(ValueError):
                    self.upload()
                self.assertEqual([method for method, _ in self.paths], ["GET", "POST"])
                self.assertEqual(self.paths[1], ("POST", "/upload/image"))

    def test_readback_byte_mismatch_is_terminal_no_retry(self):
        self.mode = "bad-readback"
        with self.assertRaises(ValueError):
            self.upload()
        self.assertEqual([method for method, _ in self.paths], ["GET", "POST", "GET"])
        self.assertNotIn("INPUT_VERIFIED", self.authorized)

    def test_authority_failure_digest_failure_invalid_png_and_deadline_have_zero_network(self):
        def deny(_phase):
            raise ValueError("policy denied")
        for data, digest, authorize, deadline in (
            (self.png, self.digest, deny, time.monotonic() + 3),
            (self.png, "0" * 64, self.authorized.append, time.monotonic() + 3),
            (b"invalid" * 10, sha256(b"invalid" * 10).hexdigest(), self.authorized.append, time.monotonic() + 3),
            (self.png, self.digest, self.authorized.append, time.monotonic() - 1),
        ):
            with self.assertRaises(ValueError):
                self.transport.upload_input_png(data, digest, deadline_monotonic=deadline, authorize=authorize)
        self.assertEqual(self.paths, [])

    def test_environment_proxy_cannot_change_trusted_upload_target(self):
        with patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:1/", "HTTPS_PROXY": "http://127.0.0.1:1/", "ALL_PROXY": "http://127.0.0.1:1/", "NO_PROXY": ""}):
            self.upload()
        self.assertEqual([method for method, _ in self.paths], ["GET", "POST", "GET"])

    def test_same_image_is_read_verified_and_reused_without_second_upload(self):
        first = self.upload()
        self.paths, self.authorized = [], []
        self.assertEqual(self.upload(), first)
        self.assertEqual([method for method, _ in self.paths], ["GET"])
        self.assertEqual(self.authorized, ["INPUT_LOOKUP", "INPUT_LOOKUP_READ", "INPUT_VERIFIED"])

    def test_existing_content_mismatch_is_rejected_without_overwrite_or_prompt(self):
        self.exists, self.mode = True, "bad-readback"
        with self.assertRaises(ValueError):
            self.upload()
        self.assertEqual([method for method, _ in self.paths], ["GET"])
        self.assertNotIn("INPUT_WRITE", self.authorized)


if __name__ == "__main__":
    unittest.main()
