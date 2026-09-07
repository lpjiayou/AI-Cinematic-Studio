"""Authenticated HTTP/SQLite recovery, using independent disposable fixtures."""

import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import http.client
from hashlib import sha256
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
from unittest.mock import patch
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.script_studio import ScriptStudioApplicationService
from apps.creator_workspace_mvp.server import create_server
from apps.creator_workspace_mvp.server import CreatorRequestHandler
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.script_studio import ScriptStudioPublicBoundary, ScriptStudioPublicError
from services.v5_core_os.script_studio.generation_recovery import GenerationStorageError
from services.v5_core_os.script_studio.generation_recovery_sqlite import SqliteGenerationStore, TABLE
from services.v5_core_os.text_generation import TextGenerationTimeoutError, TextGenerationUnavailableError
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_script_studio_m3 import script_candidate, seed_episode, WORKSPACE
from tests.unit.test_series_intelligence_consumer_m6_p3 import seed_consumer_on
from tests.unit.test_series_intelligence_m6 import ScopeAuthority, ApprovalAuthority
from tests.unit.test_script_generation_recovery_e3f import snapshot, rows
from services.v5_core_os.episode_production import create_local_development_boundary as create_production
from tests.integration.test_creator_m5_m7_entrypoints_e3e_http import identity_authority
from tests.unit.test_script_acceptance import ExactAcceptanceAuthority


REPO = Path(__file__).resolve().parents[2]
GENERATE = "/creator/api/v1/script-versions/generate"
CONFIRM = "/creator/api/v1/script-versions/confirm"
CHILD_MODULE = "tests.integration.test_creator_script_recovery_e3f_http"


class ScriptRecoveryHttpTests(unittest.TestCase):
    def start(self, *, bound=False, production=False):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "creator.sqlite3"
        self.assembly = LifecycleAssembly.sqlite(
            self.database, initialize_or_upgrade=True,
            m6_scope_authority=ScopeAuthority(), m6_approval_authority=ApprovalAuthority(),
            script_acceptance_authority=ExactAcceptanceAuthority())
        if bound:
            create_project = self.assembly.project_context.create_project
            with patch.object(self.assembly.project_context, "create_project", side_effect=lambda value:
                              create_project({**value, "aspectRatio": "16:9"} if production else value)):
                self.seed = seed_consumer_on(self.assembly, workspace=WORKSPACE, plan_index=0 if production else 1)
            self.scope = self.seed["context"]
        else:
            series, episode = seed_episode(self.assembly.series_episode)
            self.scope = {"workspaceRef": WORKSPACE, "seriesRef": series["seriesRef"],
                          "episodeRef": episode["episodeRef"]}
        self.token = secrets.token_urlsafe(48)
        self.foreign_token = secrets.token_urlsafe(48)
        auth = PublicApiAuthenticator.from_mapping({"schemaVersion": "creator.public-auth.v1",
            "credentials": [{"credentialRef": "e3f-test-" + workspace, "workspaceRef": workspace,
                "tokenSha256": sha256(token.encode()).hexdigest(), "enabled": True}
                for workspace, token in ((WORKSPACE, self.token), ("foreign-workspace", self.foreign_token))]})
        candidate = script_candidate()
        if production:
            candidate["scenes"][0]["characters"].append("旅人")
            candidate["scenes"][0]["action"] += "旅人走进房间。"
        self.capability = FakeTextGenerationCapability([json.dumps(candidate, ensure_ascii=False) for _ in range(4)])
        self.production = create_production(Path(self.temp.name) / "production.sqlite3",
            project_boundary=self.assembly.project_context, series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning, script_studio_boundary=self.assembly.script_studio,
            initialize_if_missing=True, identity_reference_authority=identity_authority()) if production else None
        self.server = create_server(("127.0.0.1", 0), AiDirectorService(self.capability),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            script_studio_service=ScriptStudioApplicationService(self.capability),
            episode_production_boundary=self.production,
            public_authenticator=auth, allow_internal_routes=False)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.addCleanup(self.stop)
        self.body = {k: v for k, v in self.scope.items() if k != "workspaceRef"}

    def stop(self):
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())
        self.token = None
        self.foreign_token = None
        self.server = None

    def post(self, path, body, *, token=None, raw=None):
        req = request.Request(f"http://127.0.0.1:{self.server.server_port}{path}", method="POST",
            data=raw if raw is not None else json.dumps(body).encode(), headers={"Content-Type": "application/json",
                "Authorization": "Bearer " + (token or self.token)})
        try:
            response = request.urlopen(req, timeout=15)
        except error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def generation_counterexample(self, bound):
        self.start(bound=bound)
        status, first = self.post(GENERATE, self.body)
        self.assertEqual(201, status, first)
        self.assertEqual("creator.script-studio.script-version.v2" if bound else
                         "creator.script-studio.script-version.v1", first["scriptVersion"]["schemaVersion"])
        calls = len(self.capability.commands)
        status, _ = self.post(GENERATE, self.body)
        self.assertGreaterEqual(status, 400)
        self.assertEqual(calls, len(self.capability.commands),
                         "original counterexample: extra generation before existing Script rejection")

    def confirmation_counterexample(self, bound):
        self.start(bound=bound)
        status, first = self.post(GENERATE, self.body)
        self.assertEqual(201, status, first)
        command = {**self.body, "scriptRef": first["script"]["scriptRef"],
                   "scriptVersionRef": first["scriptVersion"]["scriptVersionRef"], "humanConfirmed": True}
        status, confirmed = self.post(CONFIRM, command)
        self.assertEqual(201, status, confirmed)
        status, repeated = self.post(CONFIRM, command)
        self.assertEqual(confirmed["script"], repeated["script"],
                         "original counterexample: repeated confirmation advances root metadata")
        self.assertEqual(200, status)
        self.assertEqual(confirmed["confirmedVersion"], repeated["confirmedVersion"])

    def test_original_generate_v1_counterexample(self):
        self.generation_counterexample(False)

    def test_original_generate_v2_counterexample(self):
        self.generation_counterexample(True)

    def test_original_confirm_v1_counterexample(self):
        self.confirmation_counterexample(False)

    def test_original_confirm_v2_counterexample(self):
        self.confirmation_counterexample(True)

    def read(self):
        return self.assembly.script_studio.get_workspace(WORKSPACE, self.scope["seriesRef"], self.scope["episodeRef"])

    def confirm_body(self, generated):
        return {**self.body, "scriptRef": generated["script"]["scriptRef"],
                "scriptVersionRef": generated["scriptVersion"]["scriptVersionRef"], "humanConfirmed": True}

    def append(self, generated):
        content = {k: deepcopy(generated["scriptVersion"][k]) for k in
                   ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
        content["synopsis"] += " A new immutable draft."
        return self.assembly.script_studio.create_version({**self.scope,
            "scriptRef": generated["script"]["scriptRef"],
            "baseScriptVersionRef": generated["scriptVersion"]["scriptVersionRef"],
            "changeKind": "manual-edit", "content": content})

    def test_keyed_first_exact_replay_changed_scope_and_original_payload_after_edits(self):
        for bound in (False, True):
            with self.subTest(bound=bound):
                self.start(bound=bound)
                try:
                    body = {**self.body, "idempotencyKey": "keyed-original-payload"}
                    status, first = self.post(GENERATE, body)
                    self.assertEqual(201, status, first)
                    self.assertFalse(first["idempotentReplay"])
                    before = snapshot(self.database)
                    status, replay = self.post(GENERATE, body)
                    self.assertEqual(200, status, replay)
                    self.assertTrue(replay["idempotentReplay"])
                    for k in ("script", "scriptVersion"):
                        self.assertEqual(first[k], replay[k])
                    self.assertEqual(before, snapshot(self.database))
                    if bound:
                        changed = {k: v for k, v in body.items() if k != "projectRef"}
                    else:
                        _, episode = seed_episode(self.assembly.series_episode)
                        changed = {**body, "seriesRef": episode["seriesRef"], "episodeRef": episode["episodeRef"]}
                    before = snapshot(self.database)
                    status, conflict = self.post(GENERATE, changed)
                    self.assertEqual((409, "idempotency_conflict"), (status, conflict["error"]["code"]))
                    self.assertEqual(before, snapshot(self.database))
                    self.post(CONFIRM, self.confirm_body(first))
                    self.append(first)
                    before = snapshot(self.database)
                    status, replay = self.post(GENERATE, body)
                    self.assertEqual(200, status, replay)
                    self.assertEqual(first["script"], replay["script"])
                    self.assertEqual(3, self.read()["script"]["version"])
                    self.assertEqual(before, snapshot(self.database))
                    self.assertEqual(1, len(self.capability.commands))
                    self.assertNotIn(body["idempotencyKey"].encode(), self.database.read_bytes())
                    restarted = LifecycleAssembly.sqlite(self.database, m6_scope_authority=ScopeAuthority(),
                                                        m6_approval_authority=ApprovalAuthority())
                    self.assertEqual("COMPLETED", restarted.script_studio.reserve_generation(
                        {**self.scope, "idempotencyKey": body["idempotencyKey"]})["state"])
                finally:
                    self.stop()

    def test_closed_generation_and_confirmation_dtos_auth_scope_and_strict_keys(self):
        self.start()
        before = snapshot(self.database)
        for field in ("prompt", "model", "provider", "content", "scriptRef", "m6ConsumerBinding",
                      "payloadDigest", "authority", "result", "workspaceRef"):
            self.assertEqual(400, self.post(GENERATE, {**self.body, field: "forbidden"})[0], field)
        for key in (None, True, 1.0, "", " leading", "trailing ", "a/b", "a\\b", ".", "..", "a\n", "x" * 201):
            self.assertEqual(400, self.post(GENERATE, {**self.body, "idempotencyKey": key})[0])
        raw = json.dumps(self.body)[:-1] + ',"episodeRef":"duplicate"}'
        self.assertEqual(400, self.post(GENERATE, {}, raw=raw.encode())[0])
        self.assertEqual(400, self.post(GENERATE, {}, raw=b'{"seriesRef":NaN,"episodeRef":"x"}')[0])
        self.assertEqual(400, self.post(GENERATE + "?extra=1", self.body)[0])
        self.assertEqual(401, self.post(GENERATE, self.body, token="unknown-credential")[0])
        self.assertEqual(404, self.post(GENERATE, self.body, token=self.foreign_token)[0])
        self.assertEqual(0, len(self.capability.commands))
        self.assertEqual(before, snapshot(self.database))
        _, first = self.post(GENERATE, self.body)
        command = self.confirm_body(first)
        before = snapshot(self.database)
        for expected in (None, True, False, 1.0, "1", 0, -1):
            self.assertEqual(400, self.post(CONFIRM, {**command, "expectedScriptVersion": expected})[0])
        for field in ("idempotencyKey", "approvalRef", "m6ConsumerBinding", "confirmedVersion", "content", "workspaceRef"):
            self.assertEqual(400, self.post(CONFIRM, {**command, field: "forbidden"})[0])
        self.assertEqual(400, self.post(CONFIRM + "?extra=1", command)[0])
        self.assertEqual(404, self.post(CONFIRM, command, token=self.foreign_token)[0])
        self.assertEqual(400, self.post(CONFIRM, {}, raw=(json.dumps(command)[:-1] + ',"humanConfirmed":true}').encode())[0])
        self.assertEqual(before, snapshot(self.database))

    def test_provider_uncertainty_never_resubmits_and_known_invalid_output_is_terminal(self):
        for outcome in (TextGenerationTimeoutError(), TextGenerationUnavailableError(), "invalid"):
            with self.subTest(outcome=type(outcome).__name__):
                self.start()
                try:
                    self.capability._outcomes = (["{}", "{}"] if outcome == "invalid" else [outcome])
                    body = {**self.body, "idempotencyKey": "provider-case"}
                    status, first = self.post(GENERATE, body)
                    self.assertEqual(409 if outcome == "invalid" else 200, status, first)
                    calls = len(self.capability.commands)
                    state = json.loads(rows(self.database, TABLE)[0][5])["state"]
                    self.assertEqual("FAILED" if outcome == "invalid" else "PENDING", state)
                    before = snapshot(self.database)
                    status, retry = self.post(GENERATE, body)
                    self.assertEqual(409, status)
                    self.assertEqual("invalid_provider_output" if outcome == "invalid" else "script_generation_pending",
                                     retry["error"]["code"])
                    self.assertEqual(calls, len(self.capability.commands))
                    self.assertEqual(before, snapshot(self.database))
                    self.assertEqual([], self.read()["versions"])
                    if outcome == "invalid":
                        self.capability._outcomes = [json.dumps(script_candidate())]
                        self.assertEqual(201, self.post(GENERATE, {**self.body, "idempotencyKey": "known-new-attempt"})[0])
                        self.assertEqual(calls + 1, len(self.capability.commands))
                    else:
                        self.assertEqual(409, self.post(GENERATE, {**self.body, "idempotencyKey": "cannot-bypass"})[0])
                        self.assertEqual(409, self.post(GENERATE, self.body)[0])
                        self.assertEqual(calls, len(self.capability.commands))
                finally:
                    self.stop()

    def test_storage_unavailable_prevents_text_and_lost_result_stays_pending(self):
        self.start()
        before = snapshot(self.database)
        with patch.object(SqliteGenerationStore, "save", side_effect=GenerationStorageError()):
            status, failure = self.post(GENERATE, {**self.body, "idempotencyKey": "storage"})
        self.assertEqual((503, "script_generation_storage_unavailable"), (status, failure["error"]["code"]))
        self.assertEqual(before, snapshot(self.database))
        self.assertEqual(0, len(self.capability.commands))
        save = SqliteGenerationStore.save

        def lose_result(store, record):
            if record["state"] == "RESULT_READY":
                raise GenerationStorageError()
            return save(store, record)

        with patch.object(SqliteGenerationStore, "save", lose_result):
            self.assertEqual(503, self.post(GENERATE, {**self.body, "idempotencyKey": "storage"})[0])
        self.assertEqual(1, len(self.capability.commands))
        self.assertEqual("PENDING", json.loads(rows(self.database, TABLE)[0][5])["state"])
        self.assertEqual(409, self.post(GENERATE, {**self.body, "idempotencyKey": "storage"})[0])
        self.assertEqual(1, len(self.capability.commands))

    def test_manual_import_winner_during_generation_is_preserved(self):
        self.start()
        generate = self.capability.generate
        winner = []

        def competing(command):
            # The existing legal initial import path wins while no Lifecycle lock
            # spans generation. It is not modified by this task.
            status, imported = self.post("/creator/api/v1/script-versions/reviewed-import", {
                **self.body, "uploadedSourceByteDigest": "a" * 64,
                "normalizedSourceDocumentDigest": "b" * 64, "reviewedDocumentDigest": "c" * 64,
                "content": {k: script_candidate()[k] for k in
                            ("title", "logline", "synopsis", "targetDurationSec", "scenes")}})
            self.assertEqual(201, status, imported)
            winner.append(imported)
            return generate(command)

        with patch.object(self.capability, "generate", side_effect=competing):
            status, conflict = self.post(GENERATE, {**self.body, "idempotencyKey": "competing-import"})
        self.assertEqual((409, "script_already_exists"), (status, conflict["error"]["code"]))
        self.assertEqual(1, len(self.capability.commands))
        self.assertEqual([winner[0]["scriptVersion"]], self.read()["versions"])
        self.assertEqual(winner[0]["script"], self.read()["script"])
        self.assertEqual("RESULT_READY", json.loads(rows(self.database, TABLE)[0][5])["state"])

    def test_confirmation_cas_and_same_target_concurrency(self):
        for bound in (False, True):
            with self.subTest(bound=bound):
                self.start(bound=bound)
                try:
                    _, first = self.post(GENERATE, self.body)
                    confirm = {**self.confirm_body(first), "expectedScriptVersion": 1}
                    with ThreadPoolExecutor(2) as pool:
                        results = list(pool.map(lambda _: self.post(CONFIRM, confirm), range(2)))
                    self.assertEqual([200, 201], sorted(r[0] for r in results), results)
                    self.assertEqual(2, self.read()["script"]["version"])
                    before = snapshot(self.database)
                    self.assertEqual(200, self.post(CONFIRM, confirm)[0])
                    self.assertEqual(before, snapshot(self.database))
                    second = self.append(first)
                    third = self.append(second)
                    target_b, target_c = self.confirm_body(second), self.confirm_body(third)
                    expected = self.read()["script"]["version"]
                    barrier = threading.Barrier(2)

                    def switch(body):
                        barrier.wait(10)
                        return self.post(CONFIRM, {**body, "expectedScriptVersion": expected})

                    with ThreadPoolExecutor(2) as pool:
                        results = list(pool.map(switch, (target_b, target_c)))
                    self.assertEqual([201, 409], sorted(r[0] for r in results), results)
                    winner = next(r[1] for r in results if r[0] == 201)
                    self.assertEqual("version_conflict", next(r[1]["error"]["code"] for r in results if r[0] == 409))
                    before = snapshot(self.database)
                    for old in (self.confirm_body(first), confirm):
                        self.assertEqual(409, self.post(CONFIRM, old)[0])
                    self.assertEqual(before, snapshot(self.database))
                    self.assertEqual(winner["script"], self.read()["script"])
                finally:
                    self.stop()

    def test_new_interpreter_crash_windows_preserve_durable_calls_and_atomicity(self):
        cases = (("reservation", 0, "PENDING", 0), ("capability", 1, "PENDING", 0),
                 ("returned", 1, "PENDING", 0), ("result-ready", 1, "RESULT_READY", 0),
                 ("transaction", 1, "RESULT_READY", 0), ("response", 1, "COMPLETED", 1))
        for bound in (False, True):
            for fault, calls, expected_state, scripts in cases:
                with self.subTest(bound=bound, fault=fault):
                    self.start(bound=bound)
                    self.stop()
                    body = {**self.body, "idempotencyKey": "crash-recovery"}
                    counter = Path(self.temp.name) / "calls.jsonl"
                    child = ChildRuntime(self.database, counter, fault=fault)
                    self.addCleanup(child.close)
                    with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
                        child.post(GENERATE, body)
                    self.assertEqual(70, child.process.wait(timeout=15))
                    child.close()
                    self.assertEqual(calls, call_count(counter))
                    self.assertEqual(expected_state, json.loads(rows(self.database, TABLE)[0][5])["state"])
                    self.assertEqual(scripts, len(rows(self.database, "v5_scripts")))
                    self.assertEqual(scripts, len(rows(self.database, "v5_script_versions")))
                    # The transaction fault exited after the actual domain insert;
                    # reopening SQLite rolls it back, without test cleanup SQL.
                    restarted = ChildRuntime(self.database, counter)
                    self.addCleanup(restarted.close)
                    before = snapshot(self.database)
                    status, recovered = restarted.post(GENERATE, body)
                    if expected_state == "PENDING":
                        self.assertEqual((409, "script_generation_pending"), (status, recovered["error"]["code"]))
                        self.assertEqual(before, snapshot(self.database))
                    else:
                        self.assertEqual(200, status, recovered)
                        self.assertEqual(expected_state == "COMPLETED", recovered["idempotentReplay"])
                        self.assertEqual(expected_state == "RESULT_READY", recovered.get("recoveredFromResultReady", False))
                        before = snapshot(self.database)
                        status, replay = restarted.post(GENERATE, body)
                        self.assertEqual(200, status, replay)
                        self.assertTrue(replay["idempotentReplay"])
                        self.assertEqual(recovered["scriptVersion"], replay["scriptVersion"])
                        self.assertEqual(before, snapshot(self.database))
                    self.assertEqual(calls, call_count(counter))
                    self.assertNotEqual(child.pid, restarted.pid)
                    self.assertNotEqual(os.getpid(), restarted.pid)
                    restarted.close()

    def test_two_processes_same_key_different_key_and_unkeyed_exclude_duplicate_calls(self):
        for mode in ("same-key", "different-key", "unkeyed"):
            with self.subTest(mode=mode):
                self.start(bound=True)
                self.stop()
                counter = Path(self.temp.name) / "calls.jsonl"
                first = ChildRuntime(self.database, counter, fault="blocked-capability")
                second = ChildRuntime(self.database, counter)
                self.addCleanup(first.close)
                self.addCleanup(second.close)
                body = {**self.body, **({} if mode == "unkeyed" else {"idempotencyKey": "first"})}
                other = {**body, **({"idempotencyKey": "second"} if mode == "different-key" else {})}
                with ThreadPoolExecutor(1) as pool:
                    running = pool.submit(first.post, GENERATE, body)
                    self.assertEqual("capability-entered", first.event()["stage"])
                    try:
                        status, pending = second.post(GENERATE, other)
                        self.assertEqual((409, "script_generation_pending"), (status, pending["error"]["code"]))
                        self.assertEqual(1, call_count(counter))
                    finally:
                        first.send({"release": True})
                    status, result = running.result(timeout=15)
                self.assertEqual(201, status, result)
                self.assertEqual(1, call_count(counter))
                self.assertEqual(1, len(rows(self.database, "v5_script_versions")))
                first.close()
                second.close()

    def test_confirmation_response_loss_new_interpreter_noop_is_byte_stable(self):
        for bound in (False, True):
            with self.subTest(bound=bound):
                self.start(bound=bound)
                _, generated = self.post(GENERATE, self.body)
                body = {**self.confirm_body(generated), "expectedScriptVersion": 1}
                self.stop()
                counter = Path(self.temp.name) / "confirm-calls.jsonl"
                first = ChildRuntime(self.database, counter, fault="confirm-response")
                self.addCleanup(first.close)
                with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
                    first.post(CONFIRM, body)
                self.assertEqual(70, first.process.wait(timeout=15))
                first.close()
                before = snapshot(self.database)
                second = ChildRuntime(self.database, counter)
                self.addCleanup(second.close)
                status, confirmed = second.post(CONFIRM, body)
                self.assertEqual(200, status, confirmed)
                self.assertEqual(2, confirmed["script"]["version"])
                self.assertEqual(before, snapshot(self.database))
                self.assertEqual(0, call_count(counter))
                self.assertNotEqual(first.pid, second.pid)
                second.close()

    def advance_m5_source(self):
        current = self.seed["confirmedBound"]
        changed = self.assembly.series_planning.create_episode_plan_item_binding_version({
            **{k: self.scope[k] for k in ("workspaceRef", "projectRef", "seriesRef")},
            "seriesPlanRef": current["seriesPlanRef"], "expectedPlanVersion": current["version"],
            "episodePlanItemBindings": [self.seed["binding"]]})
        self.assembly.series_planning.confirm_version({"workspaceRef": WORKSPACE,
            "seriesPlanRef": changed["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": changed["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": changed["plan"]["version"], "humanConfirmed": True})

    def test_generation_source_drift_never_rebinds_saved_output(self):
        for bound in (False, True):
            with self.subTest(bound=bound):
                self.start(bound=bound)
                try:
                    save_result = self.assembly.script_studio.save_generation_result
                    source = self.assembly.series_episode.build_script_studio_bootstrap
                    changed = []

                    def after_result(ticket, content):
                        save_result(ticket, content)
                        if bound:
                            self.advance_m5_source()
                        else:
                            # V1's Episode binding is immutable in the current API.
                            # Model a changed owner read at the existing source port;
                            # no test invents a new public binding mutation.
                            changed.append(True)

                    def owner_read(*args):
                        result = source(*args)
                        if changed:
                            result["sourcePlanVersion"] += 1
                        return result

                    with patch.object(self.assembly.script_studio, "save_generation_result", side_effect=after_result), \
                         patch.object(self.assembly.series_episode, "build_script_studio_bootstrap", side_effect=owner_read):
                        status, failure = self.post(GENERATE, {**self.body, "idempotencyKey": "source-change"})
                        self.assertEqual((409, "m6_baseline_stale" if bound else "script_generation_source_changed"),
                                         (status, failure["error"]["code"]))
                    self.assertEqual(1, len(self.capability.commands))
                    self.assertEqual([], rows(self.database, "v5_scripts"))
                    self.assertEqual("RESULT_READY", json.loads(rows(self.database, TABLE)[0][5])["state"])
                finally:
                    self.stop()

    def test_confirmation_noop_still_checks_current_m6_and_immutable_source(self):
        self.start(bound=True)
        _, generated = self.post(GENERATE, self.body)
        body = self.confirm_body(generated)
        self.assertEqual(201, self.post(CONFIRM, body)[0])
        before = snapshot(self.database)
        from services.v5_core_os.series_intelligence.errors import SeriesIntelligenceError
        with patch.object(ScopeAuthority, "resolve_scope", side_effect=SeriesIntelligenceError("authority_unavailable")):
            status, denied = self.post(CONFIRM, body)
        self.assertEqual(403, status, denied)
        self.assertEqual(before, snapshot(self.database))
        self.advance_m5_source()
        before = snapshot(self.database)
        status, stale = self.post(CONFIRM, body)
        self.assertEqual((409, "m6_baseline_stale"), (status, stale["error"]["code"]))
        self.assertEqual(before, snapshot(self.database))

    def test_v1_noop_rejects_corrupt_immutable_content_and_source_before_any_write(self):
        for field in ("content_json", "source_plan_version"):
            with self.subTest(field=field):
                self.start()
                try:
                    _, generated = self.post(GENERATE, self.body)
                    confirm = self.confirm_body(generated)
                    self.assertEqual(201, self.post(CONFIRM, confirm)[0])
                    with sqlite3.connect(self.database) as connection:
                        if field == "content_json":
                            connection.execute("UPDATE v5_script_versions SET content_json='{}'")
                        else:
                            connection.execute("UPDATE v5_script_versions SET source_plan_version=source_plan_version+1")
                    before = snapshot(self.database)
                    status, failure = self.post(CONFIRM, confirm)
                    self.assertEqual((500, "application_error"), (status, failure["error"]["code"]))
                    self.assertEqual(before, snapshot(self.database))
                finally:
                    self.stop()

    def test_confirmation_same_and_different_targets_serialize_across_processes(self):
        self.start(bound=True)
        _, generated = self.post(GENERATE, self.body)
        body = {**self.confirm_body(generated), "expectedScriptVersion": 1}
        self.stop()
        counter = Path(self.temp.name) / "confirm-process-calls.jsonl"
        first, second = ChildRuntime(self.database, counter), ChildRuntime(self.database, counter)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda child: child.post(CONFIRM, body), (first, second)))
        self.assertEqual([200, 201], sorted(r[0] for r in results), results)
        self.assertEqual(2, self.read()["script"]["version"])
        a = self.append(generated)
        b = self.append(a)
        expected = self.read()["script"]["version"]
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda pair: pair[0].post(CONFIRM,
                {**self.confirm_body(pair[1]), "expectedScriptVersion": expected}), ((first, a), (second, b))))
        self.assertEqual([201, 409], sorted(r[0] for r in results), results)
        self.assertEqual(expected + 1, self.read()["script"]["version"])
        self.assertEqual(0, call_count(counter))
        first.close()
        second.close()

    def test_same_target_reviewed_import_cannot_bypass_trusted_acceptance(self):
        self.start()
        status, imported = self.post("/creator/api/v1/script-versions/reviewed-import", {
            **self.body, "uploadedSourceByteDigest": "a" * 64,
            "normalizedSourceDocumentDigest": "b" * 64, "reviewedDocumentDigest": "c" * 64,
            "content": {k: script_candidate()[k] for k in
                        ("title", "logline", "synopsis", "targetDurationSec", "scenes")}})
        self.assertEqual(201, status, imported)
        confirm = self.confirm_body(imported)
        self.assertEqual(403, self.post(CONFIRM, confirm)[0])
        self.assembly.script_studio.accept_reviewed_import({**self.scope,
            "scriptRef": confirm["scriptRef"], "scriptVersionRef": confirm["scriptVersionRef"],
            "idempotencyKey": "trusted-acceptance", "approvalRef": "approval-k2-002-v1-4"})
        self.assertEqual(confirm["scriptVersionRef"], self.read()["script"]["confirmedScriptVersionRef"])
        before = snapshot(self.database)
        status, rejected = self.post(CONFIRM, confirm)
        self.assertEqual((403, "trusted_approval_required"), (status, rejected["error"]["code"]))
        self.assertEqual(before, snapshot(self.database))

    def test_noop_preserves_production_and_m7_while_real_edit_and_switch_still_stale(self):
        self.start(bound=True, production=True)
        _, generated = self.post(GENERATE, self.body)
        confirm = self.confirm_body(generated)
        status, first = self.post(CONFIRM, confirm)
        self.assertEqual(201, status, first)
        run_body = {**self.body, "idempotencyKey": "e3f-stable-run", "shotsPerScene": [1, 1]}
        status, run = self.post("/creator/api/v1/episode-production-runs", run_body)
        self.assertEqual(201, status, run)
        path = "/creator/api/v1/episode-production-runs/" + run["run"]["productionRunRef"] + "/narrative-validation"
        validation_body = {**self.body, "validationProfileRef": "m7.narrative-currentness",
                           "validationProfileVersion": 1, "idempotencyKey": "e3f-stable-validation"}
        status, validation = self.post(path, validation_body)
        self.assertEqual(200, status, validation)
        self.assertEqual(("PASS", "CURRENT"), (validation["validation"]["result"], validation["validation"]["currentness"]))
        before = {p.name: snapshot(p) for p in Path(self.temp.name).glob("*.sqlite3")}
        status, noop = self.post(CONFIRM, confirm)
        self.assertEqual(200, status, noop)
        self.assertEqual(first, noop)
        status, run_replay = self.post("/creator/api/v1/episode-production-runs", run_body)
        self.assertEqual(200, status, run_replay)
        self.assertEqual({k: v for k, v in run["run"].items() if k != "idempotentReplay"},
                         {k: v for k, v in run_replay["run"].items() if k != "idempotentReplay"})
        status, validation_replay = self.post(path, validation_body)
        self.assertEqual(200, status, validation_replay)
        self.assertEqual(validation["validation"]["payloadDigest"], validation_replay["validation"]["payloadDigest"])
        self.assertEqual("CURRENT", validation_replay["validation"]["currentness"])
        self.assertEqual(before, {p.name: snapshot(p) for p in Path(self.temp.name).glob("*.sqlite3")})
        edited = self.append(generated)
        self.assertEqual(409, self.post("/creator/api/v1/episode-production-runs", run_body)[0])
        self.assertEqual(409, self.post(path, validation_body)[0])
        status, switched = self.post(CONFIRM, {**self.confirm_body(edited), "expectedScriptVersion": edited["script"]["version"]})
        self.assertEqual(201, status, switched)
        self.assertEqual(409, self.post(path, validation_body)[0])
        self.assertEqual(1, len(self.capability.commands))

    def test_v1_confirmation_noop_keeps_the_legacy_production_snapshot(self):
        self.start(bound=True, production=True)
        legacy = {k: v for k, v in self.body.items() if k != "projectRef"}
        status, generated = self.post(GENERATE, legacy)
        self.assertEqual(201, status, generated)
        self.assertEqual("creator.script-studio.script-version.v1", generated["scriptVersion"]["schemaVersion"])
        confirm = {**legacy, "scriptRef": generated["script"]["scriptRef"],
                   "scriptVersionRef": generated["scriptVersion"]["scriptVersionRef"], "humanConfirmed": True}
        status, first = self.post(CONFIRM, confirm)
        self.assertEqual(201, status, first)
        run_body = {**self.body, "idempotencyKey": "e3f-v1-stable-run", "shotsPerScene": [1, 1]}
        status, run = self.post("/creator/api/v1/episode-production-runs", run_body)
        self.assertEqual(201, status, run)
        before = {p.name: snapshot(p) for p in Path(self.temp.name).glob("*.sqlite3")}
        status, noop = self.post(CONFIRM, confirm)
        self.assertEqual(200, status, noop)
        self.assertEqual(first, noop)
        status, replay = self.post("/creator/api/v1/episode-production-runs", run_body)
        self.assertEqual(200, status, replay)
        self.assertEqual({k: v for k, v in run["run"].items() if k != "idempotentReplay"},
                         {k: v for k, v in replay["run"].items() if k != "idempotentReplay"})
        self.assertEqual(before, {p.name: snapshot(p) for p in Path(self.temp.name).glob("*.sqlite3")})

    def test_invalid_m6_access_never_falls_back_or_enters_generation(self):
        self.start(bound=True)
        before = snapshot(self.database)
        status, unavailable = self.post(GENERATE, {**self.body, "projectRef": "missing-project"})
        self.assertEqual(403, status, unavailable)
        self.assertEqual("m6_consumer_authority_unavailable", unavailable["error"]["code"])
        from services.v5_core_os.series_intelligence.errors import SeriesIntelligenceError
        with patch.object(ScopeAuthority, "resolve_scope", side_effect=SeriesIntelligenceError("authority_unavailable")):
            status, denied = self.post(GENERATE, self.body)
        self.assertEqual(403, status, denied)
        self.assertEqual(0, len(self.capability.commands))
        self.assertEqual(before, snapshot(self.database))


def call_count(path):
    return len(path.read_text().splitlines()) if path.exists() else 0


class DurableCountingCapability:
    def __init__(self, path, fault, released):
        self.path, self.fault, self.released = path, fault, released

    def generate(self, _command):
        descriptor = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, (json.dumps({"pid": os.getpid(), "call": "SCRIPT_CANDIDATE"}) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if self.fault == "capability":
            os._exit(70)
        if self.fault == "blocked-capability":
            print(json.dumps({"stage": "capability-entered"}), flush=True)
            if not self.released.wait(20):
                raise RuntimeError("test release deadline")
        return json.dumps(script_candidate(), ensure_ascii=False)


class ChildRuntime:
    def __init__(self, database, counter, *, fault=""):
        self.token = secrets.token_urlsafe(48)
        self.process = subprocess.Popen([sys.executable, "-m", CHILD_MODULE, "--serve-e3f"], cwd=REPO,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        try:
            self.send({"database": str(database), "counter": str(counter), "fault": fault, "token": self.token})
            ready = self.event()
            if ready.get("stage") != "ready" or ready.get("package") != "tests.integration":
                raise RuntimeError("invalid child entrypoint")
            self.port, self.pid = ready["port"], ready["pid"]
            if self.pid != self.process.pid:
                raise RuntimeError("invalid child process identity")
        except BaseException:
            self.close()
            raise

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def event(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(15):
                raise RuntimeError("child startup/event deadline")
            line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("child exited before event: " + self.process.stderr.read()[:1500])
        return json.loads(line)

    def post(self, path, body):
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            client.request("POST", path, json.dumps(body).encode(),
                {"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def close(self):
        if self.process.poll() is None:
            try:
                self.send({"stop": True})
                self.process.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if not stream.closed:
                stream.close()
        self.token = None


def child_main():
    config = json.loads(sys.stdin.readline())
    assembly = LifecycleAssembly.sqlite(config["database"], m6_scope_authority=ScopeAuthority(),
                                        m6_approval_authority=ApprovalAuthority())
    fault = config["fault"]
    released = threading.Event()
    capability = DurableCountingCapability(config["counter"], fault, released)
    auth = PublicApiAuthenticator.from_mapping({"schemaVersion": "creator.public-auth.v1",
        "credentials": [{"credentialRef": "e3f-child", "workspaceRef": WORKSPACE,
                         "tokenSha256": sha256(config.pop("token").encode()).hexdigest(), "enabled": True}]})
    if fault == "reservation":
        reserve = ScriptStudioPublicBoundary.reserve_generation

        def reserve_exit(boundary, command):
            reserve(boundary, command)
            os._exit(70)

        ScriptStudioPublicBoundary.reserve_generation = reserve_exit
    if fault in {"returned", "result-ready"}:
        save_result = ScriptStudioPublicBoundary.save_generation_result

        def save_exit(boundary, ticket, content):
            if fault == "result-ready":
                save_result(boundary, ticket, content)
            os._exit(70)

        ScriptStudioPublicBoundary.save_generation_result = save_exit
    if fault == "transaction":
        save = SqliteGenerationStore.save

        def transaction_exit(store, record):
            if record["state"] == "COMPLETED":
                connection = store._state.connection_or_none()
                assert connection.execute("SELECT COUNT(*) FROM v5_script_versions").fetchone()[0] == 1
                os._exit(70)
            return save(store, record)

        SqliteGenerationStore.save = transaction_exit
    if fault in {"response", "confirm-response"}:
        send = CreatorRequestHandler._send_json

        def lost_response(handler, status, body):
            if handler.path == (CONFIRM if fault == "confirm-response" else GENERATE) and status in {200, 201} and body.get("ok"):
                os._exit(70)
            return send(handler, status, body)

        CreatorRequestHandler._send_json = lost_response
    server = create_server(("127.0.0.1", 0), AiDirectorService(FakeTextGenerationCapability([])),
        series_episode_boundary=assembly.series_episode, project_boundary=assembly.project_context,
        series_planning_boundary=assembly.series_planning, script_studio_boundary=assembly.script_studio,
        script_studio_service=ScriptStudioApplicationService(capability),
        public_authenticator=auth, allow_internal_routes=False)

    def control():
        for line in sys.stdin:
            value = json.loads(line)
            if value.get("release"):
                released.set()
            if value.get("stop"):
                break
        released.set()
        server.shutdown()

    thread = threading.Thread(target=control, daemon=True)
    thread.start()
    print(json.dumps({"stage": "ready", "port": server.server_port, "pid": os.getpid(), "package": __package__}), flush=True)
    try:
        server.serve_forever(poll_interval=0.01)
    finally:
        server.server_close()


if __name__ == "__main__":
    if sys.argv[1:] == ["--serve-e3f"]:
        child_main()
    else:
        unittest.main()
