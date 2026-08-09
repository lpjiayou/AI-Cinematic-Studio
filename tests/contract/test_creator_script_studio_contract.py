import inspect
import unittest

from services.v5_core_os.script_studio import (
    ScriptStudioPublicBoundary,
    ScriptStudioPublicError,
    create_in_memory_boundary,
    create_local_development_boundary,
)
from services.v5_core_os.series_episode import create_in_memory_boundary as create_series_boundary
from tests.unit.test_script_studio_m3 import Refs, WORKSPACE, content_from_candidate, seed_episode


class CreatorScriptStudioContractTests(unittest.TestCase):
    def setUp(self):
        self.refs = Refs()
        self.upstream = create_series_boundary(ref_factory=self.refs)
        self.series, self.episode = seed_episode(self.upstream)
        self.boundary = create_in_memory_boundary(self.upstream, ref_factory=self.refs)
        self.scope = {
            "workspaceRef": WORKSPACE,
            "seriesRef": self.series["seriesRef"],
            "episodeRef": self.episode["episodeRef"],
        }

    def test_public_package_exports_only_stable_boundary_factories(self):
        import services.v5_core_os.script_studio as package

        self.assertEqual(
            package.__all__,
            [
                "ScriptStudioPublicBoundary",
                "ScriptStudioPublicError",
                "create_in_memory_boundary",
                "create_local_development_boundary",
                "create_local_development_boundary_from_environment",
            ],
        )
        self.assertTrue(inspect.isclass(ScriptStudioPublicBoundary))
        self.assertTrue(inspect.isclass(ScriptStudioPublicError))
        self.assertTrue(callable(create_local_development_boundary))

    def test_script_version_contract_contains_required_identity_content_and_lineage(self):
        created = self.boundary.create_version(
            {**self.scope, "changeKind": "ai-generation", "content": content_from_candidate()}
        )
        version = created["scriptVersion"]
        required = {
            "schemaVersion",
            "scriptRef",
            "scriptVersionRef",
            "seriesRef",
            "episodeRef",
            "sourcePlanRef",
            "sourcePlanSchemaVersion",
            "sourcePlanVersion",
            "versionNumber",
            "title",
            "logline",
            "synopsis",
            "targetDurationSec",
            "scenes",
        }
        self.assertTrue(required.issubset(version))
        self.assertEqual(version["schemaVersion"], "creator.script-studio.script-version.v1")
        scene_required = {
            "scriptSceneRef",
            "sceneNumber",
            "heading",
            "location",
            "timeOfDay",
            "characters",
            "action",
            "dialogue",
            "narration",
            "subtitleText",
            "estimatedDurationSec",
            "scenePurpose",
            "continuityNotes",
            "productionNotes",
        }
        self.assertEqual(set(version["scenes"][0]), scene_required)
        self.assertEqual(set(version["scenes"][0]["dialogue"][0]), {"speaker", "text", "emotion"})

    def test_storyboard_contract_is_gated_by_confirmed_version_and_keeps_m4_gate(self):
        created = self.boundary.create_version(
            {**self.scope, "changeKind": "ai-generation", "content": content_from_candidate()}
        )
        with self.assertRaises(ScriptStudioPublicError) as context:
            self.boundary.build_storyboard_bootstrap(
                WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]
            )
        self.assertEqual((context.exception.status, context.exception.code), (409, "script_not_confirmed"))
        self.boundary.confirm_version(
            {
                **self.scope,
                "scriptRef": created["script"]["scriptRef"],
                "scriptVersionRef": created["scriptVersion"]["scriptVersionRef"],
                "humanConfirmed": True,
            }
        )
        bootstrap = self.boundary.build_storyboard_bootstrap(
            WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]
        )
        self.assertEqual(bootstrap["schemaVersion"], "creator.storyboard.bootstrap-input.v1")
        self.assertEqual(bootstrap["nextGate"], "m4-ip-character-binding-required")
        self.assertFalse(bootstrap["storyboardProductionAuthorized"])

    def test_application_depends_only_on_public_script_studio_package(self):
        server_source = inspect.getsource(__import__("apps.creator_workspace_mvp.server", fromlist=["*"]))
        application_source = inspect.getsource(__import__("apps.creator_workspace_mvp.script_studio", fromlist=["*"]))
        combined = server_source + application_source
        self.assertNotIn("script_studio.foundation", combined)
        self.assertNotIn("SqliteScriptStudioAdapter", combined)
        self.assertNotIn("sqlite3", combined)
        self.assertNotIn("CREATE TABLE", combined)
        self.assertNotIn("INSERT INTO", combined)


if __name__ == "__main__":
    unittest.main()
