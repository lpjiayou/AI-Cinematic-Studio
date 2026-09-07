"""Authenticated HTTP over real SQLite for candidate issuance and recovery."""

import copy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import secrets
import selectors
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.ai_director_candidate_receipts import (
    create_candidate_receipt_service, new_pending_command,
)
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import PUBLIC_AI_DIRECTOR_ENDPOINT, PUBLIC_CONFIRM_PLAN_ENDPOINT
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v5_core_os.text_generation import TextGenerationUnavailableError
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


TABLE = 'creator_ai_director_candidate_commands'
WORKSPACE = 'e3c-http-workspace'
FOREIGN_WORKSPACE = 'e3c-http-foreign'


class CandidateHttpHarness:
    def __init__(self, path, *, initialize=True, capability=None, tokens=None):
        self.path = Path(path)
        self.capability = capability if capability is not None else FakeTextGenerationCapability([json.dumps(valid_plan())] * 40)
        self.tokens = tokens or (secrets.token_urlsafe(40), secrets.token_urlsafe(40))
        auth = PublicApiAuthenticator.from_mapping({
            'schemaVersion': 'creator.public-auth.v1',
            'credentials': [
                {'credentialRef': f'e3c-credential-{i}', 'workspaceRef': workspace,
                 'tokenSha256': sha256(token.encode()).hexdigest(), 'enabled': True}
                for i, (workspace, token) in enumerate(zip((WORKSPACE, FOREIGN_WORKSPACE), self.tokens))
            ],
        })
        self.assembly = LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=initialize)
        self.server = create_server(
            ('127.0.0.1', 0), AiDirectorService(self.capability),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_boundary=self.assembly.script_studio,
            public_authenticator=auth, allow_internal_routes=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(5)
            assert not self.thread.is_alive()
            self.server = None
            self.assembly = None

    def request(self, path=PUBLIC_AI_DIRECTOR_ENDPOINT, body=None, *, token=None, raw=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        payload = raw if raw is not None else json.dumps(body, ensure_ascii=False).encode()
        try:
            client.request('POST', path, payload, {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (token or self.tokens[0])})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def rows(self, table=TABLE):
        con = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        try:
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                return []
            return [dict(row) for row in con.execute(f'SELECT * FROM {table}')]
        finally:
            con.close()


class CandidateBaselineRegressionTests(unittest.TestCase):
    """These safety assertions fail against the frozen pre-E3C baseline."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'creator.sqlite3'
        self.http = CandidateHttpHarness(self.path)
        self.addCleanup(lambda: self.http.close())
        self.body = {'brief': valid_brief(), 'idempotencyKey': 'e3c-candidate-command'}

    def test_keyed_source_identity_is_replayed(self):
        first_status, first = self.http.request(body=self.body)
        status, replay = self.http.request(body=self.body)
        self.replay_evidence = {
            'firstStatus': first_status, 'replayStatus': status,
            'first': first, 'replay': replay,
            'providerCalls': len(self.http.capability.commands),
            'applicationCommands': len(self.http.rows()),
            'confirmedPlans': len(self.http.rows('v5_confirmed_creative_plans')),
        }
        self.assertEqual((first_status, status), (200, 200))
        self.assertEqual(first['sourcePlanRef'], replay['sourcePlanRef'])
        self.assertEqual(first['sourcePlanVersion'], replay['sourcePlanVersion'])
        self.assertEqual(first['candidateDigest'], replay['candidateDigest'])
        self.assertEqual(first['plan'], replay['plan'])
        self.assertFalse(first['idempotentReplay'])
        self.assertTrue(replay['idempotentReplay'])

    def test_keyed_replay_does_not_recall_generation(self):
        self.http.request(body=self.body)
        self.http.request(body=self.body)
        self.assertEqual(len(self.http.capability.commands), 1)

    def test_key_is_bound_to_durable_application_receipt(self):
        self.http.request(body=self.body)
        self.http.request(body=self.body)
        self.assertEqual(len(self.http.rows()), 1)
        self.assertEqual(self.http.rows()[0]['state'], 'COMPLETED')
        self.assertEqual(self.http.rows('v5_confirmed_creative_plans'), [])

    def test_unknown_public_field_is_rejected_before_generation(self):
        status, result = self.http.request(body={**self.body, 'unknownField': True})
        self.assertEqual(status, 400)
        self.assertEqual(result['error']['code'], 'invalid_request')
        self.assertEqual(len(self.http.capability.commands), 0)
        self.assertEqual(self.http.rows(), [])

    def test_duplicate_json_key_is_rejected_before_generation(self):
        raw = ('{"brief":' + json.dumps(valid_brief()) + ',"idempotencyKey":"one","idempotencyKey":"two"}').encode()
        status, result = self.http.request(raw=raw)
        self.assertEqual(status, 400)
        self.assertEqual(result['error']['code'], 'invalid_request')
        self.assertEqual(len(self.http.capability.commands), 0)

    def test_fresh_sqlite_server_replays_without_generation(self):
        _, first = self.http.request(body=self.body)
        capability, tokens = self.http.capability, self.http.tokens
        self.http.close()
        self.http = CandidateHttpHarness(self.path, initialize=False, capability=capability, tokens=tokens)
        status, replay = self.http.request(body=self.body)
        self.assertEqual(status, 200)
        self.assertEqual(first['sourcePlanRef'], replay['sourcePlanRef'])
        self.assertEqual(len(capability.commands), 1)

    def test_unissued_source_cannot_create_confirmed_plan(self):
        status, result = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, {
            'humanConfirmed': True, 'brief': valid_brief(), 'plan': valid_plan(),
            'sourcePlanRef': 'ai-director-candidate-unissued', 'sourcePlanVersion': 1,
            'idempotencyKey': 'e3c-confirm-unissued',
        })
        self.assertEqual(status, 404)
        self.assertEqual(result['error']['code'], 'ai_director_candidate_not_issued')
        self.assertEqual(self.http.rows('v5_confirmed_creative_plans'), [])

    def test_unkeyed_frontend_envelope_remains_compatible(self):
        status, first = self.http.request(body={'brief': valid_brief()})
        status2, second = self.http.request(body={'brief': valid_brief()})
        self.assertEqual((status, status2), (200, 200))
        self.assertEqual(set(first), {'ok', 'kind', 'confirmationRequired', 'sourcePlanRef', 'sourcePlanVersion', 'plan'})
        self.assertNotEqual(first['sourcePlanRef'], second['sourcePlanRef'])


class CandidateRecoveryAndBindingTests(unittest.TestCase):
    setUp = CandidateBaselineRegressionTests.setUp

    @staticmethod
    def confirmation(candidate, **changes):
        return {'humanConfirmed': True, 'brief': valid_brief(), 'plan': candidate['plan'],
                'sourcePlanRef': candidate['sourcePlanRef'], 'sourcePlanVersion': 1,
                'idempotencyKey': 'e3c-confirmation', **changes}

    def test_all_seven_changed_brief_fields_conflict_without_calls_or_writes(self):
        _, first = self.http.request(body=self.body)
        before = self.path.read_bytes()
        for field in ('topic', 'theme', 'audience', 'duration', 'platform', 'style', 'character'):
            with self.subTest(field=field):
                brief = {**valid_brief(), field: '35' if field == 'duration' else 'changed input'}
                status, result = self.http.request(body={**self.body, 'brief': brief})
                self.assertEqual((status, result['error']['code']), (409, 'ai_director_candidate_idempotency_conflict'))
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(len(self.http.capability.commands), 1)
        self.assertEqual(self.http.request(body=self.body)[1]['candidateDigest'], first['candidateDigest'])

    def test_issued_and_unkeyed_candidates_confirm_and_replay_with_e3b(self):
        for keyed in (False, True):
            with self.subTest(keyed=keyed):
                body = self.body if keyed else {'brief': valid_brief()}
                _, candidate = self.http.request(body=body)
                command = self.confirmation(candidate)
                if not keyed:
                    del command['idempotencyKey']
                first_status, first = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command)
                before = self.path.read_bytes()
                status, replay = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command)
                self.assertEqual((first_status, status), (201, 200))
                self.assertEqual(first['confirmedPlan'], replay['confirmedPlan'])
                self.assertRegex(first['confirmedPlan']['creativePlanRef'], r'^creative-plan-[0-9a-f]{64}$')
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(set(first), {'ok', 'confirmedPlan', 'idempotentReplay'} if keyed else {'ok', 'confirmedPlan'})
        self.assertEqual(len(self.http.rows()), 2)
        self.assertEqual(len(self.http.rows('v5_confirmed_creative_plans')), 2)

    def test_source_scope_version_and_content_binding_rejections_create_no_confirmed_plan(self):
        _, candidate = self.http.request(body=self.body)
        changed_plan = copy.deepcopy(candidate['plan'])
        changed_plan['storyDirection']['title'] = 'forged title'
        variants = [
            ({'sourcePlanRef': 'unknown'}, None, 404, 'ai_director_candidate_not_issued'),
            ({}, self.http.tokens[1], 404, 'ai_director_candidate_not_issued'),
            ({'sourcePlanVersion': 2}, None, 409, 'ai_director_candidate_version_mismatch'),
            ({'sourcePlanVersion': True}, None, 400, 'invalid_request'),
            ({'brief': {**valid_brief(), 'theme': 'changed theme'}}, None, 409, 'ai_director_candidate_content_mismatch'),
            ({'brief': {**valid_brief(), 'duration': '300'}}, None, 409, 'ai_director_candidate_content_mismatch'),
            ({'plan': changed_plan}, None, 409, 'ai_director_candidate_content_mismatch'),
        ]
        before = self.path.read_bytes()
        for change, token, status, code in variants:
            with self.subTest(change=change, foreign=token is not None):
                actual, result = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.confirmation(candidate, **change), token=token)
                self.assertEqual((actual, result['error']['code']), (status, code))
                self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.http.rows('v5_confirmed_creative_plans'), [])

    def test_failed_and_pending_receipts_cannot_confirm_and_never_retry(self):
        service = create_candidate_receipt_service(self.path)
        pending = new_pending_command(WORKSPACE, valid_brief(), self.body['idempotencyKey'])
        service.store.reserve(pending)
        pending_candidate = {'plan': valid_plan(), 'sourcePlanRef': pending.sourcePlanRef}
        before = self.path.read_bytes()
        self.assertEqual(self.http.request(body=self.body)[1]['error']['code'], 'ai_director_candidate_generation_pending')
        self.assertEqual(self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.confirmation(pending_candidate))[0], 404)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.http.capability.commands), 0)
        self.http.close()
        capability = FakeTextGenerationCapability([TextGenerationUnavailableError()])
        self.http = CandidateHttpHarness(self.path, initialize=False, capability=capability)
        failed_body = {**self.body, 'idempotencyKey': 'failed-command'}
        first = self.http.request(body=failed_body)
        before = self.path.read_bytes()
        self.assertEqual(first[0], 200)
        self.assertEqual(first[1]['error']['code'], 'provider_unavailable')
        self.assertEqual(self.http.request(body=failed_body), first)
        row = next(row for row in self.http.rows() if row['state'] == 'FAILED')
        command = self.confirmation({'plan': valid_plan(), 'sourcePlanRef': row['source_plan_ref']})
        self.assertEqual(self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command)[0], 404)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(capability.commands), 1)
        self.assertEqual(self.http.rows('v5_confirmed_creative_plans'), [])

    def test_corrupt_or_unavailable_receipt_returns_503_without_generation_or_confirmation(self):
        _, candidate = self.http.request(body=self.body)
        pristine = self.path.read_bytes()
        for sql in (f"UPDATE {TABLE} SET request_digest='" + 'a' * 64 + "'", f'DROP TABLE {TABLE}'):
            with self.subTest(sql=sql):
                self.path.write_bytes(pristine)
                with sqlite3.connect(self.path) as connection:
                    connection.execute(sql)
                before = self.path.read_bytes()
                for endpoint, body in [(PUBLIC_AI_DIRECTOR_ENDPOINT, self.body),
                                       (PUBLIC_CONFIRM_PLAN_ENDPOINT, self.confirmation(candidate))]:
                    status, error = self.http.request(endpoint, body)
                    self.assertEqual((status, error['error']['code']), (503, 'ai_director_candidate_receipt_unavailable'))
                    self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(len(self.http.capability.commands), 1)
                self.assertEqual(self.http.rows('v5_confirmed_creative_plans'), [])

    def test_provider_does_not_hold_transaction_and_pending_is_visible_to_other_connection(self):
        entered, release = threading.Event(), threading.Event()
        class BlockingCapability(FakeTextGenerationCapability):
            def generate(self, command):
                result = super().generate(command)
                if len(self.commands) == 1:
                    entered.set()
                    if not release.wait(10):
                        raise RuntimeError('test provider was not released')
                return result
        self.http.close()
        capability = BlockingCapability([json.dumps(valid_plan())] * 3)
        self.http = CandidateHttpHarness(self.path, initialize=False, capability=capability)
        second = CandidateHttpHarness(self.path, initialize=False, capability=capability, tokens=self.http.tokens)
        self.addCleanup(second.close)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.http.request, body=self.body)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.http.rows()[0]['state'], 'PENDING')
                status, result = second.request(body=self.body)
                self.assertEqual((status, result['error']['code']), (409, 'ai_director_candidate_generation_pending'))
                before = self.path.read_bytes()
                changed = {**self.body, 'brief': {**valid_brief(), 'theme': 'conflicting pending'}}
                self.assertEqual(second.request(body=changed)[1]['error']['code'], 'ai_director_candidate_idempotency_conflict')
                self.assertEqual(self.path.read_bytes(), before)
                foreign = second.request(body=self.body, token=second.tokens[1])
                self.assertEqual(foreign[0], 200)
            finally:
                release.set()
            winner = future.result(timeout=10)
        replay = second.request(body=self.body)
        self.assertEqual(winner[1]['sourcePlanRef'], replay[1]['sourcePlanRef'])
        self.assertNotEqual(winner[1]['sourcePlanRef'], foreign[1]['sourcePlanRef'])
        self.assertEqual(len(capability.commands), 2)
        self.assertEqual(len(self.http.rows()), 2)
        with sqlite3.connect(self.path, timeout=1) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.rollback()

    def test_response_loss_and_fresh_process_restart_replay_without_provider(self):
        tokens = self.http.tokens
        self.http.close()
        first = CandidateProcess(self.path, tokens)
        self.addCleanup(first.close)
        client = http.client.HTTPConnection('127.0.0.1', first.port, timeout=10)
        client.request('POST', PUBLIC_AI_DIRECTOR_ENDPOINT, json.dumps(self.body).encode(), {
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens[0]})
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        response.close()  # Deliberately discard the committed response body.
        client.close()
        committed = self.http.rows()[0]
        status, replay = first.request(self.body)
        self.assertEqual(status, 200)
        self.assertEqual(replay['candidateDigest'], committed['candidate_digest'])
        self.assertEqual(first.close(), 1)
        before = self.path.read_bytes()
        second = CandidateProcess(self.path, tokens)
        self.addCleanup(second.close)
        status, restarted = second.request(self.body)
        self.assertEqual(status, 200)
        self.assertEqual(restarted, replay)
        self.assertEqual(second.close(), 0)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.http.rows()), 1)

    def test_crash_after_reservation_fresh_process_preserves_pending_and_new_key_can_generate(self):
        tokens = self.http.tokens
        self.http.close()
        first = CandidateProcess(self.path, tokens, crash=True)
        self.addCleanup(first.close)
        with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
            first.request(self.body)
        self.assertEqual(first.process.wait(timeout=10), 23)
        self.assertEqual(self.http.rows()[0]['state'], 'PENDING')
        before = self.path.read_bytes()
        second = CandidateProcess(self.path, tokens)
        self.addCleanup(second.close)
        status, result = second.request(self.body)
        self.assertEqual((status, result['error']['code']), (409, 'ai_director_candidate_generation_pending'))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(second.request({**self.body, 'idempotencyKey': 'explicit-new-command'})[0], 200)
        self.assertEqual(second.close(), 1)
        self.assertEqual({row['state'] for row in self.http.rows()}, {'PENDING', 'COMPLETED'})

    def test_simultaneous_commands_in_distinct_processes_have_one_generation_winner(self):
        tokens = self.http.tokens
        self.http.close()
        for changed in (False, True):
            with self.subTest(changed=changed):
                servers = [CandidateProcess(self.path, tokens), CandidateProcess(self.path, tokens)]
                for server in servers:
                    self.addCleanup(server.close)
                body = {**self.body, 'idempotencyKey': 'concurrent-' + str(changed)}
                bodies = [body, {**body, 'brief': {**valid_brief(), 'theme': 'competitor'}} if changed else body]
                barrier = threading.Barrier(2)
                def call(index):
                    barrier.wait(timeout=5)
                    return servers[index].request(bodies[index])
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(call, range(2)))
                winners = [i for i, (status, result) in enumerate(results) if status == 200 and not result['idempotentReplay']]
                self.assertEqual(len(winners), 1)
                winner = winners[0]
                loser_status, loser = results[1 - winner]
                if changed:
                    self.assertEqual((loser_status, loser['error']['code']), (409, 'ai_director_candidate_idempotency_conflict'))
                elif loser_status == 409:
                    self.assertEqual(loser['error']['code'], 'ai_director_candidate_generation_pending')
                else:
                    self.assertEqual(loser_status, 200)
                    self.assertTrue(loser['idempotentReplay'])
                replay = servers[1 - winner].request(bodies[winner])[1]
                self.assertEqual(replay['candidateDigest'], results[winner][1]['candidateDigest'])
                self.assertEqual(sum(server.close() for server in servers), 1)
        self.assertEqual(len(self.http.rows()), 2)
        self.assertEqual(len({row['source_plan_ref'] for row in self.http.rows()}), 2)


class CandidateProcess:
    """A genuinely new Python interpreter and authenticated SQLite HTTP server."""

    def __init__(self, path, tokens, *, crash=False):
        self.tokens = tokens
        self.calls = None
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'tests.integration.test_creator_ai_director_candidate_idempotency_e3c',
             '--candidate-worker', str(path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.process.stdin.write(json.dumps({'tokens': tokens, 'crash': crash}) + '\n')
        self.process.stdin.flush()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                if not selector.select(10):
                    raise AssertionError('candidate worker startup timed out')
            self.port = json.loads(self.process.stdout.readline())['port']
        except BaseException:
            self.process.kill()
            _out, errors = self.process.communicate(timeout=10)
            raise AssertionError('candidate worker startup failed: ' + errors)

    def request(self, body):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            client.request('POST', PUBLIC_AI_DIRECTOR_ENDPOINT, json.dumps(body).encode(), {
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.tokens[0]})
            result = client.getresponse()
            return result.status, json.loads(result.read())
        finally:
            client.close()

    def close(self):
        if self.calls is not None:
            return self.calls
        if self.process.poll() is not None:
            self.process.communicate(timeout=10)
            self.calls = 0
            return self.calls
        try:
            output, errors = self.process.communicate('stop\n', timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=10)
            raise AssertionError('candidate worker shutdown timed out')
        if self.process.returncode != 0:
            raise AssertionError('candidate worker failed: ' + errors)
        self.calls = json.loads(output)['calls']
        return self.calls


def _candidate_worker(path):
    settings = json.loads(sys.stdin.readline())
    capability = FakeTextGenerationCapability([json.dumps(valid_plan())] * 4)
    if settings['crash']:
        def crash(_command):
            os._exit(23)
        capability.generate = crash
    http = CandidateHttpHarness(path, initialize=False, capability=capability, tokens=settings['tokens'])
    print(json.dumps({'port': http.server.server_port}), flush=True)
    try:
        sys.stdin.readline()
    finally:
        http.close()
    print(json.dumps({'calls': len(capability.commands)}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--candidate-worker':
        _candidate_worker(sys.argv[2])
    else:
        unittest.main()
