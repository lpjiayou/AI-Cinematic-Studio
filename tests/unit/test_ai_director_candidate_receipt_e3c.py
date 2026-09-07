"""Identity, command transitions, and exact optional SQLite component tests."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from apps.creator_workspace_mvp.ai_director import AiDirectorService, PlanGenerationError
from apps.creator_workspace_mvp.ai_director_candidate_receipts import (
    AiDirectorCandidateReceiptError, create_candidate_receipt_service, new_pending_command,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_episode.ai_director_candidate_receipt_sqlite import (
    AiDirectorCandidateStorageError, TABLE, MARKER_TABLE, IDENTITY_INDEX, SOURCE_REF_INDEX,
    canonical_digest, canonical_json, index_statements, seal_record, validate_command,
)
from services.v5_core_os.text_generation import TextGenerationTimeoutError, TextGenerationUnavailableError
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


class AiDirectorCandidateIdentityTests(unittest.TestCase):
    def test_frozen_utf8_identity_vector_and_independent_source_separator(self):
        one = new_pending_command('workspace-vector-一', valid_brief(), 'E3C fixed vector')
        two = new_pending_command('workspace-vector-一', {**valid_brief(), 'theme': 'different'}, 'E3C fixed vector')
        identity = '83329459a59463350d7e4b485837e1d543191d83aed237f975d91a093037277f'
        source = 'd9d764534a3c4db64039f2dff0b7a717e529906964fb9acf5a56a7cb0c13b328'
        self.assertEqual(one.commandRef, 'ai-director-candidate-command-' + identity)
        self.assertEqual(one.sourcePlanRef, 'ai-director-candidate-' + source)
        self.assertEqual((one.commandRef, one.sourcePlanRef), (two.commandRef, two.sourcePlanRef))
        self.assertNotEqual(one.requestDigest, two.requestDigest)
        for workspace, key in [('other-workspace', 'E3C fixed vector'), ('workspace-vector-一', 'other-key')]:
            changed = new_pending_command(workspace, valid_brief(), key)
            self.assertNotEqual(one.sourcePlanRef, changed.sourcePlanRef)
        self.assertNotIn('E3C fixed vector', canonical_json(asdict(one)))
        self.assertNotEqual(one.identityDigest, source)

    def test_normalized_brief_and_candidate_digest_are_canonical(self):
        service = create_candidate_receipt_service()
        raw = valid_brief()
        first = service.generate_candidate('workspace', raw, idempotency_key='key', generator=lambda _: valid_plan())
        normalized = {**raw, 'topic': ' ' + raw['topic'] + ' ', 'duration': '30 seconds'}
        replay = service.generate_candidate('workspace', normalized, idempotency_key='key', generator=self.fail)
        self.assertEqual(first['candidateDigest'], replay['candidateDigest'])
        self.assertTrue(replay['idempotentReplay'])
        record = service.store.get_by_source('workspace', first['sourcePlanRef'])
        candidate = json.loads(record.candidateJson)
        self.assertEqual(canonical_digest(candidate), first['candidateDigest'])
        self.assertEqual(canonical_json(candidate), record.candidateJson)
        self.assertNotEqual(canonical_digest(first), canonical_digest(replay))
        for number in (float('nan'), float('inf'), float('-inf')):
            with self.assertRaises(ValueError):
                canonical_json({'number': number})

    def test_reply_is_detached_and_confirmation_uses_stored_canonical_plan(self):
        service = create_candidate_receipt_service()
        result = service.generate_candidate('workspace', valid_brief(), idempotency_key='key', generator=lambda _: valid_plan())
        original = json.loads(json.dumps(result['plan']))
        resolved = service.resolve_for_confirmation('workspace', result['sourcePlanRef'], 1, valid_brief(), original)
        self.assertEqual(resolved, original)
        self.assertIsNot(resolved, original)
        result['plan']['storyDirection']['title'] = 'browser mutation'
        replay = service.generate_candidate('workspace', valid_brief(), idempotency_key='key', generator=self.fail)
        self.assertEqual(replay['plan'], original)


class AiDirectorCandidateSqliteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'creator.sqlite3'
        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=True)

    def service(self):
        return create_candidate_receipt_service(self.path)

    def issue(self, service=None, key='key'):
        return (service or self.service()).generate_candidate(
            'workspace', valid_brief(), idempotency_key=key, generator=lambda _: valid_plan())

    def execute(self, sql, args=()):
        with sqlite3.connect(self.path) as connection:
            connection.execute(sql, args)

    def test_absent_component_then_exact_addition_and_m6_restart(self):
        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False)
        with sqlite3.connect(self.path) as connection:
            before = connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
        service = self.service()
        self.issue(service)
        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False)
        self.assertEqual(self.service().store.count(), 1)
        with sqlite3.connect(self.path) as connection:
            after = dict(connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall())
            for name, ddl in before:
                self.assertEqual(after[name], ddl)
            self.assertEqual(set(after) - {name for name, _ in before}, {TABLE, MARKER_TABLE})
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def assert_corrupt_rejected(self):
        with self.assertRaises(AiDirectorCandidateStorageError):
            self.service()
        with self.assertRaises(Exception):
            LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False)

    def test_partial_table_marker_and_each_index_fail_closed(self):
        self.service()
        pristine = self.path.read_bytes()
        for name, kind in [(TABLE, 'TABLE'), (MARKER_TABLE, 'TABLE'), (IDENTITY_INDEX, 'INDEX'), (SOURCE_REF_INDEX, 'INDEX')]:
            with self.subTest(name=name):
                self.path.write_bytes(pristine)
                self.execute(f'DROP {kind} {name}')
                self.assert_corrupt_rejected()

    def test_altered_table_index_marker_and_unknown_object_fail_closed(self):
        self.service()
        pristine = self.path.read_bytes()
        commands = [
            f'ALTER TABLE {TABLE} ADD COLUMN extra TEXT',
            f'UPDATE {MARKER_TABLE} SET schema_version=2',
            f'INSERT INTO {MARKER_TABLE} VALUES (\'unknown\',1)',
            f'CREATE INDEX unknown_candidate_index ON {TABLE}(state)',
            'CREATE TABLE unrelated_undeclared (id TEXT)',
        ]
        for sql in commands:
            with self.subTest(sql=sql):
                self.path.write_bytes(pristine)
                self.execute(sql)
                if 'unrelated_undeclared' in sql:
                    with self.assertRaises(Exception):
                        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False)
                else:
                    self.assert_corrupt_rejected()
        for index in (IDENTITY_INDEX, SOURCE_REF_INDEX):
            with self.subTest(index=index):
                self.path.write_bytes(pristine)
                self.execute(f'DROP INDEX {index}')
                self.execute(f'CREATE INDEX {index} ON {TABLE}(workspace_ref, state)')
                self.assert_corrupt_rejected()

    def test_every_durable_row_is_revalidated_including_request_digest(self):
        self.issue(key='one')
        self.issue(key='two')
        pristine = self.path.read_bytes()
        changes = {'request_digest': 'a' * 64, 'candidate_json': '{}', 'state': 'UNKNOWN',
                   'created_at': '2026-02-30T00:00:00.000000Z', 'candidate_digest': 'b' * 64,
                   'failure_code': 'provider body secret', 'source_plan_version': 2}
        for column, value in changes.items():
            with self.subTest(column=column):
                self.path.write_bytes(pristine)
                self.execute(f'UPDATE {TABLE} SET {column}=? WHERE rowid=(SELECT MAX(rowid) FROM {TABLE})', (value,))
                self.assert_corrupt_rejected()

    def test_resealed_invalid_state_nullability_timestamp_and_candidate_fail_closed(self):
        service = self.service()
        result = self.issue(service)
        row = service.store.get_by_source('workspace', result['sourcePlanRef'])
        for changed in [replace(row, state='PENDING'), replace(row, state='FAILED'),
                        replace(row, completedAt=None), replace(row, sourcePlanVersion=True),
                        replace(row, createdAt='2026-02-30T00:00:00.000000Z'),
                        replace(row, candidateJson=row.candidateJson + ' '),
                        replace(row, state='UNKNOWN')]:
            with self.subTest(changed=changed.state):
                with self.assertRaises(AiDirectorCandidateStorageError):
                    validate_command(seal_record(changed))

    def test_unique_identity_and_source_constraints_cannot_be_bypassed_on_restart(self):
        self.issue(key='one')
        self.issue(key='two')
        pristine = self.path.read_bytes()
        for column, index in [('identity_digest', IDENTITY_INDEX), ('source_plan_ref', SOURCE_REF_INDEX)]:
            with self.subTest(column=column):
                self.path.write_bytes(pristine)
                with self.assertRaises(sqlite3.IntegrityError):
                    self.execute(f'UPDATE {TABLE} SET {column}=(SELECT {column} FROM {TABLE} LIMIT 1)')
                self.execute(f'DROP INDEX {index}')
                self.execute(f'UPDATE {TABLE} SET {column}=(SELECT {column} FROM {TABLE} LIMIT 1)')
                self.assert_corrupt_rejected()
                with self.assertRaises(sqlite3.IntegrityError):
                    self.execute(index_statements()[0 if column == 'identity_digest' else 1])

    def test_completion_is_atomic_and_cannot_replace_terminal_or_identity(self):
        service = self.service()
        pending = new_pending_command('workspace', valid_brief(), 'key')
        self.assertTrue(service.store.reserve(pending)[1])
        failed = seal_record(replace(pending, state='FAILED', failureCode='application_error', completedAt=pending.createdAt))
        with self.assertRaises(AiDirectorCandidateStorageError):
            service.store.finish(pending, seal_record(replace(failed, requestDigest='f' * 64)))
        service.store.finish(pending, failed)
        with self.assertRaises(AiDirectorCandidateStorageError):
            service.store.finish(pending, failed)
        self.assertEqual(service.store.get_by_source('workspace', pending.sourcePlanRef), failed)

    def test_provider_failure_replays_only_stable_codes_and_new_key_can_generate(self):
        outcomes = [
            ('provider_timeout', [TextGenerationTimeoutError()], 1),
            ('provider_unavailable', [TextGenerationUnavailableError()], 1),
            ('invalid_provider_output', ['{}', '{}'], 2),
            ('application_error', [RuntimeError('RAW-EXCEPTION-SECRET')], 1),
        ]
        service = self.service()
        for code, failures, calls in outcomes:
            capability = FakeTextGenerationCapability(failures + [json.dumps(valid_plan())])
            generator = AiDirectorService(capability).generate
            for replay in (False, True):
                with self.subTest(code=code, replay=replay):
                    with self.assertRaises(AiDirectorCandidateReceiptError) as caught:
                        service.generate_candidate('workspace', valid_brief(), idempotency_key=code, generator=generator)
                    self.assertEqual((caught.exception.status, caught.exception.code), (200, code))
                    self.assertEqual(caught.exception.idempotent_replay, replay)
                    self.assertEqual(len(capability.commands), calls)
            self.assertTrue(service.generate_candidate('workspace', valid_brief(), idempotency_key=code+'-new', generator=generator)['ok'])
        self.assertNotIn(b'RAW-EXCEPTION-SECRET', self.path.read_bytes())

    def test_repair_once_is_one_command_and_replay_has_no_additional_calls(self):
        service = self.service()
        capability = FakeTextGenerationCapability(['{}', json.dumps(valid_plan())])
        generator = AiDirectorService(capability).generate
        result = service.generate_candidate('workspace', valid_brief(), idempotency_key='repair', generator=generator)
        replay = service.generate_candidate('workspace', valid_brief(), idempotency_key='repair', generator=generator)
        self.assertEqual(len(capability.commands), 2)
        self.assertEqual(service.store.count(), 1)
        self.assertEqual(result['candidateDigest'], replay['candidateDigest'])


if __name__ == '__main__':
    unittest.main()
