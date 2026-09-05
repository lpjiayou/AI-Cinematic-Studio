import copy
from dataclasses import replace
import hashlib
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
    ProjectPublicError,
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
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


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


def create_binding_context(*, count=4):
    refs = Refs()
    assembly = LifecycleAssembly.in_memory(
        ref_factory=refs,
        clock=lambda: "2026-08-10T00:00:00.000Z",
    )
    series_record = assembly.series_episode.create_series({
        "workspaceRef": WORKSPACE,
        "contentProfileRef": PROFILE,
        "title": "晚灯",
        "plannedEpisodeCount": count,
    })
    project = assembly.project_context.create_project({
        "workspaceRef": WORKSPACE,
        "contentProfileRef": PROFILE,
        "projectType": "series",
        "seriesRef": series_record["seriesRef"],
        "title": "晚灯系列制作",
        "plannedEpisodeCount": count,
    })
    source_plan = valid_plan()
    confirmed_creative_plan = assembly.series_episode.confirm_creative_plan({
        "workspaceRef": WORKSPACE,
        "humanConfirmed": True,
        "sourcePlanRef": "director-plan-m5",
        "sourcePlanSchemaVersion": source_plan["schemaVersion"],
        "sourcePlanVersion": 1,
        "brief": valid_brief(),
        "sourcePlan": source_plan,
    })
    episodes = [
        assembly.series_episode.create_episode({
            "workspaceRef": WORKSPACE,
            "seriesRef": series_record["seriesRef"],
            "creativePlanRef": confirmed_creative_plan["creativePlanRef"],
            "episodeNumber": number,
            "title": f"第{number}集",
        })
        for number in range(1, count + 1)
    ]
    initial = confirm(
        assembly.series_planning,
        series_record,
        project,
        valid_candidate(count),
    )
    bindings = [
        {
            "episodeRef": episode["episodeRef"],
            "episodePlanItemRef": item["episodePlanItemRef"],
        }
        for episode, item in zip(episodes, initial["version"]["episodePlanItems"])
    ]
    return assembly, series_record, project, episodes, initial, bindings


class SeriesDirectorTests(unittest.TestCase):
    def test_candidate_validator_enforces_project_count_and_rejects_provider_identity(self):
        context = {"plannedEpisodeCount": 4}
        validated = validate_series_plan_candidate(valid_candidate(), context)
        self.assertEqual(len(validated["episodePlanItems"]), 4)
        invalid = valid_candidate()
        invalid["projectRef"] = "provider-project"
        with self.assertRaises(SeriesPlanCandidateError):
            validate_series_plan_candidate(invalid, context)

    def test_candidate_integer_fields_require_exact_int_without_coercion(self):
        paths = (
            ("main-arc-number", ("mainArcs", 0, "arcNumber")),
            ("main-arc-start", ("mainArcs", 0, "episodeStart")),
            ("main-arc-end", ("mainArcs", 0, "episodeEnd")),
            ("sub-arc-start", ("subArcs", 0, "episodeStart")),
            ("sub-arc-end", ("subArcs", 0, "episodeEnd")),
            ("episode-number", ("episodePlanItems", 0, "episodeNumber")),
            ("episode-arc-number", ("episodePlanItems", 0, "arcNumber")),
        )
        for value in (True, 1.0, 1.9, "1", None):
            for name, path in paths:
                with self.subTest(field=name, value=repr(value)):
                    candidate = valid_candidate()
                    target = candidate[path[0]][path[1]]
                    target[path[2]] = value
                    with self.assertRaises(SeriesPlanCandidateError):
                        validate_series_plan_candidate(
                            candidate, {"plannedEpisodeCount": 4}
                        )
            with self.subTest(field="plannedEpisodeCount", value=repr(value)):
                with self.assertRaises(SeriesPlanCandidateError):
                    validate_series_plan_candidate(
                        valid_candidate(), {"plannedEpisodeCount": value}
                    )

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

    def test_v1_version_and_m6_source_remain_golden_and_unbound(self):
        created = confirm(self.planning, self.series_record, self.project)
        version = created["version"]
        self.assertEqual(version["schemaVersion"], "v5.series-plan-version.v1")
        self.assertNotIn("episodePlanItemBindings", version)
        self.assertEqual(
            set(version),
            {
                "schemaVersion", "workspaceRef", "contentProfileRef", "projectRef",
                "seriesRef", "seriesPlanRef", "seriesPlanVersionRef", "versionNumber",
                "seriesConcept", "premise", "logline", "mainNarrativeDirection",
                "mainArcs", "subArcs", "characterArcIntents", "episodePlanItems",
                "narrativeRhythm", "worldIntent", "continuityIntent",
                "foreshadowingContext", "productionAssumptions", "changeKind",
                "parentSeriesPlanVersionRef", "createdAt",
            },
        )
        source = self.planning.get_confirmed_m6_source_snapshot(
            WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"]
        )
        digest_payload = dict(source)
        digest = digest_payload.pop("seriesPlanVersionDigest")
        recomputed = hashlib.sha256(json.dumps(
            digest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        self.assertEqual(digest, recomputed)
        self.assertEqual(digest, "a96cd7d0998788ed41206f28b81f38ce1e468fa16e4c6a4c780c92d793071aee")
        self.assertEqual(source["schemaVersion"], "v5.series-plan.m6-source-snapshot.v1")
        self.assertNotIn("episodePlanItemBindings", source)

    def test_standalone_binding_version_fails_closed_without_writing(self):
        initial = confirm(self.planning, self.series_record, self.project)
        before = self.planning.get_workspace(
            WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"]
        )
        with self.assertRaises(SeriesPlanningPublicError) as unavailable:
            self.planning.create_episode_plan_item_binding_version({
                "workspaceRef": WORKSPACE,
                "projectRef": self.project["projectRef"],
                "seriesRef": self.series_record["seriesRef"],
                "seriesPlanRef": initial["plan"]["seriesPlanRef"],
                "expectedPlanVersion": initial["plan"]["version"],
                "episodePlanItemBindings": [],
            })
        self.assertEqual(
            (unavailable.exception.code, unavailable.exception.status),
            ("lifecycle_unavailable", 503),
        )
        self.assertEqual(
            self.planning.get_workspace(
                WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"]
            ),
            before,
        )


class SeriesPlanItemBindingVersionTests(unittest.TestCase):
    def binding_command(self, project, series, initial, bindings):
        return {
            "workspaceRef": WORKSPACE,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial["plan"]["version"],
            "episodePlanItemBindings": bindings,
        }

    def test_dedicated_operation_normalizes_v1_to_v2_and_explicit_v2_unbind(self):
        assembly, series, project, _, initial, bindings = create_binding_context()
        self.assertEqual(initial["version"]["schemaVersion"], "v5.series-plan-version.v1")
        self.assertNotIn("episodePlanItemBindings", initial["version"])

        bound = assembly.series_planning.create_episode_plan_item_binding_version(
            self.binding_command(project, series, initial, list(reversed(bindings)))
        )
        self.assertEqual(bound["version"]["schemaVersion"], "v5.series-plan-version.v2")
        self.assertEqual(bound["version"]["versionNumber"], 2)
        self.assertEqual(bound["version"]["parentSeriesPlanVersionRef"], initial["version"]["seriesPlanVersionRef"])
        self.assertEqual(bound["version"]["episodePlanItemBindings"], bindings)
        self.assertEqual(bound["plan"]["status"], "draft")
        self.assertEqual(
            bound["plan"]["confirmedSeriesPlanVersionRef"],
            initial["version"]["seriesPlanVersionRef"],
        )

        unbound_command = self.binding_command(project, series, bound, [])
        unbound = assembly.series_planning.create_episode_plan_item_binding_version(unbound_command)
        self.assertEqual(unbound["version"]["schemaVersion"], "v5.series-plan-version.v2")
        self.assertEqual(unbound["version"]["versionNumber"], 3)
        self.assertEqual(unbound["version"]["episodePlanItemBindings"], [])
        self.assertEqual(unbound["version"]["parentSeriesPlanVersionRef"], bound["version"]["seriesPlanVersionRef"])
        workspace = assembly.series_planning.get_workspace(
            WORKSPACE, project["projectRef"], series["seriesRef"]
        )
        self.assertNotIn("episodePlanItemBindings", workspace["versions"][0])
        self.assertEqual(workspace["versions"][1]["episodePlanItemBindings"], bindings)
        self.assertEqual(workspace["versions"][2]["episodePlanItemBindings"], [])

    def test_exact_command_and_binding_objects_reject_unknown_missing_and_duplicate_fields(self):
        assembly, series, project, _, initial, bindings = create_binding_context()
        command = self.binding_command(project, series, initial, bindings)
        invalid_commands = []
        for field in tuple(command):
            invalid_commands.append({key: value for key, value in command.items() if key != field})
        for extra in ("humanConfirmed", "content", "unknown"):
            invalid_commands.append({**command, extra: True})
        invalid_commands.extend((
            {**command, "expectedPlanVersion": "1"},
            {**command, "expectedPlanVersion": 1.9},
            {**command, "expectedPlanVersion": True},
            {**command, "episodePlanItemBindings": [{**bindings[0], "unknown": True}]},
            {**command, "episodePlanItemBindings": [bindings[0], {
                **bindings[1], "episodeRef": bindings[0]["episodeRef"],
            }]},
            {**command, "episodePlanItemBindings": [bindings[0], {
                **bindings[1], "episodePlanItemRef": bindings[0]["episodePlanItemRef"],
            }]},
        ))
        for invalid in invalid_commands:
            with self.subTest(fields=tuple(invalid)):
                with self.assertRaises(SeriesPlanningPublicError) as rejected:
                    assembly.series_planning.create_episode_plan_item_binding_version(invalid)
                self.assertEqual(
                    (rejected.exception.code, rejected.exception.status),
                    ("invalid_request", 400),
                )
        workspace = assembly.series_planning.get_workspace(
            WORKSPACE, project["projectRef"], series["seriesRef"]
        )
        self.assertEqual(len(workspace["versions"]), 1)
        self.assertEqual(workspace["plan"]["version"], 1)

    def test_binding_scope_rejects_unknown_episode_and_wrong_plan_item_without_write(self):
        for mutation in (
            lambda bindings: [{**bindings[0], "episodeRef": "episode-outside-scope"}],
            lambda bindings: [{**bindings[0], "episodePlanItemRef": "item-outside-version"}],
        ):
            assembly, series, project, _, initial, bindings = create_binding_context()
            command = self.binding_command(project, series, initial, mutation(bindings))
            with self.assertRaises(SeriesPlanningPublicError) as rejected:
                assembly.series_planning.create_episode_plan_item_binding_version(command)
            self.assertEqual(
                (rejected.exception.code, rejected.exception.status),
                ("scope_mismatch", 400),
            )
            workspace = assembly.series_planning.get_workspace(
                WORKSPACE, project["projectRef"], series["seriesRef"]
            )
            self.assertEqual(len(workspace["versions"]), 1)
            self.assertEqual(workspace["plan"]["version"], 1)

    def test_v2_confirmation_revalidates_episode_membership_and_is_zero_write_on_failure(self):
        assembly, series, project, episodes, initial, bindings = create_binding_context()
        bound = assembly.series_planning.create_episode_plan_item_binding_version(
            self.binding_command(project, series, initial, bindings)
        )
        original_build_context = assembly.project_context.build_context

        def missing_episode(workspace_ref, project_ref, series_ref=None, episode_ref=None):
            if episode_ref == episodes[0]["episodeRef"]:
                raise ProjectPublicError("not_found", 404)
            return original_build_context(workspace_ref, project_ref, series_ref, episode_ref)

        assembly.project_context.build_context = missing_episode
        try:
            with self.assertRaises(SeriesPlanningPublicError) as rejected:
                assembly.series_planning.confirm_version({
                    "workspaceRef": WORKSPACE,
                    "seriesPlanRef": bound["plan"]["seriesPlanRef"],
                    "seriesPlanVersionRef": bound["version"]["seriesPlanVersionRef"],
                    "expectedPlanVersion": bound["plan"]["version"],
                    "humanConfirmed": True,
                })
        finally:
            assembly.project_context.build_context = original_build_context
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("scope_mismatch", 400),
        )
        workspace = assembly.series_planning.get_workspace(
            WORKSPACE, project["projectRef"], series["seriesRef"]
        )
        self.assertEqual(workspace["plan"]["version"], bound["plan"]["version"])
        self.assertEqual(workspace["plan"]["status"], "draft")
        self.assertEqual(
            workspace["plan"]["confirmedSeriesPlanVersionRef"],
            initial["version"]["seriesPlanVersionRef"],
        )

    def test_binding_write_and_confirmation_revalidate_project_series_relationship(self):
        for phase in ("write", "confirm"):
            with self.subTest(phase=phase):
                assembly, series, project, _, initial, bindings = create_binding_context()
                original = assembly.project_context.build_context
                bound = None
                if phase == "confirm":
                    bound = assembly.series_planning.create_episode_plan_item_binding_version(
                        self.binding_command(project, series, initial, bindings)
                    )

                def wrong_series(workspace_ref, project_ref, series_ref=None, episode_ref=None):
                    context = original(workspace_ref, project_ref, series_ref, episode_ref)
                    context["project"] = {
                        **context["project"],
                        "seriesRefs": ["series-not-associated"],
                    }
                    return context

                assembly.project_context.build_context = wrong_series
                try:
                    with self.assertRaises(SeriesPlanningPublicError) as rejected:
                        if phase == "write":
                            assembly.series_planning.create_episode_plan_item_binding_version(
                                self.binding_command(project, series, initial, bindings)
                            )
                        else:
                            assembly.series_planning.confirm_version({
                                "workspaceRef": WORKSPACE,
                                "seriesPlanRef": bound["plan"]["seriesPlanRef"],
                                "seriesPlanVersionRef": bound["version"]["seriesPlanVersionRef"],
                                "expectedPlanVersion": bound["plan"]["version"],
                                "humanConfirmed": True,
                            })
                finally:
                    assembly.project_context.build_context = original
                self.assertEqual(
                    (rejected.exception.code, rejected.exception.status),
                    ("scope_mismatch", 400),
                )
                workspace = assembly.series_planning.get_workspace(
                    WORKSPACE, project["projectRef"], series["seriesRef"]
                )
                self.assertEqual(len(workspace["versions"]), 1 if phase == "write" else 2)
                self.assertEqual(
                    workspace["plan"]["confirmedSeriesPlanVersionRef"],
                    initial["version"]["seriesPlanVersionRef"],
                )

    def test_manual_version_rejects_current_v2_and_cannot_downgrade_or_write(self):
        assembly, series, project, _, initial, bindings = create_binding_context()
        bound = assembly.series_planning.create_episode_plan_item_binding_version(
            self.binding_command(project, series, initial, bindings)
        )
        before = assembly.series_planning.get_workspace(
            WORKSPACE, project["projectRef"], series["seriesRef"]
        )
        with self.assertRaises(SeriesPlanningPublicError) as rejected:
            assembly.series_planning.create_manual_version({
                "workspaceRef": WORKSPACE,
                "projectRef": project["projectRef"],
                "seriesRef": series["seriesRef"],
                "seriesPlanRef": bound["plan"]["seriesPlanRef"],
                "expectedPlanVersion": bound["plan"]["version"],
                "content": {},
            })
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("version_conflict", 409),
        )
        self.assertEqual(
            assembly.series_planning.get_workspace(
                WORKSPACE, project["projectRef"], series["seriesRef"]
            ),
            before,
        )

    def test_binding_write_and_confirmation_reject_tampered_operation_lineage(self):
        for phase in ("root-write", "v2-confirm", "plan-version-write"):
            with self.subTest(phase=phase):
                assembly, series, project, _, initial, bindings = create_binding_context()
                service = assembly.series_planning._SeriesPlanningPublicBoundary__service
                repository = service.repository
                plan_key = (WORKSPACE, initial["plan"]["seriesPlanRef"])
                root_key = (
                    WORKSPACE,
                    initial["plan"]["seriesPlanRef"],
                    initial["version"]["seriesPlanVersionRef"],
                )
                command = self.binding_command(project, series, initial, bindings)

                if phase == "root-write":
                    repository._versions[root_key] = replace(
                        repository._versions[root_key], changeKind="manual-edit"
                    )
                    operation = lambda: assembly.series_planning.create_episode_plan_item_binding_version(
                        command
                    )
                    expected_count = 1
                else:
                    bound = assembly.series_planning.create_episode_plan_item_binding_version(
                        command
                    )
                    bound_key = (
                        WORKSPACE,
                        bound["plan"]["seriesPlanRef"],
                        bound["version"]["seriesPlanVersionRef"],
                    )
                    if phase == "v2-confirm":
                        repository._versions[bound_key] = replace(
                            repository._versions[bound_key], changeKind="manual-edit"
                        )
                        operation = lambda: assembly.series_planning.confirm_version({
                            "workspaceRef": WORKSPACE,
                            "seriesPlanRef": bound["plan"]["seriesPlanRef"],
                            "seriesPlanVersionRef": bound["version"]["seriesPlanVersionRef"],
                            "expectedPlanVersion": bound["plan"]["version"],
                            "humanConfirmed": True,
                        })
                    else:
                        repository._plans[plan_key] = replace(
                            repository._plans[plan_key], version=1
                        )
                        command = self.binding_command(project, series, bound, [])
                        command["expectedPlanVersion"] = 1
                        operation = lambda: assembly.series_planning.create_episode_plan_item_binding_version(
                            command
                        )
                    expected_count = 2

                with self.assertRaises(SeriesPlanningPublicError) as rejected:
                    operation()
                self.assertEqual(
                    (rejected.exception.code, rejected.exception.status),
                    ("version_conflict", 409),
                )
                self.assertEqual(len(repository.list_versions(WORKSPACE, plan_key[1])), expected_count)

    def test_workspace_rejects_corrupt_plan_and_version_identity_lineage(self):
        for corruption in (
            "plan-schema", "profile", "version-ref", "version-number-type", "created-at"
        ):
            with self.subTest(corruption=corruption):
                assembly, series, project, _, initial, _ = create_binding_context()
                repository = (
                    assembly.series_planning._SeriesPlanningPublicBoundary__service.repository
                )
                plan_key = (WORKSPACE, initial["plan"]["seriesPlanRef"])
                version_key = (
                    WORKSPACE,
                    initial["plan"]["seriesPlanRef"],
                    initial["version"]["seriesPlanVersionRef"],
                )
                if corruption == "plan-schema":
                    repository._plans[plan_key] = replace(
                        repository._plans[plan_key], schemaVersion="v5.series-plan.unknown"
                    )
                elif corruption == "profile":
                    repository._plans[plan_key] = replace(
                        repository._plans[plan_key], contentProfileRef=""
                    )
                    repository._versions[version_key] = replace(
                        repository._versions[version_key], contentProfileRef=""
                    )
                elif corruption == "version-ref":
                    repository._plans[plan_key] = replace(
                        repository._plans[plan_key],
                        currentSeriesPlanVersionRef="bad ref",
                        confirmedSeriesPlanVersionRef="bad ref",
                    )
                    repository._versions[version_key] = replace(
                        repository._versions[version_key], seriesPlanVersionRef="bad ref"
                    )
                elif corruption == "version-number-type":
                    repository._versions[version_key] = replace(
                        repository._versions[version_key], versionNumber="1"
                    )
                else:
                    repository._versions[version_key] = replace(
                        repository._versions[version_key], createdAt=""
                    )

                with self.assertRaises(SeriesPlanningPublicError) as rejected:
                    assembly.series_planning.get_workspace(
                        WORKSPACE, project["projectRef"], series["seriesRef"]
                    )
                self.assertEqual(
                    (rejected.exception.code, rejected.exception.status),
                    ("version_conflict", 409),
                )


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
