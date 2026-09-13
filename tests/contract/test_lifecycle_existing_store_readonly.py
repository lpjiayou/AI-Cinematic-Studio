"""Existing-store construction must validate without schema or fact writes."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_intelligence.migration import SeriesIntelligenceMigrationError
from services.v5_core_os.project_engine.foundation import SqliteProjectAdapter
from services.v5_core_os.script_studio.foundation import SqliteScriptStudioAdapter
from services.v5_core_os.series_episode.foundation import SqliteSeriesEpisodeAdapter
from services.v5_core_os.series_planning.foundation import SqliteSeriesPlanningAdapter
from services.v5_core_os.project_engine.project_foundation_sqlite import (
    SqliteProjectFoundationStore, TABLE as FOUNDATION_TABLE, ProjectFoundationStorageError,
)
from services.v5_core_os.script_studio.generation_recovery_sqlite import (
    SqliteGenerationStore, TABLE as GENERATION_TABLE, GenerationStorageError,
)


class ExistingLifecycleReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "fixture.sqlite3"
        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=True)

    @contextmanager
    def readonly_connections(self):
        original = sqlite3.connect
        denied = []
        write_actions = {getattr(sqlite3, name) for name in (
            "SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE", "SQLITE_CREATE_TABLE",
            "SQLITE_CREATE_INDEX", "SQLITE_CREATE_TRIGGER", "SQLITE_CREATE_VIEW",
            "SQLITE_DROP_TABLE", "SQLITE_DROP_INDEX", "SQLITE_DROP_TRIGGER",
            "SQLITE_DROP_VIEW", "SQLITE_ALTER_TABLE", "SQLITE_ATTACH", "SQLITE_DETACH",
        )}
        def authorize(action, arg1, arg2, database, trigger):
            if action in write_actions:
                denied.append((action, arg1, arg2))
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        def connect(database, *args, **kwargs):
            self.assertEqual(Path(database).resolve(), self.path)
            kwargs["uri"] = True
            connection = original(self.path.as_uri() + "?mode=ro", *args, **kwargs)
            connection.execute("PRAGMA query_only=ON")
            connection.set_authorizer(authorize)
            return connection
        before = self.path.read_bytes()
        paths = sorted(self.root.iterdir())
        with patch.object(sqlite3, "connect", side_effect=connect):
            yield denied
        self.assertEqual(denied, [], "opening existing stores attempted a write")
        self.assertEqual(sha256(before).hexdigest(), sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(paths, sorted(self.root.iterdir()), "opening created a sidecar")

    def test_existing_assembly_opens_through_real_readonly_connections_without_writes(self):
        with self.readonly_connections():
            assembly = LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False, existing_only=True)
            self.assertIsNotNone(assembly.series_episode)
            self.assertIsNotNone(assembly.script_studio)
            self.assertIsNotNone(assembly.project_context)

    def test_each_domain_adapter_validates_existing_schema_without_initializing(self):
        with self.readonly_connections():
            for adapter in (SqliteSeriesEpisodeAdapter, SqliteProjectAdapter,
                            SqliteScriptStudioAdapter, SqliteSeriesPlanningAdapter,
                            SqliteProjectFoundationStore):
                with self.subTest(adapter=adapter.__name__):
                    adapter(self.path, initialize_if_missing=False)
            SqliteGenerationStore(self.path, lifecycle_state=None, initialize_if_missing=False)

    def test_missing_optional_participant_tables_fail_closed_without_repair(self):
        original = self.path.read_bytes()
        for table, error in ((FOUNDATION_TABLE, ProjectFoundationStorageError),
                             (GENERATION_TABLE, GenerationStorageError)):
            with self.subTest(table=table):
                self.path.write_bytes(original)
                # Each malformed database is fixture-owned, never an original store.
                with sqlite3.connect(self.path) as connection:
                    connection.execute('DROP TABLE "' + table + '"')
                with self.readonly_connections():
                    with self.assertRaises(SeriesIntelligenceMigrationError):
                        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False, existing_only=True)
                    with self.assertRaises(error):
                        if table == FOUNDATION_TABLE:
                            SqliteProjectFoundationStore(self.path, initialize_if_missing=False)
                        else:
                            SqliteGenerationStore(self.path, lifecycle_state=None,
                                                  initialize_if_missing=False)

    def test_missing_database_is_not_created_by_existing_only_adapters(self):
        missing = self.root / "absent-directory" / "missing.sqlite3"
        for adapter in (SqliteSeriesEpisodeAdapter, SqliteProjectAdapter,
                        SqliteScriptStudioAdapter, SqliteSeriesPlanningAdapter,
                        SqliteProjectFoundationStore):
            with self.subTest(adapter=adapter.__name__):
                with self.assertRaises(RuntimeError):
                    adapter(missing, initialize_if_missing=False)
                self.assertFalse(missing.parent.exists())
        with self.assertRaises(GenerationStorageError):
            SqliteGenerationStore(missing, lifecycle_state=None, initialize_if_missing=False)
        self.assertFalse(missing.parent.exists())

    def test_existing_only_rejects_upgrade_before_creating_any_database(self):
        missing = self.root / "not-created.sqlite3"
        with self.assertRaisesRegex(ValueError, "cannot initialize or upgrade"):
            LifecycleAssembly.sqlite(missing, initialize_or_upgrade=True, existing_only=True)
        self.assertFalse(missing.exists())
