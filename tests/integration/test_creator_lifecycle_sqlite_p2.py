from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier, Event, Thread
import unittest

from services.v5_core_os.lifecycle_integrity import (
    AssemblyPoisonedError,
    LifecycleAssembly,
    LifecycleMigrationError,
    LifecycleOperation,
    LifecycleRollbackError,
    SqliteLifecycleState,
    migrate_lifecycle_database,
)
from services.v5_core_os.project_engine import ProjectPublicError
from services.v5_core_os.project_engine.foundation import SqliteProjectAdapter
from services.v5_core_os.script_studio.foundation import SqliteScriptStudioAdapter
from services.v5_core_os.series_episode import SeriesEpisodePublicError
from services.v5_core_os.series_episode.foundation import SqliteSeriesEpisodeAdapter
from services.v5_core_os.series_planning.foundation import SqliteSeriesPlanningAdapter
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_deletion_lifecycle_integrity import Refs, project_command, script_command
from tests.unit.test_series_planning_m5 import valid_candidate


NOW = "2026-08-12T00:00:00.000Z"


def open_fk(path):
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def seed_series(assembly, workspace="workspace-a", profile="profile-a"):
    return assembly.series_episode.create_series({
        "workspaceRef": workspace, "contentProfileRef": profile,
        "title": "SQLite series", "plannedEpisodeCount": 3,
    })


def seed_episode(assembly, series, workspace="workspace-a"):
    source = valid_plan()
    plan = assembly.series_episode.confirm_creative_plan({
        "workspaceRef": workspace, "humanConfirmed": True,
        "sourcePlanRef": "source-plan", "sourcePlanSchemaVersion": source["schemaVersion"],
        "sourcePlanVersion": 1, "brief": valid_brief(), "sourcePlan": source,
    })
    return assembly.series_episode.create_episode({
        "workspaceRef": workspace, "seriesRef": series["seriesRef"],
        "creativePlanRef": plan["creativePlanRef"], "episodeNumber": 1, "title": "Episode",
    })


def seed_bound_episode_plan(
    assembly,
    series,
    episode,
    *,
    workspace="workspace-a",
    profile="profile-a",
):
    project = assembly.project_context.create_project(
        project_command(series, workspace, profile)
    )
    initial = assembly.series_planning.confirm_candidate({
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "humanConfirmed": True,
        "candidate": valid_candidate(project["plannedEpisodeCount"]),
    })
    binding = {
        "episodeRef": episode["episodeRef"],
        "episodePlanItemRef": initial["version"]["episodePlanItems"][0][
            "episodePlanItemRef"
        ],
    }
    command = {
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "seriesPlanRef": initial["plan"]["seriesPlanRef"],
        "expectedPlanVersion": initial["plan"]["version"],
        "episodePlanItemBindings": [binding],
    }
    bound = assembly.series_planning.create_episode_plan_item_binding_version(command)
    return project, initial, bound, binding


class SqliteMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "lifecycle.sqlite3"

    def test_fresh_migration_enables_fk_and_is_repeatable(self):
        self.assertEqual(migrate_lifecycle_database(self.path, allow_upgrade=True), "fresh")
        self.assertEqual(migrate_lifecycle_database(self.path, allow_upgrade=True), "no-op")
        connection = open_fk(self.path)
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def _v1_database_with_data(self):
        series = SqliteSeriesEpisodeAdapter(self.path)
        from services.v5_core_os.series_episode.foundation import SeriesEpisodeService
        service = SeriesEpisodeService(series, ref_factory=Refs(), clock=lambda: NOW)
        created = service.create_series({
            "workspaceRef": "workspace-a", "contentProfileRef": "profile-a",
            "title": "Legacy", "plannedEpisodeCount": 1,
        })
        return created

    def test_clean_v1_upgrade_preserves_legacy_rows_and_values(self):
        created = self._v1_database_with_data()
        before = open_fk(self.path)
        try:
            row = tuple(before.execute("SELECT * FROM v5_series").fetchone())
        finally:
            before.close()
        self.assertEqual(migrate_lifecycle_database(self.path, allow_upgrade=True), "upgrade")
        after = open_fk(self.path)
        try:
            self.assertEqual(tuple(after.execute("SELECT * FROM v5_series").fetchone()), row)
            self.assertEqual(after.execute("SELECT schema_version FROM v5_series_episode_schema").fetchone()[0], 2)
            self.assertEqual(after.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            after.close()
        self.assertEqual(created["title"], "Legacy")

    def test_partial_v1_marker_table_mismatch_fails_before_writes(self):
        cases = ("marker-only", "tables-without-marker")
        for case in cases:
            with self.subTest(case=case):
                path = Path(self.temp.name) / f"partial-v1-{case}.sqlite3"
                if case == "marker-only":
                    connection = open_fk(path)
                    try:
                        connection.execute(
                            "CREATE TABLE v5_series_episode_schema("
                            "component TEXT PRIMARY KEY,schema_version INTEGER NOT NULL)"
                        )
                        connection.execute(
                            "INSERT INTO v5_series_episode_schema VALUES('series_episode',1)"
                        )
                    finally:
                        connection.close()
                else:
                    SqliteSeriesEpisodeAdapter(path)
                    connection = open_fk(path)
                    try:
                        connection.execute("DROP TABLE v5_series_episode_schema")
                    finally:
                        connection.close()
                before = path.read_bytes()
                with self.assertRaises(LifecycleMigrationError):
                    migrate_lifecycle_database(path, allow_upgrade=True)
                self.assertEqual(path.read_bytes(), before)

    def test_complete_v1_m1_to_m5_rows_are_preserved_exactly(self):
        self._v1_database_with_data()
        from services.v5_core_os.project_engine.foundation import SqliteProjectAdapter
        from services.v5_core_os.script_studio.foundation import SqliteScriptStudioAdapter
        from services.v5_core_os.series_planning.foundation import SqliteSeriesPlanningAdapter
        SqliteProjectAdapter(self.path)
        SqliteScriptStudioAdapter(self.path)
        SqliteSeriesPlanningAdapter(self.path)
        connection = open_fk(self.path)
        try:
            series_ref = connection.execute("SELECT series_ref FROM v5_series").fetchone()[0]
            connection.execute("INSERT INTO v5_confirmed_creative_plans VALUES(?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a","plan-a","v5.confirmed-creative-plan.v1","source-a","creator.ai-director.plan.v1",1,"{}","{}","confirmed",NOW,1))
            connection.execute("INSERT INTO v5_projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a","project-a","v5.project.v1","profile-a","series","Project","","","9:16",30,1,"active",NOW,NOW,1))
            connection.execute("INSERT INTO v5_project_series_relationships VALUES(?,?,?,?,?,?)", ("workspace-a","project-a",series_ref,"v5.project-series-relationship.v1",NOW,1))
            connection.execute("INSERT INTO v5_episode_projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a","episode-a","v5.episode-project.v1",series_ref,1,1,1,"Episode","draft",None,"plan-a",NOW,NOW,1))
            connection.execute("INSERT INTO v5_episode_plan_bindings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a",series_ref,"episode-a","v5.confirmed-creative-plan-binding.v1","plan-a","source-a","creator.ai-director.plan.v1",1,"{}","{}",NOW,1))
            connection.execute("INSERT INTO v5_scripts VALUES(?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a",series_ref,"episode-a","script-a","v5.script.v1","Script","script-version-a",None,NOW,NOW,1))
            connection.execute("INSERT INTO v5_script_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a","script-a","script-version-a","v5.script-version.v1",series_ref,"episode-a","source-a","creator.ai-director.plan.v1",1,1,"{}","ai-generation",None,NOW))
            connection.execute("INSERT INTO v5_series_plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a","series-plan-a","v5.series-plan.v1","profile-a","project-a",series_ref,"series-plan-version-a","series-plan-version-a","confirmed",NOW,NOW,1))
            connection.execute("INSERT INTO v5_series_plan_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a","series-plan-a","series-plan-version-a","v5.series-plan-version.v1","profile-a","project-a",series_ref,1,"{}","ai-candidate-confirmed",None,NOW))
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'v5_%' AND name NOT LIKE '%_schema' ORDER BY name")]
            before = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in tables}
        finally:
            connection.close()
        self.assertEqual(migrate_lifecycle_database(self.path, allow_upgrade=True), "upgrade")
        after = open_fk(self.path)
        try:
            for table, rows in before.items():
                self.assertEqual([tuple(row) for row in after.execute(f"SELECT * FROM {table} ORDER BY rowid")], rows, table)
            self.assertEqual(after.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            after.close()

    def test_orphan_v1_upgrade_fails_closed_without_repair(self):
        self._v1_database_with_data()
        connection = open_fk(self.path)
        try:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("CREATE TABLE v5_project_schema(component TEXT PRIMARY KEY,schema_version INTEGER NOT NULL)")
            connection.execute("INSERT INTO v5_project_schema VALUES('project_context',1)")
            connection.execute("CREATE TABLE v5_projects(workspace_ref TEXT,project_ref TEXT,schema_version TEXT,content_profile_ref TEXT,project_type TEXT,title TEXT,description TEXT,target_platform TEXT,aspect_ratio TEXT,default_duration_sec INTEGER,planned_episode_count INTEGER,status TEXT,created_at TEXT,updated_at TEXT,version INTEGER,PRIMARY KEY(workspace_ref,project_ref))")
            connection.execute("CREATE TABLE v5_project_series_relationships(workspace_ref TEXT,project_ref TEXT,series_ref TEXT,schema_version TEXT,linked_at TEXT,version INTEGER,PRIMARY KEY(workspace_ref,project_ref,series_ref))")
            connection.execute("INSERT INTO v5_projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-a","project-a","v5.project.v1","profile-a","series","P","","","9:16",30,1,"active",NOW,NOW,1))
            connection.execute("INSERT INTO v5_project_series_relationships VALUES(?,?,?,?,?,?)", ("workspace-a","project-a","missing-series","v5.project-series-relationship.v1",NOW,1))
        finally:
            connection.close()
        with self.assertRaises(LifecycleMigrationError):
            migrate_lifecycle_database(self.path, allow_upgrade=True)
        verify = sqlite3.connect(self.path)
        try:
            self.assertEqual(verify.execute("SELECT series_ref FROM v5_project_series_relationships").fetchone()[0], "missing-series")
            self.assertEqual(verify.execute("SELECT schema_version FROM v5_project_schema").fetchone()[0], 1)
        finally:
            verify.close()

    def test_cross_workspace_reference_is_rejected_and_fault_rolls_back(self):
        self._v1_database_with_data()
        connection = open_fk(self.path)
        try:
            connection.execute("CREATE TABLE v5_project_schema(component TEXT PRIMARY KEY,schema_version INTEGER NOT NULL)")
            connection.execute("INSERT INTO v5_project_schema VALUES('project_context',1)")
            connection.execute("CREATE TABLE v5_projects(workspace_ref TEXT,project_ref TEXT,schema_version TEXT,content_profile_ref TEXT,project_type TEXT,title TEXT,description TEXT,target_platform TEXT,aspect_ratio TEXT,default_duration_sec INTEGER,planned_episode_count INTEGER,status TEXT,created_at TEXT,updated_at TEXT,version INTEGER,PRIMARY KEY(workspace_ref,project_ref))")
            connection.execute("CREATE TABLE v5_project_series_relationships(workspace_ref TEXT,project_ref TEXT,series_ref TEXT,schema_version TEXT,linked_at TEXT,version INTEGER,PRIMARY KEY(workspace_ref,project_ref,series_ref))")
            connection.execute("INSERT INTO v5_projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("workspace-b","project-b","v5.project.v1","profile-b","series","P","","","9:16",30,1,"active",NOW,NOW,1))
            connection.execute("INSERT INTO v5_project_series_relationships VALUES(?,?,?,?,?,?)", ("workspace-b","project-b","series-1","v5.project-series-relationship.v1",NOW,1))
        finally:
            connection.close()
        with self.assertRaises(LifecycleMigrationError):
            migrate_lifecycle_database(self.path, allow_upgrade=True)

        clean = Path(self.temp.name) / "clean.sqlite3"
        SqliteSeriesEpisodeAdapter(clean)
        before = clean.read_bytes()
        with self.assertRaises(RuntimeError):
            migrate_lifecycle_database(
                clean, allow_upgrade=True,
                fault=lambda point: (_ for _ in ()).throw(RuntimeError("fault")) if point == "after-copy" else None,
            )
        self.assertEqual(clean.read_bytes(), before)


class SqliteAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "assembly.sqlite3"
        migrate_lifecycle_database(self.path, allow_upgrade=True)
        self.first = LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)
        self.second = LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)

    def assert_integrity(self):
        connection = open_fk(self.path)
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def test_every_sqlite_adapter_connection_enforces_foreign_keys(self):
        adapters = (
            SqliteSeriesEpisodeAdapter(self.path),
            SqliteProjectAdapter(self.path),
            SqliteScriptStudioAdapter(self.path),
            SqliteSeriesPlanningAdapter(self.path),
        )
        for adapter in adapters:
            with self.subTest(adapter=type(adapter).__name__):
                connection = adapter._connect()
                try:
                    self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                finally:
                    connection.close()

    def race(self, one, two):
        barrier = Barrier(2)
        results = []
        def run(call):
            barrier.wait()
            try:
                results.append(("ok", call()))
            except BaseException as error:
                results.append(("error", error))
        threads = [Thread(target=run, args=(one,)), Thread(target=run, args=(two,))]
        for thread in threads: thread.start()
        for thread in threads: thread.join(15)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        return results

    def ordered_race(self, first_operation, first_call, second_call, *, ref_factory=None):
        entered = Event()
        release = Event()
        def hook(operation):
            if operation is first_operation:
                entered.set()
                if not release.wait(10):
                    raise TimeoutError("ordered race was not released")
        first_assembly = LifecycleAssembly.sqlite(
            self.path, ref_factory=ref_factory or Refs(), clock=lambda: NOW, transaction_hook=hook
        )
        results = {}
        def run(name, call):
            try:
                results[name] = ("ok", call(first_assembly) if name == "first" else call(self.second))
            except BaseException as error:
                results[name] = ("error", error)
        one = Thread(target=run, args=("first", first_call))
        one.start()
        self.assertTrue(entered.wait(10))
        two = Thread(target=run, args=("second", second_call))
        two.start()
        release.set()
        one.join(15); two.join(15)
        self.assertFalse(one.is_alive()); self.assertFalse(two.is_alive())
        return results

    def test_project_relationship_and_series_delete_cross_assembly_race(self):
        series = seed_series(self.first)
        results = self.ordered_race(
            LifecycleOperation.CREATE_PROJECT,
            lambda assembly: assembly.project_context.create_project(project_command(series)),
            lambda assembly: assembly.series_episode.delete_series("workspace-a", series["seriesRef"]),
        )
        self.assertEqual(results["first"][0], "ok", repr(results))
        self.assertEqual(results["second"][1].code, "dependent_project_exists")
        self.assert_integrity()

    def test_series_delete_first_rejects_late_project_relationship(self):
        series = seed_series(self.first)
        results = self.ordered_race(
            LifecycleOperation.DELETE_SERIES,
            lambda assembly: assembly.series_episode.delete_series("workspace-a", series["seriesRef"]),
            lambda assembly: assembly.project_context.create_project(project_command(series)),
        )
        self.assertEqual(results["first"][0], "ok")
        self.assertEqual(results["second"][1].code, "not_found")
        self.assert_integrity()

    def test_script_create_and_episode_delete_cross_assembly_race(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        results = self.ordered_race(
            LifecycleOperation.CREATE_SCRIPT_VERSION,
            lambda assembly: assembly.script_studio.create_version(script_command(series, episode)),
            lambda assembly: assembly.series_episode.delete_episode("workspace-a", series["seriesRef"], episode["episodeRef"]),
        )
        self.assertEqual(results["first"][0], "ok")
        self.assertEqual(results["second"][1].code, "dependent_script_exists")
        self.assert_integrity()

    def test_historical_binding_blocks_episode_delete_after_unbind_and_restart(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        project, initial, bound, _ = seed_bound_episode_plan(
            self.first, series, episode
        )
        self.first.series_planning.create_episode_plan_item_binding_version({
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial["plan"]["seriesPlanRef"],
            "expectedPlanVersion": bound["plan"]["version"],
            "episodePlanItemBindings": [],
        })
        restarted = LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)

        with self.assertRaises(SeriesEpisodePublicError) as error:
            restarted.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            )
        self.assertEqual(
            (error.exception.code, error.exception.status),
            ("dependent_series_plan_binding_exists", 409),
        )
        connection = open_fk(self.path)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM v5_series_plan_versions "
                    "WHERE workspace_ref=? AND series_ref=? AND schema_version=?",
                    (
                        "workspace-a",
                        series["seriesRef"],
                        "v5.series-plan-version.v2",
                    ),
                ).fetchone()[0],
                2,
            )
            self.assertIsNotNone(
                connection.execute(
                    "SELECT 1 FROM v5_episode_projects "
                    "WHERE workspace_ref=? AND series_ref=? AND episode_ref=?",
                    ("workspace-a", series["seriesRef"], episode["episodeRef"]),
                ).fetchone()
            )
        finally:
            connection.close()
        self.assert_integrity()

    def test_v1_series_plan_row_bytes_are_unchanged_by_bind_unbind_and_restart(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        project, initial, bound, _ = seed_bound_episode_plan(
            self.first, series, episode
        )
        connection = open_fk(self.path)
        try:
            before = tuple(connection.execute(
                "SELECT schema_version,content_json FROM v5_series_plan_versions "
                "WHERE workspace_ref=? AND series_plan_version_ref=?",
                ("workspace-a", initial["version"]["seriesPlanVersionRef"]),
            ).fetchone())
        finally:
            connection.close()
        self.first.series_planning.create_episode_plan_item_binding_version({
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial["plan"]["seriesPlanRef"],
            "expectedPlanVersion": bound["plan"]["version"],
            "episodePlanItemBindings": [],
        })
        LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)
        connection = open_fk(self.path)
        try:
            after = tuple(connection.execute(
                "SELECT schema_version,content_json FROM v5_series_plan_versions "
                "WHERE workspace_ref=? AND series_plan_version_ref=?",
                ("workspace-a", initial["version"]["seriesPlanVersionRef"]),
            ).fetchone())
        finally:
            connection.close()
        self.assertEqual(after, before)
        self.assertEqual(before[0], "v5.series-plan-version.v1")

    def test_binding_commit_uncertainty_poisons_and_restart_reconciles_durable_v2(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        project = self.first.project_context.create_project(project_command(series))
        initial = self.first.series_planning.confirm_candidate({
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": valid_candidate(project["plannedEpisodeCount"]),
        })
        command = {
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial["plan"]["version"],
            "episodePlanItemBindings": [{
                "episodeRef": episode["episodeRef"],
                "episodePlanItemRef": initial["version"]["episodePlanItems"][0][
                    "episodePlanItemRef"
                ],
            }],
        }
        uncertain_refs = Refs()
        uncertain_refs("series-plan-version")
        uncertain = LifecycleAssembly.sqlite(
            self.path, ref_factory=uncertain_refs, clock=lambda: NOW
        )
        state = uncertain.state
        original_connect = state._connect

        class CommitThenRaise:
            def __init__(self, inner): self.inner = inner
            def __getattr__(self, name): return getattr(self.inner, name)
            def commit(self):
                self.inner.commit()
                raise sqlite3.OperationalError("commit outcome uncertain")

        state._connect = lambda: CommitThenRaise(original_connect())
        with self.assertRaises(LifecycleRollbackError):
            uncertain.series_planning.create_episode_plan_item_binding_version(command)
        self.assertEqual(uncertain.diagnostic_snapshot()["state"], "poisoned")
        with self.assertRaises(AssemblyPoisonedError):
            uncertain.series_planning.get_workspace(
                "workspace-a", project["projectRef"], series["seriesRef"]
            )
        restarted = LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)
        workspace = restarted.series_planning.get_workspace(
            "workspace-a", project["projectRef"], series["seriesRef"]
        )
        self.assertEqual(workspace["versions"][-1]["schemaVersion"], "v5.series-plan-version.v2")
        with self.assertRaises(SeriesEpisodePublicError) as blocked:
            restarted.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            )
        self.assertEqual(blocked.exception.code, "dependent_series_plan_binding_exists")

    def test_binding_rollback_failure_poisons_and_restart_reads_exact_preimage(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        project = self.first.project_context.create_project(project_command(series))
        initial = self.first.series_planning.confirm_candidate({
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": valid_candidate(project["plannedEpisodeCount"]),
        })
        rollback_refs = Refs()
        rollback_refs("series-plan-version")
        uncertain = LifecycleAssembly.sqlite(
            self.path, ref_factory=rollback_refs, clock=lambda: NOW
        )
        state = uncertain.state
        original_connect = state._connect

        class FailingRollback:
            def __init__(self, inner): self.inner = inner
            def __getattr__(self, name): return getattr(self.inner, name)
            def rollback(self):
                raise sqlite3.OperationalError("rollback outcome uncertain")

        state._connect = lambda: FailingRollback(original_connect())
        service = uncertain.series_planning._SeriesPlanningPublicBoundary__service
        original_append = service.repository.append_version

        def append_then_fail(*args, **kwargs):
            original_append(*args, **kwargs)
            raise RuntimeError("fail after binding append")

        service.repository.append_version = append_then_fail
        with self.assertRaises(LifecycleRollbackError):
            uncertain.series_planning.create_episode_plan_item_binding_version({
                "workspaceRef": "workspace-a",
                "projectRef": project["projectRef"],
                "seriesRef": series["seriesRef"],
                "seriesPlanRef": initial["plan"]["seriesPlanRef"],
                "expectedPlanVersion": initial["plan"]["version"],
                "episodePlanItemBindings": [{
                    "episodeRef": episode["episodeRef"],
                    "episodePlanItemRef": initial["version"]["episodePlanItems"][0][
                        "episodePlanItemRef"
                    ],
                }],
            })
        self.assertEqual(uncertain.diagnostic_snapshot()["state"], "poisoned")
        restarted = LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)
        workspace = restarted.series_planning.get_workspace(
            "workspace-a", project["projectRef"], series["seriesRef"]
        )
        self.assertEqual(len(workspace["versions"]), 1)
        self.assertEqual(workspace["plan"]["version"], initial["plan"]["version"])

    def test_script_dependency_precedes_series_plan_binding_dependency(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        seed_bound_episode_plan(self.first, series, episode)
        self.first.script_studio.create_version(script_command(series, episode))

        with self.assertRaises(SeriesEpisodePublicError) as error:
            self.first.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            )
        self.assertEqual(
            (error.exception.code, error.exception.status),
            ("dependent_script_exists", 409),
        )

    def test_binding_create_and_episode_delete_cross_assembly_race(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        project = self.first.project_context.create_project(project_command(series))
        initial = self.first.series_planning.confirm_candidate({
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": valid_candidate(project["plannedEpisodeCount"]),
        })
        command = {
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial["plan"]["version"],
            "episodePlanItemBindings": [{
                "episodeRef": episode["episodeRef"],
                "episodePlanItemRef": initial["version"]["episodePlanItems"][0][
                    "episodePlanItemRef"
                ],
            }],
        }
        binding_refs = Refs()
        binding_refs("series-plan-version")
        results = self.ordered_race(
            LifecycleOperation.APPEND_SERIES_PLAN_VERSION,
            lambda assembly: assembly.series_planning.create_episode_plan_item_binding_version(
                command
            ),
            lambda assembly: assembly.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            ),
            ref_factory=binding_refs,
        )
        self.assertEqual(results["first"][0], "ok", repr(results))
        self.assertEqual(
            (results["second"][1].code, results["second"][1].status),
            ("dependent_series_plan_binding_exists", 409),
        )
        self.assert_integrity()

    def test_episode_delete_first_rejects_late_binding_cross_assembly(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        project = self.first.project_context.create_project(project_command(series))
        initial = self.first.series_planning.confirm_candidate({
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": valid_candidate(project["plannedEpisodeCount"]),
        })
        command = {
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial["plan"]["version"],
            "episodePlanItemBindings": [{
                "episodeRef": episode["episodeRef"],
                "episodePlanItemRef": initial["version"]["episodePlanItems"][0][
                    "episodePlanItemRef"
                ],
            }],
        }
        results = self.ordered_race(
            LifecycleOperation.DELETE_EPISODE,
            lambda assembly: assembly.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            ),
            lambda assembly: assembly.series_planning.create_episode_plan_item_binding_version(
                command
            ),
        )
        self.assertEqual(results["first"][0], "ok", repr(results))
        self.assertEqual(results["second"][0], "error", repr(results))
        self.assertIn(results["second"][1].code, {"not_found", "scope_mismatch"})
        connection = open_fk(self.path)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM v5_series_plan_versions "
                    "WHERE workspace_ref=? AND series_plan_ref=?",
                    ("workspace-a", initial["plan"]["seriesPlanRef"]),
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()
        self.assert_integrity()

    def test_partial_binding_write_rolls_back_sqlite_version_and_episode(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        project = self.first.project_context.create_project(project_command(series))
        initial = self.first.series_planning.confirm_candidate({
            "workspaceRef": "workspace-a",
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": valid_candidate(project["plannedEpisodeCount"]),
        })
        service = self.first.series_planning._SeriesPlanningPublicBoundary__service
        original = service.repository.append_version

        def append_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("injected failure after SQLite binding append")

        service.repository.append_version = append_then_fail
        try:
            with self.assertRaises(RuntimeError):
                self.first.series_planning.create_episode_plan_item_binding_version({
                    "workspaceRef": "workspace-a",
                    "projectRef": project["projectRef"],
                    "seriesRef": series["seriesRef"],
                    "seriesPlanRef": initial["plan"]["seriesPlanRef"],
                    "expectedPlanVersion": initial["plan"]["version"],
                    "episodePlanItemBindings": [{
                        "episodeRef": episode["episodeRef"],
                        "episodePlanItemRef": initial["version"]["episodePlanItems"][0][
                            "episodePlanItemRef"
                        ],
                    }],
                })
        finally:
            service.repository.append_version = original
        connection = open_fk(self.path)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM v5_series_plan_versions "
                    "WHERE workspace_ref=? AND series_plan_ref=?",
                    ("workspace-a", initial["plan"]["seriesPlanRef"]),
                ).fetchone()[0],
                1,
            )
            self.assertIsNotNone(
                connection.execute(
                    "SELECT 1 FROM v5_episode_projects "
                    "WHERE workspace_ref=? AND series_ref=? AND episode_ref=?",
                    ("workspace-a", series["seriesRef"], episode["episodeRef"]),
                ).fetchone()
            )
        finally:
            connection.close()
        self.assertEqual(self.first.diagnostic_snapshot()["state"], "ready")
        self.assert_integrity()

    def test_malformed_and_unknown_exact_scope_v2_history_blocks_episode_delete(self):
        for corruption in ("malformed-json", "unknown-schema", "empty-created-at"):
            with self.subTest(corruption=corruption):
                path = Path(self.temp.name) / f"{corruption}.sqlite3"
                migrate_lifecycle_database(path, allow_upgrade=True)
                assembly = LifecycleAssembly.sqlite(path, ref_factory=Refs(), clock=lambda: NOW)
                series = seed_series(assembly)
                episode = seed_episode(assembly, series)
                _, _, bound, _ = seed_bound_episode_plan(assembly, series, episode)
                connection = open_fk(path)
                try:
                    if corruption == "malformed-json":
                        connection.execute(
                            "UPDATE v5_series_plan_versions SET content_json=? "
                            "WHERE workspace_ref=? AND series_plan_version_ref=?",
                            (
                                "{",
                                "workspace-a",
                                bound["version"]["seriesPlanVersionRef"],
                            ),
                        )
                    elif corruption == "unknown-schema":
                        connection.execute(
                            "UPDATE v5_series_plan_versions SET schema_version=? "
                            "WHERE workspace_ref=? AND series_plan_version_ref=?",
                            (
                                "v5.series-plan-version.unknown",
                                "workspace-a",
                                bound["version"]["seriesPlanVersionRef"],
                            ),
                        )
                    else:
                        connection.execute(
                            "UPDATE v5_series_plan_versions SET created_at='' "
                            "WHERE workspace_ref=? AND series_plan_version_ref=?",
                            ("workspace-a", bound["version"]["seriesPlanVersionRef"]),
                        )
                finally:
                    connection.close()
                restarted = LifecycleAssembly.sqlite(path, ref_factory=Refs(), clock=lambda: NOW)
                with self.assertRaises(SeriesEpisodePublicError) as error:
                    restarted.series_episode.delete_episode(
                        "workspace-a", series["seriesRef"], episode["episodeRef"]
                    )
                self.assertEqual(
                    (error.exception.code, error.exception.status),
                    ("dependent_series_plan_binding_exists", 409),
                )

    def test_exact_scope_plan_with_all_version_rows_missing_blocks_episode_delete(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        _, initial, _, _ = seed_bound_episode_plan(self.first, series, episode)
        connection = open_fk(self.path)
        try:
            connection.execute(
                "DELETE FROM v5_series_plan_versions "
                "WHERE workspace_ref=? AND series_plan_ref=?",
                ("workspace-a", initial["plan"]["seriesPlanRef"]),
            )
        finally:
            connection.close()

        restarted = LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)
        with self.assertRaises(SeriesEpisodePublicError) as error:
            restarted.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            )
        self.assertEqual(
            (error.exception.code, error.exception.status),
            ("dependent_series_plan_binding_exists", 409),
        )

    def test_project_relationship_history_cannot_be_hidden_by_corrupt_sqlite_scope(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        _, initial, _, _ = seed_bound_episode_plan(self.first, series, episode)
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            connection.execute(
                "UPDATE v5_series_plans SET series_ref=? "
                "WHERE workspace_ref=? AND series_plan_ref=?",
                ("series-hidden", "workspace-a", initial["plan"]["seriesPlanRef"]),
            )
            connection.execute(
                "UPDATE v5_series_plan_versions SET series_ref=? "
                "WHERE workspace_ref=? AND series_plan_ref=?",
                ("series-hidden", "workspace-a", initial["plan"]["seriesPlanRef"]),
            )
        finally:
            connection.close()

        repository = SqliteSeriesPlanningAdapter(self.path)
        self.assertTrue(
            repository.lifecycle_has_episode_binding_dependency(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            )
        )
        with self.assertRaises(LifecycleMigrationError):
            LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)

    def test_malformed_historical_version_ref_blocks_sqlite_episode_delete(self):
        series = seed_series(self.first)
        bound_episode = seed_episode(self.first, series)
        other_episode = self.first.series_episode.create_episode({
            "workspaceRef": "workspace-a",
            "seriesRef": series["seriesRef"],
            "creativePlanRef": bound_episode["creativePlanRef"],
            "episodeNumber": 2,
            "title": "第2集",
        })
        _, initial, bound, _ = seed_bound_episode_plan(
            self.first, series, bound_episode
        )
        connection = open_fk(self.path)
        try:
            connection.execute(
                "UPDATE v5_series_plan_versions SET series_plan_version_ref=? "
                "WHERE workspace_ref=? AND series_plan_ref=? AND version_number=1",
                ("bad ref", "workspace-a", initial["plan"]["seriesPlanRef"]),
            )
            connection.execute(
                "UPDATE v5_series_plan_versions SET parent_version_ref=? "
                "WHERE workspace_ref=? AND series_plan_ref=? AND version_number=2",
                ("bad ref", "workspace-a", initial["plan"]["seriesPlanRef"]),
            )
            connection.execute(
                "UPDATE v5_series_plans SET confirmed_version_ref=? "
                "WHERE workspace_ref=? AND series_plan_ref=?",
                (
                    bound["version"]["seriesPlanVersionRef"],
                    "workspace-a",
                    initial["plan"]["seriesPlanRef"],
                ),
            )
        finally:
            connection.close()

        restarted = LifecycleAssembly.sqlite(self.path, ref_factory=Refs(), clock=lambda: NOW)
        with self.assertRaises(SeriesEpisodePublicError) as protected:
            restarted.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], other_episode["episodeRef"]
            )
        self.assertEqual(protected.exception.code, "dependent_series_plan_binding_exists")

    def test_append_and_series_delete_cross_assembly_race(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        initial = self.first.script_studio.create_version(script_command(series, episode))
        append = script_command(series, episode)
        append["content"] = {key: initial["scriptVersion"][key] for key in ("title","logline","synopsis","targetDurationSec","scenes")}
        append.update({"changeKind":"manual-edit","scriptRef":initial["script"]["scriptRef"],"baseScriptVersionRef":initial["scriptVersion"]["scriptVersionRef"]})
        append_refs = Refs()
        append_refs("script-version")
        results = self.ordered_race(
            LifecycleOperation.CREATE_SCRIPT_VERSION,
            lambda assembly: assembly.script_studio.create_version(append),
            lambda assembly: assembly.series_episode.delete_series("workspace-a", series["seriesRef"]),
            ref_factory=append_refs,
        )
        self.assertEqual(results["first"][0], "ok", repr(results))
        self.assertEqual(results["second"][1].code, "dependent_script_exists")
        self.assert_integrity()

    def test_first_script_version_and_series_delete_cross_assembly_race(self):
        series = seed_series(self.first)
        episode = seed_episode(self.first, series)
        results = self.ordered_race(
            LifecycleOperation.CREATE_SCRIPT_VERSION,
            lambda assembly: assembly.script_studio.create_version(script_command(series, episode)),
            lambda assembly: assembly.series_episode.delete_series("workspace-a", series["seriesRef"]),
        )
        self.assertEqual(results["first"][0], "ok")
        self.assertEqual(results["second"][1].code, "dependent_script_exists")
        self.assert_integrity()

    def test_same_refs_across_workspaces_are_isolated(self):
        fixed = Refs(fixed=True)
        assembly = LifecycleAssembly.sqlite(self.path, ref_factory=fixed, clock=lambda: NOW)
        a = seed_series(assembly, "workspace-a", "profile-a")
        b = seed_series(assembly, "workspace-b", "profile-b")
        ea = seed_episode(assembly, a, "workspace-a")
        eb = seed_episode(assembly, b, "workspace-b")
        assembly.script_studio.create_version(script_command(b, eb, "workspace-b"))
        assembly.series_episode.delete_episode("workspace-a", a["seriesRef"], ea["episodeRef"])
        self.assertEqual(assembly.series_episode.get_episode("workspace-b", b["seriesRef"], eb["episodeRef"])["workspaceRef"], "workspace-b")
        self.assert_integrity()

    def test_same_binding_refs_across_workspaces_are_isolated(self):
        fixed = Refs(fixed=True)
        assembly = LifecycleAssembly.sqlite(self.path, ref_factory=fixed, clock=lambda: NOW)
        series_a = seed_series(assembly, "workspace-a", "profile-a")
        episode_a = seed_episode(assembly, series_a, "workspace-a")
        series_b = seed_series(assembly, "workspace-b", "profile-b")
        episode_b = seed_episode(assembly, series_b, "workspace-b")
        seed_bound_episode_plan(
            assembly,
            series_b,
            episode_b,
            workspace="workspace-b",
            profile="profile-b",
        )

        deleted = assembly.series_episode.delete_episode(
            "workspace-a", series_a["seriesRef"], episode_a["episodeRef"]
        )
        self.assertEqual(deleted["deletedEpisodeCount"], 1)
        self.assertEqual(
            assembly.series_episode.get_episode(
                "workspace-b", series_b["seriesRef"], episode_b["episodeRef"]
            )["workspaceRef"],
            "workspace-b",
        )
        self.assert_integrity()

    def test_fk_error_is_domain_mapped(self):
        series = seed_series(self.first)
        fake = dict(series)
        fake["seriesRef"] = "missing"
        with self.assertRaises(ProjectPublicError) as error:
            self.first.project_context.create_project(project_command(fake))
        self.assertEqual(error.exception.code, "not_found")

    def test_commit_uncertainty_poisoned_state(self):
        state = SqliteLifecycleState(self.path)
        class FailingCommit:
            def __init__(self, inner): self.inner = inner
            def execute(self, *args, **kwargs): return self.inner.execute(*args, **kwargs)
            def rollback(self): return self.inner.rollback()
            def close(self): return self.inner.close()
            def commit(self): raise sqlite3.OperationalError("uncertain")
        original = state._connect
        state._connect = lambda: FailingCommit(original())
        with self.assertRaises(LifecycleRollbackError):
            with state.lease(workspace_ref="workspace", operation=LifecycleOperation.CREATE_PROJECT):
                pass
        self.assertEqual(state.diagnostic_snapshot()["state"], "poisoned")
        with self.assertRaises(AssemblyPoisonedError):
            with state.lease(workspace_ref="workspace", operation=LifecycleOperation.CREATE_PROJECT):
                pass

    def test_rollback_failure_poisoned_state(self):
        state = SqliteLifecycleState(self.path)
        class FailingRollback:
            def __init__(self, inner): self.inner = inner
            def execute(self, *args, **kwargs): return self.inner.execute(*args, **kwargs)
            def rollback(self): raise sqlite3.OperationalError("rollback uncertain")
            def close(self): return self.inner.close()
            def commit(self): return self.inner.commit()
        original = state._connect
        state._connect = lambda: FailingRollback(original())
        with self.assertRaises(LifecycleRollbackError):
            with state.lease(workspace_ref="workspace", operation=LifecycleOperation.CREATE_PROJECT):
                raise RuntimeError("mutation failed")
        self.assertEqual(state.diagnostic_snapshot()["state"], "poisoned")
        with self.assertRaises(AssemblyPoisonedError):
            with state.lease(workspace_ref="workspace", operation=LifecycleOperation.CREATE_PROJECT):
                pass


if __name__ == "__main__":
    unittest.main()
