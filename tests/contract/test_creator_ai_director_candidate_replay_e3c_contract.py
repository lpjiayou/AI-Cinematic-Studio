"""Closed public request and stable candidate response contract over HTTP."""

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tests.integration.test_creator_ai_director_candidate_idempotency_e3c import CandidateHttpHarness
from tests.unit.test_ai_director_phase1 import valid_brief


class AiDirectorCandidatePublicContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.http = CandidateHttpHarness(Path(temporary.name) / 'creator.sqlite3')
        self.addCleanup(self.http.close)

    def assert_rejected(self, body=None, raw=None, code='invalid_request'):
        before = self.http.path.read_bytes()
        status, result = self.http.request(body=body, raw=raw)
        self.assertEqual((status, result['error']['code']), (400, code))
        self.assertEqual(self.http.path.read_bytes(), before)
        self.assertEqual(self.http.rows(), [])
        self.assertEqual(self.http.capability.commands, [])

    def test_only_two_closed_top_level_shapes_are_accepted(self):
        for field in ['workspaceRef', 'sourcePlanRef', 'sourcePlanVersion', 'candidateDigest',
                      'planDigest', 'briefDigest', 'plan', 'provider', 'unknownField']:
            with self.subTest(field=field):
                self.assert_rejected({'brief': valid_brief(), field: 'forbidden'})
        self.assert_rejected({})
        self.assert_rejected({'idempotencyKey': 'key'})

    def test_invalid_keys_are_never_coerced_trimmed_echoed_or_stored(self):
        for key in [None, True, 1, {}, [], '', ' leading', 'trailing ', 'line\nfeed',
                    'control\x00', 'hidden\u200b', 'path/key', 'path\\key', '.', '..', 'x' * 201]:
            with self.subTest(key=repr(key)):
                self.assert_rejected({'brief': valid_brief(), 'idempotencyKey': key})

    def test_duplicate_keys_and_nonfinite_depth_and_numeric_bounds_remain_strict(self):
        brief = json.dumps(valid_brief())
        raw_values = [
            '{"brief":' + brief + ',"brief":' + brief + '}',
            '{"brief":' + brief.replace('"theme":', '"theme":"duplicate","theme":') + '}',
            *['{"brief":' + brief + ',"idempotencyKey":' + value + '}' for value in ('NaN', 'Infinity', '-Infinity', '1e9999', '1' * 5000)],
            '{"brief":' + '[' * 100 + '0' + ']' * 100 + '}',
        ]
        for raw in raw_values:
            with self.subTest(raw=raw[:100]):
                self.assert_rejected(raw=raw.encode())

    def test_invalid_brief_has_zero_command_and_generation_effects(self):
        self.assert_rejected({'brief': {}, 'idempotencyKey': 'valid-key'}, code='invalid_brief')

    def test_keyed_envelope_stable_payload_and_raw_key_absence(self):
        key = 'NONPERSISTED-CANDIDATE-KEY-' + 'k' * 100
        body = {'brief': valid_brief(), 'idempotencyKey': key}
        responses = [self.http.request(body=body) for _ in range(2)]
        required = {'ok', 'kind', 'confirmationRequired', 'sourcePlanRef', 'sourcePlanVersion',
                    'candidateDigest', 'candidateReceiptSchemaVersion', 'idempotentReplay', 'plan'}
        for index, (status, result) in enumerate(responses):
            self.assertEqual(status, 200)
            self.assertEqual(set(result), required)
            self.assertEqual(result['candidateReceiptSchemaVersion'], 'creator.ai-director-candidate-receipt.v1')
            self.assertRegex(result['candidateDigest'], r'^[0-9a-f]{64}$')
            self.assertRegex(result['sourcePlanRef'], r'^ai-director-candidate-[0-9a-f]{64}$')
            self.assertEqual(result['idempotentReplay'], bool(index))
            self.assertNotIn(key, json.dumps(result))
        for row in self.http.rows():
            for value in row.values():
                if isinstance(value, str):
                    self.assertNotIn(key, value)
        self.assertNotIn(key.encode(), self.http.path.read_bytes())

    def test_raw_candidate_key_and_bearer_are_not_logged_on_replay_or_conflict(self):
        output = StringIO()
        key = 'CANDIDATE-NONLOGGED-KEY'
        body = {'brief': valid_brief(), 'idempotencyKey': key}
        changed = {**body, 'brief': {**valid_brief(), 'theme': 'private changed input'}}
        with redirect_stdout(output), redirect_stderr(output):
            results = [self.http.request(body=value) for value in (body, body, changed)]
        self.assertEqual([status for status, _ in results], [200, 200, 409])
        self.assertNotIn(key, output.getvalue())
        self.assertNotIn(self.http.tokens[0], output.getvalue())
        self.assertNotIn('private changed input', output.getvalue())


if __name__ == '__main__':
    unittest.main()
