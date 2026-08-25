import json
from pathlib import Path
import sqlite3
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
from services.v5_core_os.text_generation import TextGenerationTimeoutError
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v5_core_os.script_studio import (
    ScriptStudioPublicError,
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
        self.capability = FakeTextGenerationCapability(
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
            AiDirectorService(self.capability),
            series_episode_boundary=self.series_boundary,
            script_studio_service=ScriptStudioApplicationService(self.capability),
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
        self.assertEqual(len(self.capability.commands), 2)

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
        self.capability._outcomes = [
            json.dumps(invalid, ensure_ascii=False),
            json.dumps(script_candidate(), ensure_ascii=False),
        ]
        generated = self.generate()
        self.assertEqual(len(self.capability.commands), 2)
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
        self.capability._outcomes = [TextGenerationTimeoutError()]
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
        self.capability._outcomes = [json.dumps({"schemaVersion": SCENE_REWRITE_SCHEMA_VERSION})]
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

    def test_reviewed_import_provenance_and_unconfirmed_state_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "creator.sqlite3"
            series_boundary = create_local_series_boundary(database)
            series, episode = seed_episode(series_boundary)
            script_boundary = create_local_script_boundary(database, series_boundary)
            imported = script_boundary.create_version(
                {
                    "workspaceRef": WORKSPACE,
                    "seriesRef": series["seriesRef"],
                    "episodeRef": episode["episodeRef"],
                    "changeKind": "reviewed-import",
                    "uploadedSourceByteDigest": "a" * 64,
                    "normalizedSourceDocumentDigest": "b" * 64,
                    "reviewedDocumentDigest": "d" * 64,
                    "importedByRef": "creator-reviewer-credential",
                    "content": {
                        key: script_candidate()[key]
                        for key in (
                            "title",
                            "logline",
                            "synopsis",
                            "targetDurationSec",
                            "scenes",
                        )
                    },
                }
            )
            restarted_series = create_local_series_boundary(database)
            restarted_script = create_local_script_boundary(
                database, restarted_series
            )
            workspace = restarted_script.get_workspace(
                WORKSPACE, series["seriesRef"], episode["episodeRef"]
            )
            self.assertIsNone(workspace["script"]["confirmedScriptVersionRef"])
            provenance = workspace["versions"][0]["importProvenance"]
            self.assertEqual(provenance["uploadedSourceByteDigest"], "a" * 64)
            self.assertEqual(
                provenance["normalizedSourceDocumentDigest"], "b" * 64
            )
            self.assertEqual(provenance["reviewedDocumentDigest"], "d" * 64)
            self.assertEqual(
                provenance["importedByRef"], "creator-reviewer-credential"
            )
            self.assertEqual(
                provenance["digestAssertionState"],
                "AUTHENTICATED_SERVICE_CREDENTIAL_DECLARATION_UNVERIFIED",
            )
            self.assertEqual(
                provenance["reviewedDocumentToContentBindingState"],
                "NOT_VERIFIED",
            )
            self.assertRegex(
                provenance["canonicalScriptContentDigest"], r"^[0-9a-f]{64}$"
            )
            self.assertRegex(
                provenance["importProvenanceDigest"], r"^[0-9a-f]{64}$"
            )

    def test_reviewed_import_sqlite_provenance_tampering_fails_closed(self):
        def remove_provenance(content):
            content.pop("importProvenance")

        def alter_digest(content):
            content["importProvenance"]["uploadedSourceByteDigest"] = "f" * 64

        def invalidate_service_credential(content):
            content["importProvenance"]["importedByRef"] = "bad credential"

        def inject_workspace(content):
            content["workspaceRef"] = "forged-workspace"

        def inject_publication_authority(content):
            content["publicationAllowed"] = True

        def inject_canonical_authority(content):
            content["canonicalExecutableScriptRef"] = "forged-canonical-script"

        def inject_scene_authority(content):
            content["scenes"][0]["canonicalShotRef"] = "forged-canonical-shot"

        for label, tamper in (
            ("removed", remove_provenance),
            ("digest_changed", alter_digest),
            ("service_credential_invalid", invalidate_service_credential),
            ("workspace_scope", inject_workspace),
            ("publication_authority", inject_publication_authority),
            ("canonical_authority", inject_canonical_authority),
            ("scene_authority", inject_scene_authority),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                database = Path(directory) / "creator.sqlite3"
                series_boundary = create_local_series_boundary(database)
                series, episode = seed_episode(series_boundary)
                script_boundary = create_local_script_boundary(
                    database, series_boundary
                )
                imported = script_boundary.create_version(
                    {
                        "workspaceRef": WORKSPACE,
                        "seriesRef": series["seriesRef"],
                        "episodeRef": episode["episodeRef"],
                        "changeKind": "reviewed-import",
                        "uploadedSourceByteDigest": "a" * 64,
                        "normalizedSourceDocumentDigest": "b" * 64,
                        "reviewedDocumentDigest": "c" * 64,
                        "importedByRef": "creator-reviewer-credential",
                        "content": {
                            key: script_candidate()[key]
                            for key in (
                                "title",
                                "logline",
                                "synopsis",
                                "targetDurationSec",
                                "scenes",
                            )
                        },
                    }
                )
                with sqlite3.connect(database) as connection:
                    row = connection.execute(
                        "SELECT content_json FROM v5_script_versions "
                        "WHERE script_version_ref = ?",
                        (imported["scriptVersion"]["scriptVersionRef"],),
                    ).fetchone()
                    content = json.loads(row[0])
                    tamper(content)
                    connection.execute(
                        "UPDATE v5_script_versions SET content_json = ? "
                        "WHERE script_version_ref = ?",
                        (
                            json.dumps(
                                content,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            imported["scriptVersion"]["scriptVersionRef"],
                        ),
                    )
                restarted_series = create_local_series_boundary(database)
                restarted_script = create_local_script_boundary(
                    database, restarted_series
                )
                with self.assertRaises(ScriptStudioPublicError) as caught:
                    restarted_script.get_workspace(
                        WORKSPACE, series["seriesRef"], episode["episodeRef"]
                    )
                self.assertEqual(
                    (caught.exception.status, caught.exception.code),
                    (500, "application_error"),
                )

    def test_corrupt_sqlite_parent_blocks_derived_version_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "creator.sqlite3"
            series_boundary = create_local_series_boundary(database)
            series, episode = seed_episode(series_boundary)
            script_boundary = create_local_script_boundary(database, series_boundary)
            scope = {
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "episodeRef": episode["episodeRef"],
            }
            imported = script_boundary.create_version(
                {
                    **scope,
                    "changeKind": "reviewed-import",
                    "uploadedSourceByteDigest": "a" * 64,
                    "normalizedSourceDocumentDigest": "b" * 64,
                    "reviewedDocumentDigest": "c" * 64,
                    "importedByRef": "creator-reviewer-credential",
                    "content": {
                        key: script_candidate()[key]
                        for key in (
                            "title",
                            "logline",
                            "synopsis",
                            "targetDurationSec",
                            "scenes",
                        )
                    },
                }
            )
            script_ref = imported["script"]["scriptRef"]
            version_ref = imported["scriptVersion"]["scriptVersionRef"]
            derived_content = {
                key: imported["scriptVersion"][key]
                for key in (
                    "title",
                    "logline",
                    "synopsis",
                    "targetDurationSec",
                    "scenes",
                )
            }
            derived_content = json.loads(
                json.dumps(derived_content, ensure_ascii=False)
            )
            derived_content["title"] = "不得写入的 SQLite 派生版本"

            with sqlite3.connect(database) as connection:
                before_script = connection.execute(
                    "SELECT current_script_version_ref, version FROM v5_scripts "
                    "WHERE workspace_ref = ? AND script_ref = ?",
                    (WORKSPACE, script_ref),
                ).fetchone()
                before_count = connection.execute(
                    "SELECT COUNT(*) FROM v5_script_versions "
                    "WHERE workspace_ref = ? AND script_ref = ?",
                    (WORKSPACE, script_ref),
                ).fetchone()[0]
                row = connection.execute(
                    "SELECT content_json FROM v5_script_versions "
                    "WHERE workspace_ref = ? AND script_ref = ? "
                    "AND script_version_ref = ?",
                    (WORKSPACE, script_ref, version_ref),
                ).fetchone()
                poisoned = json.loads(row[0])
                poisoned["canonicalExecutableScriptRef"] = "forged-script"
                connection.execute(
                    "UPDATE v5_script_versions SET content_json = ? "
                    "WHERE workspace_ref = ? AND script_ref = ? "
                    "AND script_version_ref = ?",
                    (
                        json.dumps(
                            poisoned,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        WORKSPACE,
                        script_ref,
                        version_ref,
                    ),
                )

            with self.assertRaises(ScriptStudioPublicError) as caught:
                script_boundary.create_version(
                    {
                        **scope,
                        "scriptRef": script_ref,
                        "baseScriptVersionRef": version_ref,
                        "changeKind": "manual-edit",
                        "content": derived_content,
                    }
                )
            self.assertEqual(
                (caught.exception.status, caught.exception.code),
                (500, "application_error"),
            )
            with sqlite3.connect(database) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT current_script_version_ref, version FROM v5_scripts "
                        "WHERE workspace_ref = ? AND script_ref = ?",
                        (WORKSPACE, script_ref),
                    ).fetchone(),
                    before_script,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM v5_script_versions "
                        "WHERE workspace_ref = ? AND script_ref = ?",
                        (WORKSPACE, script_ref),
                    ).fetchone()[0],
                    before_count,
                )


if __name__ == "__main__":
    unittest.main()
