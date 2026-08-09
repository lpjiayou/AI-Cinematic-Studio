from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.project_engine import (
    ProjectPublicError,
    create_in_memory_boundary as create_project_boundary,
    create_local_development_boundary as create_local_project_boundary,
)
from services.v5_core_os.series_episode import (
    create_in_memory_boundary as create_series_boundary,
    create_local_development_boundary as create_local_series_boundary,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


WORKSPACE = "workspace-m4"
PROFILE = "content-profile-m4"


class Refs:
    def __init__(self):
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-m4-{self.counts[prefix]}"


def create_series(boundary, *, profile=PROFILE, title="Series"):
    return boundary.create_series(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": profile,
            "title": title,
            "plannedEpisodeCount": 12,
        }
    )


def create_project(boundary, series, **overrides):
    value = {
        "workspaceRef": WORKSPACE,
        "contentProfileRef": PROFILE,
        "projectType": "series",
        "seriesRef": series["seriesRef"],
        "title": "Wanlight production",
        "description": "M4 Project Context",
        "targetPlatform": "short-video",
        "aspectRatio": "9:16",
        "defaultDurationSec": 30,
        "plannedEpisodeCount": 12,
    }
    value.update(overrides)
    return boundary.create_project(value)


class ProjectContextServiceTests(unittest.TestCase):
    def setUp(self):
        self.refs = Refs()
        self.series = create_series_boundary(ref_factory=self.refs)
        self.projects = create_project_boundary(
            self.series,
            ref_factory=self.refs,
            clock=lambda: "2026-08-10T00:00:00.000Z",
        )

    def test_create_project_owns_ref_and_preserves_series_identity(self):
        series = create_series(self.series)
        project = create_project(self.projects, series)
        self.assertEqual(project["schemaVersion"], "v5.project.v1")
        self.assertEqual(project["projectRef"], "project-m4-1")
        self.assertNotEqual(project["projectRef"], series["seriesRef"])
        self.assertEqual(project["seriesRefs"], [series["seriesRef"]])
        self.assertEqual(project["contentProfileRef"], series["contentProfileRef"])
        self.assertEqual(project["status"], "active")
        self.assertEqual(project["version"], 1)

    def test_series_project_requires_real_series_and_matching_profile(self):
        with self.assertRaises(ProjectPublicError) as missing:
            create_project(self.projects, {"seriesRef": "missing-series"})
        self.assertEqual((missing.exception.code, missing.exception.status), ("not_found", 404))

        series = create_series(self.series, profile="profile-other")
        with self.assertRaises(ProjectPublicError) as mismatch:
            create_project(self.projects, series)
        self.assertEqual((mismatch.exception.code, mismatch.exception.status), ("scope_mismatch", 400))
        self.assertEqual(self.projects.list_projects(WORKSPACE), [])

    def test_series_can_belong_to_only_one_project(self):
        series = create_series(self.series)
        create_project(self.projects, series)
        with self.assertRaises(ProjectPublicError) as duplicate:
            create_project(self.projects, series, title="Duplicate")
        self.assertEqual((duplicate.exception.code, duplicate.exception.status), ("duplicate_record", 409))
        self.assertEqual(len(self.projects.list_projects(WORKSPACE)), 1)

    def test_context_resolves_project_series_and_episode_without_rewriting_refs(self):
        series = create_series(self.series)
        source_plan = valid_plan()
        plan = self.series.confirm_creative_plan(
            {
                "workspaceRef": WORKSPACE,
                "humanConfirmed": True,
                "brief": valid_brief(),
                "sourcePlan": source_plan,
                "sourcePlanRef": "source-plan-m4",
                "sourcePlanSchemaVersion": source_plan["schemaVersion"],
                "sourcePlanVersion": 1,
            }
        )
        episode = self.series.create_episode(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "title": "Episode 001",
            }
        )
        project = create_project(self.projects, series)
        context = self.projects.build_context(
            WORKSPACE, project["projectRef"], series["seriesRef"], episode["episodeRef"]
        )
        self.assertEqual(context["schemaVersion"], "creator.project-context.v1")
        self.assertEqual(context["projectRef"], project["projectRef"])
        self.assertEqual(context["seriesRef"], series["seriesRef"])
        self.assertEqual(context["episodeRef"], episode["episodeRef"])
        self.assertEqual(
            context["episode"]["confirmedPlanBinding"]["sourcePlanRef"],
            "source-plan-m4",
        )
        self.assertIsNone(context["episode"]["canonicalProjectRef"])

    def test_archive_is_non_destructive_and_versioned(self):
        series = create_series(self.series)
        project = create_project(self.projects, series)
        archived = self.projects.archive_project(WORKSPACE, project["projectRef"])
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["version"], 2)
        self.assertEqual(archived["seriesRefs"], [series["seriesRef"]])
        self.assertEqual(self.series.get_series(WORKSPACE, series["seriesRef"])["seriesRef"], series["seriesRef"])


class ProjectContextSqliteTests(unittest.TestCase):
    def test_project_and_relationship_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            refs = Refs()
            series_boundary = create_local_series_boundary(path)
            series = create_series(series_boundary)
            first = create_local_project_boundary(path, series_boundary)
            project = create_project(first, series)
            restarted_series = create_local_series_boundary(path)
            restarted = create_local_project_boundary(path, restarted_series)
            loaded = restarted.build_context(WORKSPACE, project["projectRef"])
            self.assertEqual(loaded["projectRef"], project["projectRef"])
            self.assertEqual(loaded["seriesRef"], series["seriesRef"])
            self.assertEqual(loaded["series"]["seriesRef"], series["seriesRef"])

    def test_failed_relationship_insert_rolls_back_project(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            series_boundary = create_local_series_boundary(path)
            series = create_series(series_boundary)
            first = create_local_project_boundary(path, series_boundary)
            create_project(first, series, title="First")
            with self.assertRaises(ProjectPublicError):
                create_project(first, series, title="Must roll back")
            self.assertEqual([item["title"] for item in first.list_projects(WORKSPACE)], ["First"])


if __name__ == "__main__":
    unittest.main()
