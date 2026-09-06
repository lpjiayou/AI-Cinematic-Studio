"""Closed public M1 request/envelope contracts over the real HTTP handler."""

import copy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp.public_contract import PUBLIC_CONFIRM_PLAN_ENDPOINT
from tests.integration.test_creator_creative_plan_confirmation_idempotency_e3b import (
    ConfirmationHttpHarness,
    WORKSPACE,
)


class CreatorConfirmedPlanReplayContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.http = ConfirmationHttpHarness(Path(temporary.name) / "contract.sqlite3")
        self.addCleanup(self.http.close)
        self.command = self.http.command()

    def assert_invalid(self, command=None, *, raw=None, code="invalid_request"):
        before = self.http.rows()
        status, failure = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command, raw=raw)
        self.assertEqual(status, 400)
        self.assertEqual(set(failure), {"ok", "error"})
        self.assertIs(failure["ok"], False)
        self.assertEqual(set(failure["error"]), {"code", "message"})
        self.assertEqual(failure["error"]["code"], code)
        self.assertEqual(self.http.rows(), before)

    def test_two_exact_request_shapes_and_unchanged_confirmed_plan_fields(self):
        self.assertEqual(set(self.command), {
            "humanConfirmed", "brief", "plan", "sourcePlanRef", "sourcePlanVersion", "idempotencyKey",
        })
        expected_plan = {"schemaVersion", "workspaceRef", "creativePlanRef", "sourcePlanRef",
                         "sourcePlanSchemaVersion", "sourcePlanVersion", "brief", "sourcePlan",
                         "confirmationStatus", "confirmedAt", "version"}
        for explicit in (True, False):
            command = dict(self.command)
            if not explicit:
                del command["idempotencyKey"]
            for expected_status in (201, 200):
                status, response = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command)
                self.assertEqual(status, expected_status)
                self.assertEqual(set(response), {"ok", "confirmedPlan", "idempotentReplay"} if explicit else {"ok", "confirmedPlan"})
                self.assertEqual(set(response["confirmedPlan"]), expected_plan)
                self.assertEqual(response["confirmedPlan"]["workspaceRef"], WORKSPACE)
                self.assertEqual(response["confirmedPlan"]["schemaVersion"], "v5.confirmed-creative-plan.v1")
                if explicit:
                    self.assertIs(response["idempotentReplay"], expected_status == 200)

    def test_unknown_and_server_owned_fields_are_rejected_without_stripping(self):
        for field in ("workspaceRef", "creativePlanRef", "sourcePlanSchemaVersion", "confirmationStatus",
                      "confirmedAt", "version", "requestDigest", "idempotentReplay", "idempotencyMode", "unknownField"):
            with self.subTest(field=field):
                self.assert_invalid({**self.command, field: "client-claim"})

    def test_missing_required_fields_are_rejected(self):
        for field in set(self.command) - {"idempotencyKey"}:
            missing = dict(self.command)
            del missing[field]
            with self.subTest(field=field):
                self.assert_invalid(missing)

    def test_invalid_explicit_keys_are_never_coerced_or_treated_as_legacy(self):
        for key in (None, True, 9, 1.0, [], {}, "", " leading", "trailing ", ".", "..",
                    "a/b", "a\\b", "a\nb", "a\x00b", "a\x7fb", "x" * 201):
            with self.subTest(key_type=type(key).__name__):
                self.assert_invalid({**self.command, "idempotencyKey": key})

    def test_duplicate_json_fields_at_top_level_and_nested_in_plan_are_rejected(self):
        import json
        raw = json.dumps(self.command).encode()
        self.assert_invalid(raw=b'{"humanConfirmed":false,' + raw[1:])
        self.assert_invalid(raw=raw.replace(b'"shotNo": 1', b'"shotNo": 2, "shotNo": 1', 1))

    def test_strict_json_depth_numbers_and_positive_integer_contract_remain_enforced(self):
        for raw in (b'{"plan":NaN}', b'{"plan":Infinity}', b'{"plan":-Infinity}',
                    b'{"plan":1e999}', b'{"x":' + b'[' * 65 + b'0' + b']' * 65 + b'}',
                    b'{"x":' + b'1' * 129 + b'}'):
            self.assert_invalid(raw=raw)
        for version in (True, 1.0, 1.5, "1", None, 0, -1):
            with self.subTest(version=version):
                self.assert_invalid({**self.command, "sourcePlanVersion": version})

    def test_authentication_precedes_body_validation_and_confirmation_remains_explicit(self):
        status, failure = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, {}, token="unrecognized-test-token")
        self.assertEqual(status, 401)
        self.assertEqual(failure["error"]["code"], "authentication_required")
        for confirmed in (False, 1, "true", None):
            status, failure = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, {**self.command, "humanConfirmed": confirmed})
            self.assertEqual(status, 409)
            self.assertEqual(failure["error"]["code"], "creative_plan_not_confirmed")
        self.assertEqual(self.http.rows(), [])

    def test_conflict_is_stable_and_error_projection_contains_no_request_content(self):
        status, _first = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)
        self.assertEqual(status, 201)
        command = copy.deepcopy(self.command)
        command["brief"]["theme"] = "private-changed-theme"
        status, failure = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command)
        self.assertEqual(status, 409)
        self.assertEqual(set(failure), {"ok", "error"})
        self.assertEqual(failure["error"]["code"], "creative_plan_idempotency_conflict")
        for forbidden in (self.command["idempotencyKey"], command["brief"]["theme"],
                          self.command["sourcePlanRef"], "SQLite", "Traceback", str(self.http.path)):
            self.assertNotIn(forbidden, str(failure))
        self.assertEqual(len(self.http.rows()), 1)

    def test_raw_key_is_not_logged_on_success_replay_or_conflict(self):
        output = StringIO()
        changed = copy.deepcopy(self.command)
        changed["brief"]["theme"] = "different theme"
        with redirect_stdout(output), redirect_stderr(output):
            results = [self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, value)
                       for value in (self.command, self.command, changed)]
        self.assertEqual([status for status, _body in results], [201, 200, 409])
        self.assertNotIn(self.command["idempotencyKey"], output.getvalue())
        self.assertNotIn(self.http.tokens[0], output.getvalue())
