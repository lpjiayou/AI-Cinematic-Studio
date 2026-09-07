"""M5 recovery through authenticated HTTP, real LifecycleAssembly and SQLite."""

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
from types import SimpleNamespace
import unittest

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT as CONFIRM,
    PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT as GENERATE,
)
from apps.creator_workspace_mvp.series_director import SeriesDirectorApplicationService
from apps.creator_workspace_mvp.series_plan_candidate_receipts import create_local_development_receipt_service
from apps.creator_workspace_mvp.series_plan_candidate_commands import new_pending_command
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v5_core_os.text_generation import TextGenerationTimeoutError
from services.v5_core_os.series_planning.candidate_command_sqlite import seal_record
from dataclasses import replace
from tests.unit.test_project_foundation import valid_command as foundation_command
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE = "e3d-http-workspace"
FOREIGN_WORKSPACE = "e3d-http-foreign"
TABLE = "creator_series_plan_candidate_commands"

# CI discovery imports this file under a bare name; child interpreters need
# the stable package entrypoint from this checkout.
CHILD_MODULE = "tests.integration.test_creator_series_plan_idempotency_e3d"
REPO_ROOT = Path(__file__).resolve().parents[2]


class SeriesPlanHttpHarness:
    def __init__(self, path, *, initialize=True, capability=None, tokens=None):
        self.path = Path(path)
        self.tokens = tokens or (secrets.token_urlsafe(40), secrets.token_urlsafe(40))
        self.capability = capability if capability is not None else FakeTextGenerationCapability(
            [json.dumps(valid_candidate(), ensure_ascii=False)] * 50
        )
        auth = PublicApiAuthenticator.from_mapping({
            "schemaVersion": "creator.public-auth.v1",
            "credentials": [
                {"credentialRef": f"e3d-credential-{i}", "workspaceRef": workspace,
                 "tokenSha256": sha256(token.encode()).hexdigest(), "enabled": True}
                for i, (workspace, token) in enumerate(zip((WORKSPACE, FOREIGN_WORKSPACE), self.tokens))
            ],
        })
        self.assembly = LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=initialize)
        self.receipts = create_local_development_receipt_service(self.path)
        self.server = create_server(
            ("127.0.0.1", 0), AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_boundary=self.assembly.script_studio,
            series_director_service=SeriesDirectorApplicationService(self.capability),
            series_plan_candidate_receipt_service=self.receipts,
            public_authenticator=auth, allow_internal_routes=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(5)
            assert not self.thread.is_alive()
            self.server = None
            self.assembly = None

    def request(self, path, body=None, *, token=None, raw=None, method="POST"):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=15)
        data = raw if raw is not None else json.dumps(body, ensure_ascii=False).encode()
        try:
            client.request(method, path, data if method == "POST" else None, {
                "Content-Type": "application/json", "Authorization": "Bearer " + (token or self.tokens[0]),
            })
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def foundation(self, *, key="e3d-foundation", token=None):
        status, result = self.request(PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, foundation_command(key=key), token=token)
        assert status == 201, (status, result)
        value = result["foundation"]
        return {"projectRef": value["project"]["projectRef"], "seriesRef": value["series"]["seriesRef"]}

    def rows(self, table=TABLE):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                return []
            return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
        finally:
            connection.close()

    def schema(self):
        with sqlite3.connect(self.path) as connection:
            return connection.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall()


class SeriesPlanBaselineRegressionTests(unittest.TestCase):
    """Established before production edits; six recovery gates fail on 85ddf84."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "creator.sqlite3"
        self.http = SeriesPlanHttpHarness(self.path)
        self.addCleanup(lambda: self.http.close())
        self.scope = self.http.foundation()
        self.body = {**self.scope, "creativeInput": "E3D isolated creative input", "idempotencyKey": "e3d-generation"}

    def confirmation(self, *, keyed=True):
        legacy = {k: v for k, v in self.body.items() if k != "idempotencyKey"}
        status, result = self.http.request(GENERATE, legacy)
        self.assertEqual(status, 200)
        command = {**self.scope, "humanConfirmed": True, "candidateRef": result["candidateRef"], "candidate": result["candidate"]}
        if keyed:
            command["idempotencyKey"] = "e3d-confirmation"
        return command

    def test_keyed_generation_is_accepted(self):
        status, first = self.http.request(GENERATE, self.body)
        self.assertEqual(status, 200, first)
        self.assertFalse(first["idempotentReplay"])
        self.assertEqual(self.http.rows()[0]["state"], "COMPLETED")

    def test_generation_replay_reserves_once_and_calls_once(self):
        first = self.http.request(GENERATE, self.body)
        replay = self.http.request(GENERATE, self.body)
        self.assertEqual(len(self.http.capability.commands), 1, (first, replay))
        self.assertEqual(first[1]["candidateRef"], replay[1]["candidateRef"])
        self.assertTrue(replay[1]["idempotentReplay"])
        self.assertEqual(len(self.http.rows()), 1)
        changed = self.http.request(GENERATE, {**self.body, "creativeInput": "changed input"})
        self.assertEqual((changed[0], changed[1]["error"]["code"]), (409, "series_plan_candidate_idempotency_conflict"))
        self.e3d_evidence = {"candidateFirstStatus": first[0], "candidateReplayStatus": replay[0],
            "candidateChangedStatus": changed[0], "candidateChangedCode": changed[1]["error"]["code"],
            "firstCandidateRef": first[1]["candidateRef"], "replayCandidateRef": replay[1]["candidateRef"],
            "firstCandidateDigest": first[1]["candidateDigest"], "replayCandidateDigest": replay[1]["candidateDigest"],
            "candidateEqual": first[1]["candidate"] == replay[1]["candidate"],
            "logicalGenerationCount": len(self.http.capability.commands), "applicationRows": len(self.http.rows())}

    def test_generation_restart_replays_the_durable_candidate(self):
        first_status, first = self.http.request(GENERATE, self.body)
        tokens = self.http.tokens
        self.http.close()
        self.http = SeriesPlanHttpHarness(self.path, initialize=False, tokens=tokens)
        status, replay = self.http.request(GENERATE, self.body)
        self.assertEqual((first_status, status), (200, 200))
        self.assertEqual(first["candidateRef"], replay["candidateRef"])
        self.assertEqual(self.http.capability.commands, [])

    def test_keyed_confirmation_is_accepted(self):
        status, result = self.http.request(CONFIRM, self.confirmation())
        self.assertEqual(status, 201, result)
        self.assertFalse(result["idempotentReplay"])

    def test_confirmation_replay_preserves_original_plan_and_version(self):
        command = self.confirmation()
        first_status, first = self.http.request(CONFIRM, command)
        before = self.path.read_bytes()
        status, replay = self.http.request(CONFIRM, command)
        self.assertEqual((first_status, status), (201, 200))
        self.assertEqual(first["plan"], replay["plan"])
        self.assertEqual(first["version"], replay["version"])
        self.assertEqual(before, self.path.read_bytes())
        self.e3d_evidence = {"confirmationFirstStatus": first_status, "confirmationReplayStatus": status,
            "firstPlan": first["plan"], "replayPlan": replay["plan"],
            "firstVersionRef": first["version"]["seriesPlanVersionRef"], "replayVersionRef": replay["version"]["seriesPlanVersionRef"],
            "firstEpisodeItemRefs": [item["episodePlanItemRef"] for item in first["version"]["episodePlanItems"]],
            "replayEpisodeItemRefs": [item["episodePlanItemRef"] for item in replay["version"]["episodePlanItems"]],
            "versionEqual": first["version"] == replay["version"], "databaseBytesUnchanged": before == self.path.read_bytes()}

    def test_concurrent_confirmation_has_one_winner_and_one_replay(self):
        command = self.confirmation()
        barrier = threading.Barrier(2)

        def confirm():
            barrier.wait(5)
            return self.http.request(CONFIRM, command)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: confirm(), range(2)))
        self.assertEqual(sorted(status for status, _ in results), [200, 201])
        self.assertEqual(results[0][1]["plan"], results[1][1]["plan"])
        self.assertEqual(len(self.http.rows("v5_series_plans")), 1)

    def test_unkeyed_control_preserves_generation_and_duplicate_semantics(self):
        first_command = self.confirmation(keyed=False)
        second_command = self.confirmation(keyed=False)
        self.assertEqual(len(self.http.capability.commands), 2)
        self.assertEqual(first_command, second_command)
        self.assertEqual(len(self.http.rows("creator_series_plan_candidate_receipts")), 1)
        self.assertEqual(self.http.rows(), [])
        self.assertEqual(self.http.request(CONFIRM, first_command)[0], 201)
        status, result = self.http.request(CONFIRM, second_command)
        self.assertEqual((status, result["error"]["code"]), (409, "duplicate_record"))


class SeriesPlanRecoveryAndContractTests(unittest.TestCase):
    setUp = SeriesPlanBaselineRegressionTests.setUp
    confirmation = SeriesPlanBaselineRegressionTests.confirmation

    def keyed_candidate(self, **changes):
        status, result = self.http.request(GENERATE, {**self.body, **changes})
        self.assertEqual(status, 200, result)
        self.assertTrue(result["ok"], result)
        return result

    def confirm_body(self, candidate, *, scope=None, key="e3d-confirmation"):
        return {**(scope or self.scope), "humanConfirmed": True, "candidateRef": candidate["candidateRef"],
                "candidate": candidate["candidate"], "idempotencyKey": key}

    def assert_rejected_without_write(self, path, body, status, code, **kwargs):
        before = self.path.read_bytes()
        calls = len(self.http.capability.commands)
        actual, failure = self.http.request(path, body, **kwargs)
        self.assertEqual((actual, failure["error"]["code"]), (status, code))
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(calls, len(self.http.capability.commands))

    def test_closed_generation_and_confirmation_fields_keys_duplicates_and_nonfinite(self):
        command = {**self.scope, "humanConfirmed": True, "candidateRef": "unissued", "candidate": valid_candidate(), "idempotencyKey": "confirmation"}
        for path, body in ((GENERATE, self.body), (CONFIRM, command)):
            fields = ("workspaceRef", "sourceProjectVersion", "sourceSeriesVersion", "sourceContextDigest",
                      "candidateDigest", "seriesPlanRef", "seriesPlanVersionRef", "provider", "publicationAllowed", "unknown")
            for field in fields:
                with self.subTest(path=path, field=field):
                    self.assert_rejected_without_write(path, {**body, field: "forged"}, 400, "invalid_request")
            for key in (None, False, 7, [], {}, "", " x", "x ", ".", "..", "a/b", "a\\b", "x\x00y", "x" * 201):
                with self.subTest(path=path, key=repr(key)):
                    self.assert_rejected_without_write(path, {**body, "idempotencyKey": key}, 400, "invalid_request")
            raw = json.dumps(body)[:-1] + ',"idempotencyKey":"second"}'
            self.assert_rejected_without_write(path, None, 400, "invalid_request", raw=raw.encode())
            for nonfinite in ("NaN", "Infinity", "-Infinity"):
                raw = json.dumps(body).replace('"idempotencyKey": "' + body["idempotencyKey"] + '"', '"idempotencyKey": ' + nonfinite)
                self.assert_rejected_without_write(path, None, 400, "invalid_request", raw=raw.encode())
        self.assert_rejected_without_write(GENERATE, {**self.body, "candidateRef": "forged"}, 400, "invalid_request")
        self.assert_rejected_without_write(CONFIRM, {k: v for k, v in command.items() if k != "candidateRef"}, 400, "invalid_request")
        for invalid_ref in (None, "", False, 1, [], {}):
            self.assert_rejected_without_write(CONFIRM, {**command, "candidateRef": invalid_ref}, 400, "invalid_request")
        self.assertEqual(self.http.rows(), [])
        self.assertEqual(self.http.rows("v5_series_plans"), [])

    def test_all_accepted_generation_shapes_and_stable_keyed_envelope(self):
        legacy = {k: v for k, v in self.body.items() if k not in {"idempotencyKey", "seriesRef"}}
        for body in (legacy, {**legacy, "seriesRef": self.scope["seriesRef"]}):
            status, result = self.http.request(GENERATE, body)
            self.assertEqual(status, 200)
            self.assertEqual(set(result), {"ok", "kind", "confirmationRequired", "candidateRef", "candidateDigest", "sourceContextDigest",
                                          "candidateReceiptSchemaVersion", "candidateReceiptReplay", "candidate"})
            self.assertEqual(result["candidateReceiptSchemaVersion"], "creator.series-plan-candidate-receipt.v1")
        v1_rows = self.http.rows("creator_series_plan_candidate_receipts")
        first = self.keyed_candidate()
        self.assertEqual(first["candidateReceiptSchemaVersion"], "creator.series-plan-candidate-receipt.v2")
        self.assertFalse(first["candidateReceiptReplay"])
        self.assertFalse(first["idempotentReplay"])
        before = self.path.read_bytes()
        no_series = {k: v for k, v in self.body.items() if k != "seriesRef"}
        status, replay = self.http.request(GENERATE, no_series)
        self.assertEqual(status, 200)
        self.assertEqual(replay, {**first, "candidateReceiptReplay": True, "idempotentReplay": True})
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(self.http.rows("creator_series_plan_candidate_receipts"), v1_rows)
        self.assertEqual(len(self.http.capability.commands), 3)

    def test_changed_input_scope_source_and_workspace_isolation(self):
        first = self.keyed_candidate()
        other_scope = self.http.foundation(key="another-project")
        for changed in ({"creativeInput": "different input"}, other_scope):
            self.assert_rejected_without_write(GENERATE, {**self.body, **changed}, 409, "series_plan_candidate_idempotency_conflict")
        foreign_scope = self.http.foundation(key="foreign-project", token=self.http.tokens[1])
        status, foreign = self.http.request(GENERATE, {**self.body, **foreign_scope}, token=self.http.tokens[1])
        self.assertEqual(status, 200)
        self.assertNotEqual(first["candidateRef"], foreign["candidateRef"])
        self.http.assembly.project_context.archive_project(WORKSPACE, self.scope["projectRef"])
        self.assert_rejected_without_write(GENERATE, self.body, 409, "series_plan_candidate_idempotency_conflict")
        self.assert_rejected_without_write(CONFIRM, self.confirm_body(first), 409, "series_plan_candidate_stale")

    def test_pending_failed_commands_cannot_confirm_or_retry(self):
        from apps.creator_workspace_mvp.series_plan_candidate_receipts import build_series_plan_candidate_context
        context = build_series_plan_candidate_context(self.http.assembly.project_context.build_context(
            WORKSPACE, self.scope["projectRef"], self.scope["seriesRef"]))
        for state in ("PENDING", "FAILED"):
            key = "state-" + state
            pending = new_pending_command(context["sourceContext"], self.body["creativeInput"], key)
            store = self.http.receipts.commands.store
            store.reserve(pending)
            if state == "FAILED":
                store.finish(pending, seal_record(replace(pending, state="FAILED", failureCode="provider_timeout", completedAt=pending.createdAt)))
            body = {**self.body, "idempotencyKey": key}
            self.assert_rejected_without_write(GENERATE, body, 409 if state == "PENDING" else 200,
                                               "series_plan_candidate_generation_pending" if state == "PENDING" else "provider_timeout")
            self.assert_rejected_without_write(CONFIRM, {**self.scope, "humanConfirmed": True,
                "candidateRef": pending.candidateRef, "candidate": valid_candidate(), "idempotencyKey": "confirmation"},
                409, "series_plan_candidate_not_issued")
        self.assertEqual(len(self.http.capability.commands), 0)

    def test_real_generation_failure_is_durable_and_returns_identical_product_error(self):
        self.http.capability._outcomes = [TextGenerationTimeoutError()]
        status, first = self.http.request(GENERATE, self.body)
        self.assertEqual(status, 200)
        self.assertEqual(first["error"]["code"], "provider_timeout")
        before = self.path.read_bytes()
        self.assertEqual(self.http.request(GENERATE, self.body), (status, first))
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(len(self.http.capability.commands), 1)
        self.assertEqual(self.http.rows()[0]["state"], "FAILED")

    def test_unified_resolver_rejects_ambiguity_and_supports_v2_without_candidate_ref(self):
        candidate = self.keyed_candidate()
        body = self.confirm_body(candidate)
        legacy = {k: v for k, v in body.items() if k not in {"candidateRef", "idempotencyKey"}}
        legacy_generation = {k: v for k, v in self.body.items() if k != "idempotencyKey"}
        self.http.request(GENERATE, legacy_generation)
        self.assert_rejected_without_write(CONFIRM, legacy, 409, "series_plan_candidate_receipt_ambiguous")
        self.assertEqual(self.http.request(CONFIRM, body)[0], 201)
        other_scope = self.http.foundation(key="v2-compatibility")
        candidate = self.keyed_candidate(**other_scope, idempotencyKey="v2-compatible")
        legacy = {**other_scope, "humanConfirmed": True, "candidate": candidate["candidate"]}
        self.assertEqual(self.http.request(CONFIRM, legacy)[0], 201)

    def test_validation_precedes_confirmation_identity_and_never_mutates(self):
        candidate = self.keyed_candidate()
        command = self.confirm_body(candidate)
        self.assertEqual(self.http.request(CONFIRM, command)[0], 201)
        malformed = {**command, "candidateRef": "unknown", "candidate": {}}
        self.assert_rejected_without_write(CONFIRM, malformed, 409, "series_plan_candidate_not_issued")
        changed = copy.deepcopy(command)
        changed["candidate"]["premise"] = "forged content"
        self.assert_rejected_without_write(CONFIRM, changed, 409, "series_plan_candidate_content_mismatch")
        self.assert_rejected_without_write(CONFIRM, {**command, "candidate": {}}, 409, "series_plan_candidate_content_mismatch")
        foreign_scope = self.http.foundation(key="foreign", token=self.http.tokens[1])
        self.assert_rejected_without_write(CONFIRM, {**command, **foreign_scope}, 409, "series_plan_candidate_not_issued", token=self.http.tokens[1])
        other_scope = self.http.foundation(key="other-scope")
        self.assert_rejected_without_write(CONFIRM, {**command, **other_scope}, 409, "series_plan_candidate_scope_mismatch")
        other = self.keyed_candidate(idempotencyKey="second-issued-candidate")
        self.assert_rejected_without_write(CONFIRM, self.confirm_body(other), 409, "series_plan_confirmation_idempotency_conflict")
        other = self.keyed_candidate(**other_scope, idempotencyKey="other-scope-candidate")
        self.assert_rejected_without_write(CONFIRM, self.confirm_body(other, scope=other_scope), 409, "series_plan_confirmation_idempotency_conflict")
        self.assert_rejected_without_write(CONFIRM, {**command, "idempotencyKey": "other-confirmation"}, 409, "duplicate_record")

    def test_independent_compositions_share_reservation_with_no_transaction_across_generation(self):
        entered, release = threading.Event(), threading.Event()
        original = self.http.capability.generate
        observed = []
        def generation(command):
            with sqlite3.connect(self.path, timeout=0.2) as connection:
                connection.execute("BEGIN IMMEDIATE")
                observed.append(connection.execute(f"SELECT state FROM {TABLE}").fetchone()[0])
            entered.set()
            if not release.wait(10):
                raise AssertionError("generation release timed out")
            return original(command)
        self.http.capability.generate = generation
        other = SeriesPlanHttpHarness(self.path, initialize=False, tokens=self.http.tokens)
        self.addCleanup(other.close)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.http.request, GENERATE, self.body)
            try:
                self.assertTrue(entered.wait(5))
                before = self.path.read_bytes()
                status, pending = other.request(GENERATE, self.body)
                self.assertEqual((status, pending["error"]["code"]), (409, "series_plan_candidate_generation_pending"))
                status, conflict = other.request(GENERATE, {**self.body, "creativeInput": "changed"})
                self.assertEqual((status, conflict["error"]["code"]), (409, "series_plan_candidate_idempotency_conflict"))
                self.assertEqual(before, self.path.read_bytes())
            finally:
                release.set()
            first_status, first = future.result(10)
        self.assertEqual(first_status, 200)
        self.assertTrue(first["ok"])
        self.assertEqual(observed, ["PENDING"])
        self.assertEqual(len(self.http.capability.commands), 1)
        self.assertEqual(other.capability.commands, [])
        self.assertEqual(other.request(GENERATE, self.body)[1]["candidateRef"], first["candidateRef"])
        self.assertEqual(len(self.http.rows()), 1)

    def test_independent_confirmation_races_return_replay_or_conflict(self):
        first = self.keyed_candidate()
        second = self.keyed_candidate(idempotencyKey="second-generation")
        other = SeriesPlanHttpHarness(self.path, initialize=False, tokens=self.http.tokens)
        self.addCleanup(other.close)
        barrier = threading.Barrier(2)
        def confirm(pair):
            http, candidate = pair
            barrier.wait(5)
            return http.request(CONFIRM, self.confirm_body(candidate))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(confirm, [(self.http, first), (other, second)]))
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual([result["error"]["code"] for status, result in results if status == 409], ["series_plan_confirmation_idempotency_conflict"])
        winner = first if results[0][0] == 201 else second
        before = self.path.read_bytes()
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replay = list(pool.map(confirm, [(self.http, winner), (other, winner)]))
        self.assertEqual([status for status, _ in replay], [200, 200])
        self.assertEqual(replay[0][1], replay[1][1])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(len(self.http.rows("v5_series_plans")), 1)
        self.assertEqual(len(self.http.rows("v5_series_plan_versions")), 1)
        with sqlite3.connect(self.path, timeout=0.2) as connection:
            connection.execute("BEGIN IMMEDIATE")

    def test_response_loss_recovers_candidate_and_confirmation_from_sqlite(self):
        def lose_response(path, body, expected):
            client = http.client.HTTPConnection("127.0.0.1", self.http.server.server_port, timeout=10)
            try:
                client.request("POST", path, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + self.http.tokens[0]})
                response = client.getresponse()
                self.assertEqual(response.status, expected)
                response.close()
            finally:
                client.close()
        lose_response(GENERATE, self.body, 200)
        before = self.path.read_bytes()
        candidate = self.keyed_candidate()
        self.assertTrue(candidate["idempotentReplay"])
        self.assertEqual(before, self.path.read_bytes())
        command = self.confirm_body(candidate)
        lose_response(CONFIRM, command, 201)
        before = self.path.read_bytes()
        status, replay = self.http.request(CONFIRM, command)
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(len(self.http.capability.commands), 1)

    def test_runtime_command_corruption_returns_503_without_generation_or_domain_writes(self):
        candidate = self.keyed_candidate()
        with sqlite3.connect(self.path) as connection:
            connection.execute(f"UPDATE {TABLE} SET row_digest=?", ("f" * 64,))
        self.assert_rejected_without_write(GENERATE, self.body, 503, "series_plan_candidate_command_unavailable")
        self.assert_rejected_without_write(CONFIRM, self.confirm_body(candidate), 503, "series_plan_candidate_command_unavailable")
        self.assertEqual(self.http.rows("v5_series_plans"), [])


class FreshProcessHttp:
    request = SeriesPlanHttpHarness.request

    def __init__(self, path, tokens, *, crash=False):
        self.tokens = tokens
        self.process = subprocess.Popen(
            [sys.executable, "-m", CHILD_MODULE, "--http-child", str(Path(path).resolve())],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.process.stdin.write(json.dumps({"tokens": tokens, "crash": crash}) + "\n")
        self.process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(15):
                self.process.kill()
                self.process.communicate()
                raise AssertionError("child HTTP startup timed out")
        ready = self.process.stdout.readline()
        if not ready:
            _, stderr = self.process.communicate(timeout=5)
            raise AssertionError("child HTTP startup failed: " + stderr)
        self.server = SimpleNamespace(server_port=json.loads(ready)["port"])
        self.stats = None

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write("stop\n")
            self.process.stdin.flush()
        try:
            output, stderr = self.process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate()
            raise AssertionError("child HTTP shutdown timed out")
        if output.strip():
            self.stats = json.loads(output.strip().splitlines()[-1])
        if self.process.returncode not in (0, 23):
            raise AssertionError("child HTTP failed: " + stderr)


class FreshProcessSeriesPlanTests(unittest.TestCase):
    setUp = SeriesPlanBaselineRegressionTests.setUp

    def test_new_python_process_replays_completed_candidate_and_confirmed_root(self):
        status, candidate = self.http.request(GENERATE, self.body)
        self.assertEqual(status, 200)
        command = {**self.scope, "candidateRef": candidate["candidateRef"], "candidate": candidate["candidate"],
                   "humanConfirmed": True, "idempotencyKey": "fresh-process-confirmation"}
        status, confirmed = self.http.request(CONFIRM, command)
        self.assertEqual(status, 201)
        tokens = self.http.tokens
        self.http.close()
        before = self.path.read_bytes()
        child = FreshProcessHttp(self.path, tokens)
        try:
            status, replay = child.request(GENERATE, self.body)
            self.assertEqual(status, 200)
            self.assertEqual(replay, {**candidate, "idempotentReplay": True, "candidateReceiptReplay": True})
            status, replay = child.request(CONFIRM, command)
            self.assertEqual((status, replay), (200, {**confirmed, "idempotentReplay": True}))
        finally:
            child.close()
        self.assertEqual(child.stats["calls"], 0)
        self.assertEqual(before, self.path.read_bytes())

    def test_process_death_after_reservation_never_reissues_pending_generation(self):
        tokens = self.http.tokens
        self.http.close()
        child = FreshProcessHttp(self.path, tokens, crash=True)
        try:
            with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
                child.request(GENERATE, self.body)
            self.assertEqual(child.process.wait(timeout=5), 23)
        finally:
            child.close()
        rows = self.http.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "PENDING")
        before = self.path.read_bytes()
        restarted = FreshProcessHttp(self.path, tokens)
        try:
            status, result = restarted.request(GENERATE, self.body)
            self.assertEqual((status, result["error"]["code"]), (409, "series_plan_candidate_generation_pending"))
        finally:
            restarted.close()
        self.assertEqual(restarted.stats["calls"], 0)
        self.assertEqual(before, self.path.read_bytes())


def _http_child(path):
    config = json.loads(sys.stdin.readline())
    class Capability(FakeTextGenerationCapability):
        def generate(self, command):
            if config["crash"]:
                os._exit(23)
            return super().generate(command)
    capability = Capability([])
    http = SeriesPlanHttpHarness(Path(path), initialize=False, tokens=config["tokens"], capability=capability)
    print(json.dumps({"port": http.server.server_port}), flush=True)
    try:
        sys.stdin.readline()
    finally:
        http.close()
    print(json.dumps({"calls": len(capability.commands)}), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--http-child":
        _http_child(sys.argv[2])
    else:
        unittest.main()
