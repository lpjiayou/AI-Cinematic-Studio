import inspect
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os import project_engine as public_package
from services.v5_core_os.project_engine.foundation import (
    PROJECT_CONTEXT_SCHEMA_VERSION,
    PROJECT_SCHEMA_VERSION,
    PROJECT_SERIES_RELATIONSHIP_SCHEMA_VERSION,
    InMemoryProjectAdapter,
    ProjectContextService,
    ProjectRepository,
    SqliteProjectAdapter,
)
from services.v5_core_os.series_episode import (
    create_in_memory_boundary as create_series_boundary,
    create_local_development_boundary as create_local_series_boundary,
)


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "apps" / "creator_workspace_mvp" / "server.py"
WORKSPACE = "workspace-project-contract"
PROFILE = "content-profile-project-contract"


class Refs:
    def __init__(self):
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-contract-{self.counts[prefix]}"


def exercise(adapter, series_boundary):
    refs = Refs()
    service = ProjectContextService(
        adapter,
        get_series=series_boundary.get_series,
        get_episode=series_boundary.get_episode,
        ref_factory=refs,
        clock=lambda: "2026-08-10T00:00:00.000Z",
    )
    series = series_boundary.create_series(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": "Contract Series",
            "plannedEpisodeCount": 8,
        }
    )
    project = service.create_project(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "projectType": "series",
            "seriesRef": series["seriesRef"],
            "title": "Contract Project",
            "defaultDurationSec": 45,
            "plannedEpisodeCount": 8,
        }
    )
    return service, series, project


class ProjectRepositoryContractTests(unittest.TestCase):
    def test_memory_and_sqlite_share_create_read_list_relationship_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project-contract.sqlite3"
            cases = (
                (InMemoryProjectAdapter(), create_series_boundary()),
                (SqliteProjectAdapter(path), create_local_series_boundary(path)),
            )
            for adapter, series_boundary in cases:
                with self.subTest(adapter=type(adapter).__name__):
                    service, series, project = exercise(adapter, series_boundary)
                    self.assertEqual(project["schemaVersion"], PROJECT_SCHEMA_VERSION)
                    self.assertEqual(project["seriesRefs"], [series["seriesRef"]])
                    self.assertEqual(service.get_project(WORKSPACE, project["projectRef"]), project)
                    self.assertEqual(service.list_projects(WORKSPACE), [project])
                    related = adapter.list_series_relationships(WORKSPACE, project["projectRef"])
                    self.assertEqual(related[0].schemaVersion, PROJECT_SERIES_RELATIONSHIP_SCHEMA_VERSION)
                    context = service.build_context(WORKSPACE, project["projectRef"])
                    self.assertEqual(context["schemaVersion"], PROJECT_CONTEXT_SCHEMA_VERSION)
                    self.assertEqual(context["seriesRef"], series["seriesRef"])

    def test_repository_port_contains_domain_operations_not_storage_details(self):
        methods = {
            name
            for name, value in inspect.getmembers(ProjectRepository, inspect.isfunction)
            if not name.startswith("__")
        }
        self.assertEqual(
            methods,
            {
                "archive_project",
                "create_project",
                "get_project",
                "get_project_for_series",
                "list_projects",
                "list_series_relationships",
            },
        )
        self.assertFalse(any("sql" in name.lower() or "table" in name.lower() for name in methods))


class ProjectArchitectureContractTests(unittest.TestCase):
    def test_project_owner_is_physically_under_v5(self):
        path = Path(inspect.getfile(ProjectContextService)).resolve()
        self.assertIn("services", path.parts)
        self.assertIn("v5_core_os", path.parts)
        self.assertNotIn("apps", path.parts)

    def test_compatibility_engine_and_new_public_boundary_share_one_package(self):
        self.assertTrue(hasattr(public_package, "ProjectEngine"))
        self.assertTrue(hasattr(public_package, "ProjectPublicBoundary"))
        self.assertTrue(callable(public_package.create_in_memory_boundary))
        self.assertTrue(callable(public_package.create_local_development_boundary))

    def test_creator_server_imports_public_boundary_only(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn("from services.v5_core_os.project_engine import", source)
        self.assertNotIn("project_engine.foundation", source)
        self.assertNotIn("SqliteProjectAdapter", source)
        self.assertNotIn("InMemoryProjectAdapter", source)


if __name__ == "__main__":
    unittest.main()
