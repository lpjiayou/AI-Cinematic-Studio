import json
import math
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import unittest
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    CAPABILITIES_ENDPOINT,
    PUBLIC_CONFIRM_PLAN_ENDPOINT,
    PUBLIC_EPISODES_ENDPOINT,
    PUBLIC_PROJECTS_ENDPOINT,
    PUBLIC_SERIES_ENDPOINT,
)
from apps.creator_workspace_mvp.server import MAX_REQUEST_BYTES, create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_episode import SeriesEpisodePublicError
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


WORKSPACE = "workspace-public-json-integrity"
PROFILE = "content-profile-public-json-integrity"


def _reject_nonstandard_constant(token):
    raise ValueError(f"non-standard JSON constant: {token}")


def _strict_loads(raw):
    return json.loads(raw.decode("utf-8"), parse_constant=_reject_nonstandard_constant)


class _NonFiniteProjectProjection:
    def __init__(self, delegate):
        self._delegate = delegate

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def list_projects(self, workspace_ref):
        return [{"workspaceRef": workspace_ref, "defaultDurationSec": math.nan}]


class _CountingProjectBoundary:
    def __init__(self, delegate):
        self._delegate = delegate
        self.create_calls = 0

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def create_project(self, command):
        self.create_calls += 1
        return self._delegate.create_project(command)


class CreatorPublicJsonNumericIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "creator.sqlite3"
        self.assembly = LifecycleAssembly.sqlite(
            self.database_path,
            initialize_or_upgrade=True,
        )
        self.capability = FakeTextGenerationCapability(
            [json.dumps(valid_plan(), ensure_ascii=False)] * 4
        )
        self.token = secrets.token_urlsafe(48)
        self.project_boundary = _CountingProjectBoundary(self.assembly.project_context)
        self.server = self._new_server(self.project_boundary)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self._stop_server)

    def _new_server(self, project_boundary):
        return create_server(
            ("127.0.0.1", 0),
            AiDirectorService(self.capability),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=project_boundary,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_boundary=self.assembly.script_studio,
            public_authenticator=PublicApiAuthenticator.for_token(
                self.token,
                WORKSPACE,
            ),
            allow_internal_routes=False,
            canonical_registration_boundary=self.assembly.canonical_registration,
        )

    def _stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.server = None

    def _raw_post(self, path, body):
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            response = request.urlopen(req, timeout=5)
        except error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()
        with response:
            return response.status, dict(response.headers.items()), response.read()

    def _post(self, path, payload):
        return self._raw_post(
            path,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    def _get(self, path):
        req = request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            response = request.urlopen(req, timeout=5)
        except error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()
        with response:
            return response.status, dict(response.headers.items()), response.read()

    def _database_counts(self):
        with sqlite3.connect(self.database_path) as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            return {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in tables
            }

    @staticmethod
    def _project_json(probe_fragment, *, title="JSON depth probe"):
        prefix = json.dumps(
            {
                "contentProfileRef": PROFILE,
                "projectType": "standalone",
                "title": title,
                "defaultDurationSec": 60,
                "plannedEpisodeCount": 1,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )[:-1]
        return f'{prefix},"probe":{probe_fragment}}}'.encode("utf-8")

    def assert_invalid_request_without_writes(self, body):
        before = self._database_counts()
        calls_before = self.project_boundary.create_calls
        status, headers, raw = self._raw_post(PUBLIC_PROJECTS_ENDPOINT, body)
        after = self._database_counts()
        calls_after = self.project_boundary.create_calls
        payload = _strict_loads(raw)
        self.assertEqual(
            (
                status,
                headers.get("Content-Type"),
                payload["error"]["code"],
                calls_after,
                after,
            ),
            (
                400,
                "application/json; charset=utf-8",
                "invalid_request",
                calls_before,
                before,
            ),
        )
        serialized = raw.decode("utf-8")
        self.assertNotIn("Traceback", serialized)
        self.assertNotIn(str(self.database_path), serialized)
        self.assertNotIn(self.token, serialized)

    def test_strict_json_rejects_invalid_text_constants_numbers_and_shapes(self):
        invalid_cases = {
            "invalid-utf8": b'{"title":"\xff"}',
            "malformed-json": b'{"title":1e+}',
            "nan": self._project_json("NaN"),
            "infinity": self._project_json("Infinity"),
            "negative-infinity": self._project_json("-Infinity"),
            "overflow-float": self._project_json("1e999"),
            "long-number-token": self._project_json("1" * 129),
            "non-object": b"[]",
        }
        for label, body in invalid_cases.items():
            with self.subTest(label=label):
                self.assertLess(len(body), MAX_REQUEST_BYTES)
                self.assert_invalid_request_without_writes(body)

    def test_json_depth_limit_is_exact_and_string_escape_aware(self):
        depth_64 = self._project_json(
            "[" * 63 + json.dumps('brackets [ { and escaped quote "') + "]" * 63,
            title="Depth 64",
        )
        self.assertLess(len(depth_64), MAX_REQUEST_BYTES)
        status, _, raw = self._raw_post(PUBLIC_PROJECTS_ENDPOINT, depth_64)
        self.assertEqual(status, 201)
        self.assertTrue(_strict_loads(raw)["ok"])

        depth_65 = self._project_json("[" * 64 + "0" + "]" * 64, title="Depth 65")
        self.assert_invalid_request_without_writes(depth_65)

    def test_twenty_five_thousand_levels_are_rejected_and_server_survives(self):
        body = self._project_json("[" * 25_000 + "0" + "]" * 25_000)
        self.assertLess(len(body), MAX_REQUEST_BYTES)
        self.assert_invalid_request_without_writes(body)

        status, _, raw = self._post(
            PUBLIC_PROJECTS_ENDPOINT,
            {
                "contentProfileRef": PROFILE,
                "projectType": "standalone",
                "title": "Valid after rejected request",
                "defaultDurationSec": 60,
                "plannedEpisodeCount": 1,
            },
        )
        self.assertEqual(status, 201)
        self.assertTrue(_strict_loads(raw)["ok"])

    def test_fractional_public_integer_fields_leave_no_durable_facts(self):
        commands = (
            (
                "project defaultDurationSec",
                PUBLIC_PROJECTS_ENDPOINT,
                {
                    "contentProfileRef": PROFILE,
                    "projectType": "standalone",
                    "title": "Fractional project duration",
                    "defaultDurationSec": 1.9,
                    "plannedEpisodeCount": 1,
                },
            ),
            (
                "project plannedEpisodeCount",
                PUBLIC_PROJECTS_ENDPOINT,
                {
                    "contentProfileRef": PROFILE,
                    "projectType": "standalone",
                    "title": "Fractional project",
                    "defaultDurationSec": 60,
                    "plannedEpisodeCount": 1.9,
                },
            ),
            (
                "series plannedEpisodeCount",
                PUBLIC_SERIES_ENDPOINT,
                {
                    "contentProfileRef": PROFILE,
                    "title": "Fractional series",
                    "plannedEpisodeCount": 1.9,
                },
            ),
            (
                "creative plan sourcePlanVersion",
                PUBLIC_CONFIRM_PLAN_ENDPOINT,
                {
                    "humanConfirmed": True,
                    "sourcePlanRef": "candidate-fractional-version",
                    "sourcePlanVersion": 1.9,
                    "brief": valid_brief(),
                    "plan": valid_plan(),
                },
            ),
        )
        for label, path, payload in commands:
            with self.subTest(label=label):
                before = self._database_counts()
                status, _, raw = self._post(path, payload)
                after = self._database_counts()
                parsed = _strict_loads(raw)
                self.assertEqual((status, parsed["ok"], after), (400, False, before))

    def test_fractional_episode_numbers_leave_no_episode_or_binding(self):
        status, _, raw = self._post(
            PUBLIC_SERIES_ENDPOINT,
            {
                "contentProfileRef": PROFILE,
                "title": "Episode integer parent",
                "plannedEpisodeCount": 3,
            },
        )
        self.assertEqual(status, 201)
        series = _strict_loads(raw)["series"]
        status, _, raw = self._post(
            PUBLIC_CONFIRM_PLAN_ENDPOINT,
            {
                "humanConfirmed": True,
                "sourcePlanRef": "candidate-episode-integer",
                "sourcePlanVersion": 1,
                "brief": valid_brief(),
                "plan": valid_plan(),
            },
        )
        self.assertEqual(status, 201)
        confirmed = _strict_loads(raw)["confirmedPlan"]

        for field in ("episodeNumber", "seasonNumber", "volumeNumber"):
            command = {
                "seriesRef": series["seriesRef"],
                "creativePlanRef": confirmed["creativePlanRef"],
                "episodeNumber": 1,
                "seasonNumber": 1,
                "volumeNumber": 1,
                "title": "Fractional episode",
            }
            command[field] = 1.9
            with self.subTest(field=field):
                before = self._database_counts()
                status, _, raw = self._post(PUBLIC_EPISODES_ENDPOINT, command)
                after = self._database_counts()
                parsed = _strict_loads(raw)
                self.assertEqual((status, parsed["ok"], after), (400, False, before))

    def test_nonfinite_confirm_is_rejected_before_any_sqlite_write(self):
        plan = valid_plan()
        plan["storyboardPlan"][0]["durationSec"] = math.nan
        command = {
            "workspaceRef": WORKSPACE,
            "humanConfirmed": True,
            "sourcePlanRef": "candidate-nonfinite",
            "sourcePlanSchemaVersion": plan["schemaVersion"],
            "sourcePlanVersion": 1,
            "brief": valid_brief(),
            "sourcePlan": plan,
        }
        before = self._database_counts()
        rejected = False
        try:
            self.assembly.series_episode.confirm_creative_plan(command)
        except SeriesEpisodePublicError:
            rejected = True
        after = self._database_counts()
        self.assertEqual((rejected, after), (True, before))

    def test_valid_plan_confirm_and_episode_survive_sqlite_restart(self):
        series = self.assembly.series_episode.create_series(
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "title": "Restart series",
                "plannedEpisodeCount": 1,
            }
        )
        plan = valid_plan()
        confirmed = self.assembly.series_episode.confirm_creative_plan(
            {
                "workspaceRef": WORKSPACE,
                "humanConfirmed": True,
                "sourcePlanRef": "candidate-restart",
                "sourcePlanSchemaVersion": plan["schemaVersion"],
                "sourcePlanVersion": 1,
                "brief": valid_brief(),
                "sourcePlan": plan,
            }
        )
        episode = self.assembly.series_episode.create_episode(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "creativePlanRef": confirmed["creativePlanRef"],
                "episodeNumber": 1,
                "seasonNumber": 1,
                "volumeNumber": 1,
                "title": "Restart episode",
            }
        )

        restarted = LifecycleAssembly.sqlite(self.database_path)
        restored = restarted.series_episode.get_episode(
            WORKSPACE,
            series["seriesRef"],
            episode["episodeRef"],
        )
        self.assertEqual(restored["creativePlanRef"], confirmed["creativePlanRef"])
        _strict_loads(json.dumps(restored, ensure_ascii=False, allow_nan=False).encode("utf-8"))

    def test_nonfinite_public_projection_returns_safe_standard_json_500(self):
        self._stop_server()
        self.server = self._new_server(
            _NonFiniteProjectProjection(self.assembly.project_context)
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

        status, headers, raw = self._get(PUBLIC_PROJECTS_ENDPOINT)
        payload = _strict_loads(raw)
        self.assertEqual(
            (status, headers.get("Content-Type"), payload["error"]["code"]),
            (500, "application/json; charset=utf-8", "application_error"),
        )
        serialized = raw.decode("utf-8")
        self.assertNotIn("NaN", serialized)
        self.assertNotIn("Infinity", serialized)
        self.assertNotIn(self.token, serialized)

    def test_valid_capability_response_is_strict_standard_json(self):
        status, headers, raw = self._get(CAPABILITIES_ENDPOINT)
        payload = _strict_loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(payload["schemaVersion"], "creator.public.capabilities.v1")


if __name__ == "__main__":
    unittest.main()
