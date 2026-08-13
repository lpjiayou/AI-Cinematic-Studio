import copy
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier, Event, Thread
import unittest
import unicodedata

from services.v5_core_os.lifecycle_integrity import (
    LifecycleAssembly,
    LifecycleMigrationError,
    LifecycleOperation,
    migrate_lifecycle_database,
)
from services.v5_core_os.lifecycle_integrity.sqlite_schema import (
    MARKERS,
    SQLITE_LIFECYCLE_SCHEMA_VERSION,
    index_statements,
    table_statements,
)
from services.v5_core_os.series_episode.foundation import SqliteSeriesEpisodeAdapter
from services.v5_core_os.series_intelligence import M6Scope, VerifiedApproval
from services.v5_core_os.series_intelligence.migration import (
    SeriesIntelligenceMigrationError,
    migrate_series_intelligence_database,
    validate_series_intelligence_database,
)
from services.v5_core_os.series_intelligence.public import (
    SeriesIntelligencePublicError,
)
from tests.unit.test_series_intelligence_m6 import (
    NOW,
    base_command,
    bible_content,
    character_content,
    confirmed_components,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_series_planning_m5 import valid_candidate


class TaggedRefs:
    def __init__(self, tag):
        self.tag = tag
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-{self.tag}-{self.counts[prefix]}"


class FixedRefs:
    def __call__(self, prefix):
        return f"{prefix}-shared"


class PrefixCollisionRefs:
    def __init__(self, collision_prefix, tag):
        self.collision_prefix = collision_prefix
        self.unique = TaggedRefs(tag)

    def __call__(self, prefix):
        if prefix == self.collision_prefix:
            return f"{prefix}-collision"
        return self.unique(prefix)


class BlockingGetMapping:
    def __init__(self, delegate, entered, release):
        self.delegate = delegate
        self.entered = entered
        self.release = release

    def get(self, key, default=None):
        value = self.delegate.get(key, default)
        self.entered.set()
        if not self.release.wait(15):
            raise TimeoutError("concurrent read was not released")
        return value

    def __getattr__(self, name):
        return getattr(self.delegate, name)


class ConfiguredScopeAuthority:
    def __init__(self, business_domain="series-production", tenant_id="tenant-m6"):
        self.business_domain = business_domain
        self.tenant_id = tenant_id

    def resolve_scope(self, workspace_ref, project_ref, series_ref):
        return M6Scope(
            self.business_domain,
            self.tenant_id,
            workspace_ref,
            project_ref,
            series_ref,
        )


class ApprovalAuthority:
    def verify_approval(self, *, scope, approval_ref, action):
        if approval_ref != "approval-human":
            raise RuntimeError("approval was not resolved")
        return VerifiedApproval(approval_ref, "actor-owner", "human")


def open_fk(path):
    connection = sqlite3.connect(path, isolation_level=None, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def create_accepted_v2(path):
    """Create an accepted Lifecycle V2 database without the additive M6 schema."""
    connection = open_fk(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in table_statements():
            connection.execute(statement)
        for marker, component in MARKERS.items():
            connection.execute(
                f"CREATE TABLE {marker} ("
                "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
            )
            connection.execute(
                f"INSERT INTO {marker} VALUES (?, ?)",
                (component, SQLITE_LIFECYCLE_SCHEMA_VERSION),
            )
        for statement in index_statements():
            connection.execute(statement)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_accepted_v1(path):
    """Create the smallest accepted pre-R2 Lifecycle V1 database."""
    SqliteSeriesEpisodeAdapter(path)


def seed_all_v2_tables(path):
    connection = open_fk(path)
    try:
        values = {
            "v5_series": (
                "workspace-a", "series-a", "v5.series.v1", "profile-a", "Series",
                "", "active", 4, NOW, NOW, 1,
            ),
            "v5_confirmed_creative_plans": (
                "workspace-a", "creative-plan-a", "v5.confirmed-creative-plan.v1",
                "source-a", "creator.ai-director.plan.v1", 1, "{}", "{}",
                "confirmed", NOW, 1,
            ),
            "v5_projects": (
                "workspace-a", "project-a", "v5.project.v1", "profile-a", "series",
                "Project", "", "", "9:16", 30, 4, "active", NOW, NOW, 1,
            ),
            "v5_project_series_relationships": (
                "workspace-a", "project-a", "series-a",
                "v5.project-series-relationship.v1", NOW, 1,
            ),
            "v5_episode_projects": (
                "workspace-a", "episode-a", "v5.episode-project.v1", "series-a", 1,
                1, 1, "Episode", "draft", None, "creative-plan-a", NOW, NOW, 1,
            ),
            "v5_episode_plan_bindings": (
                "workspace-a", "series-a", "episode-a",
                "v5.confirmed-creative-plan-binding.v1", "creative-plan-a", "source-a",
                "creator.ai-director.plan.v1", 1, "{}", "{}", NOW, 1,
            ),
            "v5_scripts": (
                "workspace-a", "series-a", "episode-a", "script-a", "v5.script.v1",
                "Script", "script-version-a", None, NOW, NOW, 1,
            ),
            "v5_script_versions": (
                "workspace-a", "script-a", "script-version-a", "v5.script-version.v1",
                "series-a", "episode-a", "source-a", "creator.ai-director.plan.v1", 1,
                1, "{}", "ai-generation", None, NOW,
            ),
            "v5_series_plans": (
                "workspace-a", "series-plan-a", "v5.series-plan.v1", "profile-a",
                "project-a", "series-a", "series-plan-version-a",
                "series-plan-version-a", "confirmed", NOW, NOW, 1,
            ),
            "v5_series_plan_versions": (
                "workspace-a", "series-plan-a", "series-plan-version-a",
                "v5.series-plan-version.v1", "profile-a", "project-a", "series-a", 1,
                "{}", "ai-candidate-confirmed", None, NOW,
            ),
        }
        for table, row in values.items():
            placeholders = ",".join("?" for _ in row)
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", row)
    finally:
        connection.close()


def snapshot_tables(path, *, prefix="v5_"):
    connection = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name LIKE ? ORDER BY name",
                (f"{prefix}%",),
            )
        ]
        return {
            table: [tuple(row) for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            )]
            for table in tables
        }
    finally:
        connection.close()


def snapshot_database(path):
    """Capture logical schema and rows; an absent and an empty file are equivalent."""
    if not path.exists():
        return (), {}
    connection = sqlite3.connect(path)
    try:
        objects = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            )
        )
        tables = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        rows = {
            table: tuple(
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            )
            for table in tables
        }
        return objects, rows
    finally:
        connection.close()


def new_assembly(
    path,
    *,
    refs=None,
    scope_authority=None,
    transaction_hook=None,
    fault_hook=None,
):
    return LifecycleAssembly.sqlite(
        path,
        ref_factory=refs or TaggedRefs("default"),
        clock=lambda: NOW,
        transaction_hook=transaction_hook,
        m6_scope_authority=scope_authority or ConfiguredScopeAuthority(),
        m6_approval_authority=ApprovalAuthority(),
        m6_fault_hook=fault_hook,
    )


def seed_m1_to_m5(assembly, *, workspace="workspace-m6"):
    series = assembly.series_episode.create_series({
        "workspaceRef": workspace,
        "contentProfileRef": f"profile-{workspace}",
        "title": "晚灯",
        "plannedEpisodeCount": 4,
    })
    project = assembly.project_context.create_project({
        "workspaceRef": workspace,
        "contentProfileRef": f"profile-{workspace}",
        "projectType": "series",
        "seriesRef": series["seriesRef"],
        "title": "晚灯系列制作",
        "plannedEpisodeCount": 4,
    })
    plan = assembly.series_planning.confirm_candidate({
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "humanConfirmed": True,
        "candidate": valid_candidate(),
    })
    return {
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "plan": plan,
    }


def seed_bound_v2(assembly, context, *, binding_count=2):
    source = valid_plan()
    confirmed = assembly.series_episode.confirm_creative_plan({
        "workspaceRef": context["workspaceRef"],
        "humanConfirmed": True,
        "sourcePlanRef": f"binding-source-{context['workspaceRef']}",
        "sourcePlanSchemaVersion": source["schemaVersion"],
        "sourcePlanVersion": 1,
        "brief": valid_brief(),
        "sourcePlan": source,
    })
    episodes = [
        assembly.series_episode.create_episode({
            "workspaceRef": context["workspaceRef"],
            "seriesRef": context["seriesRef"],
            "creativePlanRef": confirmed["creativePlanRef"],
            "episodeNumber": number,
            "title": f"第{number}集",
        })
        for number in range(1, binding_count + 1)
    ]
    item_refs = [
        item["episodePlanItemRef"]
        for item in context["plan"]["version"]["episodePlanItems"]
    ]
    requested = [
        {
            "episodeRef": episode["episodeRef"],
            "episodePlanItemRef": item_refs[index],
        }
        for index, episode in enumerate(episodes)
    ]
    created = assembly.series_planning.create_episode_plan_item_binding_version({
        "workspaceRef": context["workspaceRef"],
        "projectRef": context["projectRef"],
        "seriesRef": context["seriesRef"],
        "seriesPlanRef": context["plan"]["plan"]["seriesPlanRef"],
        "expectedPlanVersion": context["plan"]["plan"]["version"],
        "episodePlanItemBindings": list(reversed(requested)),
    })
    assembly.series_planning.confirm_version({
        "workspaceRef": context["workspaceRef"],
        "seriesPlanRef": created["plan"]["seriesPlanRef"],
        "seriesPlanVersionRef": created["version"]["seriesPlanVersionRef"],
        "expectedPlanVersion": created["plan"]["version"],
        "humanConfirmed": True,
    })
    return created, requested


def activate(assembly, context, bible, characters, operation="activate"):
    return assembly.series_intelligence.activate_baseline({
        **base_command(context, operation),
        "seriesBibleRef": bible["root"]["seriesBibleRef"],
        "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
        "characterContinuityRef": characters["root"]["characterContinuityRef"],
        "characterContinuityVersionRef": characters["version"][
            "characterContinuityVersionRef"
        ],
        "expectedActivationRevision": 0,
        "approvalRef": "approval-human",
    })


def scoped_outbox(boundary, context):
    return boundary.get_outbox(
        context["workspaceRef"],
        context["projectRef"],
        context["seriesRef"],
    )


def replacement_components(assembly, context, bible, characters):
    m6 = assembly.series_intelligence
    bible_v2 = m6.create_bible_version({
        **base_command(context, "bible-v2-create"),
        "seriesBibleRef": bible["root"]["seriesBibleRef"],
        "expectedRevision": bible["root"]["revision"],
        "candidate": True,
        "content": bible_content("location-v2"),
    })
    bible_v2 = m6.confirm_bible_version({
        **base_command(context, "bible-v2-confirm"),
        "seriesBibleRef": bible_v2["root"]["seriesBibleRef"],
        "seriesBibleVersionRef": bible_v2["version"]["seriesBibleVersionRef"],
        "expectedRevision": bible_v2["root"]["revision"],
        "approvalRef": "approval-human",
    })
    source = assembly.series_planning.get_confirmed_m6_source_snapshot(
        context["workspaceRef"], context["projectRef"], context["seriesRef"]
    )
    character_v2 = m6.create_character_version({
        **base_command(context, "character-v2-create"),
        "characterContinuityRef": characters["root"]["characterContinuityRef"],
        "expectedRevision": characters["root"]["revision"],
        "candidate": True,
        "seriesBibleRef": bible_v2["root"]["seriesBibleRef"],
        "seriesBibleVersionRef": bible_v2["version"]["seriesBibleVersionRef"],
        "content": character_content(
            [item["episodePlanItemRef"] for item in source["episodePlanItems"]],
            "location-v2",
        ),
    })
    character_v2 = m6.confirm_character_version({
        **base_command(context, "character-v2-confirm"),
        "characterContinuityRef": character_v2["root"]["characterContinuityRef"],
        "characterContinuityVersionRef": character_v2["version"][
            "characterContinuityVersionRef"
        ],
        "expectedRevision": character_v2["root"]["revision"],
        "approvalRef": "approval-human",
    })
    return bible_v2, character_v2


class SeriesIntelligenceSqliteMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def assert_validation_entrypoints_reject_without_repair(self, path):
        before = snapshot_database(path)
        entrypoints = (
            ("validate", validate_series_intelligence_database),
            ("m6-noop", migrate_series_intelligence_database),
            (
                "combined-noop",
                lambda target: migrate_lifecycle_database(
                    target, allow_upgrade=True
                ),
            ),
        )
        for name, entrypoint in entrypoints:
            with self.subTest(entrypoint=name):
                with self.assertRaises(RuntimeError):
                    entrypoint(path)
        self.assertEqual(snapshot_database(path), before)

    def test_combined_fresh_v2_upgrade_and_repeated_noop(self):
        fresh = Path(self.temp.name) / "fresh.sqlite3"
        self.assertEqual(
            migrate_lifecycle_database(fresh, allow_upgrade=True), "fresh"
        )
        self.assertEqual(
            migrate_lifecycle_database(fresh, allow_upgrade=True), "no-op"
        )

        upgrade = Path(self.temp.name) / "upgrade.sqlite3"
        create_accepted_v2(upgrade)
        self.assertEqual(
            migrate_lifecycle_database(upgrade, allow_upgrade=True), "upgrade"
        )
        self.assertEqual(
            migrate_lifecycle_database(upgrade, allow_upgrade=True), "no-op"
        )
        connection = open_fk(upgrade)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT schema_version FROM v5_series_intelligence_schema "
                    "WHERE component='series_intelligence'"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def test_v2_upgrade_preserves_every_existing_m1_to_m5_field(self):
        path = Path(self.temp.name) / "preserve.sqlite3"
        create_accepted_v2(path)
        seed_all_v2_tables(path)
        before = snapshot_tables(path)
        self.assertEqual(
            migrate_lifecycle_database(path, allow_upgrade=True), "upgrade"
        )
        after = snapshot_tables(path)
        for table, rows in before.items():
            with self.subTest(table=table):
                self.assertEqual(after[table], rows)

    def test_all_m6_migration_fault_points_rollback_schema_markers_and_rows(self):
        for point in (
            "after-copy",
            "before-marker-update",
            "before-verify",
            "before-commit",
        ):
            with self.subTest(point=point):
                path = Path(self.temp.name) / f"fault-{point}.sqlite3"
                create_accepted_v2(path)
                seed_all_v2_tables(path)
                before = snapshot_tables(path)
                with self.assertRaises(RuntimeError):
                    migrate_lifecycle_database(
                        path,
                        allow_upgrade=True,
                        fault=lambda current, target=point: (
                            (_ for _ in ()).throw(RuntimeError(target))
                            if current == target else None
                        ),
                    )
                self.assertEqual(snapshot_tables(path), before)

    def test_combined_fresh_m6_faults_leave_no_partial_lifecycle_schema(self):
        for point in (
            "after-copy",
            "before-marker-update",
            "before-verify",
            "before-commit",
        ):
            with self.subTest(point=point):
                path = Path(self.temp.name) / f"fresh-combined-{point}.sqlite3"
                before = snapshot_database(path)
                occurrences = {point: 0}

                def fail_during_m6(current, target=point):
                    if current != target:
                        return
                    occurrences[target] += 1
                    expected = 1 if target in {
                        "after-copy", "before-marker-update"
                    } else 2
                    if occurrences[target] == expected:
                        raise RuntimeError(target)

                with self.assertRaises(RuntimeError):
                    migrate_lifecycle_database(
                        path,
                        allow_upgrade=True,
                        fault=fail_during_m6,
                    )
                self.assertEqual(snapshot_database(path), before)

    def test_combined_v1_to_m6_faults_restore_the_exact_v1_database(self):
        for point in (
            "after-copy",
            "before-marker-update",
            "before-verify",
            "before-commit",
        ):
            with self.subTest(point=point):
                path = Path(self.temp.name) / f"v1-combined-{point}.sqlite3"
                create_accepted_v1(path)
                before = snapshot_database(path)
                occurrences = {point: 0}

                def fail_during_m6(current, target=point):
                    if current != target:
                        return
                    occurrences[target] += 1
                    if occurrences[target] == 2:
                        raise RuntimeError(target)

                with self.assertRaises(RuntimeError):
                    migrate_lifecycle_database(
                        path,
                        allow_upgrade=True,
                        fault=fail_during_m6,
                    )
                self.assertEqual(snapshot_database(path), before)

    def test_complete_but_forged_m6_schema_is_not_accepted_as_noop(self):
        mutations = {
            "missing-active-index": lambda connection: connection.execute(
                "DROP INDEX ux_m6_one_active_baseline"
            ),
            "forged-operation-table": lambda connection: (
                connection.execute("DROP TABLE v5_m6_operations"),
                connection.execute(
                    "CREATE TABLE v5_m6_operations (forged_column TEXT)"
                ),
            ),
            "extra-marker-row": lambda connection: connection.execute(
                "INSERT INTO v5_series_intelligence_schema VALUES ('forged', 1)"
            ),
            "rogue-trigger": lambda connection: connection.execute(
                "CREATE TRIGGER forged_m6_trigger "
                "AFTER INSERT ON v5_m6_operations BEGIN SELECT 1; END"
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                path = Path(self.temp.name) / f"forged-{name}.sqlite3"
                migrate_lifecycle_database(path, allow_upgrade=True)
                connection = open_fk(path)
                try:
                    mutate(connection)
                finally:
                    connection.close()
                before = snapshot_database(path)
                with self.assertRaises(SeriesIntelligenceMigrationError):
                    validate_series_intelligence_database(path)
                with self.assertRaises(SeriesIntelligenceMigrationError):
                    migrate_series_intelligence_database(path)
                self.assertEqual(snapshot_database(path), before)

    def test_standalone_m6_migration_rejects_a_database_without_accepted_v2(self):
        path = Path(self.temp.name) / "forged-lifecycle.sqlite3"
        connection = open_fk(path)
        try:
            connection.execute(
                "CREATE TABLE v5_series_plan_versions ("
                "workspace_ref TEXT, project_ref TEXT, series_ref TEXT, "
                "series_plan_ref TEXT, series_plan_version_ref TEXT, "
                "UNIQUE(workspace_ref,project_ref,series_ref,"
                "series_plan_ref,series_plan_version_ref))"
            )
        finally:
            connection.close()
        before = snapshot_database(path)
        with self.assertRaises(SeriesIntelligenceMigrationError):
            migrate_series_intelligence_database(path)
        self.assertEqual(snapshot_database(path), before)

    def test_allow_upgrade_false_rejects_v2_to_m6_without_any_change(self):
        path = Path(self.temp.name) / "upgrade-disabled.sqlite3"
        create_accepted_v2(path)
        seed_all_v2_tables(path)
        before = snapshot_database(path)
        with self.assertRaises(LifecycleMigrationError):
            migrate_lifecycle_database(path, allow_upgrade=False)
        self.assertEqual(snapshot_database(path), before)

    def test_tampered_durable_rows_fail_validation_and_noop_without_repair(self):
        def bible_only(path):
            assembly = new_assembly(path, refs=TaggedRefs("tamper"))
            context = seed_m1_to_m5(assembly, workspace="workspace-tamper")
            assembly.series_intelligence.create_bible_version({
                **base_command(context, "tamper-create-bible"),
                "content": bible_content(),
            })

        def activated(path):
            assembly = new_assembly(path, refs=TaggedRefs("tamper"))
            context = seed_m1_to_m5(assembly, workspace="workspace-tamper")
            bible, characters = confirmed_components(assembly, context)
            activate(assembly, context, bible, characters, "tamper-activate")

        cases = {
            "root-record-json": (
                bible_only,
                "UPDATE v5_m6_series_bibles SET record_json='{}'",
            ),
            "version-content-json": (
                bible_only,
                "UPDATE v5_m6_series_bible_versions SET content_json='{}'",
            ),
            "version-digests": (
                bible_only,
                "UPDATE v5_m6_series_bible_versions "
                f"SET content_digest='{'0' * 64}', canonical_digest='{'0' * 64}'",
            ),
            "operation-result-json": (
                bible_only,
                "UPDATE v5_m6_operations SET result_json='{'",
            ),
            "outbox-projection": (
                activated,
                "UPDATE v5_m6_outbox SET event_type='TamperedEvent'",
            ),
        }
        for name, (seed, mutation) in cases.items():
            with self.subTest(name=name):
                path = Path(self.temp.name) / f"tampered-row-{name}.sqlite3"
                migrate_lifecycle_database(path, allow_upgrade=True)
                seed(path)
                connection = open_fk(path)
                try:
                    connection.execute(mutation)
                finally:
                    connection.close()
                before = snapshot_database(path)

                for validation in (
                    validate_series_intelligence_database,
                    lambda target: migrate_series_intelligence_database(target),
                    lambda target: migrate_lifecycle_database(
                        target, allow_upgrade=True
                    ),
                ):
                    with self.subTest(name=name, validation=repr(validation)):
                        with self.assertRaises(RuntimeError):
                            validation(path)
                self.assertEqual(snapshot_database(path), before)

    def test_type_lineage_and_operation_shape_tampering_is_fail_closed(self):
        def bible_with_two_versions(path):
            assembly = new_assembly(path, refs=TaggedRefs("lineage-tamper"))
            context = seed_m1_to_m5(
                assembly, workspace="workspace-lineage-tamper"
            )
            original = assembly.series_intelligence.create_bible_version({
                **base_command(context, "lineage-create-v1"),
                "content": bible_content(),
            })
            assembly.series_intelligence.create_bible_version({
                **base_command(context, "lineage-create-v2"),
                "seriesBibleRef": original["root"]["seriesBibleRef"],
                "expectedRevision": original["root"]["revision"],
                "candidate": True,
                "content": bible_content("lineage-v2"),
            })

        def confirmed_bible(path):
            assembly = new_assembly(path, refs=TaggedRefs("confirmed-tamper"))
            context = seed_m1_to_m5(
                assembly, workspace="workspace-confirmed-tamper"
            )
            bible, _characters = confirmed_components(assembly, context)
            assembly.series_intelligence.create_bible_version({
                **base_command(context, "confirmed-create-v2"),
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "expectedRevision": bible["root"]["revision"],
                "candidate": True,
                "content": bible_content("unconfirmed-v2"),
            })

        def activated(path):
            assembly = new_assembly(path, refs=TaggedRefs("event-type-tamper"))
            context = seed_m1_to_m5(
                assembly, workspace="workspace-event-type-tamper"
            )
            bible, characters = confirmed_components(assembly, context)
            activate(assembly, context, bible, characters, "type-activate")

        def mutate_json(connection, table, where, mutate):
            row = connection.execute(
                f"SELECT rowid,record_json FROM {table} {where}"
            ).fetchone()
            record = json.loads(row["record_json"])
            mutate(record)
            connection.execute(
                f"UPDATE {table} SET record_json=? WHERE rowid=?",
                (
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    row["rowid"],
                ),
            )

        def revision_bool(connection):
            mutate_json(
                connection,
                "v5_m6_series_bibles",
                "",
                lambda record: record.__setitem__("revision", True),
            )

        def event_version_bool(connection):
            row = connection.execute(
                "SELECT position,event_json FROM v5_m6_outbox"
            ).fetchone()
            event = json.loads(row["event_json"])
            event["eventVersion"] = True
            connection.execute(
                "UPDATE v5_m6_outbox SET event_json=? WHERE position=?",
                (
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    row["position"],
                ),
            )

        def confirmed_ref_to_candidate(connection):
            candidate_ref = connection.execute(
                "SELECT series_bible_version_ref FROM v5_m6_series_bible_versions "
                "WHERE status='CANDIDATE'"
            ).fetchone()[0]
            mutate_json(
                connection,
                "v5_m6_series_bibles",
                "",
                lambda record: record.__setitem__(
                    "confirmedSeriesBibleVersionRef", candidate_ref
                ),
            )
            connection.execute(
                "UPDATE v5_m6_series_bibles "
                "SET confirmed_series_bible_version_ref=?",
                (candidate_ref,),
            )

        def parent_self(connection):
            target = connection.execute(
                "SELECT series_bible_version_ref FROM v5_m6_series_bible_versions "
                "WHERE version_number=2"
            ).fetchone()[0]
            mutate_json(
                connection,
                "v5_m6_series_bible_versions",
                "WHERE version_number=2",
                lambda record: record.__setitem__(
                    "parentSeriesBibleVersionRef", target
                ),
            )
            connection.execute(
                "UPDATE v5_m6_series_bible_versions "
                "SET parent_series_bible_version_ref=? WHERE version_number=2",
                (target,),
            )

        def parent_forward(connection):
            target = connection.execute(
                "SELECT series_bible_version_ref FROM v5_m6_series_bible_versions "
                "WHERE version_number=2"
            ).fetchone()[0]
            mutate_json(
                connection,
                "v5_m6_series_bible_versions",
                "WHERE version_number=1",
                lambda record: record.__setitem__(
                    "parentSeriesBibleVersionRef", target
                ),
            )
            connection.execute(
                "UPDATE v5_m6_series_bible_versions "
                "SET parent_series_bible_version_ref=? WHERE version_number=1",
                (target,),
            )

        cases = (
            ("revision-bool", bible_with_two_versions, revision_bool),
            ("event-version-bool", activated, event_version_bool),
            ("confirmed-ref-candidate", confirmed_bible, confirmed_ref_to_candidate),
            ("parent-self", bible_with_two_versions, parent_self),
            ("parent-forward", bible_with_two_versions, parent_forward),
            (
                "canonical-empty-operation-result",
                bible_with_two_versions,
                lambda connection: connection.execute(
                    "UPDATE v5_m6_operations SET result_json='{}'"
                ),
            ),
        )
        for name, seed, mutate in cases:
            with self.subTest(name=name):
                path = Path(self.temp.name) / f"integrity-{name}.sqlite3"
                migrate_lifecycle_database(path, allow_upgrade=True)
                seed(path)
                connection = open_fk(path)
                try:
                    mutate(connection)
                finally:
                    connection.close()
                self.assert_validation_entrypoints_reject_without_repair(path)

    def test_missing_activation_outbox_is_rejected_by_validation_and_noop(self):
        path = Path(self.temp.name) / "missing-activation-outbox.sqlite3"
        migrate_lifecycle_database(path, allow_upgrade=True)
        assembly = new_assembly(path, refs=TaggedRefs("missing-outbox"))
        context = seed_m1_to_m5(assembly, workspace="workspace-missing-outbox")
        bible, characters = confirmed_components(assembly, context)
        activate(assembly, context, bible, characters, "activation-with-event")

        connection = open_fk(path)
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM v5_m6_outbox").fetchone()[0],
                1,
            )
            connection.execute("DELETE FROM v5_m6_outbox")
        finally:
            connection.close()
        self.assert_validation_entrypoints_reject_without_repair(path)

    def test_missing_durable_operations_are_rejected_by_validation_and_noop(self):
        path = Path(self.temp.name) / "missing-operations.sqlite3"
        migrate_lifecycle_database(path, allow_upgrade=True)
        assembly = new_assembly(path, refs=TaggedRefs("missing-operations"))
        context = seed_m1_to_m5(assembly, workspace="workspace-missing-operations")
        bible, characters = confirmed_components(assembly, context)
        activate(assembly, context, bible, characters, "activation-with-operations")

        connection = open_fk(path)
        try:
            self.assertGreater(
                connection.execute(
                    "SELECT COUNT(*) FROM v5_m6_operations"
                ).fetchone()[0],
                0,
            )
            connection.execute("DELETE FROM v5_m6_operations")
        finally:
            connection.close()
        self.assert_validation_entrypoints_reject_without_repair(path)

    def test_replacement_event_order_and_mutual_refs_are_fail_closed(self):
        def seed_replacement(path, tag):
            migrate_lifecycle_database(path, allow_upgrade=True)
            assembly = new_assembly(path, refs=TaggedRefs(tag))
            context = seed_m1_to_m5(assembly, workspace=f"workspace-{tag}")
            bible, characters = confirmed_components(assembly, context)
            activate(assembly, context, bible, characters, "activate-original")
            bible_v2, character_v2 = replacement_components(
                assembly, context, bible, characters
            )
            assembly.series_intelligence.activate_baseline({
                **base_command(context, "activate-replacement"),
                "seriesBibleRef": bible_v2["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible_v2["version"][
                    "seriesBibleVersionRef"
                ],
                "characterContinuityRef": character_v2["root"][
                    "characterContinuityRef"
                ],
                "characterContinuityVersionRef": character_v2["version"][
                    "characterContinuityVersionRef"
                ],
                "expectedActivationRevision": 1,
                "approvalRef": "approval-human",
            })

        def swap_event_positions(connection):
            rows = connection.execute(
                "SELECT position,event_type FROM v5_m6_outbox ORDER BY position"
            ).fetchall()
            superseded = next(
                row["position"] for row in rows
                if row["event_type"] == "M6BaselineSuperseded"
            )
            latest_confirmed = max(
                row["position"] for row in rows
                if row["event_type"] == "M6BaselineConfirmed"
            )
            connection.execute(
                "UPDATE v5_m6_outbox SET position=-1 WHERE position=?",
                (superseded,),
            )
            connection.execute(
                "UPDATE v5_m6_outbox SET position=? WHERE position=?",
                (superseded, latest_confirmed),
            )
            connection.execute(
                "UPDATE v5_m6_outbox SET position=? WHERE position=-1",
                (latest_confirmed,),
            )

        def swap_event_aggregate_refs(connection):
            snapshots = {
                row["status"]: row
                for row in connection.execute(
                    "SELECT status,m6_baseline_snapshot_ref,activation_revision,"
                    "content_digest FROM v5_m6_baseline_snapshots"
                )
            }
            rows = connection.execute(
                "SELECT position,event_type,event_json FROM v5_m6_outbox "
                "ORDER BY position"
            ).fetchall()
            superseded = next(
                row for row in rows
                if row["event_type"] == "M6BaselineSuperseded"
            )
            latest_confirmed = max(
                (
                    row for row in rows
                    if row["event_type"] == "M6BaselineConfirmed"
                ),
                key=lambda row: row["position"],
            )
            superseded_event = json.loads(superseded["event_json"])
            superseded_event["aggregateRef"] = snapshots["ACTIVE"][
                "m6_baseline_snapshot_ref"
            ]
            superseded_event["payload"]["supersededSnapshotRef"] = snapshots[
                "ACTIVE"
            ]["m6_baseline_snapshot_ref"]
            confirmed_event = json.loads(latest_confirmed["event_json"])
            confirmed_event["aggregateRef"] = snapshots["SUPERSEDED"][
                "m6_baseline_snapshot_ref"
            ]
            confirmed_event["payload"].update({
                "m6BaselineSnapshotRef": snapshots["SUPERSEDED"][
                    "m6_baseline_snapshot_ref"
                ],
                "activationRevision": snapshots["SUPERSEDED"][
                    "activation_revision"
                ],
                "contentDigest": snapshots["SUPERSEDED"]["content_digest"],
            })
            canonical = lambda value: json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            connection.execute(
                "UPDATE v5_m6_outbox SET aggregate_ref=?,event_json=? "
                "WHERE position=?",
                (
                    superseded_event["aggregateRef"],
                    canonical(superseded_event),
                    superseded["position"],
                ),
            )
            connection.execute(
                "UPDATE v5_m6_outbox SET aggregate_ref=?,event_json=? "
                "WHERE position=?",
                (
                    confirmed_event["aggregateRef"],
                    canonical(confirmed_event),
                    latest_confirmed["position"],
                ),
            )

        for name, mutate in (
            ("swapped-position", swap_event_positions),
            ("mutual-aggregate-refs", swap_event_aggregate_refs),
        ):
            with self.subTest(name=name):
                path = Path(self.temp.name) / f"replacement-{name}.sqlite3"
                seed_replacement(path, name)
                connection = open_fk(path)
                try:
                    mutate(connection)
                finally:
                    connection.close()
                self.assert_validation_entrypoints_reject_without_repair(path)

    def test_partial_m6_schema_fails_closed_without_repair(self):
        path = Path(self.temp.name) / "partial.sqlite3"
        create_accepted_v2(path)
        connection = open_fk(path)
        try:
            connection.execute(
                "CREATE TABLE v5_series_intelligence_schema ("
                "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO v5_series_intelligence_schema VALUES "
                "('series_intelligence', 1)"
            )
        finally:
            connection.close()
        before = snapshot_tables(path)
        with self.assertRaises(RuntimeError):
            migrate_lifecycle_database(path, allow_upgrade=True)
        self.assertEqual(snapshot_tables(path), before)


class SeriesIntelligenceSqliteRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "m6-runtime.sqlite3"
        migrate_lifecycle_database(self.path, allow_upgrade=True)
        self.refs = TaggedRefs("first")
        self.assembly = new_assembly(self.path, refs=self.refs)
        self.context = seed_m1_to_m5(self.assembly)

    def restart(self, *, tag="restart", refs=None, scope_authority=None, **kwargs):
        return new_assembly(
            self.path,
            refs=refs or TaggedRefs(tag),
            scope_authority=scope_authority,
            **kwargs,
        )

    def assert_integrity(self):
        connection = open_fk(self.path)
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def test_confirmed_v2_source_and_digest_survive_sqlite_restart(self):
        created, expected_bindings = seed_bound_v2(self.assembly, self.context)
        source = self.assembly.series_planning.get_confirmed_m6_source_snapshot(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )
        self.assertEqual(
            created["version"]["episodePlanItemBindings"], expected_bindings
        )
        self.assertEqual(
            source["schemaVersion"], "v5.series-plan.m6-source-snapshot.v2"
        )
        self.assertEqual(source["episodePlanItemBindings"], expected_bindings)
        bible, characters = confirmed_components(self.assembly, self.context)
        snapshot = activate(
            self.assembly,
            self.context,
            bible,
            characters,
            "v2-restart-activate",
        )
        self.assertEqual(
            snapshot["seriesPlanVersionDigest"], source["seriesPlanVersionDigest"]
        )
        validate_series_intelligence_database(self.path)

        restarted = self.restart(tag="v2-source-restart")
        self.assertEqual(
            restarted.series_planning.get_confirmed_m6_source_snapshot(
                self.context["workspaceRef"],
                self.context["projectRef"],
                self.context["seriesRef"],
            ),
            source,
        )
        self.assertEqual(
            restarted.series_intelligence.get_workspace(
                self.context["workspaceRef"],
                self.context["projectRef"],
                self.context["seriesRef"],
            )["activeBaseline"]["seriesPlanVersionDigest"],
            source["seriesPlanVersionDigest"],
        )

    def test_write_accepted_subarc_edge_survives_v2_m6_validation_and_restart(self):
        connection = open_fk(self.path)
        try:
            row = connection.execute(
                "SELECT series_plan_version_ref,content_json "
                "FROM v5_series_plan_versions WHERE schema_version=?",
                ("v5.series-plan-version.v1",),
            ).fetchone()
            content = json.loads(row["content_json"])
            content["subArcs"][0]["episodeStart"] = 2
            content["subArcs"][0]["episodeEnd"] = 1
            connection.execute(
                "UPDATE v5_series_plan_versions SET content_json=? "
                "WHERE series_plan_version_ref=?",
                (
                    json.dumps(content, ensure_ascii=False, sort_keys=True),
                    row["series_plan_version_ref"],
                ),
            )
        finally:
            connection.close()
        created, _ = seed_bound_v2(self.assembly, self.context, binding_count=1)
        self.assertEqual(
            created["version"]["subArcs"][0],
            content["subArcs"][0],
        )
        bible, characters = confirmed_components(self.assembly, self.context)
        activate(
            self.assembly,
            self.context,
            bible,
            characters,
            "v2-subarc-edge-activate",
        )
        validate_series_intelligence_database(self.path)
        restarted = self.restart(tag="v2-subarc-edge-restart")
        self.assertEqual(
            restarted.series_planning.get_confirmed_m6_source_snapshot(
                self.context["workspaceRef"],
                self.context["projectRef"],
                self.context["seriesRef"],
            )["seriesPlanVersionRef"],
            created["version"]["seriesPlanVersionRef"],
        )

    def test_tampered_v2_m5_content_fails_validation_and_restarted_m6_read(self):
        def mutate_schema(path):
            connection = open_fk(path)
            try:
                connection.execute(
                    "UPDATE v5_series_plan_versions "
                    "SET schema_version='v5.series-plan-version.v99' "
                    "WHERE schema_version='v5.series-plan-version.v2'"
                )
            finally:
                connection.close()

        def mutate_content(path, mutation):
            connection = open_fk(path)
            try:
                row = connection.execute(
                    "SELECT series_plan_version_ref,content_json "
                    "FROM v5_series_plan_versions "
                    "WHERE schema_version='v5.series-plan-version.v2'"
                ).fetchone()
                content = json.loads(row["content_json"])
                mutation(content)
                connection.execute(
                    "UPDATE v5_series_plan_versions SET content_json=? "
                    "WHERE series_plan_version_ref=?",
                    (
                        json.dumps(content, ensure_ascii=False, sort_keys=True),
                        row["series_plan_version_ref"],
                    ),
                )
            finally:
                connection.close()

        def mutate_raw_content(path, mutation):
            connection = open_fk(path)
            try:
                row = connection.execute(
                    "SELECT series_plan_version_ref,content_json "
                    "FROM v5_series_plan_versions "
                    "WHERE schema_version='v5.series-plan-version.v2'"
                ).fetchone()
                connection.execute(
                    "UPDATE v5_series_plan_versions SET content_json=? "
                    "WHERE series_plan_version_ref=?",
                    (
                        mutation(row["content_json"]),
                        row["series_plan_version_ref"],
                    ),
                )
            finally:
                connection.close()

        cases = {
            "unknown-schema": mutate_schema,
            "unknown-field": lambda path: mutate_content(
                path, lambda content: content.__setitem__("unexpected", True)
            ),
            "noncanonical-binding-order": lambda path: mutate_content(
                path, lambda content: content["episodePlanItemBindings"].reverse()
            ),
            "floating-number": lambda path: mutate_content(
                path,
                lambda content: content["episodePlanItems"][0].__setitem__(
                    "episodeNumber", 1.0
                ),
            ),
            "noncanonical-json": lambda path: mutate_raw_content(
                path,
                lambda raw: json.dumps(
                    json.loads(raw),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
            "nfc-duplicate-key": lambda path: mutate_raw_content(
                path,
                lambda raw: '{"e\\u0301": 1, "é": 2, ' + raw[1:],
            ),
            "leading-space-text": lambda path: mutate_content(
                path,
                lambda content: content.__setitem__(
                    "seriesConcept", " " + content["seriesConcept"]
                ),
            ),
            "overlong-text": lambda path: mutate_content(
                path, lambda content: content.__setitem__("seriesConcept", "x" * 6001)
            ),
            "subarc-out-of-range": lambda path: mutate_content(
                path,
                lambda content: content["subArcs"][0].__setitem__(
                    "episodeStart", len(content["episodePlanItems"]) + 1
                ),
            ),
            "overlong-list-item": lambda path: mutate_content(
                path,
                lambda content: content["productionAssumptions"].__setitem__(
                    0, "x" * 1201
                ),
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                path = Path(self.temp.name) / f"v2-source-tamper-{name}.sqlite3"
                migrate_lifecycle_database(path, allow_upgrade=True)
                assembly = new_assembly(path, refs=TaggedRefs(name))
                context = seed_m1_to_m5(
                    assembly, workspace=f"workspace-{name}"
                )
                seed_bound_v2(assembly, context)
                confirmed_components(assembly, context)
                validate_series_intelligence_database(path)
                mutate(path)
                before = snapshot_database(path)

                for validation in (
                    validate_series_intelligence_database,
                    migrate_series_intelligence_database,
                ):
                    with self.subTest(validation=validation.__name__):
                        with self.assertRaises(RuntimeError):
                            validation(path)
                with self.assertRaises(RuntimeError):
                    new_assembly(path, refs=TaggedRefs(f"restart-{name}"))
                self.assertEqual(snapshot_database(path), before)

    def test_v1_schema_marker_cannot_smuggle_v2_binding_field(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        activate(self.assembly, self.context, bible, characters, "v1-field-spoof")
        connection = open_fk(self.path)
        try:
            row = connection.execute(
                "SELECT series_plan_version_ref,content_json "
                "FROM v5_series_plan_versions WHERE schema_version=?",
                ("v5.series-plan-version.v1",),
            ).fetchone()
            content = json.loads(row["content_json"])
            content["episodePlanItemBindings"] = []
            connection.execute(
                "UPDATE v5_series_plan_versions SET content_json=? "
                "WHERE series_plan_version_ref=?",
                (
                    json.dumps(content, ensure_ascii=False, sort_keys=True),
                    row["series_plan_version_ref"],
                ),
            )
        finally:
            connection.close()
        with self.assertRaises(RuntimeError):
            validate_series_intelligence_database(self.path)
        with self.assertRaises(RuntimeError):
            self.restart(tag="v1-field-spoof-restart")

    def assert_ref_collision_rolls_back(self, assembly, collision):
        boundary = assembly.series_intelligence
        before_database = snapshot_database(self.path)
        before_workspace = boundary.get_workspace(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )
        before_diagnostic = boundary.diagnostic_snapshot()
        before_outbox = scoped_outbox(boundary, self.context)

        with self.assertRaises(SeriesIntelligencePublicError) as rejected:
            collision()
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("duplicate_record", 409),
        )
        self.assertEqual(snapshot_database(self.path), before_database)
        self.assertEqual(
            boundary.get_workspace(
                self.context["workspaceRef"],
                self.context["projectRef"],
                self.context["seriesRef"],
            ),
            before_workspace,
        )
        self.assertEqual(boundary.diagnostic_snapshot(), before_diagnostic)
        self.assertEqual(scoped_outbox(boundary, self.context), before_outbox)
        self.assert_integrity()

    @staticmethod
    def race(*calls):
        barrier = Barrier(len(calls))
        results = []

        def run(call):
            barrier.wait()
            try:
                results.append(("ok", call()))
            except BaseException as error:
                results.append(("error", error))

        threads = [Thread(target=run, args=(call,)) for call in calls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
        if any(thread.is_alive() for thread in threads):
            raise AssertionError("SQLite race did not terminate")
        return results

    def test_restart_roundtrip_preserves_every_m6_fact_and_projection(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        snapshot = activate(self.assembly, self.context, bible, characters)
        before = self.assembly.series_intelligence.get_workspace(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )
        before_events = scoped_outbox(
            self.assembly.series_intelligence, self.context
        )

        self.assertEqual(
            migrate_lifecycle_database(self.path, allow_upgrade=True), "no-op"
        )

        restarted = self.restart()
        after = restarted.series_intelligence.get_workspace(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )
        self.assertEqual(after, before)
        self.assertEqual(
            scoped_outbox(restarted.series_intelligence, self.context),
            before_events,
        )
        self.assertEqual(
            after["activeBaseline"]["m6BaselineSnapshotRef"],
            snapshot["m6BaselineSnapshotRef"],
        )
        self.assert_integrity()

    def test_restart_replays_idempotency_and_rejects_changed_payload(self):
        command = {
            **base_command(self.context, "durable-idempotency"),
            "content": bible_content(),
        }
        original = self.assembly.series_intelligence.create_bible_version(command)
        restarted = self.restart()
        self.assertEqual(
            restarted.series_intelligence.create_bible_version(copy.deepcopy(command)),
            original,
        )
        changed = copy.deepcopy(command)
        changed["content"]["worldRules"][0]["statement"] = "changed"
        with self.assertRaises(SeriesIntelligencePublicError) as conflict:
            restarted.series_intelligence.create_bible_version(changed)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")
        self.assertEqual(
            restarted.series_intelligence.diagnostic_snapshot()["bibleVersionCount"], 1
        )

    def test_complete_scope_isolates_same_refs_operations_and_facts(self):
        fixed_a = self.restart(
            tag="unused-a",
            refs=FixedRefs(),
            scope_authority=ConfiguredScopeAuthority("lab", "tenant-a"),
        )
        command = {
            **base_command(self.context, "same-operation"),
            "content": bible_content(),
        }
        first = fixed_a.series_intelligence.create_bible_version(command)

        fixed_b = self.restart(
            tag="unused-b",
            refs=FixedRefs(),
            scope_authority=ConfiguredScopeAuthority("commercial", "tenant-b"),
        )
        second = fixed_b.series_intelligence.create_bible_version(copy.deepcopy(command))
        self.assertEqual(first["root"]["seriesBibleRef"], second["root"]["seriesBibleRef"])
        self.assertEqual(
            first["version"]["seriesBibleVersionRef"],
            second["version"]["seriesBibleVersionRef"],
        )
        self.assertNotEqual(first["root"]["businessDomain"], second["root"]["businessDomain"])
        self.assertNotEqual(first["root"]["tenantId"], second["root"]["tenantId"])
        connection = open_fk(self.path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM v5_m6_series_bibles").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM v5_m6_operations").fetchone()[0], 2)
        finally:
            connection.close()

    def test_complete_scope_isolates_same_event_identity_and_outbox(self):
        first = self.restart(
            tag="unused-event-a",
            refs=FixedRefs(),
            scope_authority=ConfiguredScopeAuthority("lab", "tenant-a"),
        )
        second = self.restart(
            tag="unused-event-b",
            refs=FixedRefs(),
            scope_authority=ConfiguredScopeAuthority("commercial", "tenant-b"),
        )
        first_bible, first_characters = confirmed_components(first, self.context)
        second_bible, second_characters = confirmed_components(second, self.context)

        first_snapshot = activate(
            first,
            self.context,
            first_bible,
            first_characters,
            "same-activation-operation",
        )
        second_snapshot = activate(
            second,
            self.context,
            second_bible,
            second_characters,
            "same-activation-operation",
        )
        self.assertEqual(
            first_snapshot["m6BaselineSnapshotRef"],
            second_snapshot["m6BaselineSnapshotRef"],
        )

        events = (
            scoped_outbox(first.series_intelligence, self.context)
            + scoped_outbox(second.series_intelligence, self.context)
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(len({event["eventId"] for event in events}), 1)
        self.assertEqual(
            {
                (event["businessDomain"], event["tenantId"])
                for event in events
            },
            {("lab", "tenant-a"), ("commercial", "tenant-b")},
        )
        connection = open_fk(self.path)
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM v5_m6_outbox").fetchone()[0],
                2,
            )
        finally:
            connection.close()

    def test_unicode_scope_and_generated_refs_are_nfc_and_survive_restart(self):
        decomposed = unicodedata.normalize("NFD", "café")
        workspace = f"workspace-{decomposed}"
        authority = ConfiguredScopeAuthority(
            business_domain=f"domain-{decomposed}",
            tenant_id=f"tenant-{decomposed}",
        )
        assembly = self.restart(
            refs=TaggedRefs(decomposed),
            scope_authority=authority,
        )
        context = seed_m1_to_m5(assembly, workspace=workspace)

        try:
            result = assembly.series_intelligence.create_bible_version({
                **base_command(context, f"operation-{decomposed}"),
                "content": bible_content(),
            })
        except SeriesIntelligencePublicError as rejected:
            self.assertIn(rejected.code, {"invalid_request", "scope_mismatch"})
            self.assertNotEqual(assembly.state.diagnostic_snapshot()["state"], "poisoned")
            self.assertEqual(
                assembly.series_intelligence.diagnostic_snapshot()["bibleCount"],
                0,
            )
            return

        canonical_context = {
            **context,
            "workspaceRef": unicodedata.normalize("NFC", context["workspaceRef"]),
            "projectRef": unicodedata.normalize("NFC", context["projectRef"]),
            "seriesRef": unicodedata.normalize("NFC", context["seriesRef"]),
        }
        for value in (
            result["root"]["businessDomain"],
            result["root"]["tenantId"],
            result["root"]["workspaceRef"],
            result["root"]["projectRef"],
            result["root"]["seriesRef"],
            result["root"]["seriesBibleRef"],
            result["version"]["seriesBibleVersionRef"],
        ):
            self.assertEqual(value, unicodedata.normalize("NFC", value))
        validate_series_intelligence_database(self.path)
        restarted = self.restart(
            tag="unicode-restart",
            scope_authority=ConfiguredScopeAuthority(
                unicodedata.normalize("NFC", authority.business_domain),
                unicodedata.normalize("NFC", authority.tenant_id),
            ),
        )
        workspace_projection = restarted.series_intelligence.get_workspace(
            canonical_context["workspaceRef"],
            canonical_context["projectRef"],
            canonical_context["seriesRef"],
        )
        self.assertEqual(workspace_projection["seriesBible"], result["root"])
        self.assertEqual(
            restarted.state.diagnostic_snapshot()["state"], "ready"
        )

    def test_outbox_requires_explicit_trusted_scope(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        activate(self.assembly, self.context, bible, characters, "private-event")

        with self.assertRaises(SeriesIntelligencePublicError) as unscoped:
            self.assembly.series_intelligence.get_outbox()
        self.assertEqual(
            (unscoped.exception.code, unscoped.exception.status),
            ("invalid_request", 400),
        )

        rejecting = LifecycleAssembly.sqlite(
            self.path,
            ref_factory=TaggedRefs("rejecting-reader"),
            clock=lambda: NOW,
        )
        with self.assertRaises(SeriesIntelligencePublicError) as rejected:
            rejecting.series_intelligence.get_outbox(
                self.context["workspaceRef"],
                self.context["projectRef"],
                self.context["seriesRef"],
            )
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("authority_unavailable", 403),
        )

    def test_corruption_in_another_tenant_does_not_affect_scoped_workspace_read(self):
        own_bible = self.assembly.series_intelligence.create_bible_version({
            **base_command(self.context, "own-scope-bible"),
            "content": bible_content(),
        })
        other = self.restart(
            tag="other-tenant",
            scope_authority=ConfiguredScopeAuthority("series-production", "tenant-other"),
        )
        other.series_intelligence.create_bible_version({
            **base_command(self.context, "other-scope-bible"),
            "content": bible_content("other-location"),
        })
        connection = open_fk(self.path)
        try:
            connection.execute(
                "UPDATE v5_m6_series_bibles SET record_json='{' "
                "WHERE tenant_id='tenant-other'"
            )
        finally:
            connection.close()

        projection = self.assembly.series_intelligence.get_workspace(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )
        self.assertEqual(projection["seriesBible"], own_bible["root"])
        self.assertEqual(len(projection["seriesBibleVersions"]), 1)

    def test_same_components_new_operation_is_noop_without_extra_outbox_event(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        command = {
            **base_command(self.context, "idempotent-activation"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"][
                "characterContinuityRef"
            ],
            "characterContinuityVersionRef": characters["version"][
                "characterContinuityVersionRef"
            ],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-human",
        }
        first = self.assembly.series_intelligence.activate_baseline(command)
        before = scoped_outbox(self.assembly.series_intelligence, self.context)
        before_operations = self.assembly.series_intelligence.diagnostic_snapshot()[
            "operationCount"
        ]
        restarted = self.restart(tag="same-components-noop")
        noop_command = {
            **command,
            "operationRef": "same-components-new-operation",
            "idempotencyKey": "same-components-new-idempotency",
            "expectedActivationRevision": first["activationRevision"],
        }
        self.assertEqual(
            restarted.series_intelligence.activate_baseline(noop_command),
            first,
        )
        self.assertEqual(
            scoped_outbox(restarted.series_intelligence, self.context), before
        )
        self.assertEqual(len(before), 1)
        self.assertEqual(
            restarted.series_intelligence.diagnostic_snapshot()["operationCount"],
            before_operations + 1,
        )
        validate_series_intelligence_database(self.path)
        self.assertEqual(
            migrate_lifecycle_database(self.path, allow_upgrade=True), "no-op"
        )

    def test_bible_version_fixed_ref_collision_is_rejected_atomically(self):
        assembly = self.restart(
            refs=PrefixCollisionRefs("series-bible-version", "bible-collision")
        )
        boundary = assembly.series_intelligence
        original = boundary.create_bible_version({
            **base_command(self.context, "bible-collision-original"),
            "content": bible_content(),
        })

        self.assert_ref_collision_rolls_back(
            assembly,
            lambda: boundary.create_bible_version({
                **base_command(self.context, "bible-collision-attempt"),
                "seriesBibleRef": original["root"]["seriesBibleRef"],
                "expectedRevision": original["root"]["revision"],
                "content": bible_content("location-bible-collision"),
            }),
        )

    def test_character_version_fixed_ref_collision_is_rejected_atomically(self):
        assembly = self.restart(
            refs=PrefixCollisionRefs(
                "character-continuity-version", "character-collision"
            )
        )
        bible, characters = confirmed_components(assembly, self.context)
        source = assembly.series_planning.get_confirmed_m6_source_snapshot(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )

        self.assert_ref_collision_rolls_back(
            assembly,
            lambda: assembly.series_intelligence.create_character_version({
                **base_command(self.context, "character-collision-attempt"),
                "characterContinuityRef": characters["root"][
                    "characterContinuityRef"
                ],
                "expectedRevision": characters["root"]["revision"],
                "candidate": True,
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                "content": character_content(
                    [
                        item["episodePlanItemRef"]
                        for item in source["episodePlanItems"]
                    ]
                ),
            }),
        )

    def test_baseline_snapshot_fixed_ref_collision_is_rejected_atomically(self):
        assembly = self.restart(
            refs=PrefixCollisionRefs("m6-baseline", "snapshot-collision")
        )
        bible, characters = confirmed_components(assembly, self.context)
        activate(
            assembly,
            self.context,
            bible,
            characters,
            "snapshot-collision-original",
        )
        bible_v2, character_v2 = replacement_components(
            assembly, self.context, bible, characters
        )

        self.assert_ref_collision_rolls_back(
            assembly,
            lambda: assembly.series_intelligence.activate_baseline({
                **base_command(self.context, "snapshot-collision-attempt"),
                "seriesBibleRef": bible_v2["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible_v2["version"][
                    "seriesBibleVersionRef"
                ],
                "characterContinuityRef": character_v2["root"][
                    "characterContinuityRef"
                ],
                "characterContinuityVersionRef": character_v2["version"][
                    "characterContinuityVersionRef"
                ],
                "expectedActivationRevision": 1,
                "approvalRef": "approval-human",
            }),
        )

    def test_sqlite_lock_failure_is_a_stable_public_error_without_engine_leak(self):
        blocker = open_fk(self.path)
        original_connect = self.assembly.state._connect

        def no_wait_connect():
            connection = sqlite3.connect(self.path, timeout=0, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            return connection

        try:
            blocker.execute("BEGIN IMMEDIATE")
            self.assembly.state._connect = no_wait_connect
            with self.assertRaises(SeriesIntelligencePublicError) as rejected:
                self.assembly.series_intelligence.create_bible_version({
                    **base_command(self.context, "locked-database"),
                    "content": bible_content(),
                })
            self.assertEqual(
                (rejected.exception.code, rejected.exception.status),
                ("lifecycle_unavailable", 503),
            )
            rendered = str(rejected.exception).lower()
            self.assertNotIn("sqlite", rendered)
            self.assertNotIn("database", rendered)
            self.assertNotIn("locked", rendered)
            self.assertNotIn("sql", rendered)
        finally:
            self.assembly.state._connect = original_connect
            blocker.rollback()
            blocker.close()
        self.assertEqual(
            self.assembly.series_intelligence.diagnostic_snapshot()["bibleCount"],
            0,
        )

    def test_corrupted_durable_read_is_a_stable_public_error_without_detail_leak(self):
        self.assembly.series_intelligence.create_bible_version({
            **base_command(self.context, "corrupt-read-source"),
            "content": bible_content(),
        })
        connection = open_fk(self.path)
        try:
            connection.execute(
                "UPDATE v5_m6_series_bibles SET record_json='{'"
            )
        finally:
            connection.close()

        with self.assertRaises(SeriesIntelligencePublicError) as rejected:
            self.assembly.series_intelligence.get_workspace(
                self.context["workspaceRef"],
                self.context["projectRef"],
                self.context["seriesRef"],
            )
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("invalid_request", 400),
        )
        rendered = str(rejected.exception).lower()
        for forbidden in (
            "sqlite",
            "json",
            "record_json",
            "v5_m6",
            "projection",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, rendered)

    def test_coordinated_content_projection_tamper_with_old_digest_fails_closed(self):
        created = self.assembly.series_intelligence.create_bible_version({
            **base_command(self.context, "coordinated-content-source"),
            "content": bible_content(),
        })
        connection = open_fk(self.path)
        try:
            row = connection.execute(
                "SELECT rowid,record_json,content_digest,canonical_digest "
                "FROM v5_m6_series_bible_versions"
            ).fetchone()
            record = json.loads(row["record_json"])
            record["content"]["worldRules"][0]["statement"] = "tampered together"
            tampered_content = json.dumps(
                record["content"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            tampered_record = json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            connection.execute(
                "UPDATE v5_m6_series_bible_versions "
                "SET record_json=?,content_json=? WHERE rowid=?",
                (tampered_record, tampered_content, row["rowid"]),
            )
            persisted = connection.execute(
                "SELECT content_digest,canonical_digest "
                "FROM v5_m6_series_bible_versions WHERE rowid=?",
                (row["rowid"],),
            ).fetchone()
            self.assertEqual(persisted["content_digest"], row["content_digest"])
            self.assertEqual(persisted["canonical_digest"], row["canonical_digest"])
            self.assertEqual(
                row["content_digest"], created["version"]["contentDigest"]
            )
        finally:
            connection.close()

        with self.assertRaises(SeriesIntelligencePublicError) as rejected:
            self.assembly.series_intelligence.get_workspace(
                self.context["workspaceRef"],
                self.context["projectRef"],
                self.context["seriesRef"],
            )
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("invalid_request", 400),
        )

    def test_coordinated_operation_result_tamper_fails_closed_on_runtime_replay(self):
        command = {
            **base_command(self.context, "coordinated-operation-result"),
            "content": bible_content(),
        }
        self.assembly.series_intelligence.create_bible_version(command)
        connection = open_fk(self.path)
        try:
            row = connection.execute(
                "SELECT rowid,result_json FROM v5_m6_operations "
                "WHERE operation_type='create-series-bible-version'"
            ).fetchone()
            result = json.loads(row["result_json"])
            result["version"]["content"]["worldRules"][0][
                "statement"
            ] = "tampered replay result"
            connection.execute(
                "UPDATE v5_m6_operations SET result_json=? WHERE rowid=?",
                (
                    json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    row["rowid"],
                ),
            )
        finally:
            connection.close()

        with self.assertRaises(SeriesIntelligencePublicError) as rejected:
            self.assembly.series_intelligence.create_bible_version(command)
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("invalid_request", 400),
        )
        self.assertEqual(str(rejected.exception), "invalid_request")

    def test_coordinated_outbox_payload_tamper_fails_closed_on_runtime_read(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        activate(
            self.assembly,
            self.context,
            bible,
            characters,
            "coordinated-outbox-payload",
        )
        connection = open_fk(self.path)
        try:
            row = connection.execute(
                "SELECT position,event_json FROM v5_m6_outbox "
                "WHERE event_type='M6BaselineConfirmed'"
            ).fetchone()
            event = json.loads(row["event_json"])
            event["payload"]["contentDigest"] = "0" * 64
            connection.execute(
                "UPDATE v5_m6_outbox SET event_json=? WHERE position=?",
                (
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    row["position"],
                ),
            )
        finally:
            connection.close()

        with self.assertRaises(SeriesIntelligencePublicError) as rejected:
            scoped_outbox(self.assembly.series_intelligence, self.context)
        self.assertEqual(
            (rejected.exception.code, rejected.exception.status),
            ("invalid_request", 400),
        )
        self.assertEqual(str(rejected.exception), "invalid_request")

    def test_get_workspace_concurrent_write_returns_one_committed_projection(self):
        bible, _characters = confirmed_components(self.assembly, self.context)
        reader = self.restart(tag="consistent-reader")
        writer = self.restart(tag="consistent-writer")
        before = reader.series_intelligence.get_workspace(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )

        entered = Event()
        release = Event()
        reader_boundary = reader.series_intelligence
        service = reader_boundary._SeriesIntelligencePublicBoundary__service
        original_bibles = service.repository.bibles
        service.repository.bibles = BlockingGetMapping(
            original_bibles, entered, release
        )
        result = {}

        def read_workspace():
            try:
                result["read"] = ("ok", reader_boundary.get_workspace(
                    self.context["workspaceRef"],
                    self.context["projectRef"],
                    self.context["seriesRef"],
                ))
            except BaseException as error:
                result["read"] = ("error", error)

        thread = Thread(target=read_workspace)
        thread.start()
        writer_done = Event()

        def write_version():
            try:
                result["write"] = ("ok", writer.series_intelligence.create_bible_version({
                    **base_command(self.context, "consistent-concurrent-version"),
                    "seriesBibleRef": bible["root"]["seriesBibleRef"],
                    "expectedRevision": bible["root"]["revision"],
                    "candidate": True,
                    "content": bible_content("location-consistent-v2"),
                }))
            except BaseException as error:
                result["write"] = ("error", error)
            finally:
                writer_done.set()

        writer_thread = None
        try:
            self.assertTrue(entered.wait(15))
            writer_thread = Thread(target=write_version)
            writer_thread.start()
            # An implementation without a read snapshot lets the write commit while
            # this read is paused. A correct snapshot may serialize the writer, in
            # which case release the reader and then allow the writer to commit.
            writer_done.wait(1)
        finally:
            release.set()
            thread.join(20)
            if writer_thread is not None:
                writer_thread.join(20)
            service.repository.bibles = original_bibles
        self.assertFalse(thread.is_alive())
        self.assertIsNotNone(writer_thread)
        self.assertFalse(writer_thread.is_alive())
        self.assertEqual(result["read"][0], "ok", repr(result))
        self.assertEqual(result["write"][0], "ok", repr(result))
        after = reader_boundary.get_workspace(
            self.context["workspaceRef"],
            self.context["projectRef"],
            self.context["seriesRef"],
        )
        self.assertIn(result["read"][1], (before, after))

    def test_version_insert_fault_rolls_back_root_version_and_operation(self):
        connection = open_fk(self.path)
        try:
            connection.execute(
                "CREATE TRIGGER fail_m6_bible_version "
                "BEFORE INSERT ON v5_m6_series_bible_versions "
                "BEGIN SELECT RAISE(ABORT, 'injected version failure'); END"
            )
        finally:
            connection.close()
        with self.assertRaises(SeriesIntelligencePublicError):
            self.assembly.series_intelligence.create_bible_version({
                **base_command(self.context, "version-fault"),
                "content": bible_content(),
            })
        connection = open_fk(self.path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM v5_m6_series_bibles").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM v5_m6_series_bible_versions").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM v5_m6_operations").fetchone()[0], 0)
        finally:
            connection.close()

    def test_outbox_failure_rolls_back_snapshot_operation_and_event(self):
        enabled = {"value": False}

        def hook(point):
            if enabled["value"] and point == "after-outbox-write":
                raise RuntimeError("injected outbox failure")

        assembly = self.restart(tag="outbox", fault_hook=hook)
        bible, characters = confirmed_components(assembly, self.context)
        before = assembly.series_intelligence.diagnostic_snapshot()
        enabled["value"] = True
        with self.assertRaises(RuntimeError):
            activate(assembly, self.context, bible, characters, "outbox-fault")
        restarted = self.restart(tag="outbox-check")
        after = restarted.series_intelligence.diagnostic_snapshot()
        self.assertEqual(after["snapshotCount"], before["snapshotCount"])
        self.assertEqual(after["operationCount"], before["operationCount"])
        self.assertEqual(
            scoped_outbox(restarted.series_intelligence, self.context), []
        )

    def test_cross_assembly_revision_race_has_exactly_one_winner(self):
        initial = self.assembly.series_intelligence.create_bible_version({
            **base_command(self.context, "race-root"),
            "content": bible_content(),
        })
        second = self.restart(tag="second-writer")

        def command(boundary, index):
            return lambda: boundary.create_bible_version({
                **base_command(self.context, f"race-{index}"),
                "seriesBibleRef": initial["root"]["seriesBibleRef"],
                "expectedRevision": 1,
                "content": bible_content(f"location-race-{index}"),
            })

        results = self.race(
            command(self.assembly.series_intelligence, 1),
            command(second.series_intelligence, 2),
        )
        self.assertEqual([item[0] for item in results].count("ok"), 1, repr(results))
        errors = [item[1] for item in results if item[0] == "error"]
        self.assertEqual(errors[0].code, "version_conflict")
        self.assertEqual(
            self.restart(tag="race-check").series_intelligence.diagnostic_snapshot()[
                "bibleVersionCount"
            ],
            2,
        )
        self.assert_integrity()

    def test_cross_assembly_activation_race_leaves_one_active_snapshot(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        second = self.restart(tag="activation-second")

        def call(boundary, operation):
            return lambda: boundary.activate_baseline({
                **base_command(self.context, operation),
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                "characterContinuityRef": characters["root"]["characterContinuityRef"],
                "characterContinuityVersionRef": characters["version"][
                    "characterContinuityVersionRef"
                ],
                "expectedActivationRevision": 0,
                "approvalRef": "approval-human",
            })

        results = self.race(
            call(self.assembly.series_intelligence, "activate-a"),
            call(second.series_intelligence, "activate-b"),
        )
        self.assertEqual([item[0] for item in results].count("ok"), 1, repr(results))
        errors = [item[1] for item in results if item[0] == "error"]
        self.assertEqual(errors[0].code, "version_conflict")
        connection = open_fk(self.path)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM v5_m6_baseline_snapshots WHERE status='ACTIVE'"
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()

    def test_m5_confirmation_winning_race_makes_old_m6_activation_stale(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        old_plan = self.context["plan"]
        fields = {
            "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs",
            "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
            "worldIntent", "continuityIntent", "foreshadowingContext",
            "productionAssumptions",
        }
        content = {field: copy.deepcopy(old_plan["version"][field]) for field in fields}
        content["premise"] = "M5 wins the serialized source race"
        next_plan = self.assembly.series_planning.create_manual_version({
            "workspaceRef": self.context["workspaceRef"],
            "projectRef": self.context["projectRef"],
            "seriesRef": self.context["seriesRef"],
            "seriesPlanRef": old_plan["plan"]["seriesPlanRef"],
            "expectedPlanVersion": old_plan["plan"]["version"],
            "content": content,
        })

        entered = Event()
        release = Event()

        def hook(operation):
            if operation is LifecycleOperation.CONFIRM_SERIES_PLAN_VERSION:
                entered.set()
                if not release.wait(15):
                    raise TimeoutError("M5 race was not released")

        confirmer = self.restart(tag="m5-confirm", transaction_hook=hook)
        activator = self.restart(tag="m6-activate")
        results = {}

        def confirm():
            try:
                results["confirm"] = ("ok", confirmer.series_planning.confirm_version({
                    "workspaceRef": self.context["workspaceRef"],
                    "seriesPlanRef": next_plan["plan"]["seriesPlanRef"],
                    "seriesPlanVersionRef": next_plan["version"]["seriesPlanVersionRef"],
                    "expectedPlanVersion": next_plan["plan"]["version"],
                    "humanConfirmed": True,
                }))
            except BaseException as error:
                results["confirm"] = ("error", error)

        def activate_old():
            try:
                results["activate"] = ("ok", activate(
                    activator, self.context, bible, characters, "m5-race-activate"
                ))
            except BaseException as error:
                results["activate"] = ("error", error)

        first = Thread(target=confirm)
        first.start()
        self.assertTrue(entered.wait(15))
        second = Thread(target=activate_old)
        second.start()
        release.set()
        first.join(20)
        second.join(20)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(results["confirm"][0], "ok", repr(results))
        self.assertEqual(results["activate"][0], "error", repr(results))
        self.assertEqual(results["activate"][1].code, "stale_source")
        self.assertEqual(
            self.restart(tag="m5-race-check").series_intelligence.diagnostic_snapshot()[
                "snapshotCount"
            ],
            0,
        )

    def test_replacement_outbox_order_and_positions_survive_restart(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        activate(self.assembly, self.context, bible, characters, "activate-first")
        bible_v2, character_v2 = replacement_components(
            self.assembly, self.context, bible, characters
        )
        self.assembly.series_intelligence.activate_baseline({
            **base_command(self.context, "activate-replacement"),
            "seriesBibleRef": bible_v2["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible_v2["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": character_v2["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": character_v2["version"][
                "characterContinuityVersionRef"
            ],
            "expectedActivationRevision": 1,
            "approvalRef": "approval-human",
        })
        events = scoped_outbox(self.assembly.series_intelligence, self.context)
        self.assertEqual(
            [event["eventType"] for event in events],
            ["M6BaselineConfirmed", "M6BaselineSuperseded", "M6BaselineConfirmed"],
        )
        self.assertEqual(
            scoped_outbox(
                self.restart(tag="outbox-restart").series_intelligence,
                self.context,
            ),
            events,
        )
        connection = open_fk(self.path)
        try:
            positions = [
                row[0]
                for row in connection.execute(
                    "SELECT position FROM v5_m6_outbox ORDER BY position"
                )
            ]
            self.assertEqual(positions, sorted(set(positions)))
            self.assertEqual(len(positions), 3)
        finally:
            connection.close()

    def test_series_plan_and_m6_lineage_are_restrictive_and_errors_are_stable(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        activate(self.assembly, self.context, bible, characters)
        with self.assertRaises(Exception) as deletion:
            self.assembly.series_episode.delete_series(
                self.context["workspaceRef"], self.context["seriesRef"]
            )
        self.assertEqual(deletion.exception.code, "dependent_project_exists")

        connection = open_fk(self.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM v5_series_plan_versions "
                    "WHERE workspace_ref=? AND series_plan_ref=? "
                    "AND series_plan_version_ref=?",
                    (
                        self.context["workspaceRef"],
                        self.context["plan"]["plan"]["seriesPlanRef"],
                        self.context["plan"]["version"]["seriesPlanVersionRef"],
                    ),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM v5_m6_series_bibles WHERE business_domain=? "
                    "AND tenant_id=? AND workspace_ref=? AND project_ref=? AND series_ref=?",
                    (
                        "series-production",
                        "tenant-m6",
                        self.context["workspaceRef"],
                        self.context["projectRef"],
                        self.context["seriesRef"],
                    ),
                )
        finally:
            connection.close()
        self.assert_integrity()

    def test_commit_uncertainty_during_m6_write_poisoned_assembly(self):
        state = self.assembly.state

        class FailingCommit:
            def __init__(self, inner):
                self.inner = inner

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def commit(self):
                raise sqlite3.OperationalError("uncertain")

        original = state._connect
        state._connect = lambda: FailingCommit(original())
        with self.assertRaises(SeriesIntelligencePublicError) as unavailable:
            self.assembly.series_intelligence.create_bible_version({
                **base_command(self.context, "commit-uncertain"),
                "content": bible_content(),
            })
        self.assertEqual(
            (unavailable.exception.code, unavailable.exception.status),
            ("lifecycle_unavailable", 503),
        )
        self.assertEqual(state.diagnostic_snapshot()["state"], "poisoned")
        with self.assertRaises(SeriesIntelligencePublicError) as poisoned:
            self.assembly.series_intelligence.get_workspace(
                self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
            )
        self.assertEqual(
            (poisoned.exception.code, poisoned.exception.status),
            ("lifecycle_unavailable", 503),
        )

    def test_rollback_failure_during_m6_write_poisoned_assembly(self):
        state = self.assembly.state

        class FailingRollback:
            def __init__(self, inner):
                self.inner = inner

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def rollback(self):
                raise sqlite3.OperationalError("rollback uncertain")

        original = state._connect
        state._connect = lambda: FailingRollback(original())
        invalid = bible_content()
        invalid["timelineEvents"][0]["locationRef"] = "missing-location"
        with self.assertRaises(SeriesIntelligencePublicError) as unavailable:
            self.assembly.series_intelligence.create_bible_version({
                **base_command(self.context, "rollback-failure"),
                "content": invalid,
            })
        self.assertEqual(
            (unavailable.exception.code, unavailable.exception.status),
            ("lifecycle_unavailable", 503),
        )
        self.assertEqual(state.diagnostic_snapshot()["state"], "poisoned")
        with self.assertRaises(SeriesIntelligencePublicError) as poisoned:
            self.assembly.series_intelligence.create_bible_version({
                **base_command(self.context, "after-poison"),
                "content": bible_content(),
            })
        self.assertEqual(
            (poisoned.exception.code, poisoned.exception.status),
            ("lifecycle_unavailable", 503),
        )


if __name__ == "__main__":
    unittest.main()
