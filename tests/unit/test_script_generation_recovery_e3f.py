"""Repository parity, exact schema and durable row integrity for bounded E3F."""

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_intelligence.migration import SeriesIntelligenceMigrationError
from services.v5_core_os.script_studio import ScriptStudioPublicError
from services.v5_core_os.script_studio.generation_recovery import (
    InMemoryGenerationStore, GenerationStorageError, GenerationRecoveryError, canonical, digest, seal, validate_key,
)
from services.v5_core_os.script_studio.generation_recovery_sqlite import (
    SqliteGenerationStore, TABLE, MARKER_TABLE, INDEX, validate_generation_connection,
)
from tests.unit.test_script_studio_m3 import seed_episode, content_from_candidate, WORKSPACE


def rows(path, table):
    with sqlite3.connect(path) as connection:
        return connection.execute(f"SELECT * FROM {table}").fetchall()


def snapshot(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


class GenerationRecoveryStorageTests(unittest.TestCase):
    def fixture(self, sqlite=False):
        if sqlite:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            path = Path(temporary.name) / "creator.sqlite3"
            assembly = LifecycleAssembly.sqlite(path, initialize_or_upgrade=True)
        else:
            path = None
            assembly = LifecycleAssembly.in_memory()
        series, episode = seed_episode(assembly.series_episode)
        scope = {"workspaceRef": WORKSPACE, "seriesRef": series["seriesRef"], "episodeRef": episode["episodeRef"]}
        return assembly, path, scope

    def ready(self, assembly, scope):
        command = {**scope, "idempotencyKey": "unit-command"}
        reservation = assembly.script_studio.reserve_generation(command)
        ticket = {k: reservation[k] for k in ("scope", "identityDigest")}
        assembly.script_studio.save_generation_result(ticket, content_from_candidate())
        return command, ticket

    def test_inmemory_and_sqlite_script_and_completion_failure_roll_back_together(self):
        for sqlite in (False, True):
            with self.subTest(sqlite=sqlite):
                assembly, path, scope = self.fixture(sqlite)
                command, ticket = self.ready(assembly, scope)
                before = snapshot(path) if path else assembly.script_studio.get_workspace(
                    WORKSPACE, scope["seriesRef"], scope["episodeRef"])
                store_type = SqliteGenerationStore if sqlite else InMemoryGenerationStore
                save = store_type.save
                observed = []

                def fault(store, record):
                    if record["state"] == "COMPLETED":
                        # A real V5 domain write happened inside the transaction.
                        workspace = assembly.script_studio.get_workspace(WORKSPACE, scope["seriesRef"], scope["episodeRef"])
                        observed.append(workspace["versions"][0]["scriptVersionRef"])
                        raise RuntimeError("isolated completion fault")
                    return save(store, record)

                with patch.object(store_type, "save", fault), self.assertRaises(RuntimeError):
                    assembly.script_studio.complete_generation(ticket)
                self.assertEqual(1, len(observed))
                self.assertEqual(before, snapshot(path) if path else assembly.script_studio.get_workspace(
                    WORKSPACE, scope["seriesRef"], scope["episodeRef"]))
                self.assertEqual("RESULT_READY", assembly.script_studio.reserve_generation(command)["state"])
                completed = assembly.script_studio.complete_generation(ticket)
                replay = assembly.script_studio.reserve_generation(command)
                self.assertEqual(completed, replay["response"])
                self.assertEqual("COMPLETED", replay["state"])

    def test_inmemory_and_sqlite_reservation_excludes_new_keys_without_facts(self):
        for sqlite in (False, True):
            with self.subTest(sqlite=sqlite):
                assembly, _, scope = self.fixture(sqlite)
                assembly.script_studio.reserve_generation({**scope, "idempotencyKey": "first"})
                for extra in ({"idempotencyKey": "first"}, {"idempotencyKey": "other"}, {}):
                    with self.assertRaises(ScriptStudioPublicError) as error:
                        assembly.script_studio.reserve_generation({**scope, **extra})
                    self.assertEqual((409, "script_generation_pending"), (error.exception.status, error.exception.code))
                self.assertIsNone(assembly.script_studio.get_workspace(
                    WORKSPACE, scope["seriesRef"], scope["episodeRef"])["script"])

    def test_inmemory_and_sqlite_failed_result_is_terminal_but_new_key_can_reserve(self):
        for sqlite in (False, True):
            with self.subTest(sqlite=sqlite):
                assembly, _, scope = self.fixture(sqlite)
                command = {**scope, "idempotencyKey": "invalid-output"}
                reserved = assembly.script_studio.reserve_generation(command)
                assembly.script_studio.fail_generation({k: reserved[k] for k in ("scope", "identityDigest")},
                                                      "invalid_provider_output")
                with self.assertRaises(ScriptStudioPublicError) as failed:
                    assembly.script_studio.reserve_generation(command)
                self.assertEqual("invalid_provider_output", failed.exception.code)
                self.assertEqual("RESERVED", assembly.script_studio.reserve_generation(
                    {**scope, "idempotencyKey": "new-attempt"})["state"])

    def test_strict_key_identity_inputs(self):
        for key in (None, True, 1, "", " leading", "trailing ", "a/b", "a\\b", ".", "..", "a\n", "a\x00", "x" * 201, "\ud800"):
            with self.subTest(key_type=type(key).__name__), self.assertRaises(GenerationRecoveryError):
                validate_key(key)
        self.assertEqual("x" * 200, validate_key("x" * 200))
        self.assertEqual("合法键-🙂", validate_key("合法键-🙂"))

    def test_optional_component_addition_preserves_all_existing_domain_rows(self):
        assembly, path, scope = self.fixture(True)
        command, ticket = self.ready(assembly, scope)
        assembly.script_studio.complete_generation(ticket)
        domain_before = {table: rows(path, table) for table in ("v5_scripts", "v5_script_versions", "v5_episode_projects")}
        # Simulate the legitimate pre-component schema, using only a disposable DB.
        with sqlite3.connect(path) as connection:
            connection.execute(f"DROP TABLE {TABLE}")
            connection.execute(f"DROP TABLE {MARKER_TABLE}")
        LifecycleAssembly.sqlite(path)
        self.assertEqual([], rows(path, TABLE))
        self.assertEqual(domain_before, {table: rows(path, table) for table in domain_before})
        before = snapshot(path)
        LifecycleAssembly.sqlite(path)
        self.assertEqual(before, snapshot(path))
        with sqlite3.connect(path) as connection:
            self.assertEqual({2}, {row[0] for name in ("v5_series_episode_schema", "v5_project_schema",
                "v5_script_studio_schema", "v5_series_planning_schema") for row in connection.execute(f"SELECT schema_version FROM {name}")})
            self.assertEqual(1, connection.execute("SELECT schema_version FROM v5_series_intelligence_schema").fetchone()[0])

    def test_partial_marker_table_index_unknown_objects_fail_closed_without_repair(self):
        changes = (
            f"DROP TABLE {TABLE}", f"DROP TABLE {MARKER_TABLE}", f"DROP INDEX {INDEX}",
            f"UPDATE {MARKER_TABLE} SET schema_version=2", f"DELETE FROM {MARKER_TABLE}",
            f"CREATE INDEX unrecognized_generation_index ON {TABLE}(state)",
            "CREATE TABLE unrecognized_third_table(value TEXT)",
        )
        for sql in changes:
            with self.subTest(sql=sql):
                _, path, _ = self.fixture(True)
                with sqlite3.connect(path) as connection:
                    connection.execute(sql)
                before = snapshot(path)
                with self.assertRaises(SeriesIntelligenceMigrationError):
                    LifecycleAssembly.sqlite(path)
                self.assertEqual(before, snapshot(path))

    def test_pending_and_ready_tampering_is_not_promoted_after_restart(self):
        def corruption(record, kind):
            if kind == "hash":
                record["sourceDigest"] = "0" * 64
                return record
            if kind == "source":
                record["source"]["bootstrap"]["workspaceRef"] = "foreign-workspace"
                record["sourceDigest"] = digest(record["source"])
            elif kind == "content":
                record["result"]["scenes"] = []
                record["resultDigest"] = digest(record["result"])
            elif kind == "unknown-state":
                record["state"] = "UNKNOWN"
            elif kind == "fake-response":
                record["response"] = {"script": {"confirmed": True}}
            return seal(record)

        for kind in ("hash", "source", "content", "unknown-state", "fake-response"):
            with self.subTest(kind=kind):
                assembly, path, scope = self.fixture(True)
                self.ready(assembly, scope)
                with sqlite3.connect(path) as connection:
                    record = json.loads(connection.execute(f"SELECT record_json FROM {TABLE}").fetchone()[0])
                    record = corruption(record, kind)
                    connection.execute(f"UPDATE {TABLE} SET record_json=?", (canonical(record),))
                before = snapshot(path)
                with self.assertRaises(SeriesIntelligenceMigrationError):
                    LifecycleAssembly.sqlite(path)
                self.assertEqual(before, snapshot(path))
                self.assertEqual([], rows(path, "v5_scripts"))

    def test_completed_requires_actual_immutable_version_and_original_root_association(self):
        for kind in ("missing", "changed", "response-ref", "indexed-scope"):
            with self.subTest(kind=kind):
                assembly, path, scope = self.fixture(True)
                _, ticket = self.ready(assembly, scope)
                assembly.script_studio.complete_generation(ticket)
                with sqlite3.connect(path) as connection:
                    if kind == "missing":
                        connection.execute("DELETE FROM v5_script_versions")
                    elif kind == "changed":
                        connection.execute("UPDATE v5_script_versions SET created_at='2026-09-01T00:00:00.000Z'")
                    elif kind == "indexed-scope":
                        connection.execute(f"UPDATE {TABLE} SET episode_ref='foreign-episode'")
                    else:
                        record = json.loads(connection.execute(f"SELECT record_json FROM {TABLE}").fetchone()[0])
                        record["response"]["scriptVersion"]["scriptRef"] = "foreign-script"
                        connection.execute(f"UPDATE {TABLE} SET record_json=?", (canonical(seal(record)),))
                before = snapshot(path)
                with self.assertRaises(SeriesIntelligenceMigrationError):
                    LifecycleAssembly.sqlite(path)
                self.assertEqual(before, snapshot(path))

    def test_same_target_confirm_noop_and_guarded_switch_adapter_parity(self):
        for sqlite in (False, True):
            with self.subTest(sqlite=sqlite):
                assembly, path, scope = self.fixture(sqlite)
                created = assembly.script_studio.create_version({**scope, "changeKind": "ai-generation",
                                                                 "content": content_from_candidate()})
                confirm = {**scope, "scriptRef": created["script"]["scriptRef"], "humanConfirmed": True,
                           "scriptVersionRef": created["scriptVersion"]["scriptVersionRef"]}
                first = assembly.script_studio.confirm_version(confirm)
                before = snapshot(path) if path else first
                for extra in ({}, {"expectedScriptVersion": 1}, {"expectedScriptVersion": 2}):
                    self.assertEqual(first, assembly.script_studio.confirm_version({**confirm, **extra}))
                if path:
                    self.assertEqual(before, snapshot(path))
                content = {k: deepcopy(created["scriptVersion"][k]) for k in
                           ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
                content["synopsis"] = "Explicit new immutable content."
                second = assembly.script_studio.create_version({**scope, "scriptRef": confirm["scriptRef"],
                    "baseScriptVersionRef": confirm["scriptVersionRef"], "changeKind": "manual-edit", "content": content})
                switch = {**confirm, "scriptVersionRef": second["scriptVersion"]["scriptVersionRef"]}
                with self.assertRaises(ScriptStudioPublicError) as missing:
                    assembly.script_studio.confirm_version(switch)
                self.assertEqual("script_confirmation_precondition_required", missing.exception.code)
                switched = assembly.script_studio.confirm_version({**switch, "expectedScriptVersion": 3})
                self.assertEqual(4, switched["script"]["version"])
                for old in (confirm, {**confirm, "expectedScriptVersion": 2}):
                    with self.assertRaises(ScriptStudioPublicError):
                        assembly.script_studio.confirm_version(old)
                self.assertEqual(switched, assembly.script_studio.confirm_version(switch))


if __name__ == "__main__":
    unittest.main()
