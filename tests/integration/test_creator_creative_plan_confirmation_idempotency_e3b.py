"""Real authenticated HTTP and SQLite checks for M1 confirmation recovery."""

import copy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import http.client
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import unittest

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_AI_DIRECTOR_ENDPOINT,
    PUBLIC_CONFIRM_PLAN_ENDPOINT,
    PUBLIC_EPISODES_ENDPOINT,
    PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
    PUBLIC_SERIES_ENDPOINT,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_project_foundation import valid_command as foundation_command


WORKSPACE = "workspace-confirmation-e3b"
FOREIGN_WORKSPACE = "workspace-confirmation-e3b-foreign"


class ConfirmationHttpHarness:
    def __init__(self, path, *, initialize=True, tokens=None):
        self.path = Path(path)
        self.tokens = tokens or (secrets.token_urlsafe(40), secrets.token_urlsafe(40))
        authenticator = PublicApiAuthenticator.from_mapping({
            "schemaVersion": "creator.public-auth.v1",
            "credentials": [
                {"credentialRef": f"e3b-credential-{index}", "workspaceRef": workspace,
                 "tokenSha256": sha256(token.encode()).hexdigest(), "enabled": True}
                for index, (workspace, token) in enumerate(
                    zip((WORKSPACE, FOREIGN_WORKSPACE), self.tokens)
                )
            ],
        })
        self.assembly = LifecycleAssembly.sqlite(
            self.path, initialize_or_upgrade=initialize
        )
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([json.dumps(valid_plan())] * 4)),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_boundary=self.assembly.script_studio,
            public_authenticator=authenticator,
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}
        )
        self.thread.start()

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            assert not self.thread.is_alive()
            self.server = None
            self.assembly = None

    def request(self, path, body=None, *, method="POST", token=None, raw=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        encoded = raw if raw is not None else json.dumps(body, ensure_ascii=False).encode()
        try:
            client.request(method, path, encoded if method == "POST" else None, {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + (token or self.tokens[0]),
            })
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def command(self):
        status, candidate = self.request(PUBLIC_AI_DIRECTOR_ENDPOINT, {"brief": valid_brief()})
        assert status == 200 and candidate["ok"] is True
        return {
            "humanConfirmed": True, "brief": valid_brief(), "plan": candidate["plan"],
            "sourcePlanRef": candidate["sourcePlanRef"],
            "sourcePlanVersion": candidate["sourcePlanVersion"],
            "idempotencyKey": "confirmation-e3b-command",
        }

    def rows(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM v5_confirmed_creative_plans ORDER BY workspace_ref, creative_plan_ref"
            )]
        finally:
            connection.close()

    def schema(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            return connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall()
        finally:
            connection.close()


class CreativePlanConfirmationIdempotencyHttpTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "lifecycle.sqlite3"
        self.http = ConfirmationHttpHarness(self.path)
        self.addCleanup(lambda: self.http.close())
        self.command = self.http.command()

    def test_exact_replay_returns_the_original_durable_plan(self):
        first_status, first = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)
        durable_bytes = self.path.read_bytes()
        second_status, second = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)
        self.confirmation_receipt = {
            "firstStatus": first_status, "replayStatus": second_status,
            "firstCreativePlanRef": first["confirmedPlan"]["creativePlanRef"],
            "replayCreativePlanRef": second["confirmedPlan"]["creativePlanRef"],
            "firstPlan": first["confirmedPlan"], "replayPlan": second["confirmedPlan"],
        }
        self.assertEqual((first_status, second_status), (201, 200))
        self.assertEqual(first["confirmedPlan"], second["confirmedPlan"])
        self.assertIs(first["idempotentReplay"], False)
        self.assertIs(second["idempotentReplay"], True)
        self.assertEqual(len(self.http.rows()), 1)
        self.assertEqual(durable_bytes, self.path.read_bytes())

    def test_changed_keyed_requests_conflict_without_any_durable_change(self):
        status, first = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)
        self.assertEqual(status, 201)
        durable_bytes = self.path.read_bytes()
        variants = []
        for field, value in {"sourcePlanRef": "another-source", "sourcePlanVersion": 2,
                             "brief": {**self.command["brief"], "theme": "changed theme"}}.items():
            variants.append({**self.command, field: value})
        changed_plan = copy.deepcopy(self.command)
        changed_plan["plan"]["storyDirection"]["title"] = "changed title"
        variants.append(changed_plan)
        for changed in variants:
            with self.subTest(changed_fields=[key for key in changed if changed[key] != self.command[key]]):
                code, rejected = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, changed)
                self.assertEqual(code, 409)
                self.assertEqual(rejected["error"]["code"], "creative_plan_idempotency_conflict")
                self.assertEqual(durable_bytes, self.path.read_bytes())
        self.assertEqual(len(self.http.rows()), 1)
        self.assertEqual(self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)[1]["confirmedPlan"], first["confirmedPlan"])

    def test_legacy_frontend_body_replays_without_changing_the_envelope(self):
        legacy = dict(self.command)
        del legacy["idempotencyKey"]
        first_status, first = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, legacy)
        replay_status, replay = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, legacy)
        self.assertEqual((first_status, replay_status), (201, 200))
        self.assertEqual(set(first), {"ok", "confirmedPlan"})
        self.assertEqual(first, replay)
        self.assertEqual(len(self.http.rows()), 1)
        for field in ("brief", "plan"):
            changed = copy.deepcopy(legacy)
            if field == "brief":
                changed[field]["theme"] = "different theme"
            else:
                changed[field]["storyDirection"]["title"] = "different title"
            status, failure = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, changed)
            self.assertEqual(status, 409)
            self.assertEqual(failure["error"]["code"], "creative_plan_idempotency_conflict")
            self.assertEqual(len(self.http.rows()), 1)

    def test_response_loss_retry_reads_the_committed_winner(self):
        client = http.client.HTTPConnection("127.0.0.1", self.http.server.server_port, timeout=10)
        client.request("POST", PUBLIC_CONFIRM_PLAN_ENDPOINT, json.dumps(self.command).encode(), {
            "Content-Type": "application/json", "Authorization": "Bearer " + self.http.tokens[0],
        })
        response = client.getresponse()
        self.assertEqual(response.status, 201)
        # Headers arrive after the real transaction commits. Discard the body.
        response.close()
        client.close()
        committed = self.http.rows()
        self.assertEqual(len(committed), 1)
        status, replay = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["confirmedPlan"]["creativePlanRef"], committed[0]["creative_plan_ref"])
        self.assertEqual(replay["confirmedPlan"]["confirmedAt"], committed[0]["confirmed_at"])
        self.assertEqual(self.http.rows(), committed)

    def test_fresh_composition_restart_preserves_keyed_and_source_identity_replay(self):
        legacy = dict(self.command)
        del legacy["idempotencyKey"]
        commands = [self.command, legacy]
        first = [self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, value) for value in commands]
        self.assertEqual([item[0] for item in first], [201, 201])
        before = self.http.rows()
        schema = self.http.schema()
        self.http.close()
        self.assertIsNone(self.http.assembly)
        self.http = ConfirmationHttpHarness(self.path, initialize=False)
        for value, (_status, original) in zip(commands, first):
            status, replay = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, value)
            self.assertEqual(status, 200)
            self.assertEqual(replay["confirmedPlan"], original["confirmedPlan"])
        self.assertEqual(self.http.rows(), before)
        self.assertEqual(self.http.schema(), schema)

    def _concurrent_requests(self, changed):
        # Distinct assemblies force correctness beyond one process-local lock.
        second = ConfirmationHttpHarness(self.path, initialize=False, tokens=self.http.tokens)
        self.addCleanup(second.close)
        commands = [self.command, copy.deepcopy(self.command)]
        if changed:
            commands[1]["brief"]["theme"] = "competing theme"
        barrier = threading.Barrier(2)
        servers = [self.http, second]
        def call(index):
            barrier.wait(timeout=5)
            return servers[index].request(PUBLIC_CONFIRM_PLAN_ENDPOINT, commands[index])
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(call, range(2)))
        self.assertEqual(len(self.http.rows()), 1)
        return results, commands

    def test_concurrent_exact_replay_across_sqlite_assemblies(self):
        results, _commands = self._concurrent_requests(False)
        self.assertEqual(sorted(status for status, _body in results), [200, 201])
        self.assertEqual(results[0][1]["confirmedPlan"], results[1][1]["confirmedPlan"])
        self.assertEqual({body["idempotentReplay"] for _status, body in results}, {False, True})

    def test_concurrent_changed_requests_conflict_without_mixing_content(self):
        results, commands = self._concurrent_requests(True)
        self.assertEqual(sorted(status for status, _body in results), [201, 409])
        for index, (status, body) in enumerate(results):
            if status == 201:
                winner = body["confirmedPlan"]
                self.assertEqual(winner["brief"], commands[index]["brief"])
                self.assertEqual(winner["sourcePlan"], commands[index]["plan"])
                self.assertEqual(json.loads(self.http.rows()[0]["brief_json"]), winner["brief"])
            else:
                self.assertEqual(body["error"]["code"], "creative_plan_idempotency_conflict")

    def test_distinct_explicit_keys_are_independent_commands(self):
        first = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)
        second = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, {**self.command, "idempotencyKey": "other-command"})
        self.assertEqual((first[0], second[0]), (201, 201))
        self.assertNotEqual(first[1]["confirmedPlan"]["creativePlanRef"], second[1]["confirmedPlan"]["creativePlanRef"])
        self.assertEqual(len(self.http.rows()), 2)

    def test_same_key_and_source_identity_in_different_workspaces_are_isolated(self):
        for keyed in (True, False):
            command = dict(self.command)
            if not keyed:
                del command["idempotencyKey"]
            first_status, first = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command)
            second_status, second = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command, token=self.http.tokens[1])
            self.assertEqual((first_status, second_status), (201, 201))
            self.assertEqual(first["confirmedPlan"]["workspaceRef"], WORKSPACE)
            self.assertEqual(second["confirmedPlan"]["workspaceRef"], FOREIGN_WORKSPACE)
            self.assertNotEqual(first["confirmedPlan"]["creativePlanRef"], second["confirmedPlan"]["creativePlanRef"])
            for token, expected in zip(self.http.tokens, (first, second)):
                status, replay = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command, token=token)
                self.assertEqual(status, 200)
                self.assertEqual(replay["confirmedPlan"], expected["confirmedPlan"])
        self.assertEqual(len(self.http.rows()), 4)

    def test_raw_key_and_request_metadata_are_not_stored_and_schema_is_unchanged(self):
        schema = self.http.schema()
        key = "E3B-NONPERSISTED-" + secrets.token_hex(24)
        command = {**self.command, "idempotencyKey": key}
        for _ in range(2):
            _status, response = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, command)
            self.assertNotIn(key, json.dumps(response))
        self.assertNotIn(key.encode(), self.path.read_bytes())
        self.assertNotIn(key, json.dumps(self.http.rows()))
        self.assertEqual(self.http.schema(), schema)
        self.assertEqual(set(self.http.rows()[0]), {
            "workspace_ref", "creative_plan_ref", "schema_version", "source_plan_ref",
            "source_plan_schema_version", "source_plan_version", "brief_json", "source_plan_json",
            "confirmation_status", "confirmed_at", "version",
        })

    @staticmethod
    def _episode_command(plan):
        return {"creativePlanRef": plan["creativePlanRef"], "episodeNumber": 1,
                "seasonNumber": 1, "volumeNumber": 1, "title": "E3B regression episode"}

    def test_returned_plan_supports_project_foundation_and_public_episode_readback(self):
        status, result = self.http.request(PUBLIC_CONFIRM_PLAN_ENDPOINT, self.command)
        self.assertEqual(status, 201)
        plan = result["confirmedPlan"]
        status, created = self.http.request(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            foundation_command(episode=self._episode_command(plan)),
        )
        self.assertEqual(status, 201)
        foundation = created["foundation"]
        path = f"{PUBLIC_EPISODES_ENDPOINT}/{foundation['episode']['episodeRef']}?seriesRef={foundation['series']['seriesRef']}"
        status, readback = self.http.request(path, method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(readback["episode"]["confirmedPlanBinding"]["creativePlanRef"], plan["creativePlanRef"])
        self.assertEqual(readback["episode"]["confirmedPlanBinding"]["sourcePlan"], plan["sourcePlan"])
        self.assertEqual(self.http.request(path, method="GET", token=self.http.tokens[1])[0], 404)

    def test_legacy_random_ref_remains_readable_and_bindable_after_restart(self):
        command = {"workspaceRef": WORKSPACE, "humanConfirmed": True,
                   "sourcePlanRef": self.command["sourcePlanRef"], "sourcePlanVersion": 1,
                   "sourcePlanSchemaVersion": self.command["plan"]["schemaVersion"],
                   "brief": self.command["brief"], "sourcePlan": self.command["plan"]}
        legacy = self.http.assembly.series_episode.confirm_creative_plan(command)
        original_rows = self.http.rows()
        self.assertRegex(legacy["creativePlanRef"], r"^creative-plan-[0-9a-f]{32}$")
        self.http.close()
        self.http = ConfirmationHttpHarness(self.path, initialize=False)
        status, series = self.http.request(PUBLIC_SERIES_ENDPOINT, {
            "contentProfileRef": "e3b-profile", "title": "E3B regression Series", "plannedEpisodeCount": 1,
        })
        self.assertEqual(status, 201)
        series_ref = series["series"]["seriesRef"]
        status, created = self.http.request(PUBLIC_EPISODES_ENDPOINT, {
            **self._episode_command(legacy), "seriesRef": series_ref,
        })
        self.assertEqual(status, 201)
        status, fetched = self.http.request(
            f"{PUBLIC_EPISODES_ENDPOINT}/{created['episode']['episodeRef']}?seriesRef={series_ref}", method="GET"
        )
        self.assertEqual(status, 200)
        self.assertEqual(fetched["episode"]["confirmedPlanBinding"]["sourcePlan"], legacy["sourcePlan"])
        self.assertEqual(self.http.rows(), original_rows)


if __name__ == "__main__":
    unittest.main()
