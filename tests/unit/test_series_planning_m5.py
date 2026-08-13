import copy
import json
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp.series_director import (
    SERIES_PLAN_CANDIDATE_SCHEMA_VERSION,
    SeriesDirectorApplicationService,
    SeriesDirectorGenerationError,
    SeriesPlanCandidateError,
    validate_series_plan_candidate,
)
from services.v5_core_os.text_generation import (
    TextGenerationPurpose,
    TextGenerationTimeoutError,
    TextGenerationUnavailableError,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v5_core_os.project_engine import (
    create_in_memory_boundary as create_project_boundary,
    create_local_development_boundary as create_local_project_boundary,
)
from services.v5_core_os.series_episode import (
    create_in_memory_boundary as create_series_boundary,
    create_local_development_boundary as create_local_series_boundary,
)
from services.v5_core_os.series_planning import (
    SeriesPlanningPublicError,
    create_in_memory_boundary as create_planning_boundary,
    create_local_development_boundary as create_local_planning_boundary,
)


WORKSPACE = "workspace-m5"
PROFILE = "content-profile-m5"


class Refs:
    def __init__(self):
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-m5-{self.counts[prefix]}"


def valid_candidate(count=4):
    return {
        "schemaVersion": SERIES_PLAN_CANDIDATE_SCHEMA_VERSION,
        "seriesConcept": "晚灯在百集城市寓言中见证人与人的相互陪伴。",
        "premise": "一盏灯以不干预的方式守护城市夜归者。",
        "logline": "晚灯跨越不同人生阶段，串联一座城市的温暖选择。",
        "mainNarrativeDirection": "从孤独观察走向主动建立连接。",
        "mainArcs": [
            {
                "arcNumber": 1,
                "title": "相遇",
                "episodeStart": 1,
                "episodeEnd": count,
                "objective": "建立晚灯与城市居民的连接。",
                "turningPoint": "晚灯发现陪伴可以被传递。",
            }
        ],
        "subArcs": [
            {"title": "城市回声", "episodeStart": 1, "episodeEnd": count, "purpose": "连接不同人物选择。"}
        ],
        "characterArcIntents": [
            {
                "roleLabel": "晚灯",
                "startingState": "孤独观察者",
                "developmentIntent": "学会接受和传递陪伴",
                "destination": "城市共同记忆的见证者",
            }
        ],
        "episodePlanItems": [
            {
                "episodeNumber": index,
                "title": f"第{index}夜",
                "logline": f"晚灯在第{index}夜见证一次选择。",
                "arcNumber": 1,
                "narrativePurpose": "推进连接主题。",
                "continuityNotes": ["晚灯光色保持暖黄"],
                "foreshadowing": ["远处另一盏灯的回应"],
            }
            for index in range(1, count + 1)
        ],
        "narrativeRhythm": "每四集形成一次情绪起伏。",
        "worldIntent": "当代城市夜晚，现实质感与温暖光源并存。",
        "continuityIntent": ["晚灯的空间位置稳定", "人物选择产生跨集回声"],
        "foreshadowingContext": ["另一盏灯逐步靠近主叙事"],
        "productionAssumptions": ["单集30秒", "竖屏优先"],
    }


def create_context(*, local_path=None, count=4):
    refs = Refs()
    if local_path is None:
        series = create_series_boundary(ref_factory=refs)
        projects = create_project_boundary(series, ref_factory=refs)
        planning = create_planning_boundary(projects, ref_factory=refs, clock=lambda: "2026-08-10T00:00:00.000Z")
    else:
        series = create_local_series_boundary(local_path)
        projects = create_local_project_boundary(local_path, series)
        planning = create_local_planning_boundary(local_path, projects)
    series_record = series.create_series({
        "workspaceRef": WORKSPACE,
        "contentProfileRef": PROFILE,
        "title": "晚灯",
        "plannedEpisodeCount": count,
    })
    project = projects.create_project({
        "workspaceRef": WORKSPACE,
        "contentProfileRef": PROFILE,
        "projectType": "series",
        "seriesRef": series_record["seriesRef"],
        "title": "晚灯系列制作",
        "plannedEpisodeCount": count,
    })
    return series, projects, planning, series_record, project


def confirm(planning, series_record, project, candidate=None):
    return planning.confirm_candidate({
        "workspaceRef": WORKSPACE,
        "projectRef": project["projectRef"],
        "seriesRef": series_record["seriesRef"],
        "humanConfirmed": True,
        "candidate": candidate or valid_candidate(project["plannedEpisodeCount"]),
    })


class SeriesDirectorTests(unittest.TestCase):
    def test_candidate_validator_enforces_project_count_and_rejects_provider_identity(self):
        context = {"plannedEpisodeCount": 4}
        validated = validate_series_plan_candidate(valid_candidate(), context)
        self.assertEqual(len(validated["episodePlanItems"]), 4)
        invalid = valid_candidate()
        invalid["projectRef"] = "provider-project"
        with self.assertRaises(SeriesPlanCandidateError):
            validate_series_plan_candidate(invalid, context)

    def test_series_director_uses_v5_capability_and_repairs_at_most_once(self):
        invalid = valid_candidate()
        invalid["episodePlanItems"] = invalid["episodePlanItems"][:-1]
        capability = FakeTextGenerationCapability([json.dumps(invalid), json.dumps(valid_candidate())])
        result = SeriesDirectorApplicationService(capability).generate({"plannedEpisodeCount": 4}, "建立百集陪伴主线")
        self.assertEqual(len(result["episodePlanItems"]), 4)
        self.assertEqual(len(capability.commands), 2)
        self.assertTrue(all(command.purpose is TextGenerationPurpose.SERIES_PLAN_CANDIDATE for command in capability.commands))

    def test_provider_contract_contains_complete_exact_count_json_shape(self):
        capability = FakeTextGenerationCapability([json.dumps(valid_candidate(), ensure_ascii=False)])
        SeriesDirectorApplicationService(capability).generate({"plannedEpisodeCount": 4}, "建立系列主线")
        prompt = json.loads(capability.commands[0].messages[1].content)
        contract = prompt["requiredContract"]
        example = contract["completeJsonShapeExample"]
        self.assertEqual(example["schemaVersion"], SERIES_PLAN_CANDIDATE_SCHEMA_VERSION)
        self.assertEqual(len(example["episodePlanItems"]), 4)
        self.assertEqual([item["episodeNumber"] for item in example["episodePlanItems"]], [1, 2, 3, 4])
        self.assertIn("raw JSON object without Markdown code fences", " ".join(contract["rules"]))

    def test_invalid_repair_never_becomes_authoritative_candidate(self):
        capability = FakeTextGenerationCapability(["not-json", "still-not-json"])
        with self.assertRaises(SeriesDirectorGenerationError) as context:
            SeriesDirectorApplicationService(capability).generate({"plannedEpisodeCount": 4}, "系列方向")
        self.assertEqual(context.exception.code, "invalid_provider_output")
        self.assertEqual(len(capability.commands), 2)

    def test_timeout_maps_to_stable_series_director_error(self):
        capability = FakeTextGenerationCapability([TextGenerationTimeoutError(status=504)])
        with self.assertRaises(SeriesDirectorGenerationError) as context:
            SeriesDirectorApplicationService(capability).generate({"plannedEpisodeCount": 4}, "系列方向")
        self.assertEqual(context.exception.code, "provider_timeout")
        self.assertEqual(context.exception.diagnostic_category, "provider_timeout")
        self.assertEqual(context.exception.provider_status, 504)

    def test_unavailable_maps_to_stable_series_director_error(self):
        capability = FakeTextGenerationCapability([
            TextGenerationUnavailableError(category="network_error", status=503)
        ])
        with self.assertRaises(SeriesDirectorGenerationError) as context:
            SeriesDirectorApplicationService(capability).generate({"plannedEpisodeCount": 4}, "系列方向")
        self.assertEqual(context.exception.code, "provider_unavailable")
        self.assertEqual(context.exception.diagnostic_category, "network_error")
        self.assertEqual(context.exception.provider_status, 503)


class SeriesPlanningDomainTests(unittest.TestCase):
    def setUp(self):
        self.series, self.projects, self.planning, self.series_record, self.project = create_context()

    def test_confirmation_creates_local_identity_and_no_episode_records(self):
        result = confirm(self.planning, self.series_record, self.project)
        plan = result["plan"]
        version = result["version"]
        self.assertEqual(plan["seriesPlanRef"], "series-plan-m5-1")
        self.assertEqual(version["seriesPlanVersionRef"], "series-plan-version-m5-1")
        self.assertEqual(plan["confirmedSeriesPlanVersionRef"], version["seriesPlanVersionRef"])
        self.assertEqual(
            [item["episodePlanItemRef"] for item in version["episodePlanItems"]],
            [f"episode-plan-item-m5-{index}" for index in range(1, 5)],
        )
        self.assertEqual(self.series.list_series(WORKSPACE)[0]["episodes"], [])

    def test_human_confirmation_is_required_and_duplicate_plan_is_blocked(self):
        with self.assertRaises(SeriesPlanningPublicError) as missing:
            self.planning.confirm_candidate({
                "workspaceRef": WORKSPACE,
                "projectRef": self.project["projectRef"],
                "seriesRef": self.series_record["seriesRef"],
                "humanConfirmed": False,
                "candidate": valid_candidate(),
            })
        self.assertEqual((missing.exception.code, missing.exception.status), ("series_plan_not_confirmed", 409))
        confirm(self.planning, self.series_record, self.project)
        with self.assertRaises(SeriesPlanningPublicError) as duplicate:
            confirm(self.planning, self.series_record, self.project)
        self.assertEqual((duplicate.exception.code, duplicate.exception.status), ("duplicate_record", 409))

    def test_manual_version_is_immutable_and_requires_explicit_reconfirmation(self):
        first = confirm(self.planning, self.series_record, self.project)
        content_keys = set(valid_candidate()) - {"schemaVersion"}
        content = {key: copy.deepcopy(first["version"][key]) for key in content_keys}
        content["premise"] = "修订后的系列前提。"
        second = self.planning.create_manual_version({
            "workspaceRef": WORKSPACE,
            "projectRef": self.project["projectRef"],
            "seriesRef": self.series_record["seriesRef"],
            "seriesPlanRef": first["plan"]["seriesPlanRef"],
            "expectedPlanVersion": 1,
            "content": content,
        })
        self.assertEqual(second["version"]["versionNumber"], 2)
        self.assertEqual(second["plan"]["confirmedSeriesPlanVersionRef"], first["version"]["seriesPlanVersionRef"])
        workspace = self.planning.get_workspace(WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"])
        self.assertEqual(workspace["versions"][0]["premise"], first["version"]["premise"])
        confirmed = self.planning.confirm_version({
            "workspaceRef": WORKSPACE,
            "seriesPlanRef": second["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": second["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": second["plan"]["version"],
            "humanConfirmed": True,
        })
        self.assertEqual(confirmed["confirmedSeriesPlanVersionRef"], second["version"]["seriesPlanVersionRef"])

    def test_m6_bridge_is_deterministic_and_preserves_lineage(self):
        result = confirm(self.planning, self.series_record, self.project)
        first = self.planning.build_m6_bootstrap(WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"])
        second = self.planning.build_m6_bootstrap(WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"])
        self.assertEqual(first, second)
        self.assertEqual(first["schemaVersion"], "creator.series-plan.m6-bootstrap.v1")
        self.assertEqual(first["projectRef"], self.project["projectRef"])
        self.assertEqual(first["seriesPlanRef"], result["plan"]["seriesPlanRef"])


class SeriesPlanningPersistenceTests(unittest.TestCase):
    def test_plan_versions_confirmation_and_project_relationship_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            series, projects, planning, series_record, project = create_context(local_path=path)
            result = confirm(planning, series_record, project)
            restarted_series = create_local_series_boundary(path)
            restarted_projects = create_local_project_boundary(path, restarted_series)
            restarted = create_local_planning_boundary(path, restarted_projects)
            workspace = restarted.get_workspace(WORKSPACE, project["projectRef"], series_record["seriesRef"])
            self.assertEqual(workspace["plan"]["seriesPlanRef"], result["plan"]["seriesPlanRef"])
            self.assertEqual(len(workspace["versions"]), 1)
            self.assertEqual(workspace["context"]["projectRef"], project["projectRef"])

    def test_failed_duplicate_confirmation_rolls_back_without_partial_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            _, _, planning, series_record, project = create_context(local_path=path)
            confirm(planning, series_record, project)
            with self.assertRaises(SeriesPlanningPublicError):
                confirm(planning, series_record, project)
            workspace = planning.get_workspace(WORKSPACE, project["projectRef"], series_record["seriesRef"])
            self.assertEqual(len(workspace["versions"]), 1)


if __name__ == "__main__":
    unittest.main()
