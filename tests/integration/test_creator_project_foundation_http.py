import copy
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import unittest
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.project_foundation import (
    ProjectFoundationApplicationError,
    ProjectFoundationApplicationService,
)
from apps.creator_workspace_mvp.public_auth import (
    PUBLIC_AUTH_SCHEMA_VERSION,
    PublicApiAuthenticator,
    token_sha256,
)
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_CONFIRM_PLAN_ENDPOINT,
    PUBLIC_EPISODES_ENDPOINT,
    PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
    PUBLIC_PROJECTS_ENDPOINT,
    PUBLIC_SERIES_ENDPOINT,
)
from apps.creator_workspace_mvp.series_plan_candidate_receipts import (
    create_local_development_receipt_service,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import (
    LifecycleAssembly,
    validate_lifecycle_database,
)
from services.v5_core_os.project_engine.project_foundation_sqlite import TABLE
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_project_foundation import PROFILE, WORKSPACE, valid_command


FOREIGN_WORKSPACE = "workspace-project-foundation-foreign"


class _OneShotFault:
    def __init__(self, point):
        self.point = point
        self.fired = False

    def __call__(self, point):
        if point == self.point and not self.fired:
            self.fired = True
            raise RuntimeError(f"fault:{point}")


class _UnavailableService:
    def execute(self, *_args):
        raise ProjectFoundationApplicationError(
            "project_foundation_unavailable", 503
        )

    get = execute


class _UnexpectedOnceService:
    def __init__(self, delegate):
        self.delegate = delegate
        self.failed = False

    def execute(self, *args):
        if not self.failed:
            self.failed = True
            raise RuntimeError("unexpected test fault")
        return self.delegate.execute(*args)

    def get(self, *args):
        return self.delegate.get(*args)


class FoundationHttpHarness:
    def __init__(
        self,
        path,
        *,
        initialize=True,
        fault_hook=None,
        authenticator=None,
        receipt_service=None,
        service_override=None,
    ):
        self.path = Path(path)
        self.token = secrets.token_urlsafe(48)
        self.foreign_token = secrets.token_urlsafe(48)
        self.authenticator = authenticator or PublicApiAuthenticator.for_token(
            self.token, WORKSPACE
        )
        self.assembly = (
            LifecycleAssembly.sqlite(
                self.path,
                initialize_or_upgrade=True,
            )
            if initialize
            else LifecycleAssembly.sqlite_from_environment(
                {"CREATOR_DATA_PATH": str(self.path)}
            )
        )
        self.receipt_service = receipt_service
        default_service = ProjectFoundationApplicationService(
            self.assembly.project_foundation_store,
            self.assembly.coordinator,
            self.assembly.series_episode,
            self.assembly.project_context,
            fault_hook=fault_hook,
        )
        self.foundation_service = service_override or default_service
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_plan_candidate_receipt_service=receipt_service,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_boundary=self.assembly.script_studio,
            canonical_registration_boundary=self.assembly.canonical_registration,
            project_foundation_service=self.foundation_service,
            public_authenticator=self.authenticator,
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.server = None
        if self.receipt_service is not None:
            self.receipt_service.store.close()

    def post(
        self,
        path,
        payload=None,
        *,
        token=None,
        body=None,
        authenticated=True,
    ):
        raw = body if body is not None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {token or self.token}"
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=raw,
            method="POST",
            headers=headers,
        )
        return self._open(http_request)

    def get(self, path, *, token=None, authenticated=True):
        headers = {}
        if authenticated:
            headers["Authorization"] = f"Bearer {token or self.token}"
        return self._open(
            request.Request(f"{self.base_url}{path}", headers=headers)
        )

    @staticmethod
    def _open(http_request):
        try:
            response = request.urlopen(http_request, timeout=10)
        except error.HTTPError as exc:
            raw = exc.read()
            return exc.code, dict(exc.headers.items()), json.loads(raw.decode("utf-8"))
        with response:
            raw = response.read()
            return response.status, dict(response.headers.items()), json.loads(raw.decode("utf-8"))

    def confirm_plan(self):
        status, _headers, payload = self.post(
            PUBLIC_CONFIRM_PLAN_ENDPOINT,
            {
                "humanConfirmed": True,
                "brief": valid_brief(),
                "plan": valid_plan(),
                "sourcePlanRef": "source-plan-project-foundation-http",
                "sourcePlanVersion": 1,
            },
        )
        if status != 201:
            raise AssertionError(payload)
        return payload["confirmedPlan"]

    def counts(self, workspace=WORKSPACE):
        with sqlite3.connect(self.path) as connection:
            return tuple(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE workspace_ref=?",
                    (workspace,),
                ).fetchone()[0]
                for table in (
                    "v5_series",
                    "v5_projects",
                    "v5_episode_projects",
                    TABLE,
                )
            )


class CreatorProjectFoundationHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "creator.sqlite3"
        self.harness = FoundationHttpHarness(self.path)
        self.addCleanup(self.harness.close)

    @staticmethod
    def episode_command(plan, *, key="foundation-with-episode"):
        return valid_command(
            key=key,
            episode={
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "seasonNumber": 1,
                "volumeNumber": 1,
                "title": "Episode 001",
            },
        )

    def test_one_command_safely_replaces_the_three_lossy_client_steps(self):
        plan = self.harness.confirm_plan()
        command = self.episode_command(plan)
        status, _headers, created = self.harness.post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            command,
        )
        self.assertEqual(201, status)
        self.assertFalse(created["idempotentReplay"])
        self.assertFalse(created["recoveredFromPending"])
        foundation = created["foundation"]
        self.assertEqual((1, 1, 1, 1), self.harness.counts())
        self.assertEqual(
            foundation["series"]["seriesRef"],
            foundation["project"]["seriesRefs"][0],
        )

        status, _headers, replay = self.harness.post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            command,
        )
        self.assertEqual(200, status)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(foundation, replay["foundation"])
        self.assertEqual((1, 1, 1, 1), self.harness.counts())

        status, _headers, fetched = self.harness.get(
            f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/{foundation['foundationRef']}"
        )
        self.assertEqual(200, status)
        self.assertEqual(foundation, fetched["foundation"])
        with sqlite3.connect(self.path) as connection:
            binding = connection.execute(
                "SELECT creative_plan_ref FROM v5_episode_plan_bindings "
                "WHERE workspace_ref=? AND series_ref=? AND episode_ref=?",
                (
                    WORKSPACE,
                    foundation["series"]["seriesRef"],
                    foundation["episode"]["episodeRef"],
                ),
            ).fetchone()
            self.assertEqual(plan["creativePlanRef"], binding[0])
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM v5_scripts"
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM v5_canonical_registrations"
                ).fetchone()[0],
            )

    def test_public_auth_scope_validation_and_stable_errors(self):
        command = valid_command()
        for method, args in (
            (self.harness.post, (PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, command)),
            (
                self.harness.get,
                (f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/unknown",),
            ),
        ):
            with self.subTest(method=method.__name__):
                status, headers, payload = method(*args, authenticated=False)
                self.assertEqual(401, status)
                self.assertEqual("application/json; charset=utf-8", headers["Content-Type"])
                self.assertEqual("authentication_required", payload["error"]["code"])

        scoped = {**command, "workspaceRef": WORKSPACE}
        status, _headers, payload = self.harness.post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, scoped
        )
        self.assertEqual(400, status)
        self.assertEqual("client_workspace_scope_forbidden", payload["error"]["code"])

        for mutation in (
            lambda value: value.update({"foundationRef": "client-owned"}),
            lambda value: value["project"].update({"authorityRef": "client-owned"}),
            lambda value: value["project"].update({"defaultDurationSec": True}),
            lambda value: value["project"].update({"defaultDurationSec": 1.9}),
            lambda value: value["project"].update({"defaultDurationSec": "60"}),
        ):
            invalid = copy.deepcopy(command)
            mutation(invalid)
            status, _headers, payload = self.harness.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, invalid
            )
            self.assertEqual(400, status)
            self.assertEqual("invalid_project_foundation", payload["error"]["code"])

        canonical = json.dumps(command, separators=(",", ":"))
        for token in ("NaN", "Infinity", "-Infinity", "1e999"):
            raw = canonical.replace('"defaultDurationSec":60', f'"defaultDurationSec":{token}')
            status, headers, payload = self.harness.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
                body=raw.encode("utf-8"),
            )
            self.assertEqual(400, status)
            self.assertEqual("application/json; charset=utf-8", headers["Content-Type"])
            self.assertEqual("invalid_request", payload["error"]["code"])

        missing_plan = self.episode_command(
            {"creativePlanRef": "creative-plan-not-confirmed"},
            key="missing-plan",
        )
        status, _headers, payload = self.harness.post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, missing_plan
        )
        self.assertEqual(409, status)
        self.assertEqual("creative_plan_not_confirmed", payload["error"]["code"])
        self.assertEqual((0, 0, 0, 1), self.harness.counts())

        status, _headers, payload = self.harness.get(
            f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/unknown-foundation"
        )
        self.assertEqual(404, status)
        self.assertEqual("project_foundation_not_found", payload["error"]["code"])

    def test_changed_replay_and_foreign_workspace_never_mix_or_disclose(self):
        status, _headers, created = self.harness.post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, valid_command()
        )
        self.assertEqual(201, status)
        changed = valid_command()
        changed["project"]["title"] = "Changed title"
        status, _headers, payload = self.harness.post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, changed
        )
        self.assertEqual(409, status)
        self.assertEqual(
            "project_foundation_idempotency_conflict",
            payload["error"]["code"],
        )
        self.assertEqual((1, 1, 0, 1), self.harness.counts())

        foreign_token = secrets.token_urlsafe(48)
        foreign = FoundationHttpHarness(
            self.path,
            initialize=False,
            authenticator=PublicApiAuthenticator.for_token(
                foreign_token, FOREIGN_WORKSPACE
            ),
        )
        foreign.token = foreign_token
        try:
            foundation_ref = created["foundation"]["foundationRef"]
            status, _headers, payload = foreign.get(
                f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/{foundation_ref}"
            )
            self.assertEqual(404, status)
            self.assertEqual(
                "project_foundation_not_found", payload["error"]["code"]
            )
            status, _headers, foreign_created = foreign.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, valid_command()
            )
            self.assertEqual(201, status)
            self.assertNotEqual(
                foundation_ref,
                foreign_created["foundation"]["foundationRef"],
            )
            self.assertEqual((1, 1, 0, 1), foreign.counts(FOREIGN_WORKSPACE))
        finally:
            foreign.close()

    def test_command_store_failures_are_bounded_json_and_server_recovers(self):
        self.harness.close()
        unavailable = FoundationHttpHarness(
            self.path,
            initialize=False,
            service_override=_UnavailableService(),
        )
        try:
            status, headers, payload = unavailable.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, valid_command()
            )
            self.assertEqual(503, status)
            self.assertEqual("application/json; charset=utf-8", headers["Content-Type"])
            self.assertEqual("project_foundation_unavailable", payload["error"]["code"])
        finally:
            unavailable.close()

        recovery = FoundationHttpHarness(self.path, initialize=False)
        delegate = recovery.foundation_service
        recovery.close()
        recovery = FoundationHttpHarness(
            self.path,
            initialize=False,
            service_override=_UnexpectedOnceService(delegate),
        )
        try:
            status, headers, payload = recovery.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, valid_command()
            )
            self.assertEqual(500, status)
            self.assertEqual("application/json; charset=utf-8", headers["Content-Type"])
            self.assertEqual("application_error", payload["error"]["code"])
            self.assertNotIn(str(self.path), json.dumps(payload))
            status, _headers, payload = recovery.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, valid_command()
            )
            self.assertEqual(201, status)
            self.assertEqual("COMPLETED", payload["foundation"]["state"])
        finally:
            recovery.close()

    def test_legacy_series_project_and_episode_routes_remain_compatible(self):
        plan = self.harness.confirm_plan()
        status, _headers, series_payload = self.harness.post(
            PUBLIC_SERIES_ENDPOINT,
            {
                "contentProfileRef": PROFILE,
                "title": "Legacy Series",
                "description": "Existing request shape",
                "plannedEpisodeCount": 4,
            },
        )
        self.assertEqual(201, status)
        series = series_payload["series"]
        status, _headers, project_payload = self.harness.post(
            PUBLIC_PROJECTS_ENDPOINT,
            {
                "contentProfileRef": PROFILE,
                "projectType": "series",
                "seriesRef": series["seriesRef"],
                "title": "Legacy Project",
                "description": "Existing request shape",
                "targetPlatform": "streaming",
                "aspectRatio": "16:9",
                "defaultDurationSec": 60,
                "plannedEpisodeCount": 4,
            },
        )
        self.assertEqual(201, status)
        self.assertIn("project", project_payload)
        status, _headers, episode_payload = self.harness.post(
            PUBLIC_EPISODES_ENDPOINT,
            {
                "seriesRef": series["seriesRef"],
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "seasonNumber": 1,
                "volumeNumber": 1,
                "title": "Legacy Episode",
            },
        )
        self.assertEqual(201, status)
        self.assertIn("episode", episode_payload)
        status, _headers, payload = self.harness.post(
            "/creator/internal/project-foundations", valid_command()
        )
        self.assertEqual(404, status)
        self.assertEqual("not_found", payload["error"]["code"])


class CreatorProjectFoundationFaultAndRestartTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    @staticmethod
    def episode_command(plan, key):
        return valid_command(
            key=key,
            episode={
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "seasonNumber": 1,
                "volumeNumber": 1,
                "title": "Episode 001",
            },
        )

    def test_all_precommit_faults_leave_pending_and_restart_recovers_atomically(self):
        points = (
            "after-intent-commit",
            "after-series-create",
            "after-project-create",
            "after-episode-create",
            "before-result-receipt-update",
        )
        for index, point in enumerate(points, start=1):
            with self.subTest(point=point):
                path = Path(self.directory.name) / f"fault-{index}.sqlite3"
                failed = FoundationHttpHarness(
                    path,
                    fault_hook=_OneShotFault(point),
                )
                plan = failed.confirm_plan()
                command = self.episode_command(plan, f"fault-key-{index}")
                try:
                    status, _headers, payload = failed.post(
                        PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, command
                    )
                    self.assertEqual(500, status)
                    self.assertEqual("application_error", payload["error"]["code"])
                    self.assertEqual((0, 0, 0, 1), failed.counts())
                    with sqlite3.connect(path) as connection:
                        row = connection.execute(
                            f"SELECT state,result_json,result_digest FROM {TABLE}"
                        ).fetchone()
                    self.assertEqual(("PENDING", None, None), row)
                finally:
                    failed.close()

                recovered = FoundationHttpHarness(path, initialize=False)
                try:
                    status, _headers, payload = recovered.post(
                        PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, command
                    )
                    self.assertEqual(200, status)
                    self.assertTrue(payload["recoveredFromPending"])
                    self.assertFalse(payload["idempotentReplay"])
                    self.assertEqual((1, 1, 1, 1), recovered.counts())
                finally:
                    recovered.close()

    def test_commit_then_response_failure_replays_the_committed_refs(self):
        path = Path(self.directory.name) / "response-loss.sqlite3"
        failed = FoundationHttpHarness(
            path,
            fault_hook=_OneShotFault(
                "after-transaction-commit-before-http-response"
            ),
        )
        command = valid_command(key="response-loss-key")
        try:
            status, _headers, payload = failed.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, command
            )
            self.assertEqual(500, status)
            self.assertEqual("application_error", payload["error"]["code"])
            self.assertEqual((1, 1, 0, 1), failed.counts())
            with sqlite3.connect(path) as connection:
                stored_result = json.loads(
                    connection.execute(
                        f"SELECT result_json FROM {TABLE}"
                    ).fetchone()[0]
                )
        finally:
            failed.close()

        replayed = FoundationHttpHarness(path, initialize=False)
        try:
            status, _headers, payload = replayed.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, command
            )
            self.assertEqual(200, status)
            self.assertTrue(payload["idempotentReplay"])
            self.assertEqual(stored_result, payload["foundation"])
            self.assertEqual((1, 1, 0, 1), replayed.counts())
        finally:
            replayed.close()

    def test_completed_command_survives_full_sqlite_server_restart(self):
        path = Path(self.directory.name) / "restart.sqlite3"
        first = FoundationHttpHarness(path)
        first.receipt_service = create_local_development_receipt_service(path)
        plan = first.confirm_plan()
        command = self.episode_command(plan, "restart-key")
        try:
            status, _headers, created = first.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, command
            )
            self.assertEqual(201, status)
            foundation = created["foundation"]
        finally:
            first.close()

        validate_lifecycle_database(path)
        second_receipts = create_local_development_receipt_service(path)
        second = FoundationHttpHarness(
            path,
            initialize=False,
            receipt_service=second_receipts,
        )
        try:
            status, _headers, fetched = second.get(
                f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/{foundation['foundationRef']}"
            )
            self.assertEqual(200, status)
            self.assertEqual(foundation, fetched["foundation"])
            status, _headers, replay = second.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, command
            )
            self.assertEqual(200, status)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(foundation, replay["foundation"])
            changed = copy.deepcopy(command)
            changed["series"]["title"] = "Changed after restart"
            status, _headers, payload = second.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT, changed
            )
            self.assertEqual(409, status)
            self.assertEqual(
                "project_foundation_idempotency_conflict",
                payload["error"]["code"],
            )
            self.assertEqual((1, 1, 1, 1), second.counts())
            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    f"SELECT request_json,request_digest,result_json,result_digest "
                    f"FROM {TABLE}"
                ).fetchone()
                self.assertEqual(
                    sha256(row[0].encode()).hexdigest(), row[1]
                )
                self.assertEqual(
                    sha256(row[2].encode()).hexdigest(), row[3]
                )
                self.assertEqual(
                    2,
                    connection.execute(
                        "SELECT MIN(schema_version) FROM ("
                        "SELECT schema_version FROM v5_series_episode_schema UNION ALL "
                        "SELECT schema_version FROM v5_project_schema UNION ALL "
                        "SELECT schema_version FROM v5_script_studio_schema UNION ALL "
                        "SELECT schema_version FROM v5_series_planning_schema)"
                    ).fetchone()[0],
                )
                self.assertIsNotNone(
                    connection.execute(
                        "SELECT 1 FROM creator_series_director_schema"
                    ).fetchone()
                )
        finally:
            second.close()

        foreign_token = secrets.token_urlsafe(48)
        foreign = FoundationHttpHarness(
            path,
            initialize=False,
            authenticator=PublicApiAuthenticator.for_token(
                foreign_token, FOREIGN_WORKSPACE
            ),
        )
        foreign.token = foreign_token
        try:
            status, _headers, payload = foreign.get(
                f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/{foundation['foundationRef']}"
            )
            self.assertEqual(404, status)
            self.assertEqual(
                "project_foundation_not_found", payload["error"]["code"]
            )
        finally:
            foreign.close()


class CreatorProjectFoundationConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.sequence = 0

    def harness(self, name, *, authenticator=None):
        self.sequence += 1
        return FoundationHttpHarness(
            Path(self.directory.name) / f"{name}-{self.sequence}.sqlite3",
            authenticator=authenticator,
        )

    @staticmethod
    def concurrent_posts(harness, calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)

        def run(index, token, command):
            barrier.wait(timeout=10)
            results[index] = harness.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
                command,
                token=token,
            )

        threads = [
            threading.Thread(target=run, args=(index, token, command))
            for index, (token, command) in enumerate(calls)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        if any(thread.is_alive() for thread in threads):
            raise AssertionError("concurrent Project foundation request did not finish")
        return results

    def test_concurrent_exact_commands_share_one_result_and_leave_no_lock(self):
        harness = self.harness("same")
        try:
            command = valid_command()
            results = self.concurrent_posts(
                harness,
                ((harness.token, command), (harness.token, copy.deepcopy(command))),
            )
            self.assertEqual([200, 201], sorted(item[0] for item in results))
            foundations = [item[2]["foundation"] for item in results]
            self.assertEqual(foundations[0], foundations[1])
            self.assertEqual((1, 1, 0, 1), harness.counts())
            status, _headers, _payload = harness.post(
                PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
                valid_command(key="subsequent-key"),
            )
            self.assertEqual(201, status)
        finally:
            harness.close()

    def test_concurrent_changed_command_has_one_winner_and_no_mixed_result(self):
        harness = self.harness("changed")
        try:
            first = valid_command()
            second = copy.deepcopy(first)
            second["project"]["title"] = "Concurrent changed title"
            results = self.concurrent_posts(
                harness,
                ((harness.token, first), (harness.token, second)),
            )
            self.assertEqual([201, 409], sorted(item[0] for item in results))
            winner = next(item[2] for item in results if item[0] == 201)
            conflict = next(item[2] for item in results if item[0] == 409)
            self.assertEqual(
                "project_foundation_idempotency_conflict",
                conflict["error"]["code"],
            )
            self.assertIn(
                winner["foundation"]["project"]["title"],
                {"Wanlight Project", "Concurrent changed title"},
            )
            self.assertEqual((1, 1, 0, 1), harness.counts())
        finally:
            harness.close()

    def test_different_keys_and_workspaces_are_independent(self):
        harness = self.harness("different-keys")
        try:
            first = valid_command(key="key-a")
            second = valid_command(key="key-b")
            results = self.concurrent_posts(
                harness,
                ((harness.token, first), (harness.token, second)),
            )
            self.assertEqual([201, 201], sorted(item[0] for item in results))
            refs = {item[2]["foundation"]["foundationRef"] for item in results}
            self.assertEqual(2, len(refs))
            self.assertEqual((2, 2, 0, 2), harness.counts())
        finally:
            harness.close()

        token_a = secrets.token_urlsafe(48)
        token_b = secrets.token_urlsafe(48)
        authenticator = PublicApiAuthenticator.from_mapping(
            {
                "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
                "credentials": [
                    {
                        "credentialRef": "foundation-credential-a",
                        "workspaceRef": WORKSPACE,
                        "tokenSha256": token_sha256(token_a),
                        "enabled": True,
                    },
                    {
                        "credentialRef": "foundation-credential-b",
                        "workspaceRef": FOREIGN_WORKSPACE,
                        "tokenSha256": token_sha256(token_b),
                        "enabled": True,
                    },
                ],
            }
        )
        scoped = self.harness("different-workspaces", authenticator=authenticator)
        try:
            command = valid_command(key="shared-key")
            results = self.concurrent_posts(
                scoped,
                ((token_a, command), (token_b, copy.deepcopy(command))),
            )
            self.assertEqual([201, 201], sorted(item[0] for item in results))
            refs = {item[2]["foundation"]["foundationRef"] for item in results}
            self.assertEqual(2, len(refs))
            self.assertEqual((1, 1, 0, 1), scoped.counts(WORKSPACE))
            self.assertEqual((1, 1, 0, 1), scoped.counts(FOREIGN_WORKSPACE))
        finally:
            scoped.close()


if __name__ == "__main__":
    unittest.main()
