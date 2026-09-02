import copy
from hashlib import sha256
import json
import unittest

from services.v5_core_os.episode_production import (
    DEFAULT_VALIDATION_PROFILE_REF,
    DEFAULT_VALIDATION_PROFILE_VERSION,
    EpisodeProductionPublicError,
    FINDING_CATEGORIES,
    NarrativeValidationProfile,
    NarrativeValidationProfileRegistry,
    NarrativeValidationRule,
    create_in_memory_boundary,
)
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    run_command,
    seed_k2_roots,
)
from tests.unit.test_script_studio_m3 import content_from_candidate
from tests.unit.test_series_intelligence_consumer_m6_p3 import in_memory_consumer


SCRIPT_CONTENT_FIELDS = (
    "title",
    "logline",
    "synopsis",
    "targetDurationSec",
    "scenes",
)


class IdentityWriteSpy:
    def __init__(self):
        self.calls = []

    def authorize_reference(self, *args, **kwargs):
        self.calls.append(("authorize_reference", args, kwargs))
        raise AssertionError("M7 must not call Identity authority")

    def require_current_reference(self, *args, **kwargs):
        self.calls.append(("require_current_reference", args, kwargs))
        raise AssertionError("M7 must not call Identity authority")


def validation_profiles():
    sources = (
        ("ACTION", "林澈"),
        ("DIALOGUE", "相信"),
        ("NARRATION", "档案"),
        ("SUBTITLE_TEXT", "相信"),
    )
    category_rules = []
    for index, category in enumerate(sorted(FINDING_CATEGORIES)):
        source_field, match_text = sources[index % len(sources)]
        category_rules.append(
            NarrativeValidationRule(
                f"m7.rule.{category.lower()}.v1",
                category,
                "WARN",
                source_field,
                match_text,
                {"policyRef": f"policy-{index + 1}"},
            )
        )
    return NarrativeValidationProfileRegistry(
        (
            NarrativeValidationProfile(
                DEFAULT_VALIDATION_PROFILE_REF,
                DEFAULT_VALIDATION_PROFILE_VERSION,
            ),
            NarrativeValidationProfile(
                "m7.all-finding-categories",
                1,
                tuple(category_rules),
            ),
            NarrativeValidationProfile(
                "m7.blocking-rule",
                1,
                (
                    NarrativeValidationRule(
                        "m7.rule.blocking-action.v1",
                        "WORLD_RULE_CONFLICT",
                        "BLOCK",
                        "ACTION",
                        "不存在",
                        {"policyRef": "world-rule-memory"},
                    ),
                ),
            ),
        )
    )


def script_content(version):
    return copy.deepcopy({field: version[field] for field in SCRIPT_CONTENT_FIELDS})


def seed_m7(*, profiles=None, identity_authority=None):
    assembly, refs, project, series, episode, historical = seed_k2_roots(
        with_m6_authority=True,
        confirm_script=False,
    )
    activate_k2_m6_baseline(assembly, project, series)
    content = script_content(historical["scriptVersion"])
    content["scenes"][0]["narration"] = ["档案仍在低鸣。"]
    bound = assembly.script_studio.create_version(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": historical["script"]["scriptRef"],
            "baseScriptVersionRef": historical["scriptVersion"]["scriptVersionRef"],
            "changeKind": "manual-edit",
            "content": content,
        }
    )
    assembly.script_studio.confirm_version(
        {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": bound["script"]["scriptRef"],
            "scriptVersionRef": bound["scriptVersion"]["scriptVersionRef"],
            "humanConfirmed": True,
        }
    )
    boundary = create_in_memory_boundary(
        project_boundary=assembly.project_context,
        series_episode_boundary=assembly.series_episode,
        series_planning_boundary=assembly.series_planning,
        script_studio_boundary=assembly.script_studio,
        identity_reference_authority=identity_authority,
        narrative_validation_profiles=profiles or validation_profiles(),
        ref_factory=refs,
        clock=lambda: "2026-09-02T01:00:00Z",
    )
    run = boundary.create_run(run_command(project, series, episode))
    return {
        "assembly": assembly,
        "refs": refs,
        "project": project,
        "series": series,
        "episode": episode,
        "historical": historical,
        "bound": bound,
        "boundary": boundary,
        "run": run,
    }


def validation_command(seed, *, profile_ref=DEFAULT_VALIDATION_PROFILE_REF, key="m7-pass"):
    return {
        "workspaceRef": WORKSPACE,
        "projectRef": seed["project"]["projectRef"],
        "seriesRef": seed["series"]["seriesRef"],
        "episodeRef": seed["episode"]["episodeRef"],
        "productionRunRef": seed["run"]["productionRunRef"],
        "validationProfileRef": profile_ref,
        "validationProfileVersion": 1,
        "idempotencyKey": key,
    }


def canonical_digest(value):
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def advance_m6(seed):
    assembly = seed["assembly"]
    project = seed["project"]
    series = seed["series"]
    context = {
        "workspaceRef": WORKSPACE,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
    }
    workspace = assembly.series_intelligence.get_workspace(
        WORKSPACE, project["projectRef"], series["seriesRef"]
    )

    def operation(name):
        return {
            **context,
            "operationRef": name,
            "idempotencyKey": name,
        }

    bible_root = workspace["seriesBible"]
    bible_version = workspace["seriesBibleVersions"][-1]
    bible_content = copy.deepcopy(bible_version["content"])
    bible_content["worldRules"][0]["statement"] += "；校验规则已更新"
    new_bible = assembly.series_intelligence.create_bible_version(
        {
            **operation("m7-bible-v2-create"),
            "seriesBibleRef": bible_root["seriesBibleRef"],
            "expectedRevision": bible_root["revision"],
            "candidate": True,
            "content": bible_content,
        }
    )
    new_bible = assembly.series_intelligence.confirm_bible_version(
        {
            **operation("m7-bible-v2-confirm"),
            "seriesBibleRef": new_bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": new_bible["version"]["seriesBibleVersionRef"],
            "expectedRevision": new_bible["root"]["revision"],
            "approvalRef": "approval-human",
        }
    )
    character_root = workspace["characterContinuity"]
    character_content = copy.deepcopy(
        workspace["characterContinuityVersions"][-1]["content"]
    )
    new_characters = assembly.series_intelligence.create_character_version(
        {
            **operation("m7-characters-v2-create"),
            "characterContinuityRef": character_root["characterContinuityRef"],
            "expectedRevision": character_root["revision"],
            "candidate": True,
            "seriesBibleRef": new_bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": new_bible["version"]["seriesBibleVersionRef"],
            "content": character_content,
        }
    )
    new_characters = assembly.series_intelligence.confirm_character_version(
        {
            **operation("m7-characters-v2-confirm"),
            "characterContinuityRef": new_characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": new_characters["version"]["characterContinuityVersionRef"],
            "expectedRevision": new_characters["root"]["revision"],
            "approvalRef": "approval-human",
        }
    )
    return assembly.series_intelligence.activate_baseline(
        {
            **operation("m7-baseline-v2-activate"),
            "seriesBibleRef": new_bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": new_bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": new_characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": new_characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": workspace["activeBaseline"]["activationRevision"],
            "approvalRef": "approval-human",
        }
    )


class M3M6BindingTests(unittest.TestCase):
    def test_additive_v2_binding_is_server_resolved_and_historical_v1_is_unchanged(self):
        seed = seed_m7()
        workspace = seed["assembly"].script_studio.get_workspace(
            WORKSPACE,
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
        )
        historical, bound = workspace["versions"]
        self.assertEqual(
            historical["schemaVersion"], "creator.script-studio.script-version.v1"
        )
        self.assertNotIn("m6ConsumerBinding", historical)
        self.assertEqual(
            bound["schemaVersion"], "creator.script-studio.script-version.v2"
        )
        binding = bound["m6ConsumerBinding"]
        self.assertEqual(
            set(binding),
            {
                "workspaceRef",
                "projectRef",
                "seriesRef",
                "episodeRef",
                "seriesPlanVersionRef",
                "seriesPlanVersionDigest",
                "m6BaselineSnapshotRef",
                "m6BaselineCanonicalDigest",
                "activationRevision",
                "seriesBibleVersionRef",
                "seriesBibleVersionDigest",
                "characterContinuityVersionRef",
                "characterContinuityVersionDigest",
                "payloadDigest",
            },
        )
        payload = dict(binding)
        digest = payload.pop("payloadDigest")
        self.assertEqual(digest, canonical_digest(payload))
        self.assertEqual(
            binding,
            seed["assembly"].script_studio.resolve_current_m6_consumer_binding(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
            ),
        )

    def test_client_raw_binding_fields_are_recursively_rejected(self):
        seed = seed_m7()
        command = {
            "workspaceRef": WORKSPACE,
            "projectRef": seed["project"]["projectRef"],
            "seriesRef": seed["series"]["seriesRef"],
            "episodeRef": seed["episode"]["episodeRef"],
            "scriptRef": seed["bound"]["script"]["scriptRef"],
            "baseScriptVersionRef": seed["bound"]["scriptVersion"]["scriptVersionRef"],
            "changeKind": "manual-edit",
            "content": script_content(seed["bound"]["scriptVersion"]),
        }
        command["content"]["scenes"][0]["productionNotes"].append(
            {"m6BaselineCanonicalDigest": "0" * 64}
        )
        with self.assertRaises(Exception) as rejected:
            seed["assembly"].script_studio.create_version(command)
        self.assertEqual(rejected.exception.code, "invalid_request")

    def test_m6_bound_reviewed_import_keeps_canonical_content_digest_semantics(self):
        seeded = in_memory_consumer()
        assembly = seeded["assembly"]
        context = seeded["context"]
        created = assembly.script_studio.create_version(
            {
                **context,
                "changeKind": "reviewed-import",
                "uploadedSourceByteDigest": "1" * 64,
                "normalizedSourceDocumentDigest": "2" * 64,
                "reviewedDocumentDigest": "3" * 64,
                "importedByRef": "actor-reviewer",
                "content": content_from_candidate(),
            }
        )
        self.assertEqual(
            created["scriptVersion"]["schemaVersion"],
            "creator.script-studio.script-version.v2",
        )
        self.assertIn("m6ConsumerBinding", created["scriptVersion"])
        self.assertIn("importProvenance", created["scriptVersion"])


class M7NarrativeValidationTests(unittest.TestCase):
    def test_pass_is_current_ready_exact_replay_and_write_neutral(self):
        identity = IdentityWriteSpy()
        seed = seed_m7(identity_authority=identity)
        assembly = seed["assembly"]
        script_before = assembly.script_studio.get_workspace(
            WORKSPACE, seed["series"]["seriesRef"], seed["episode"]["episodeRef"]
        )
        m6_before = assembly.script_studio.get_m6_episode_baseline(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
        )
        command = validation_command(seed)
        first = seed["boundary"].create_narrative_validation(command)
        replay = seed["boundary"].create_narrative_validation(copy.deepcopy(command))
        self.assertEqual(first["result"], "PASS")
        self.assertEqual(first["m8Readiness"], "READY_FOR_M8")
        self.assertEqual(first["currentness"], "CURRENT")
        self.assertEqual(first["findings"], [])
        self.assertFalse(first["idempotentReplay"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            {key: value for key, value in first.items() if key != "idempotentReplay"},
            {key: value for key, value in replay.items() if key != "idempotentReplay"},
        )
        ready = seed["boundary"].require_m8_ready_validation(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
            first["consistencyValidationVersionRef"],
        )
        self.assertEqual(ready["payloadDigest"], first["payloadDigest"])
        self.assertEqual(script_before, assembly.script_studio.get_workspace(
            WORKSPACE, seed["series"]["seriesRef"], seed["episode"]["episodeRef"]
        ))
        self.assertEqual(m6_before, assembly.script_studio.get_m6_episode_baseline(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
        ))
        self.assertEqual(identity.calls, [])
        root = seed["boundary"].get_run(
            WORKSPACE, seed["run"]["productionRunRef"]
        )
        self.assertEqual(root["state"], "ROOTS_READY")
        self.assertEqual(root["completedGates"], [])

    def test_every_finding_category_warns_and_warn_never_becomes_ready(self):
        seed = seed_m7()
        result = seed["boundary"].create_narrative_validation(
            validation_command(
                seed,
                profile_ref="m7.all-finding-categories",
                key="m7-all-categories",
            )
        )
        self.assertEqual(result["result"], "WARN")
        self.assertEqual(result["m8Readiness"], "NOT_READY_PENDING_DISPOSITION")
        self.assertEqual(
            {item["category"] for item in result["findings"]},
            FINDING_CATEGORIES,
        )
        self.assertEqual(
            [item["findingOrder"] for item in result["findings"]],
            list(range(1, len(result["findings"]) + 1)),
        )
        for finding in result["findings"]:
            source_span = finding["sourceSpan"]
            self.assertEqual(
                set(source_span),
                {
                    "scriptSceneRef",
                    "sourceField",
                    "sourceIndex",
                    "startOffsetInclusive",
                    "endOffsetExclusive",
                },
            )
            embedded = dict(finding)
            digest = embedded.pop("payloadDigest")
            self.assertEqual(digest, canonical_digest(embedded))
        with self.assertRaises(EpisodeProductionPublicError) as blocked:
            seed["boundary"].require_m8_ready_validation(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                seed["run"]["productionRunRef"],
                result["consistencyValidationVersionRef"],
            )
        self.assertEqual(blocked.exception.code, "execution_not_authorized")

    def test_block_is_not_ready_and_cannot_enter_m8(self):
        seed = seed_m7()
        result = seed["boundary"].create_narrative_validation(
            validation_command(
                seed, profile_ref="m7.blocking-rule", key="m7-block"
            )
        )
        self.assertEqual((result["result"], result["m8Readiness"]), ("BLOCK", "NOT_READY"))
        with self.assertRaises(EpisodeProductionPublicError) as blocked:
            seed["boundary"].require_m8_ready_validation(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                seed["run"]["productionRunRef"],
                result["consistencyValidationVersionRef"],
            )
        self.assertEqual(blocked.exception.status, 409)

    def test_changed_replay_conflicts_without_creating_a_second_version(self):
        seed = seed_m7()
        command = validation_command(seed, key="m7-changed-replay")
        first = seed["boundary"].create_narrative_validation(command)
        changed = dict(command)
        changed["validationProfileRef"] = "m7.blocking-rule"
        with self.assertRaises(EpisodeProductionPublicError) as conflict:
            seed["boundary"].create_narrative_validation(changed)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")
        latest = seed["boundary"].get_narrative_validation(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
        )
        self.assertEqual(latest["consistencyValidationVersionRef"], first["consistencyValidationVersionRef"])
        self.assertEqual(latest["validationVersion"], 1)

    def test_cross_scope_and_foreign_workspace_are_not_found(self):
        seed = seed_m7()
        for field, value in (
            ("projectRef", "project-foreign"),
            ("seriesRef", "series-foreign"),
            ("episodeRef", "episode-foreign"),
            ("workspaceRef", "workspace-foreign"),
        ):
            command = validation_command(seed, key=f"m7-cross-{field}")
            command[field] = value
            with self.subTest(field=field), self.assertRaises(
                EpisodeProductionPublicError
            ) as missing:
                seed["boundary"].create_narrative_validation(command)
            self.assertEqual((missing.exception.status, missing.exception.code), (404, "not_found"))

    def test_stale_m6_rejects_create_and_projects_existing_validation_stale(self):
        seed = seed_m7()
        current = seed["boundary"].create_narrative_validation(
            validation_command(seed)
        )
        replacement = advance_m6(seed)
        self.assertEqual(replacement["activationRevision"], 2)
        projected = seed["boundary"].get_narrative_validation(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
            current["consistencyValidationVersionRef"],
        )
        self.assertEqual(projected["currentness"], "STALE")
        with self.assertRaises(EpisodeProductionPublicError) as stale:
            seed["boundary"].create_narrative_validation(
                validation_command(seed, key="m7-after-m6-change")
            )
        self.assertEqual(stale.exception.code, "stale_input")

    def test_stale_script_rejects_create_and_does_not_rewrite_confirmed_version(self):
        seed = seed_m7()
        current = seed["boundary"].create_narrative_validation(
            validation_command(seed)
        )
        content = script_content(seed["bound"]["scriptVersion"])
        content["title"] += " draft"
        draft = seed["assembly"].script_studio.create_version(
            {
                "workspaceRef": WORKSPACE,
                "projectRef": seed["project"]["projectRef"],
                "seriesRef": seed["series"]["seriesRef"],
                "episodeRef": seed["episode"]["episodeRef"],
                "scriptRef": seed["bound"]["script"]["scriptRef"],
                "baseScriptVersionRef": seed["bound"]["scriptVersion"]["scriptVersionRef"],
                "changeKind": "manual-edit",
                "content": content,
            }
        )
        self.assertNotEqual(
            draft["scriptVersion"]["scriptVersionRef"], current["scriptVersionRef"]
        )
        projected = seed["boundary"].get_narrative_validation(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
            current["consistencyValidationVersionRef"],
        )
        self.assertEqual(projected["currentness"], "STALE")
        with self.assertRaises(EpisodeProductionPublicError) as stale:
            seed["boundary"].create_narrative_validation(
                validation_command(seed, key="m7-after-script-change")
            )
        self.assertEqual(stale.exception.code, "stale_input")


if __name__ == "__main__":
    unittest.main()
