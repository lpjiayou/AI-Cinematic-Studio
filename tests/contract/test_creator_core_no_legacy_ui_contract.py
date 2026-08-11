import json
from pathlib import Path
import threading
import unittest
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.server import SERIES_ENDPOINT, create_server
from services.v4_platform import FakeTextProvider


ROOT = Path(__file__).resolve().parents[2]
LEGACY_UI_ROOT = ROOT / "apps" / "creator-workspace-mvp"
SERVER_SOURCE = ROOT / "apps" / "creator_workspace_mvp" / "server.py"


class CreatorCoreNoLegacyUiContractTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextProvider([])),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def test_tracked_legacy_customer_ui_is_absent(self):
        self.assertFalse(LEGACY_UI_ROOT.exists())

    def test_core_server_has_no_static_customer_ui_mount(self):
        source = SERVER_SOURCE.read_text(encoding="utf-8")
        for forbidden in (
            "SimpleHTTPRequestHandler",
            "default_static_directory",
            "static_directory",
            "super().do_GET()",
            "directory=str(directory)",
        ):
            self.assertNotIn(forbidden, source)

    def test_customer_ui_paths_return_structured_json_not_found(self):
        for path in ("/", "/index.html", "/app.js", "/styles.css", "/assets/legacy.png"):
            with self.subTest(path=path):
                with self.assertRaises(error.HTTPError) as context:
                    request.urlopen(f"{self.base_url}{path}", timeout=5)
                body = json.loads(context.exception.read().decode("utf-8"))
                self.assertEqual(context.exception.code, 404)
                self.assertEqual(context.exception.headers.get_content_type(), "application/json")
                self.assertFalse(body["ok"])
                self.assertEqual(body["error"]["code"], "not_found")

    def test_public_creator_http_api_remains_available_without_ui_assets(self):
        with request.urlopen(
            f"{self.base_url}{SERIES_ENDPOINT}?workspaceRef=workspace-rb1-2-contract",
            timeout=5,
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["series"], [])


if __name__ == "__main__":
    unittest.main()
