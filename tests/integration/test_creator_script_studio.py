import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.script_studio import (
    SCENE_REWRITE_SCHEMA_VERSION,
    ScriptStudioApplicationService,
)
from apps.creator_workspace_mvp.server import (
    SCRIPT_CONFIRM_ENDPOINT,
    SCRIPT_GENERATE_ENDPOINT,
    SCRIPT_MANUAL_VERSION_ENDPOINT,
    SCRIPT_REWRITE_ENDPOINT,
    SCRIPT_WORKSPACE_ENDPOINT,
    STORYBOARD_BOOTSTRAP_ENDPOINT,
    create_server,
)
from services.v4_platform import FakeTextProvider, ProviderTimeoutError
from services.v5_core_os.script_studio import (
    create_in_memory_boundary as create_script_boundary,
    create_local_development_boundary as create_local_script_boundary,
)
from services.v5_core_os.series_episode import (
    create_in_memory_boundary as create_series_boundary,
    create_local_development_boundary as create_local_series_boundary,
)
from tests.unit.test_script_studio_m3 import Refs, WORKSPACE, script_candidate, seed_episode


class ScriptStudioHttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.refs = Refs()
        self.series_boundary = create_series_boundary(ref_factory=self.refs)
        self.series, self.episode = seed_episode(self.series_boundary)
        self.script_boundary = create_script_boundary(self.series_boundary, ref_factory=self.refs)
        rewrite_scene = dict(script_candidate()["scenes"][0])
        rewrite_scene["action"] = "晚灯收住动作，只留下一点暖光。"
        self.provider = FakeTextProvider(
            [
                json.dumps(script_candidate(), ensure_ascii=False),
                json.dumps(
                    {
                        "schemaVersion": SCENE_REWRITE_SCHEMA_VERSION,
                        "scene": rewrite_scene,
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(self.provider),
            series_episode_boundary=self.series_boundary,
            script_studio_service=ScriptStudioApplicationService(self.provider),
            script_studio_boundary=self.script_boundary,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.scope = {
            "workspaceRef": WORKSPACE,
            "seriesRef": self.series["seriesRef"],
            "episodeRef": self.episode["episodeRef"],
        }

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post(self, path, payload):
        return request.urlopen(
            request.Request(
                f"{self.base}{path}",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            ),
            timeout=5,
        )

    def get(self, path, **query):
        suffix = f"?{parse.urlencode(query)}" if query else ""
        return request.urlopen(f"{self.base}{path}{suffix}", timeout=5)

    @staticmethod
    def payload(response):
        return json.loads(response.read().decode("utf-8"))

    def generate(self):
        with self.post(SCRIPT_GENERATE_ENDPOINT, self.scope) as response:
            self.assertEqual(response.status, 201)
            return self.payload(response)

    def test_full_http_chain_generation_manual_edit_rewrite_confirmation_and_bridge(self):
        v1 = self.generate()
        self.assertEqual(v1["scriptVersion"]["versionNumber"], 1)
        self.assertIsNone(v1["script"]["confirmedScriptVersionRef"])
        v2_content = {
            key: v1["scriptVersion"][key]
            for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")
        }
        v2_content["synopsis"] = "人工编辑后的梗概。"
        with self.post(
            SCRIPT_MANUAL_VERSION_ENDPOINT,
            {
                **self.scope,
                "scriptRef": v1["script"]["scriptRef"],
                "baseScriptVersionRef": v1["scriptVersion"]["scriptVersionRef"],
                "content": v2_content,
            },
        ) as response:
            v2 = self.payload(response)
        self.assertEqual(v2["scriptVersion"]["versionNumber"], 2)
        with self.post(
            SCRIPT_REWRITE_ENDPOINT,
            {
                **self.scope,
                "scriptRef": v1["script"]["scriptRef"],
                "baseScriptVersionRef": v2["scriptVersion"]["scriptVersionRef"],
                "scriptSceneRef": v2["scriptVersion"]["scenes"][0]["scriptSceneRef"],
                "instruction": "让这场戏更克制",
            },
        ) as response:
            v3 = self.payload(response)
        self.assertEqual(v3["scriptVersion"]["versionNumber"], 3)
        self.assertEqual(v3["scriptVersion"]["scenes"][0]["action"], "晚灯收住动作，只留下一点暖光。")
        self.assertEqual(v3["scriptVersion"]["scenes"][1], v2["scriptVersion"]["scenes"][1])
        with self.post(
            SCRIPT_CONFIRM_ENDPOINT,
            {
                **self.scope,
                "scriptRef": v1["script"]["scriptRef"],
                "scriptVersionRef": v3["scriptVersion"]["scriptVersionRef"],
                "humanConfirmed": True,
            },
        ) as response:
            confirmed = self.payload(response)
        self.assertEqual(confirmed["script"]["confirmedScriptVersionRef"], v3["scriptVersion"]["scriptVersionRef"])
        with self.get(STORYBOARD_BOOTSTRAP_ENDPOINT, **self.scope) as response:
            bootstrap = self.payload(response)["bootstrap"]
        self.assertEqual(bootstrap["schemaVersion"], "creator.storyboard.bootstrap-input.v1")
        self.assertEqual(bootstrap["scriptVersionRef"], v3["scriptVersion"]["scriptVersionRef"])
        self.assertEqual(bootstrap["sourcePlanRef"], self.episode["sourcePlanRef"])
        self.assertEqual(len(self.provider.requests), 2)

    def test_workspace_http_projection_preserves_version_history(self):
        v1 = self.generate()
        with self.get(SCRIPT_WORKSPACE_ENDPOINT, **self.scope) as response:
            workspace = self.payload(response)["workspace"]
        self.assertEqual(workspace["script"]["scriptRef"], v1["script"]["scriptRef"])
        self.assertEqual(len(workspace["versions"]), 1)
        self.assertEqual(workspace["versions"][0]["sourcePlanRef"], self.episode["sourcePlanRef"])

    def test_http_generation_repairs_missing_schema_version_once_before_persisting(self):
        invalid = script_candidate()
        invalid.pop("schemaVersion")
        self.provider._outcomes = [
            json.dumps(invalid, ensure_ascii=False),
            json.dumps(script_candidate(), ensure_ascii=False),
        ]
        generated = self.generate()
        self.assertEqual(len(self.provider.requests), 2)
        self.assertEqual(generated["scriptVersion"]["schemaVersion"], "creator.script-studio.script-version.v1")
        self.assertTrue(
            all(item["scriptSceneRef"].startswith("script-scene-") for item in generated["scriptVersion"]["scenes"])
        )

    def test_storyboard_http_rejects_draft(self):
        self.generate()
        with self.assertRaises(error.HTTPError) as context:
            self.get(STORYBOARD_BOOTSTRAP_ENDPOINT, **self.scope)
        payload = self.payload(context.exception)
        self.assertEqual((context.exception.code, payload["error"]["code"]), (409, "script_not_confirmed"))

    def test_provider_failure_leaves_no_empty_script_version_and_hides_secret(self):
        self.provider._outcomes = [ProviderTimeoutError("secret-provider-body")]
        with self.post(SCRIPT_GENERATE_ENDPOINT, self.scope) as response:
            payload = self.payload(response)
        self.assertFalse(payload["ok"])
        self.assertNotIn("secret-provider-body", json.dumps(payload))
        with self.get(SCRIPT_WORKSPACE_ENDPOINT, **self.scope) as response:
            workspace = self.payload(response)["workspace"]
        self.assertIsNone(workspace["script"])
        self.assertEqual(workspace["versions"], [])

    def test_invalid_rewrite_leaves_version_history_unchanged(self):
        generated = self.generate()
        self.provider._outcomes = [json.dumps({"schemaVersion": SCENE_REWRITE_SCHEMA_VERSION})]
        with self.post(
            SCRIPT_REWRITE_ENDPOINT,
            {
                **self.scope,
                "scriptRef": generated["script"]["scriptRef"],
                "baseScriptVersionRef": generated["scriptVersion"]["scriptVersionRef"],
                "scriptSceneRef": generated["scriptVersion"]["scenes"][0]["scriptSceneRef"],
                "instruction": "缩短对白",
            },
        ) as response:
            payload = self.payload(response)
        self.assertFalse(payload["ok"])
        with self.get(SCRIPT_WORKSPACE_ENDPOINT, **self.scope) as response:
            workspace = self.payload(response)["workspace"]
        self.assertEqual(len(workspace["versions"]), 1)

    def test_script_endpoint_rejects_malformed_json_with_structured_error(self):
        invalid = request.Request(
            f"{self.base}{SCRIPT_GENERATE_ENDPOINT}",
            data=b"{broken",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(error.HTTPError) as context:
            request.urlopen(invalid, timeout=5)
        payload = self.payload(context.exception)
        self.assertEqual(context.exception.code, 400)
        self.assertEqual(payload["error"]["code"], "invalid_request")


class ScriptStudioDurableHttpIntegrationTests(unittest.TestCase):
    def test_restart_roundtrip_uses_same_v5_owned_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "creator.sqlite3"
            refs = Refs()
            series_boundary = create_local_series_boundary(database)
            series, episode = seed_episode(series_boundary)
            script_boundary = create_local_script_boundary(database, series_boundary)
            generated = script_boundary.create_version(
                {
                    "workspaceRef": WORKSPACE,
                    "seriesRef": series["seriesRef"],
                    "episodeRef": episode["episodeRef"],
                    "changeKind": "ai-generation",
                    "content": {key: script_candidate()[key] for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")},
                }
            )
            script_boundary.confirm_version(
                {
                    "workspaceRef": WORKSPACE,
                    "seriesRef": series["seriesRef"],
                    "episodeRef": episode["episodeRef"],
                    "scriptRef": generated["script"]["scriptRef"],
                    "scriptVersionRef": generated["scriptVersion"]["scriptVersionRef"],
                    "humanConfirmed": True,
                }
            )
            restarted_series = create_local_series_boundary(database)
            restarted_script = create_local_script_boundary(database, restarted_series)
            workspace = restarted_script.get_workspace(WORKSPACE, series["seriesRef"], episode["episodeRef"])
            self.assertEqual(workspace["script"]["confirmedScriptVersionRef"], generated["scriptVersion"]["scriptVersionRef"])


if __name__ == "__main__":
    unittest.main()
