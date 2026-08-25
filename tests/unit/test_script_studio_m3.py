from contextlib import redirect_stderr
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from apps.creator_workspace_mvp.script_studio import (
    SCENE_REWRITE_SCHEMA_VERSION,
    SCRIPT_CANDIDATE_SCHEMA_VERSION,
    SCRIPT_DURATION_MAX_RATIO,
    SCRIPT_DURATION_MIN_RATIO,
    ScriptCandidateValidationError,
    ScriptGenerationError,
    ScriptStudioApplicationService,
    _generation_messages,
    validate_script_candidate,
)
from services.v5_core_os.text_generation import (
    TextGenerationPurpose,
    TextGenerationTimeoutError,
    TextGenerationUnavailableError,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v5_core_os.script_studio.foundation import (
    InMemoryScriptStudioAdapter,
    RecordNotFoundError,
    ScriptNotConfirmedError,
    ScriptStudioError,
    ScriptStudioService,
)
from services.v5_core_os.script_studio.public import (
    ScriptStudioPublicBoundary,
    ScriptStudioPublicError,
    create_local_development_boundary,
)
from services.v5_core_os.series_episode import create_in_memory_boundary as create_series_boundary
from services.v5_core_os.series_episode import create_local_development_boundary as create_local_series_boundary
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


WORKSPACE = "workspace-m3"
PROFILE = "profile-m3"
_SCRIPT_CONTENT_TEST_FIELDS = (
    "title",
    "logline",
    "synopsis",
    "targetDurationSec",
    "scenes",
)


class Refs:
    def __init__(self):
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-{self.counts[prefix]}"


def seed_episode(boundary):
    series = boundary.create_series(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": "晚灯",
            "plannedEpisodeCount": 100,
        }
    )
    plan = boundary.confirm_creative_plan(
        {
            "workspaceRef": WORKSPACE,
            "humanConfirmed": True,
            "sourcePlanRef": "director-plan-1",
            "sourcePlanSchemaVersion": "creator.ai-director.plan.v1",
            "sourcePlanVersion": 1,
            "brief": valid_brief(),
            "sourcePlan": valid_plan(),
        }
    )
    episode = boundary.create_episode(
        {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": plan["creativePlanRef"],
            "episodeNumber": 1,
            "title": "第1集",
        }
    )
    return series, episode


def script_candidate():
    return {
        "schemaVersion": SCRIPT_CANDIDATE_SCHEMA_VERSION,
        "title": "晚灯还亮着",
        "logline": "晚灯在深夜陪伴疲惫的人。",
        "synopsis": "一束温暖灯光回应孤独。",
        "targetDurationSec": 30,
        "scenes": [
            {
                "sceneNumber": 1,
                "heading": "深夜房间",
                "location": "房间",
                "timeOfDay": "深夜",
                "characters": ["晚灯"],
                "action": "房间只剩一盏灯，晚灯注意到疲惫的人。",
                "dialogue": [
                    {"speaker": "晚灯", "text": "今晚先不用证明自己。", "emotion": "克制温柔"}
                ],
                "narration": ["夜很深，灯还亮着。"],
                "subtitleText": ["今晚先不用证明自己。"],
                "estimatedDurationSec": 14,
                "scenePurpose": "建立孤独与陪伴",
                "continuityNotes": ["保持琥珀暖光"],
                "productionNotes": ["静态构图"],
            },
            {
                "sceneNumber": 2,
                "heading": "暖光回应",
                "location": "房间",
                "timeOfDay": "深夜",
                "characters": ["晚灯"],
                "action": "暖光缓慢亮起，房间仍安静但不再孤单。",
                "dialogue": [],
                "narration": ["有人陪着，就可以慢一点。"],
                "subtitleText": ["慢一点，也没有关系。"],
                "estimatedDurationSec": 16,
                "scenePurpose": "完成情绪转折",
                "continuityNotes": ["暖光方向保持一致"],
                "productionNotes": ["结尾停留三秒"],
            },
        ],
    }


def content_from_candidate(candidate=None):
    value = dict(candidate or script_candidate())
    value.pop("schemaVersion", None)
    return value


def with_scene_refs(content, refs=("scene-1", "scene-2")):
    value = json.loads(json.dumps(content, ensure_ascii=False))
    for scene, ref in zip(value["scenes"], refs):
        scene["scriptSceneRef"] = ref
    return value


class ScriptStudioDomainTests(unittest.TestCase):
    def setUp(self):
        self.refs = Refs()
        self.upstream = create_series_boundary(ref_factory=self.refs, clock=lambda: "2026-01-01T00:00:00.000Z")
        self.series, self.episode = seed_episode(self.upstream)
        self.repository = InMemoryScriptStudioAdapter()
        self.service = ScriptStudioService(
            self.repository,
            self.upstream,
            ref_factory=self.refs,
            clock=lambda: "2026-01-01T00:00:01.000Z",
        )
        self.scope = {
            "workspaceRef": WORKSPACE,
            "seriesRef": self.series["seriesRef"],
            "episodeRef": self.episode["episodeRef"],
        }

    def create_initial(self):
        return self.service.create_version(
            {**self.scope, "changeKind": "ai-generation", "content": content_from_candidate()}
        )

    def test_bootstrap_consumes_episode_confirmed_plan_without_script(self):
        workspace = self.service.get_workspace(**{
            "workspace_ref": WORKSPACE,
            "series_ref": self.series["seriesRef"],
            "episode_ref": self.episode["episodeRef"],
        })
        self.assertIsNone(workspace["script"])
        self.assertEqual(workspace["bootstrap"]["sourcePlanRef"], "director-plan-1")

    def test_initial_version_establishes_full_identity_and_lineage(self):
        result = self.create_initial()
        script = result["script"]
        version = result["scriptVersion"]
        self.assertEqual(version["schemaVersion"], "creator.script-studio.script-version.v1")
        self.assertEqual(version["seriesRef"], self.series["seriesRef"])
        self.assertEqual(version["episodeRef"], self.episode["episodeRef"])
        self.assertEqual(version["scriptRef"], script["scriptRef"])
        self.assertEqual(version["sourcePlanRef"], "director-plan-1")
        self.assertEqual(version["sourcePlanSchemaVersion"], "creator.ai-director.plan.v1")
        self.assertEqual(version["sourcePlanVersion"], 1)
        self.assertEqual(version["versionNumber"], 1)
        self.assertIsNone(script["confirmedScriptVersionRef"])
        self.assertEqual([item["sceneNumber"] for item in version["scenes"]], [1, 2])
        self.assertEqual(len({item["scriptSceneRef"] for item in version["scenes"]}), 2)

    def test_reviewed_import_records_digest_assertions_and_remains_unconfirmed(self):
        result = self.service.create_version(
            {
                **self.scope,
                "changeKind": "reviewed-import",
                "uploadedSourceByteDigest": "A" * 64,
                "normalizedSourceDocumentDigest": "B" * 64,
                "reviewedDocumentDigest": "C" * 64,
                "importedByRef": "creator-reviewer-credential",
                "content": content_from_candidate(),
            }
        )
        version = result["scriptVersion"]
        self.assertEqual(version["changeKind"], "reviewed-import")
        self.assertIsNone(result["script"]["confirmedScriptVersionRef"])
        normalized_content = {
            key: version[key]
            for key in (
                "title",
                "logline",
                "synopsis",
                "targetDurationSec",
                "scenes",
            )
        }
        canonical_digest = hashlib.sha256(
            json.dumps(
                normalized_content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        expected_provenance = {
                "uploadedSourceByteDigest": "a" * 64,
                "normalizedSourceDocumentDigest": "b" * 64,
                "reviewedDocumentDigest": "c" * 64,
                "importedByRef": "creator-reviewer-credential",
                "digestAssertionState": (
                    "AUTHENTICATED_SERVICE_CREDENTIAL_DECLARATION_UNVERIFIED"
                ),
                "reviewedDocumentToContentBindingState": "NOT_VERIFIED",
                "canonicalScriptContentDigest": canonical_digest,
        }
        expected_provenance["importProvenanceDigest"] = hashlib.sha256(
            json.dumps(
                expected_provenance,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(version["importProvenance"], expected_provenance)

    def test_reviewed_import_in_memory_content_tampering_fails_closed(self):
        imported = self.service.create_version(
            {
                **self.scope,
                "changeKind": "reviewed-import",
                "uploadedSourceByteDigest": "a" * 64,
                "normalizedSourceDocumentDigest": "b" * 64,
                "reviewedDocumentDigest": "c" * 64,
                "importedByRef": "creator-reviewer-credential",
                "content": content_from_candidate(),
            }
        )
        script_ref = imported["script"]["scriptRef"]
        version_ref = imported["scriptVersion"]["scriptVersionRef"]
        key = (WORKSPACE, script_ref, version_ref)
        original = self.repository._versions[key]
        public = ScriptStudioPublicBoundary(self.service)

        def extra_workspace(content):
            content["workspaceRef"] = "forged-workspace"

        def publication_authority(content):
            content["publicationAllowed"] = True

        def canonical_authority(content):
            content["canonicalExecutableScriptRef"] = "forged-canonical-script"

        def scene_authority(content):
            content["scenes"][0]["canonicalShotRef"] = "forged-canonical-shot"

        for label, tamper in (
            ("workspace_scope", extra_workspace),
            ("publication_authority", publication_authority),
            ("canonical_authority", canonical_authority),
            ("scene_authority", scene_authority),
        ):
            with self.subTest(label=label):
                content = json.loads(original.contentJson)
                tamper(content)
                self.repository._versions[key] = replace(
                    original,
                    contentJson=json.dumps(
                        content,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                with self.assertRaises(ScriptStudioPublicError) as caught:
                    public.get_workspace(
                        WORKSPACE,
                        self.series["seriesRef"],
                        self.episode["episodeRef"],
                    )
                self.assertEqual(
                    (caught.exception.status, caught.exception.code),
                    (500, "application_error"),
                )
        self.repository._versions[key] = original

    def test_derived_version_validates_parent_before_any_in_memory_write(self):
        imported = self.service.create_version(
            {
                **self.scope,
                "changeKind": "reviewed-import",
                "uploadedSourceByteDigest": "a" * 64,
                "normalizedSourceDocumentDigest": "b" * 64,
                "reviewedDocumentDigest": "c" * 64,
                "importedByRef": "creator-reviewer-credential",
                "content": content_from_candidate(),
            }
        )
        script_ref = imported["script"]["scriptRef"]
        version_ref = imported["scriptVersion"]["scriptVersionRef"]
        key = (WORKSPACE, script_ref, version_ref)
        original_record = self.repository._versions[key]
        original_script = self.repository.get_script(
            WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]
        )
        content = {
            field: imported["scriptVersion"][field]
            for field in _SCRIPT_CONTENT_TEST_FIELDS
        }
        content = json.loads(json.dumps(content, ensure_ascii=False))
        content["title"] = "不得写入的派生版本"
        public = ScriptStudioPublicBoundary(self.service)

        stored_content = json.loads(original_record.contentJson)
        stored_content["publicationAllowed"] = True
        poisoned_content = replace(
            original_record,
            contentJson=json.dumps(
                stored_content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        poisoned_source = replace(
            original_record,
            sourcePlanRef="forged-source-plan",
        )
        for label, poisoned in (
            ("content", poisoned_content),
            ("source_lineage", poisoned_source),
        ):
            with self.subTest(label=label):
                self.repository._versions[key] = poisoned
                with self.assertRaises(ScriptStudioPublicError) as caught:
                    public.create_version(
                        {
                            **self.scope,
                            "scriptRef": script_ref,
                            "baseScriptVersionRef": version_ref,
                            "changeKind": "manual-edit",
                            "content": content,
                        }
                    )
                self.assertEqual(
                    (caught.exception.status, caught.exception.code),
                    (500, "application_error"),
                )
                self.assertEqual(
                    self.repository.get_script(
                        WORKSPACE,
                        self.series["seriesRef"],
                        self.episode["episodeRef"],
                    ),
                    original_script,
                )
                self.assertEqual(
                    len(self.repository.list_versions(WORKSPACE, script_ref)), 1
                )
        self.repository._versions[key] = original_record

    def test_derived_version_validates_every_record_used_for_next_number(self):
        first = self.create_initial()
        first_content = {
            field: first["scriptVersion"][field]
            for field in _SCRIPT_CONTENT_TEST_FIELDS
        }
        first_content = json.loads(json.dumps(first_content, ensure_ascii=False))
        first_content["title"] = "第二版"
        second = self.service.create_version(
            {
                **self.scope,
                "scriptRef": first["script"]["scriptRef"],
                "baseScriptVersionRef": first["scriptVersion"]["scriptVersionRef"],
                "changeKind": "manual-edit",
                "content": first_content,
            }
        )
        script_ref = first["script"]["scriptRef"]
        first_key = (
            WORKSPACE,
            script_ref,
            first["scriptVersion"]["scriptVersionRef"],
        )
        original_first = self.repository._versions[first_key]
        self.repository._versions[first_key] = replace(
            original_first,
            sourcePlanVersion=original_first.sourcePlanVersion + 1,
        )
        before_script = self.repository.get_script(
            WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]
        )
        next_content = {
            field: second["scriptVersion"][field]
            for field in _SCRIPT_CONTENT_TEST_FIELDS
        }
        next_content = json.loads(json.dumps(next_content, ensure_ascii=False))
        next_content["title"] = "不得写入的第三版"
        public = ScriptStudioPublicBoundary(self.service)
        with self.assertRaises(ScriptStudioPublicError) as caught:
            public.create_version(
                {
                    **self.scope,
                    "scriptRef": script_ref,
                    "baseScriptVersionRef": second["scriptVersion"][
                        "scriptVersionRef"
                    ],
                    "changeKind": "manual-edit",
                    "content": next_content,
                }
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (500, "application_error"),
        )
        self.assertEqual(
            self.repository.get_script(
                WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]
            ),
            before_script,
        )
        self.assertEqual(len(self.repository.list_versions(WORKSPACE, script_ref)), 2)
        self.repository._versions[first_key] = original_first

    def test_reviewed_import_rejects_client_scene_refs_and_generic_confirmation(self):
        content = content_from_candidate()
        content["scenes"][0]["scriptSceneRef"] = "k2-001-reused-scene"
        command = {
            **self.scope,
            "changeKind": "reviewed-import",
            "uploadedSourceByteDigest": "a" * 64,
            "normalizedSourceDocumentDigest": "b" * 64,
            "reviewedDocumentDigest": "c" * 64,
            "importedByRef": "creator-reviewer-credential",
            "content": content,
        }
        with self.assertRaises(ScriptStudioError):
            self.service.create_version(command)

        command["content"] = content_from_candidate()
        imported = self.service.create_version(command)
        with self.assertRaises(ScriptStudioError):
            self.service.confirm_version(
                {
                    **self.scope,
                    "scriptRef": imported["script"]["scriptRef"],
                    "scriptVersionRef": imported["scriptVersion"][
                        "scriptVersionRef"
                    ],
                    "humanConfirmed": True,
                }
            )
        self.assertIsNone(
            self.repository.get_script(
                WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]
            ).confirmedScriptVersionRef
        )

    def test_reviewed_import_requires_all_source_digests_and_service_credential(self):
        base = {
            **self.scope,
            "changeKind": "reviewed-import",
            "uploadedSourceByteDigest": "a" * 64,
            "normalizedSourceDocumentDigest": "b" * 64,
            "reviewedDocumentDigest": "c" * 64,
            "importedByRef": "creator-reviewer-credential",
            "content": content_from_candidate(),
        }
        for field, value in (
            ("uploadedSourceByteDigest", "bad"),
            ("normalizedSourceDocumentDigest", "bad"),
            ("reviewedDocumentDigest", "bad"),
            ("importedByRef", ""),
        ):
            with self.subTest(field=field):
                command = dict(base)
                command[field] = value
                with self.assertRaises(ScriptStudioError):
                    self.service.create_version(command)
        self.assertIsNone(
            self.repository.get_script(
                WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]
            )
        )

    def test_reviewed_import_cannot_be_appended_to_existing_script(self):
        first = self.create_initial()
        with self.assertRaises(ScriptStudioError):
            self.service.create_version(
                {
                    **self.scope,
                    "scriptRef": first["script"]["scriptRef"],
                    "baseScriptVersionRef": first["scriptVersion"][
                        "scriptVersionRef"
                    ],
                    "changeKind": "reviewed-import",
                    "uploadedSourceByteDigest": "a" * 64,
                    "normalizedSourceDocumentDigest": "b" * 64,
                    "reviewedDocumentDigest": "c" * 64,
                    "importedByRef": "creator-reviewer-credential",
                    "content": content_from_candidate(),
                }
            )
        self.assertEqual(
            len(
                self.repository.list_versions(
                    WORKSPACE, first["script"]["scriptRef"]
                )
            ),
            1,
        )

    def test_manual_edit_creates_immutable_second_version(self):
        first = self.create_initial()
        content = {key: first["scriptVersion"][key] for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
        content = json.loads(json.dumps(content, ensure_ascii=False))
        content["synopsis"] = "人工调整后的故事梗概。"
        second = self.service.create_version(
            {
                **self.scope,
                "scriptRef": first["script"]["scriptRef"],
                "baseScriptVersionRef": first["scriptVersion"]["scriptVersionRef"],
                "changeKind": "manual-edit",
                "content": content,
            }
        )
        stored_first = self.repository.get_version(
            WORKSPACE,
            first["script"]["scriptRef"],
            first["scriptVersion"]["scriptVersionRef"],
        )
        self.assertEqual(json.loads(stored_first.contentJson)["synopsis"], "一束温暖灯光回应孤独。")
        self.assertEqual(second["scriptVersion"]["versionNumber"], 2)
        self.assertEqual(second["scriptVersion"]["changeKind"], "manual-edit")
        self.assertEqual(second["script"]["currentScriptVersionRef"], second["scriptVersion"]["scriptVersionRef"])

    def test_new_draft_does_not_replace_confirmed_reference(self):
        first = self.create_initial()
        confirmed = self.service.confirm_version(
            {**self.scope, "scriptRef": first["script"]["scriptRef"], "scriptVersionRef": first["scriptVersion"]["scriptVersionRef"], "humanConfirmed": True}
        )
        content = {key: first["scriptVersion"][key] for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
        content["title"] = "新草稿"
        second = self.service.create_version(
            {**self.scope, "scriptRef": first["script"]["scriptRef"], "baseScriptVersionRef": first["scriptVersion"]["scriptVersionRef"], "changeKind": "manual-edit", "content": content}
        )
        self.assertEqual(second["script"]["confirmedScriptVersionRef"], confirmed["confirmedVersion"]["scriptVersionRef"])
        self.assertNotEqual(second["script"]["currentScriptVersionRef"], second["script"]["confirmedScriptVersionRef"])

    def test_draft_storyboard_bootstrap_is_rejected_and_confirmed_passes(self):
        first = self.create_initial()
        with self.assertRaises(ScriptNotConfirmedError):
            self.service.build_storyboard_bootstrap(WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"])
        self.service.confirm_version(
            {**self.scope, "scriptRef": first["script"]["scriptRef"], "scriptVersionRef": first["scriptVersion"]["scriptVersionRef"], "humanConfirmed": True}
        )
        bootstrap = self.service.build_storyboard_bootstrap(WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"])
        self.assertEqual(bootstrap["schemaVersion"], "creator.storyboard.bootstrap-input.v1")
        self.assertEqual(bootstrap["scriptVersionRef"], first["scriptVersion"]["scriptVersionRef"])
        self.assertFalse(bootstrap["storyboardProductionAuthorized"])
        self.assertEqual(bootstrap["nextGate"], "m4-ip-character-binding-required")

    def test_invalid_duration_and_duplicate_scene_refs_are_rejected(self):
        bad = content_from_candidate()
        bad["scenes"][0]["estimatedDurationSec"] = 2
        bad["scenes"][1]["estimatedDurationSec"] = 2
        with self.assertRaises(ScriptStudioError):
            self.service.create_version({**self.scope, "changeKind": "ai-generation", "content": bad})
        self.assertIsNone(self.repository.get_script(WORKSPACE, self.series["seriesRef"], self.episode["episodeRef"]))

    def test_scope_mismatch_cannot_attach_script_to_other_episode(self):
        with self.assertRaises(Exception):
            self.service.create_version(
                {**self.scope, "episodeRef": "episode-missing", "changeKind": "ai-generation", "content": content_from_candidate()}
            )


class ScriptStudioApplicationTests(unittest.TestCase):
    def setUp(self):
        upstream = create_series_boundary(ref_factory=Refs())
        series, episode = seed_episode(upstream)
        self.bootstrap = upstream.build_script_studio_bootstrap(WORKSPACE, series["seriesRef"], episode["episodeRef"])

    def test_generation_calls_v5_capability_and_validates_candidate(self):
        capability = FakeTextGenerationCapability([json.dumps(script_candidate(), ensure_ascii=False)])
        result = ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(result["targetDurationSec"], 30)
        self.assertEqual(len(result["scenes"]), 2)
        self.assertEqual(len(capability.commands), 1)
        self.assertEqual(capability.commands[0].purpose, TextGenerationPurpose.SCRIPT_CANDIDATE)
        self.assertIn("creator.script-studio.script-candidate.v1", capability.commands[0].messages[1].content)

    def test_generation_failure_does_not_return_partial_candidate(self):
        invalid = json.dumps({"schemaVersion": SCRIPT_CANDIDATE_SCHEMA_VERSION})
        capability = FakeTextGenerationCapability([invalid, invalid])
        with self.assertRaises(ScriptGenerationError):
            ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(len(capability.commands), 2)

    def test_sanitized_regression_normalizes_only_missing_optional_arrays(self):
        candidate = script_candidate()
        for scene in candidate["scenes"]:
            for field in ("dialogue", "narration", "subtitleText", "continuityNotes", "productionNotes"):
                scene.pop(field)
        capability = FakeTextGenerationCapability([json.dumps(candidate, ensure_ascii=False)])
        result = ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(len(capability.commands), 1)
        for scene in result["scenes"]:
            self.assertEqual(scene["dialogue"], [])
            self.assertEqual(scene["narration"], [])
            self.assertEqual(scene["subtitleText"], [])
            self.assertEqual(scene["continuityNotes"], [])
            self.assertEqual(scene["productionNotes"], [])

    def test_exact_live_failure_missing_schema_version_is_repaired(self):
        invalid = script_candidate()
        invalid.pop("schemaVersion")
        capability = FakeTextGenerationCapability([
            json.dumps(invalid, ensure_ascii=False),
            json.dumps(script_candidate(), ensure_ascii=False),
        ])
        result = ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(result["title"], script_candidate()["title"])
        self.assertEqual(len(capability.commands), 2)
        repair_prompt = json.loads(capability.commands[1].messages[1].content)
        self.assertIn(
            {"field": "schemaVersion", "rule": "required_field"},
            repair_prompt["validationIssues"],
        )

    def test_prompt_and_validator_contract_are_aligned(self):
        messages = _generation_messages(self.bootstrap)
        prompt = json.loads(messages[1].content)
        contract = prompt["requiredContract"]
        output = contract["outputObject"]
        self.assertEqual(
            set(output),
            {"schemaVersion", "title", "logline", "synopsis", "targetDurationSec", "scenes"},
        )
        scene_fields = set(output["scenes"][0])
        required = set(contract["rules"]["requiredSceneFields"])
        optional = set(contract["rules"]["optionalSceneArraysDefaultToEmpty"])
        self.assertEqual(scene_fields, required | optional)
        self.assertEqual(
            contract["rules"]["systemOwnedFieldsMustNotAppear"],
            ["scriptRef", "scriptVersionRef", "scriptSceneRef"],
        )
        self.assertEqual(contract["rules"]["duration"]["sceneDurationTotalMin"], 30 * SCRIPT_DURATION_MIN_RATIO)
        self.assertEqual(contract["rules"]["duration"]["sceneDurationTotalMax"], 30 * SCRIPT_DURATION_MAX_RATIO)

    def test_generation_uses_exactly_one_controlled_repair(self):
        invalid = script_candidate()
        invalid["scenes"][0].pop("action")
        capability = FakeTextGenerationCapability([
            json.dumps(invalid, ensure_ascii=False),
            json.dumps(script_candidate(), ensure_ascii=False),
        ])
        result = ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(result["title"], script_candidate()["title"])
        self.assertEqual(len(capability.commands), 2)
        self.assertTrue(all(command.purpose is TextGenerationPurpose.SCRIPT_CANDIDATE for command in capability.commands))
        repair_prompt = json.loads(capability.commands[1].messages[1].content)
        self.assertEqual(repair_prompt["task"], "Repair the Script Studio candidate once. Return a complete corrected JSON object only.")
        self.assertIn(
            {"field": "scenes[0].action", "rule": "required_field"},
            repair_prompt["validationIssues"],
        )

    def test_repair_failure_stops_after_two_provider_calls_and_exposes_only_diagnostics(self):
        invalid = script_candidate()
        invalid["scenes"][0].pop("scenePurpose")
        raw = json.dumps(invalid, ensure_ascii=False)
        capability = FakeTextGenerationCapability([raw, raw])
        with self.assertRaises(ScriptGenerationError) as context:
            ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(len(capability.commands), 2)
        self.assertEqual(context.exception.code, "invalid_provider_output")
        self.assertTrue(all(len(item) == 4 for item in context.exception.validation_issues))
        self.assertNotIn(raw, str(context.exception))

    def test_schema_diagnostics_never_log_provider_content(self):
        invalid = script_candidate()
        invalid.pop("schemaVersion")
        invalid["title"] = "sensitive-provider-content-marker"
        raw = json.dumps(invalid, ensure_ascii=False)
        capability = FakeTextGenerationCapability([raw, raw])
        stream = io.StringIO()
        with redirect_stderr(stream):
            with self.assertRaises(ScriptGenerationError):
                ScriptStudioApplicationService(capability).generate(self.bootstrap)
        diagnostic = stream.getvalue()
        self.assertIn("SCRIPT_STUDIO_SCHEMA_ERROR", diagnostic)
        self.assertIn("field=schemaVersion", diagnostic)
        self.assertIn("rule=required_field", diagnostic)
        self.assertNotIn("sensitive-provider-content-marker", diagnostic)

    def test_provider_cannot_supply_system_owned_scene_reference(self):
        invalid = script_candidate()
        invalid["scenes"][0]["scriptSceneRef"] = "provider-invented-ref"
        capability = FakeTextGenerationCapability([
            json.dumps(invalid, ensure_ascii=False),
            json.dumps(script_candidate(), ensure_ascii=False),
        ])
        result = ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertNotIn("scriptSceneRef", result["scenes"][0])
        repair_prompt = json.loads(capability.commands[1].messages[1].content)
        self.assertIn(
            {"field": "scenes[0].scriptSceneRef", "rule": "unsupported_field"},
            repair_prompt["validationIssues"],
        )

    def test_duration_tolerance_accepts_realistic_edges_and_rejects_outside(self):
        for total in (29, 31, 30.5, 24, 36):
            with self.subTest(total=total):
                candidate = script_candidate()
                candidate["scenes"][0]["estimatedDurationSec"] = total / 2
                candidate["scenes"][1]["estimatedDurationSec"] = total / 2
                result = validate_script_candidate(candidate, self.bootstrap)
                self.assertEqual(sum(item["estimatedDurationSec"] for item in result["scenes"]), total)
        for total in (23.99, 36.01):
            with self.subTest(total=total):
                candidate = script_candidate()
                candidate["scenes"][0]["estimatedDurationSec"] = total / 2
                candidate["scenes"][1]["estimatedDurationSec"] = total / 2
                with self.assertRaises(ScriptCandidateValidationError) as context:
                    validate_script_candidate(candidate, self.bootstrap)
                self.assertIn(
                    "scenes[].estimatedDurationSec: duration_total_out_of_tolerance",
                    context.exception.errors,
                )

    def test_malformed_json_is_repaired_once_then_rejected(self):
        capability = FakeTextGenerationCapability(["not-json", "still-not-json"])
        with self.assertRaises(ScriptGenerationError) as context:
            ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(len(capability.commands), 2)
        self.assertEqual(
            context.exception.validation_issues,
            (
                ("initial", "$", "invalid_json", "provider_schema_error"),
                ("repair", "$", "invalid_json", "provider_schema_error"),
            ),
        )

    def test_provider_timeout_is_mapped_without_secret_or_raw_response(self):
        capability = FakeTextGenerationCapability([TextGenerationTimeoutError()])
        with self.assertRaises(ScriptGenerationError) as context:
            ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(context.exception.code, "provider_timeout")
        self.assertNotIn("secret", str(context.exception))

    def test_provider_unavailable_is_mapped_without_secret_or_raw_response(self):
        capability = FakeTextGenerationCapability([
            TextGenerationUnavailableError(category="provider_http_error", status=503)
        ])
        with self.assertRaises(ScriptGenerationError) as context:
            ScriptStudioApplicationService(capability).generate(self.bootstrap)
        self.assertEqual(context.exception.code, "provider_unavailable")
        self.assertEqual(context.exception.diagnostic_category, "provider_http_error")
        self.assertEqual(context.exception.provider_status, 503)
        self.assertEqual(context.exception.exception_name, "TextGenerationUnavailableError")

    def test_scene_rewrite_changes_only_selected_scene(self):
        current = {**content_from_candidate(), "scriptRef": "script-1", "scriptVersionRef": "version-1"}
        current["scenes"] = with_scene_refs(current["scenes"] and {"scenes": current["scenes"]})["scenes"]
        rewritten = dict(current["scenes"][0])
        rewritten.pop("scriptSceneRef")
        rewritten["action"] = "更克制的动作。"
        capability = FakeTextGenerationCapability([
            json.dumps({"schemaVersion": SCENE_REWRITE_SCHEMA_VERSION, "scene": rewritten}, ensure_ascii=False)
        ])
        result = ScriptStudioApplicationService(capability).rewrite_scene(
            bootstrap=self.bootstrap,
            current_version=current,
            script_scene_ref="scene-1",
            instruction="让这一场更克制",
        )
        self.assertEqual(result["scenes"][0]["action"], "更克制的动作。")
        self.assertEqual(result["scenes"][1], current["scenes"][1])
        self.assertEqual(capability.commands[0].purpose, TextGenerationPurpose.SCRIPT_SCENE_REWRITE)

    def test_candidate_validator_rejects_discontinuous_scenes(self):
        candidate = script_candidate()
        candidate["scenes"][1]["sceneNumber"] = 3
        with self.assertRaises(ScriptCandidateValidationError):
            validate_script_candidate(candidate, self.bootstrap)


class ScriptStudioPersistenceTests(unittest.TestCase):
    def test_sqlite_roundtrip_preserves_versions_confirmation_and_storyboard_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "creator.sqlite3"
            refs = Refs()
            upstream = create_local_series_boundary(database)
            series, episode = seed_episode(upstream)
            first_boundary = create_local_development_boundary(database, upstream)
            scope = {"workspaceRef": WORKSPACE, "seriesRef": series["seriesRef"], "episodeRef": episode["episodeRef"]}
            initial = first_boundary.create_version({**scope, "changeKind": "ai-generation", "content": content_from_candidate()})
            content = {key: initial["scriptVersion"][key] for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
            content["title"] = "晚灯还亮着 v2"
            second = first_boundary.create_version(
                {**scope, "scriptRef": initial["script"]["scriptRef"], "baseScriptVersionRef": initial["scriptVersion"]["scriptVersionRef"], "changeKind": "manual-edit", "content": content}
            )
            first_boundary.confirm_version(
                {**scope, "scriptRef": initial["script"]["scriptRef"], "scriptVersionRef": second["scriptVersion"]["scriptVersionRef"], "humanConfirmed": True}
            )
            restarted_upstream = create_local_series_boundary(database)
            restarted = create_local_development_boundary(database, restarted_upstream)
            workspace = restarted.get_workspace(WORKSPACE, series["seriesRef"], episode["episodeRef"])
            self.assertEqual(len(workspace["versions"]), 2)
            self.assertEqual(workspace["script"]["confirmedScriptVersionRef"], second["scriptVersion"]["scriptVersionRef"])
            bootstrap = restarted.build_storyboard_bootstrap(WORKSPACE, series["seriesRef"], episode["episodeRef"])
            self.assertEqual(bootstrap["title"], "晚灯还亮着 v2")

    def test_public_boundary_maps_unconfirmed_storyboard_to_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            upstream = create_series_boundary(ref_factory=Refs())
            series, episode = seed_episode(upstream)
            boundary = create_local_development_boundary(Path(directory) / "creator.sqlite3", upstream)
            scope = {"workspaceRef": WORKSPACE, "seriesRef": series["seriesRef"], "episodeRef": episode["episodeRef"]}
            boundary.create_version({**scope, "changeKind": "ai-generation", "content": content_from_candidate()})
            with self.assertRaises(ScriptStudioPublicError) as context:
                boundary.build_storyboard_bootstrap(WORKSPACE, series["seriesRef"], episode["episodeRef"])
            self.assertEqual(context.exception.status, 409)

    def test_failed_sqlite_version_insert_rolls_back_current_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "creator.sqlite3"
            upstream = create_local_series_boundary(database)
            series, episode = seed_episode(upstream)
            boundary = create_local_development_boundary(database, upstream)
            scope = {"workspaceRef": WORKSPACE, "seriesRef": series["seriesRef"], "episodeRef": episode["episodeRef"]}
            initial = boundary.create_version({**scope, "changeKind": "ai-generation", "content": content_from_candidate()})
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "CREATE TRIGGER reject_script_version BEFORE INSERT ON v5_script_versions BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
                )
                connection.commit()
            finally:
                connection.close()
            content = {key: initial["scriptVersion"][key] for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
            content["title"] = "不应保存"
            with self.assertRaises(ScriptStudioPublicError):
                boundary.create_version({
                    **scope,
                    "scriptRef": initial["script"]["scriptRef"],
                    "baseScriptVersionRef": initial["scriptVersion"]["scriptVersionRef"],
                    "changeKind": "manual-edit",
                    "content": content,
                })
            workspace = boundary.get_workspace(WORKSPACE, series["seriesRef"], episode["episodeRef"])
            self.assertEqual(len(workspace["versions"]), 1)
            self.assertEqual(workspace["script"]["currentScriptVersionRef"], initial["scriptVersion"]["scriptVersionRef"])

    def test_failed_sqlite_confirmation_leaves_confirmed_pointer_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "creator.sqlite3"
            upstream = create_local_series_boundary(database)
            series, episode = seed_episode(upstream)
            boundary = create_local_development_boundary(database, upstream)
            scope = {"workspaceRef": WORKSPACE, "seriesRef": series["seriesRef"], "episodeRef": episode["episodeRef"]}
            initial = boundary.create_version({**scope, "changeKind": "ai-generation", "content": content_from_candidate()})
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "CREATE TRIGGER reject_script_confirmation BEFORE UPDATE OF confirmed_script_version_ref ON v5_scripts BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(ScriptStudioPublicError) as context:
                boundary.confirm_version({
                    **scope,
                    "scriptRef": initial["script"]["scriptRef"],
                    "scriptVersionRef": initial["scriptVersion"]["scriptVersionRef"],
                    "humanConfirmed": True,
                })
            self.assertEqual(context.exception.status, 500)
            workspace = boundary.get_workspace(WORKSPACE, series["seriesRef"], episode["episodeRef"])
            self.assertIsNone(workspace["script"]["confirmedScriptVersionRef"])


if __name__ == "__main__":
    unittest.main()
