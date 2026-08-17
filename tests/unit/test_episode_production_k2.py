import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    SqliteMediaJobAdapter,
    V4CompositionExecutor,
)

from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    RejectingApprovalAuthority,
    StaticApprovalAuthority,
    StaticIdentityReferenceAuthority,
    create_in_memory_boundary,
    create_local_development_boundary,
    validate_executable_shot_graph,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_intelligence import M6Scope, VerifiedApproval
from services.v5_core_os.series_intelligence.errors import AuthorityUnavailableError
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE = "workspace-k2"
PROFILE = "content-profile-k2"


class K2ScopeAuthority:
    def resolve_scope(self, workspace_ref, project_ref, series_ref):
        return M6Scope(
            "series-production",
            f"tenant-{workspace_ref}",
            workspace_ref,
            project_ref,
            series_ref,
        )


class K2ApprovalAuthority:
    def verify_approval(self, *, scope, approval_ref, action):
        del scope, action
        if approval_ref != "approval-human":
            raise AuthorityUnavailableError()
        return VerifiedApproval(approval_ref, "actor-owner", "human")


class Refs:
    def __init__(self):
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-k2-{self.counts[prefix]}"


def k2_script_content(*, second_scene_suffix=""):
    return {
        "title": "记忆回声",
        "logline": "林澈与顾言在封存档案前确认一段被抹去的共同记忆。",
        "synopsis": "两人在中央记忆档案城追索同一段异常影像，并决定暂时共同保留证据。",
        "targetDurationSec": 30,
        "scenes": [
            {
                "sceneNumber": 1,
                "heading": "中央记忆档案城·校验台",
                "location": "中央记忆档案城",
                "timeOfDay": "雨夜",
                "characters": ["林澈", "顾言"],
                "action": "林澈将异常记忆片放入校验台，顾言封锁外部检索通道。",
                "dialogue": [
                    {"speaker": "顾言", "text": "从现在起，只相信我们亲眼看到的。", "emotion": "克制"}
                ],
                "narration": [],
                "subtitleText": ["只相信亲眼看到的"],
                "estimatedDurationSec": 14,
                "scenePurpose": "建立共同目标与外部压力",
                "continuityNotes": ["林澈右袖银灰粉尘保持一致"],
                "productionNotes": ["冷蓝环境，校验台使用琥珀色实景光"],
            },
            {
                "sceneNumber": 2,
                "heading": "中央记忆档案城·外环廊桥",
                "location": "外环廊桥",
                "timeOfDay": "雨夜",
                "characters": ["林澈", "顾言"],
                "action": "两人看见被系统判定为不存在的童年影像，并分别保存一份校验摘要。"
                + second_scene_suffix,
                "dialogue": [
                    {"speaker": "林澈", "text": "它被删掉了，但没有消失。", "emotion": "坚定"}
                ],
                "narration": [],
                "subtitleText": ["被删掉，不等于消失"],
                "estimatedDurationSec": 16,
                "scenePurpose": "完成证据确认并建立有限信任",
                "continuityNotes": ["两人衣着、雨向与记忆片编号连续"],
                "productionNotes": ["远景建立城市尺度，结尾停留两秒"],
            },
        ],
    }


def seed_k2_roots(
    *, bind_episode=True, confirm_script=True, with_m6_authority=False
):
    refs = Refs()
    clock = lambda: "2026-08-17T00:00:00Z"
    assembly = LifecycleAssembly.in_memory(
        ref_factory=refs,
        clock=clock,
        m6_scope_authority=K2ScopeAuthority() if with_m6_authority else None,
        m6_approval_authority=K2ApprovalAuthority() if with_m6_authority else None,
    )
    series = assembly.series_episode.create_series(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": "未来之城",
            "description": "K2 单集制作链",
            "plannedEpisodeCount": 1,
        }
    )
    project = assembly.project_context.create_project(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "projectType": "series",
            "seriesRef": series["seriesRef"],
            "title": "未来之城 K2",
            "description": "本地证据单集",
            "targetPlatform": "technical-evidence",
            "aspectRatio": "16:9",
            "plannedEpisodeCount": 1,
        }
    )
    director_plan = valid_plan()
    director_plan["storyDirection"]["title"] = "记忆回声"
    director_plan["productionPlan"]["characters"] = ["林澈", "顾言"]
    confirmed_creative = assembly.series_episode.confirm_creative_plan(
        {
            "workspaceRef": WORKSPACE,
            "humanConfirmed": True,
            "sourcePlanRef": "director-plan-k2",
            "sourcePlanSchemaVersion": director_plan["schemaVersion"],
            "sourcePlanVersion": 1,
            "brief": valid_brief(),
            "sourcePlan": director_plan,
        }
    )
    episode = assembly.series_episode.create_episode(
        {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": confirmed_creative["creativePlanRef"],
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "记忆回声",
        }
    )
    candidate = valid_candidate(1)
    candidate["seriesConcept"] = "围绕记忆权利展开的单集科幻短片。"
    candidate["episodePlanItems"][0]["title"] = "记忆回声"
    initial_plan = assembly.series_planning.confirm_candidate(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": candidate,
        }
    )
    if bind_episode:
        bound = assembly.series_planning.create_episode_plan_item_binding_version(
            {
                "workspaceRef": WORKSPACE,
                "projectRef": project["projectRef"],
                "seriesRef": series["seriesRef"],
                "seriesPlanRef": initial_plan["plan"]["seriesPlanRef"],
                "expectedPlanVersion": initial_plan["plan"]["version"],
                "episodePlanItemBindings": [
                    {
                        "episodeRef": episode["episodeRef"],
                        "episodePlanItemRef": initial_plan["version"]["episodePlanItems"][0]["episodePlanItemRef"],
                    }
                ],
            }
        )
        assembly.series_planning.confirm_version(
            {
                "workspaceRef": WORKSPACE,
                "seriesPlanRef": bound["plan"]["seriesPlanRef"],
                "seriesPlanVersionRef": bound["version"]["seriesPlanVersionRef"],
                "expectedPlanVersion": bound["plan"]["version"],
                "humanConfirmed": True,
            }
        )
    generated = assembly.script_studio.create_version(
        {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "changeKind": "ai-generation",
            "content": k2_script_content(),
        }
    )
    if confirm_script:
        assembly.script_studio.confirm_version(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "episodeRef": episode["episodeRef"],
                "scriptRef": generated["script"]["scriptRef"],
                "scriptVersionRef": generated["scriptVersion"]["scriptVersionRef"],
                "humanConfirmed": True,
            }
        )
    return assembly, refs, project, series, episode, generated


def activate_k2_m6_baseline(assembly, project, series):
    context = {
        "workspaceRef": WORKSPACE,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
    }

    def command(operation):
        return {
            **context,
            "operationRef": operation,
            "idempotencyKey": operation,
        }

    bible_content = {
        "worldRules": [
            {"worldRuleRef": "world-rule-memory", "statement": "记忆可复制但不可无痕恢复"}
        ],
        "glossaryTerms": [
            {"glossaryTermRef": "term-memory-chip", "term": "记忆片", "definition": "可验证的记忆载体"}
        ],
        "locations": [
            {"locationRef": "location-archive-city", "name": "中央记忆档案城"}
        ],
        "factions": [{"factionRef": "faction-council", "name": "记忆议会"}],
        "props": [{"propRef": "prop-memory-chip", "name": "异常记忆片"}],
        "timelineEvents": [
            {
                "timelineEventRef": "event-memory-erasure",
                "summary": "一段共同记忆被系统抹除",
                "locationRef": "location-archive-city",
                "factionRefs": ["faction-council"],
                "propRefs": ["prop-memory-chip"],
            }
        ],
        "visualConstraints": [
            {"visualConstraintRef": "visual-cold-amber", "rule": "冷蓝环境与琥珀实景光并存"}
        ],
        "prohibitedNarrativePatterns": [
            {"prohibitedNarrativePatternRef": "ban-memory-magic", "rule": "记忆恢复必须有可追溯载体"}
        ],
    }
    bible = assembly.series_intelligence.create_bible_version(
        {**command("k2-bible-create"), "candidate": True, "content": bible_content}
    )
    bible = assembly.series_intelligence.confirm_bible_version(
        {
            **command("k2-bible-confirm"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "expectedRevision": bible["root"]["revision"],
            "approvalRef": "approval-human",
        }
    )
    source = assembly.series_planning.get_confirmed_m6_source_snapshot(
        WORKSPACE, project["projectRef"], series["seriesRef"]
    )
    episode_items = [
        item["episodePlanItemRef"] for item in source["episodePlanItems"]
    ]
    character_content = {
        "characters": [
            {
                "characterRef": "character-lin",
                "name": "林澈",
                "background": "中央档案城的记忆修复师",
                "motivation": "找回被抹除的共同记忆",
                "belief": "被记录的事实仍可证明一个人存在",
                "conflict": "必须在制度秩序与个人真相之间选择",
                "goal": "验证异常记忆片并保存证据",
                "personality": "克制、敏锐、坚持证据",
                "behaviorRules": ["先验证再行动", "压力下保持低声表达"],
                "dialogueRules": ["短句", "避免情绪化修饰"],
                "forbiddenBehavior": ["不得无证据地信任系统结论"],
                "visualIdentityRules": ["黑色短发", "深色功能风衣", "右袖银灰粉尘"],
            },
            {
                "characterRef": "character-gu",
                "name": "顾言",
                "background": "记忆议会的档案监察员",
                "motivation": "阻止异常记忆被再次销毁",
                "belief": "程序只有在能够接受校验时才值得服从",
                "conflict": "职责要求上报，良知要求保护证据",
                "goal": "封锁检索通道并确认记忆片来源",
                "personality": "审慎、内敛、行动果断",
                "behaviorRules": ["先控制风险再解释", "只承诺可执行事项"],
                "dialogueRules": ["低声短句", "使用明确动词"],
                "forbiddenBehavior": ["不得泄露未确认档案"],
                "visualIdentityRules": ["灰白短发", "深灰监察制服", "琥珀色身份灯"],
            },
        ],
        "stateIntervals": [
            {
                "intervalRef": "interval-lin-location",
                "characterRef": "character-lin",
                "category": "Location",
                "startEpisodePlanItemRef": episode_items[0],
                "endEpisodePlanItemRef": None,
                "valueRef": "location-archive-city",
            },
            {
                "intervalRef": "interval-gu-location",
                "characterRef": "character-gu",
                "category": "Location",
                "startEpisodePlanItemRef": episode_items[0],
                "endEpisodePlanItemRef": None,
                "valueRef": "location-archive-city",
            },
        ],
        "relationships": [
            {
                "relationshipRef": "relationship-lin-gu",
                "fromCharacterRef": "character-lin",
                "toCharacterRef": "character-gu",
                "relationshipType": "limited-trust",
                "startEpisodePlanItemRef": episode_items[0],
                "endEpisodePlanItemRef": None,
            }
        ],
        "identityBindings": [],
    }
    characters = assembly.series_intelligence.create_character_version(
        {
            **command("k2-character-create"),
            "candidate": True,
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "content": character_content,
        }
    )
    characters = assembly.series_intelligence.confirm_character_version(
        {
            **command("k2-character-confirm"),
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedRevision": characters["root"]["revision"],
            "approvalRef": "approval-human",
        }
    )
    return assembly.series_intelligence.activate_baseline(
        {
            **command("k2-baseline-activate"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-human",
        }
    )


def k2_identity_authority(*, lin_digest=None):
    def reference(character_ref, media_type):
        return {
            "referenceRef": f"identity-reference-{character_ref}",
            "referenceVersionRef": f"identity-reference-version-{character_ref}-1",
            "contentDigest": (
                lin_digest
                if character_ref == "character-lin" and lin_digest is not None
                else sha256(f"{character_ref}:local-reference:v1".encode()).hexdigest()
            ),
            "mediaType": media_type,
            "rightsState": "LOCAL_EVIDENCE_ONLY",
            "provenance": "LOCAL_EVIDENCE",
            "approvalRef": f"local-evidence-approval-{character_ref}",
        }

    return StaticIdentityReferenceAuthority(
        {
            "character-lin": reference("character-lin", "image"),
            "character-gu": reference("character-gu", "identity-direction"),
        }
    )


def g2_command(run, **extra):
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run["productionRunRef"],
        "idempotencyKey": "k2-authority-identity-v1",
        "characterMappings": [
            {"scriptCharacterName": "林澈", "characterRef": "character-lin"},
            {"scriptCharacterName": "顾言", "characterRef": "character-gu"},
        ],
        **extra,
    }


def g3_command(run, **extra):
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run["productionRunRef"],
        "idempotencyKey": "k2-shot-graph-v1",
        "sceneBindings": [
            {
                "scriptSceneRef": budget["scriptSceneRef"],
                "locationRef": "location-archive-city",
                "propRefs": ["prop-memory-chip"],
            }
            for budget in run["manifest"]["sceneBudgets"]
        ],
        **extra,
    }


def g4_command(run, **extra):
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run["productionRunRef"],
        "idempotencyKey": "k2-asset-resolution-v1",
        **extra,
    }


def g5_command(run, **extra):
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run["productionRunRef"],
        "idempotencyKey": "k2-media-execution-v1",
        **extra,
    }


def g6_preview_command(run, **extra):
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run["productionRunRef"],
        "idempotencyKey": "k2-preview-qc-v1",
        **extra,
    }


def g6_decisions(run):
    return [
        {
            "kind": kind,
            "decision": "ACCEPT",
            "approvalRef": f"approval-{kind.lower().replace('_', '-')}",
            "actorRef": "actor-project-lead",
        }
        for kind in (
            "CREATIVE_DIRECTION",
            "IDENTITY_CONTINUITY",
            "TECHNICAL_QC",
            "FINAL_MASTER",
        )
    ]


def g6_approval_authority(run_ref):
    return StaticApprovalAuthority(
        {
            item["approvalRef"]: {
                "workspaceRef": WORKSPACE,
                "productionRunRef": run_ref,
                "kind": item["kind"],
                "actorRef": item["actorRef"],
                "authorityType": "HUMAN",
            }
            for item in g6_decisions({"productionRunRef": run_ref})
        }
    )


def g6_finalize_command(run, **extra):
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run["productionRunRef"],
        "idempotencyKey": "k2-approval-master-v1",
        "decisions": g6_decisions(run),
        **extra,
    }


def create_boundary(
    assembly,
    refs,
    *,
    database=None,
    evidence_database=None,
    identity_reference_authority=None,
):
    kwargs = {
        "project_boundary": assembly.project_context,
        "series_episode_boundary": assembly.series_episode,
        "series_planning_boundary": assembly.series_planning,
        "script_studio_boundary": assembly.script_studio,
    }
    if database is None:
        return create_in_memory_boundary(
            **kwargs,
            identity_reference_authority=identity_reference_authority,
            ref_factory=refs,
            clock=lambda: "2026-08-17T00:05:00Z",
        )
    return create_local_development_boundary(
        database,
        **kwargs,
        evidence_database_path=evidence_database,
        identity_reference_authority=identity_reference_authority,
    )


def run_command(project, series, episode, **extra):
    return {
        "workspaceRef": WORKSPACE,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "episodeRef": episode["episodeRef"],
        "idempotencyKey": "k2-golden-episode-v1",
        "shotsPerScene": [2, 2],
        **extra,
    }


class EpisodeProductionK2RootTests(unittest.TestCase):
    def test_creates_frozen_authoritative_root_with_complete_upstream_lineage(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots()
        boundary = create_boundary(assembly, refs)
        run = boundary.create_run(run_command(project, series, episode))

        self.assertEqual(run["state"], "ROOTS_READY")
        self.assertEqual(run["manifest"]["executionMode"], "LOCAL_EVIDENCE")
        self.assertFalse(run["manifest"]["publicationAllowed"])
        self.assertEqual(run["manifest"]["expectedSceneCount"], 2)
        self.assertEqual(run["manifest"]["expectedShotCount"], 4)
        self.assertEqual(run["manifest"]["requiredCharacterNames"], ["林澈", "顾言"])
        self.assertEqual(run["upstreamSnapshot"]["episode"]["episodeRef"], episode["episodeRef"])
        self.assertEqual(len(run["upstreamDigest"]), 64)
        self.assertEqual(len(run["payloadDigest"]), 64)
        self.assertFalse(run["idempotentReplay"])

    def test_idempotent_replay_is_stable_and_changed_payload_conflicts(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots()
        boundary = create_boundary(assembly, refs)
        first = boundary.create_run(run_command(project, series, episode))
        second = boundary.create_run(run_command(project, series, episode))
        self.assertEqual(first["productionRunRef"], second["productionRunRef"])
        self.assertTrue(second["idempotentReplay"])

        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.create_run(
                run_command(project, series, episode, shotsPerScene=[3, 2])
            )
        self.assertEqual((caught.exception.status, caught.exception.code), (409, "idempotency_conflict"))

    def test_manifest_counts_require_real_integers(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots()
        boundary = create_boundary(assembly, refs)
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.create_run(
                run_command(project, series, episode, shotsPerScene=[2.0, 2])
            )
        self.assertEqual((caught.exception.status, caught.exception.code), (400, "invalid_request"))

    def test_project_context_and_series_authority_must_agree(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots()

        class DriftedSeriesBoundary:
            def get_series(self, workspace_ref, series_ref):
                value = assembly.series_episode.get_series(workspace_ref, series_ref)
                return {**value, "seriesRef": "series-drifted"}

            def get_episode(self, workspace_ref, series_ref, episode_ref):
                return assembly.series_episode.get_episode(
                    workspace_ref, series_ref, episode_ref
                )

        boundary = create_in_memory_boundary(
            project_boundary=assembly.project_context,
            series_episode_boundary=DriftedSeriesBoundary(),
            series_planning_boundary=assembly.series_planning,
            script_studio_boundary=assembly.script_studio,
            ref_factory=refs,
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.create_run(run_command(project, series, episode))
        self.assertEqual((caught.exception.status, caught.exception.code), (400, "scope_mismatch"))

    def test_unbound_plan_and_unconfirmed_script_fail_closed(self):
        for kwargs in ({"bind_episode": False}, {"confirm_script": False}):
            with self.subTest(kwargs=kwargs):
                assembly, refs, project, series, episode, _ = seed_k2_roots(**kwargs)
                boundary = create_boundary(assembly, refs)
                with self.assertRaises(EpisodeProductionPublicError) as caught:
                    boundary.create_run(run_command(project, series, episode))
                self.assertEqual(
                    (caught.exception.status, caught.exception.code),
                    (409, "upstream_not_confirmed"),
                )

    def test_workspace_isolation_hides_existing_run(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots()
        boundary = create_boundary(assembly, refs)
        run = boundary.create_run(run_command(project, series, episode))
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.get_run("workspace-other", run["productionRunRef"])
        self.assertEqual((caught.exception.status, caught.exception.code), (404, "not_found"))

    def test_dedicated_sqlite_store_survives_restart_without_mutating_lifecycle_storage(self):
        assembly, _, project, series, episode, _ = seed_k2_roots()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-production.sqlite3"
            first_boundary = create_boundary(assembly, None, database=database)
            first = first_boundary.create_run(run_command(project, series, episode))
            second_boundary = create_boundary(assembly, None, database=database)
            restored = second_boundary.get_run(WORKSPACE, first["productionRunRef"])
            self.assertEqual(restored["payloadDigest"], first["payloadDigest"])
            self.assertEqual(restored["manifest"], first["manifest"])
            self.assertEqual(
                {row[0] for row in sqlite_tables(database)},
                {"v5_episode_production_schema", "v5_episode_production_runs"},
            )


class EpisodeProductionG2AuthorityIdentityTests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            self.generated,
        ) = seed_k2_roots(with_m6_authority=True)
        self.baseline = activate_k2_m6_baseline(
            self.assembly, self.project, self.series
        )

    def boundary(self, **kwargs):
        return create_boundary(
            self.assembly,
            self.refs,
            identity_reference_authority=k2_identity_authority(),
            **kwargs,
        )

    def test_records_separate_m6_decision_and_identity_lock_with_full_lineage(self):
        boundary = self.boundary()
        run = boundary.create_run(run_command(self.project, self.series, self.episode))
        result = boundary.authorize_and_lock(g2_command(run))

        authority = result["authorityDecision"]
        identity = result["identityLock"]
        self.assertEqual(result["state"], "AUTHORITY_READY")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(authority["decision"], "AUTHORIZED")
        self.assertEqual(authority["rootPayloadDigest"], run["payloadDigest"])
        self.assertEqual(
            authority["m6BaselineSnapshotRef"],
            self.baseline["m6BaselineSnapshotRef"],
        )
        self.assertEqual(authority["scriptVersionRef"], run["scriptVersionRef"])
        self.assertEqual(identity["state"], "LOCKED")
        self.assertNotEqual(
            authority["authorityDecisionRef"], identity["identityLockRef"]
        )
        self.assertEqual(
            identity["authorityDecisionDigest"], authority["payloadDigest"]
        )
        self.assertEqual(
            [item["scriptCharacterName"] for item in identity["identities"]],
            ["林澈", "顾言"],
        )
        self.assertEqual(
            set(identity["identities"][0]["reference"]),
            {
                "referenceRef", "referenceVersionRef", "contentDigest",
                "mediaType", "rightsState", "provenance", "approvalRef",
            },
        )
        projected = boundary.get_run(WORKSPACE, run["productionRunRef"])
        self.assertEqual(projected["state"], "AUTHORITY_READY")
        self.assertEqual(projected["completedGates"], ["G2_AUTHORITY_IDENTITY"])

    def test_replay_is_stable_and_changed_semantics_conflict(self):
        boundary = self.boundary()
        run = boundary.create_run(run_command(self.project, self.series, self.episode))
        first = boundary.authorize_and_lock(g2_command(run))
        replay = boundary.authorize_and_lock(g2_command(run))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["identityLock"], first["identityLock"])

        changed = g2_command(
            run,
            characterMappings=[
                {"scriptCharacterName": "林澈", "characterRef": "character-gu"},
                {"scriptCharacterName": "顾言", "characterRef": "character-lin"},
            ],
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.authorize_and_lock(changed)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "idempotency_conflict"),
        )

    def test_mapping_must_be_explicit_complete_and_one_to_one(self):
        boundary = self.boundary()
        run = boundary.create_run(run_command(self.project, self.series, self.episode))
        invalid_mappings = (
            [{"scriptCharacterName": "林澈", "characterRef": "character-lin"}],
            [
                {"scriptCharacterName": "林澈", "characterRef": "character-lin"},
                {"scriptCharacterName": "顾言", "characterRef": "character-lin"},
            ],
            [
                {"scriptCharacterName": "林澈", "characterRef": "character-lin"},
                {"scriptCharacterName": "陌生人", "characterRef": "character-gu"},
            ],
        )
        for index, mappings in enumerate(invalid_mappings):
            with self.subTest(index=index), self.assertRaises(
                EpisodeProductionPublicError
            ) as caught:
                boundary.authorize_and_lock(
                    g2_command(run, idempotencyKey=f"invalid-{index}", characterMappings=mappings)
                )
            self.assertEqual(
                (caught.exception.status, caught.exception.code),
                (400, "invalid_request"),
            )

    def test_missing_m6_or_identity_authority_fails_closed(self):
        run_boundary = create_boundary(self.assembly, self.refs)
        run = run_boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        with self.assertRaises(EpisodeProductionPublicError) as identity_missing:
            run_boundary.authorize_and_lock(g2_command(run))
        self.assertEqual(
            (identity_missing.exception.status, identity_missing.exception.code),
            (403, "authority_required"),
        )

        assembly, refs, project, series, episode, _ = seed_k2_roots()
        no_m6 = create_boundary(
            assembly,
            refs,
            identity_reference_authority=k2_identity_authority(),
        )
        run = no_m6.create_run(run_command(project, series, episode))
        with self.assertRaises(EpisodeProductionPublicError) as m6_missing:
            no_m6.authorize_and_lock(g2_command(run))
        self.assertEqual(
            (m6_missing.exception.status, m6_missing.exception.code),
            (403, "authority_required"),
        )

    def test_changed_confirmed_script_makes_frozen_root_stale(self):
        boundary = self.boundary()
        run = boundary.create_run(run_command(self.project, self.series, self.episode))
        content = {
            key: self.generated["scriptVersion"][key]
            for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")
        }
        content = json.loads(json.dumps(content, ensure_ascii=False))
        content["scenes"][1]["action"] += " 系统发出二次封存警报。"
        changed = self.assembly.script_studio.create_version(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": self.series["seriesRef"],
                "episodeRef": self.episode["episodeRef"],
                "scriptRef": self.generated["script"]["scriptRef"],
                "baseScriptVersionRef": self.generated["scriptVersion"]["scriptVersionRef"],
                "changeKind": "manual-edit",
                "content": content,
            }
        )
        self.assembly.script_studio.confirm_version(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": self.series["seriesRef"],
                "episodeRef": self.episode["episodeRef"],
                "scriptRef": changed["script"]["scriptRef"],
                "scriptVersionRef": changed["scriptVersion"]["scriptVersionRef"],
                "humanConfirmed": True,
            }
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.authorize_and_lock(g2_command(run))
        self.assertEqual(
            (caught.exception.status, caught.exception.code), (409, "stale_input")
        )

    def test_scope_isolation_hides_g2_facts(self):
        boundary = self.boundary()
        run = boundary.create_run(run_command(self.project, self.series, self.episode))
        boundary.authorize_and_lock(g2_command(run))
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.get_authority_identity(
                "workspace-other", run["productionRunRef"]
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code), (404, "not_found")
        )

    def test_evidence_sqlite_restart_preserves_exact_additive_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-production.sqlite3"
            evidence = Path(directory) / "episode-evidence.sqlite3"
            first_boundary = create_boundary(
                self.assembly,
                None,
                database=database,
                evidence_database=evidence,
                identity_reference_authority=k2_identity_authority(),
            )
            run = first_boundary.create_run(
                run_command(self.project, self.series, self.episode)
            )
            first = first_boundary.authorize_and_lock(g2_command(run))
            second_boundary = create_boundary(
                self.assembly,
                None,
                database=database,
                evidence_database=evidence,
                identity_reference_authority=k2_identity_authority(),
            )
            restored = second_boundary.get_authority_identity(
                WORKSPACE, run["productionRunRef"]
            )
            self.assertEqual(restored["identityLock"], first["identityLock"])
            self.assertEqual(
                {row[0] for row in sqlite_tables(evidence)},
                {
                    "v5_episode_production_evidence_schema",
                    "v5_episode_production_gates",
                    "v5_episode_production_facts",
                    "v5_episode_production_transitions",
                },
            )
            self.assertEqual(
                {row[0] for row in sqlite_tables(database)},
                {"v5_episode_production_schema", "v5_episode_production_runs"},
            )


class EpisodeProductionG3ShotGraphTests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            self.generated,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(self.assembly, self.project, self.series)

    def boundary(self, **kwargs):
        return create_boundary(
            self.assembly,
            self.refs,
            identity_reference_authority=k2_identity_authority(),
            **kwargs,
        )

    def prepared(self, boundary):
        run = boundary.create_run(run_command(self.project, self.series, self.episode))
        boundary.authorize_and_lock(g2_command(run))
        return run

    def test_compiles_exact_executable_graph_with_authoritative_lineage(self):
        boundary = self.boundary()
        run = self.prepared(boundary)
        result = boundary.compile_shot_graph(g3_command(run))

        graph = result["executableShotGraph"]
        shots = result["creativeShotVersions"]
        self.assertEqual(result["state"], "SHOTS_COMPILED")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(len(result["storyboardVersion"]["scenes"]), 2)
        self.assertEqual(len(shots), 4)
        self.assertEqual(graph["output"]["frameRate"], 24)
        self.assertEqual(graph["output"]["totalFrames"], 720)
        self.assertEqual(sum(shot["durationFrames"] for shot in shots[:2]), 336)
        self.assertEqual(sum(shot["durationFrames"] for shot in shots[2:]), 384)
        self.assertEqual(
            [shot["globalOrder"] for shot in shots], [1, 2, 3, 4]
        )
        self.assertEqual(
            {
                identity["characterRef"]
                for shot in shots
                for identity in shot["requiredCharacterIdentityLocks"]
            },
            {"character-lin", "character-gu"},
        )
        for shot in shots:
            self.assertTrue(shot["sourceScriptSpans"])
            self.assertEqual(
                {
                    seed["requirementType"]
                    for seed in shot["assetRequirementSeeds"]
                },
                {"character-identity", "location", "prop", "visual-style"},
            )
        validate_executable_shot_graph(graph)
        projected = boundary.get_run(WORKSPACE, run["productionRunRef"])
        self.assertEqual(projected["state"], "SHOTS_COMPILED")
        self.assertEqual(
            projected["completedGates"],
            ["G2_AUTHORITY_IDENTITY", "G3_SCRIPT_VALIDATION", "G3_SHOT_GRAPH"],
        )

    def test_replay_is_stable_and_scene_bindings_fail_closed(self):
        boundary = self.boundary()
        run = self.prepared(boundary)
        first = boundary.compile_shot_graph(g3_command(run))
        replay = boundary.compile_shot_graph(g3_command(run))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["executableShotGraph"], first["executableShotGraph"])

        second_boundary = self.boundary()
        second_run = self.prepared(second_boundary)
        invalid = g3_command(second_run)
        invalid["sceneBindings"] = invalid["sceneBindings"][:1]
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            second_boundary.compile_shot_graph(invalid)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "validation_failed"),
        )

        invalid = g3_command(second_run)
        invalid["idempotencyKey"] = "g3-invalid-authority-ref"
        invalid["sceneBindings"][0]["locationRef"] = "location-invented"
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            second_boundary.compile_shot_graph(invalid)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "validation_failed"),
        )

    def test_graph_validator_rejects_structural_tampering_and_cycles(self):
        boundary = self.boundary()
        run = self.prepared(boundary)
        graph = boundary.compile_shot_graph(g3_command(run))["executableShotGraph"]

        duplicate = json.loads(json.dumps(graph, ensure_ascii=False))
        duplicate["shots"][1]["creativeShotRef"] = duplicate["shots"][0]["creativeShotRef"]
        with self.assertRaisesRegex(Exception, "duplicate shot refs"):
            validate_executable_shot_graph(duplicate)

        unresolved = json.loads(json.dumps(graph, ensure_ascii=False))
        unresolved["shots"][0]["assetRequirementSeeds"] = []
        with self.assertRaisesRegex(Exception, "asset requirement"):
            validate_executable_shot_graph(unresolved)

        cycle = json.loads(json.dumps(graph, ensure_ascii=False))
        cycle["edges"].append(
            {
                "edgeRef": "shot-edge-cycle",
                "edgeType": "continuity",
                "fromShotRef": cycle["shots"][-1]["creativeShotRef"],
                "toShotRef": cycle["shots"][0]["creativeShotRef"],
            }
        )
        with self.assertRaisesRegex(Exception, "cycle"):
            validate_executable_shot_graph(cycle)

    def test_shot_graph_is_workspace_isolated_and_survives_sqlite_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-production.sqlite3"
            evidence = Path(directory) / "episode-evidence.sqlite3"
            first = create_boundary(
                self.assembly,
                None,
                database=database,
                evidence_database=evidence,
                identity_reference_authority=k2_identity_authority(),
            )
            run = self.prepared(first)
            compiled = first.compile_shot_graph(g3_command(run))
            second = create_boundary(
                self.assembly,
                None,
                database=database,
                evidence_database=evidence,
                identity_reference_authority=k2_identity_authority(),
            )
            restored = second.get_shot_graph_bundle(
                WORKSPACE, run["productionRunRef"]
            )
            self.assertEqual(
                restored["executableShotGraph"], compiled["executableShotGraph"]
            )
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                second.get_shot_graph_bundle(
                    "workspace-other", run["productionRunRef"]
                )
            self.assertEqual(
                (caught.exception.status, caught.exception.code), (404, "not_found")
            )


class EpisodeProductionG4AssetResolutionTests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(self.assembly, self.project, self.series)
        self.boundary = create_boundary(
            self.assembly,
            self.refs,
            identity_reference_authority=k2_identity_authority(),
        )
        self.run = self.boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        self.boundary.authorize_and_lock(g2_command(self.run))
        self.boundary.compile_shot_graph(g3_command(self.run))

    def test_resolves_all_authority_requirements_and_emits_provider_neutral_requests(self):
        result = self.boundary.resolve_assets(g4_command(self.run))
        manifest = result["assetResolutionManifest"]
        requirements = result["assetRequirements"]
        requests = result["generationRequests"]

        self.assertEqual(result["state"], "ASSETS_READY")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(manifest["summary"], {
            "requirements": 13,
            "resolvedAuthority": 5,
            "generationRequested": 8,
            "blocked": 0,
            "generationRequests": 8,
        })
        self.assertEqual(len(requirements), 13)
        self.assertEqual(len(requests), 8)
        self.assertEqual(
            {item["resolutionState"] for item in requirements},
            {"RESOLVED_AUTHORITY", "GENERATION_REQUESTED"},
        )
        self.assertEqual(
            {(item["creativeShotRef"], item["mediaKind"]) for item in requests},
            {
                (shot["creativeShotRef"], kind)
                for shot in self.boundary.get_shot_graph_bundle(
                    WORKSPACE, self.run["productionRunRef"]
                )["creativeShotVersions"]
                for kind in ("video", "audio")
            },
        )
        for item in requests:
            self.assertEqual(item["providerSelection"], "UNSELECTED")
            self.assertEqual(item["requestedProvenance"], "LOCAL_EVIDENCE")
            self.assertFalse(item["publicationAllowed"])
            self.assertIn(item["adapterCapability"], {
                "deterministic-local-video-v1",
                "deterministic-local-audio-v1",
            })
            self.assertNotIn("path", json.dumps(item).lower())
        projected = self.boundary.get_run(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(projected["state"], "ASSETS_READY")
        self.assertEqual(projected["completedGates"][-1], "G4_ASSET_RESOLUTION")

    def test_replay_is_stable_and_g4_cannot_skip_g3(self):
        first = self.boundary.resolve_assets(g4_command(self.run))
        replay = self.boundary.resolve_assets(g4_command(self.run))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["assetResolutionManifest"], first["assetResolutionManifest"])

        assembly, refs, project, series, episode, _ = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        boundary = create_boundary(
            assembly,
            refs,
            identity_reference_authority=k2_identity_authority(),
        )
        run = boundary.create_run(run_command(project, series, episode))
        boundary.authorize_and_lock(g2_command(run))
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.resolve_assets(g4_command(run))
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "upstream_not_confirmed"),
        )

    def test_g4_plan_is_workspace_isolated(self):
        self.boundary.resolve_assets(g4_command(self.run))
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.get_asset_plan(
                "workspace-other", self.run["productionRunRef"]
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code), (404, "not_found")
        )


class EpisodeProductionG5MediaExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(self.assembly, self.project, self.series)
        self.execution = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            DeterministicLocalFfmpegAdapter(),
            Path(self.directory.name) / "artifacts",
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T01:00:00Z",
        )
        self.boundary = create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            media_execution=self.execution,
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T01:00:00Z",
        )
        self.run = self.boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        self.boundary.authorize_and_lock(g2_command(self.run))
        self.boundary.compile_shot_graph(g3_command(self.run))
        self.boundary.resolve_assets(g4_command(self.run))

    def tearDown(self):
        self.directory.cleanup()

    def test_executes_real_local_media_and_registers_verified_immutable_assets(self):
        result = self.boundary.execute_media(g5_command(self.run))
        self.assertEqual(result["state"], "MEDIA_READY")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(result["mediaManifest"]["summary"], {
            "requested": 8,
            "verifiedResults": 8,
            "registeredAssets": 8,
            "videoAssets": 4,
            "audioAssets": 4,
            "failed": 0,
        })
        self.assertEqual(len(result["assetVersions"]), 8)
        self.assertEqual(len(result["generationResults"]), 8)
        self.assertTrue(all(job["state"] == "SUCCEEDED" for job in result["jobs"]))
        self.assertTrue(all(job["gpuUsed"] is False for job in result["jobs"]))
        self.assertNotIn("internalPath", json.dumps(result, ensure_ascii=False))
        root = self.execution.artifact_root.resolve()
        for asset in result["assetVersions"]:
            path = (root / asset["storageKey"]).resolve()
            self.assertIn(root, path.parents)
            self.assertTrue(path.is_file())
            self.assertGreater(asset["byteSize"], 0)
            self.assertEqual(len(asset["sha256"]), 64)
            self.assertEqual(asset["provenance"], "LOCAL_EVIDENCE")
            self.assertEqual(asset["rightsState"], "LOCAL_EVIDENCE_ONLY")
            self.assertFalse(asset["publicationAllowed"])

        replay = self.boundary.execute_media(g5_command(self.run))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            [item["assetVersionRef"] for item in replay["assetVersions"]],
            [item["assetVersionRef"] for item in result["assetVersions"]],
        )
        self.assertTrue(all(len(job["attempts"]) == 1 for job in replay["jobs"]))
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.execute_media(
                g5_command(self.run, idempotencyKey="changed-g5-command")
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "idempotency_conflict"),
        )
        self.assertEqual(
            len(self.execution.list_jobs(WORKSPACE, self.run["productionRunRef"])),
            8,
        )

    def test_unconfigured_worker_fails_closed(self):
        boundary = create_boundary(
            self.assembly,
            self.refs,
            identity_reference_authority=k2_identity_authority(),
        )
        run = boundary.create_run(
            run_command(
                self.project, self.series, self.episode,
                idempotencyKey="g5-unconfigured-run",
            )
        )
        boundary.authorize_and_lock(
            g2_command(run, idempotencyKey="g5-unconfigured-g2")
        )
        boundary.compile_shot_graph(
            g3_command(run, idempotencyKey="g5-unconfigured-g3")
        )
        boundary.resolve_assets(
            g4_command(run, idempotencyKey="g5-unconfigured-g4")
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.execute_media(
                g5_command(run, idempotencyKey="g5-unconfigured-media")
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (503, "worker_unavailable"),
        )


class EpisodeProductionG6DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(self.assembly, self.project, self.series)
        artifact_root = Path(self.directory.name) / "artifacts"
        self.execution = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            DeterministicLocalFfmpegAdapter(),
            artifact_root,
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T02:00:00Z",
        )
        expected_run_ref = "episode-production-run-k2-1"
        self.boundary = create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            media_execution=self.execution,
            composition_execution=V4CompositionExecutor.from_artifact_root(
                artifact_root
            ),
            approval_authority=g6_approval_authority(expected_run_ref),
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T02:00:00Z",
        )
        self.run = self.boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        self.assertEqual(self.run["productionRunRef"], expected_run_ref)
        self.boundary.authorize_and_lock(g2_command(self.run))
        self.boundary.compile_shot_graph(g3_command(self.run))
        self.boundary.resolve_assets(g4_command(self.run))
        self.boundary.execute_media(g5_command(self.run))

    def tearDown(self):
        self.directory.cleanup()

    def test_composes_playable_preview_qc_and_explicitly_approved_master(self):
        preview = self.boundary.compose_and_qc(g6_preview_command(self.run))
        self.assertEqual(preview["state"], "QC_READY")
        self.assertEqual(len(preview["timelineVersion"]["items"]), 4)
        self.assertEqual(
            preview["timelineVersion"]["items"][-1]["endFrameExclusive"], 720
        )
        self.assertEqual(preview["qcReport"]["result"], "PASS")
        self.assertEqual(
            {item["status"] for item in preview["qcReport"]["checks"]},
            {"PASSED"},
        )
        self.assertEqual(len(preview["qcReport"]["checks"]), 6)
        self.assertEqual(preview["previewCandidate"]["provenance"], "LOCAL_EVIDENCE")
        self.assertFalse(preview["previewCandidate"]["publicationAllowed"])

        finalized = self.boundary.approve_and_finalize(
            g6_finalize_command(self.run)
        )
        self.assertEqual(finalized["state"], "MASTER_READY")
        self.assertEqual(
            [item["kind"] for item in finalized["approvalDecisions"]],
            [
                "CREATIVE_DIRECTION",
                "IDENTITY_CONTINUITY",
                "TECHNICAL_QC",
                "FINAL_MASTER",
            ],
        )
        self.assertTrue(
            all(item["decision"] == "ACCEPT" for item in finalized["approvalDecisions"])
        )
        master = finalized["episodeMaster"]
        export = finalized["exportArtifact"]
        self.assertEqual(master["state"], "IMMUTABLE_MASTER")
        self.assertEqual(master["sha256"], export["sha256"])
        self.assertEqual(export["state"], "PLAYABLE_LOCAL_EVIDENCE")
        self.assertFalse(export["publicationAllowed"])
        artifact = self.boundary.get_export_file(
            WORKSPACE, self.run["productionRunRef"], export["exportArtifactRef"]
        )
        self.assertTrue(artifact["path"].is_file())
        self.assertEqual(
            sha256(artifact["path"].read_bytes()).hexdigest(), export["sha256"]
        )

        replay_preview = self.boundary.compose_and_qc(g6_preview_command(self.run))
        replay_master = self.boundary.approve_and_finalize(
            g6_finalize_command(self.run)
        )
        self.assertTrue(replay_preview["idempotentReplay"])
        self.assertTrue(replay_master["idempotentReplay"])
        self.assertEqual(
            replay_master["episodeMaster"]["episodeMasterVersionRef"],
            master["episodeMasterVersionRef"],
        )

    def test_rejected_or_unverified_approval_cannot_finalize(self):
        self.boundary.compose_and_qc(g6_preview_command(self.run))
        rejected = g6_finalize_command(self.run)
        rejected["decisions"][0]["decision"] = "REJECT"
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.approve_and_finalize(rejected)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "approval_rejected"),
        )

        delivery = self.boundary._EpisodeProductionPublicBoundary__delivery
        delivery.approval_authority = RejectingApprovalAuthority()
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.approve_and_finalize(g6_finalize_command(self.run))
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (403, "approval_required"),
        )
        bundle = self.boundary.get_delivery_bundle(
            WORKSPACE, self.run["productionRunRef"]
        )
        self.assertEqual(bundle["state"], "QC_READY")
        self.assertNotIn("episodeMaster", bundle)

    def test_preview_tampering_is_rejected_before_finalization(self):
        preview = self.boundary.compose_and_qc(g6_preview_command(self.run))
        path = self.execution.artifact_root / preview["previewCandidate"]["storageKey"]
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary.approve_and_finalize(g6_finalize_command(self.run))
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (422, "artifact_verification_failed"),
        )

    def test_sqlite_restart_preserves_master_lineage_and_playable_export(self):
        database = Path(self.directory.name) / "episode.sqlite3"
        evidence = Path(self.directory.name) / "evidence.sqlite3"
        jobs = Path(self.directory.name) / "jobs.sqlite3"
        artifacts = Path(self.directory.name) / "durable-artifacts"
        refs = Refs()
        execution = MediaJobCoordinator(
            SqliteMediaJobAdapter(jobs),
            DeterministicLocalFfmpegAdapter(),
            artifacts,
            ref_factory=refs,
            clock=lambda: "2026-08-17T02:30:00Z",
        )
        kwargs = {
            "project_boundary": self.assembly.project_context,
            "series_episode_boundary": self.assembly.series_episode,
            "series_planning_boundary": self.assembly.series_planning,
            "script_studio_boundary": self.assembly.script_studio,
            "evidence_database_path": evidence,
            "identity_reference_authority": k2_identity_authority(),
            "media_execution": execution,
            "composition_execution": V4CompositionExecutor.from_artifact_root(
                artifacts
            ),
            "approval_authority": g6_approval_authority(
                "episode-production-run-k2-1"
            ),
            "ref_factory": refs,
            "clock": lambda: "2026-08-17T02:30:00Z",
        }
        first = create_local_development_boundary(database, **kwargs)
        run = first.create_run(
            run_command(
                self.project,
                self.series,
                self.episode,
                idempotencyKey="g6-durable-run",
            )
        )
        first.authorize_and_lock(
            g2_command(run, idempotencyKey="g6-durable-authority")
        )
        first.compile_shot_graph(
            g3_command(run, idempotencyKey="g6-durable-shots")
        )
        first.resolve_assets(
            g4_command(run, idempotencyKey="g6-durable-assets")
        )
        first.execute_media(
            g5_command(run, idempotencyKey="g6-durable-media")
        )
        first.compose_and_qc(
            g6_preview_command(run, idempotencyKey="g6-durable-preview")
        )
        final = first.approve_and_finalize(
            g6_finalize_command(run, idempotencyKey="g6-durable-final")
        )

        restored_execution = MediaJobCoordinator(
            SqliteMediaJobAdapter(jobs, initialize_if_missing=False),
            DeterministicLocalFfmpegAdapter(),
            artifacts,
            ref_factory=refs,
            clock=lambda: "2026-08-17T02:31:00Z",
        )
        restored = create_local_development_boundary(
            database,
            **{
                **kwargs,
                "media_execution": restored_execution,
                "initialize_if_missing": False,
            },
        )
        bundle = restored.get_delivery_bundle(WORKSPACE, run["productionRunRef"])
        self.assertEqual(bundle["state"], "MASTER_READY")
        self.assertEqual(
            bundle["episodeMaster"]["payloadDigest"],
            final["episodeMaster"]["payloadDigest"],
        )
        artifact = restored.get_export_file(
            WORKSPACE,
            run["productionRunRef"],
            bundle["exportArtifact"]["exportArtifactRef"],
        )
        self.assertTrue(artifact["path"].is_file())


def sqlite_tables(path):
    import sqlite3

    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
