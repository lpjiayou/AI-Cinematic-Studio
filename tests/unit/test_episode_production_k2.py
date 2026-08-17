import json
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_in_memory_boundary,
    create_local_development_boundary,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE = "workspace-k2"
PROFILE = "content-profile-k2"


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


def seed_k2_roots(*, bind_episode=True, confirm_script=True):
    refs = Refs()
    clock = lambda: "2026-08-17T00:00:00Z"
    assembly = LifecycleAssembly.in_memory(ref_factory=refs, clock=clock)
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


def create_boundary(assembly, refs, *, database=None):
    kwargs = {
        "project_boundary": assembly.project_context,
        "series_episode_boundary": assembly.series_episode,
        "series_planning_boundary": assembly.series_planning,
        "script_studio_boundary": assembly.script_studio,
    }
    if database is None:
        return create_in_memory_boundary(
            **kwargs,
            ref_factory=refs,
            clock=lambda: "2026-08-17T00:05:00Z",
        )
    return create_local_development_boundary(database, **kwargs)


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
