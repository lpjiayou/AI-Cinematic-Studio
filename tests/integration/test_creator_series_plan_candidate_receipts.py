import copy
from hashlib import sha256
import json
import secrets
import sqlite3
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
    PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
)
from apps.creator_workspace_mvp.series_director import SeriesDirectorApplicationService
from apps.creator_workspace_mvp.series_plan_candidate_receipts import (
    CANDIDATE_RECEIPT_SCHEMA_VERSION,
    InMemorySeriesPlanCandidateReceiptStore,
    SeriesPlanCandidateReceiptService,
    build_series_plan_candidate_context,
    canonical_json_digest,
    create_local_development_receipt_service,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_intelligence.migration import (
    SeriesIntelligenceMigrationError,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE = "workspace-candidate-receipts"
PROFILE = "content-profile-candidate-receipts"


class CreatorSeriesPlanCandidateReceiptHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assembly = LifecycleAssembly.in_memory()
        self.series_a, self.project_a = self._create_series_project("A")
        self.series_b, self.project_b = self._create_series_project("B")
        self.standalone = self.assembly.project_context.create_project(
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "projectType": "standalone",
                "title": "Standalone",
                "plannedEpisodeCount": 4,
            }
        )
        self.text_generation = FakeTextGenerationCapability(
            [
                json.dumps(valid_candidate(), ensure_ascii=False),
                json.dumps(valid_candidate(), ensure_ascii=False),
            ]
        )
        self.receipt_store = InMemorySeriesPlanCandidateReceiptStore()
        self.receipt_service = SeriesPlanCandidateReceiptService(
            self.receipt_store
        )
        self.token = secrets.token_urlsafe(48)
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_director_service=SeriesDirectorApplicationService(
                self.text_generation
            ),
            series_plan_candidate_receipt_service=self.receipt_service,
            series_planning_boundary=self.assembly.series_planning,
            public_authenticator=PublicApiAuthenticator.for_token(
                self.token, WORKSPACE
            ),
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def workspace(self, project, series):
        return self.assembly.series_planning.get_workspace(
            WORKSPACE,
            project["projectRef"],
            series["seriesRef"],
        )

    def generate(self, project=None, series=None, creative_input="Plan it"):
        project = project or self.project_a
        series = series or self.series_a
        return self.post(
            PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
            {
                "projectRef": project["projectRef"],
                "seriesRef": series["seriesRef"],
                "creativeInput": creative_input,
            },
        )

    def confirm(
        self,
        generated,
        *,
        project=None,
        series=None,
        candidate=None,
        candidate_ref=True,
        human_confirmed=True,
    ):
        project = project or self.project_a
        series = series or self.series_a
        payload = {
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": human_confirmed,
            "candidate": candidate if candidate is not None else generated["candidate"],
        }
        if candidate_ref is True:
            payload["candidateRef"] = generated["candidateRef"]
        elif isinstance(candidate_ref, str):
            payload["candidateRef"] = candidate_ref
        return self.post(PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT, payload)

    def _create_series_project(self, suffix: str):
        series = self.assembly.series_episode.create_series(
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "title": f"Series {suffix}",
                "plannedEpisodeCount": 4,
            }
        )
        project = self.assembly.project_context.create_project(
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "projectType": "series",
                "seriesRef": series["seriesRef"],
                "title": f"Project {suffix}",
                "plannedEpisodeCount": 4,
            }
        )
        return series, project

    def post(self, path: str, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            response = request.urlopen(http_request, timeout=5)
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_standalone_without_series_is_stable_zero_write_rejection_and_server_recovers(
        self,
    ) -> None:
        before_a = self.workspace(self.project_a, self.series_a)
        before_b = self.workspace(self.project_b, self.series_b)
        status, payload = self.post(
            PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
            {
                "projectRef": self.standalone["projectRef"],
                "creativeInput": "Create a standalone plan",
            },
        )
        self.assertEqual(409, status)
        self.assertEqual({"ok", "error"}, set(payload))
        self.assertEqual("series_scope_required", payload["error"]["code"])
        self.assertIsInstance(payload["error"]["message"], str)
        self.assertNotIn("TypeError", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(0, len(self.text_generation.commands))
        self.assertEqual(0, self.receipt_store.count())
        self.assertEqual(before_a, self.workspace(self.project_a, self.series_a))
        self.assertEqual(before_b, self.workspace(self.project_b, self.series_b))

        valid_status, valid_payload = self.post(
            PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
            {
                "projectRef": self.project_a["projectRef"],
                "seriesRef": self.series_a["seriesRef"],
                "creativeInput": "Create a valid Series plan",
            },
        )
        self.assertEqual(200, valid_status)
        self.assertTrue(valid_payload["ok"])
        self.assertEqual(1, len(self.text_generation.commands))
        self.assertEqual(1, self.receipt_store.count())

    def test_wrong_and_foreign_series_keep_scope_errors_before_provider(self):
        missing_status, missing = self.post(
            PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
            {
                "projectRef": self.project_a["projectRef"],
                "seriesRef": "series-missing",
                "creativeInput": "Do not call the provider",
            },
        )
        self.assertEqual(400, missing_status)
        self.assertEqual("scope_mismatch", missing["error"]["code"])

        foreign_status, foreign = self.generate(
            self.project_a, self.series_b, "Still do not call the provider"
        )
        self.assertEqual(400, foreign_status)
        self.assertEqual("scope_mismatch", foreign["error"]["code"])
        self.assertEqual(0, len(self.text_generation.commands))
        self.assertEqual(0, self.receipt_store.count())

    def test_generation_returns_server_receipt_metadata_and_never_raw_input(self):
        creative_input = "private raw creative direction"
        status, payload = self.generate(creative_input=creative_input)
        self.assertEqual(200, status)
        self.assertEqual(
            {
                "ok",
                "kind",
                "confirmationRequired",
                "candidateRef",
                "candidateDigest",
                "sourceContextDigest",
                "candidateReceiptSchemaVersion",
                "candidateReceiptReplay",
                "candidate",
            },
            set(payload),
        )
        self.assertTrue(payload["confirmationRequired"])
        self.assertFalse(payload["candidateReceiptReplay"])
        self.assertEqual(
            "creator.series-plan.candidate.v1",
            payload["candidate"]["schemaVersion"],
        )
        self.assertEqual(
            CANDIDATE_RECEIPT_SCHEMA_VERSION,
            payload["candidateReceiptSchemaVersion"],
        )
        self.assertTrue(payload["candidateRef"].startswith("series-plan-candidate-"))
        self.assertLessEqual(len(payload["candidateRef"]), 200)
        self.assertNotIn(creative_input, payload["candidateRef"])
        self.assertEqual(
            canonical_json_digest(payload["candidate"]),
            payload["candidateDigest"],
        )
        trusted = self.assembly.project_context.build_context(
            WORKSPACE,
            self.project_a["projectRef"],
            self.series_a["seriesRef"],
        )
        source = build_series_plan_candidate_context(trusted)["sourceContext"]
        self.assertEqual(
            canonical_json_digest(source), payload["sourceContextDigest"]
        )
        receipt = self.receipt_store.get(WORKSPACE, payload["candidateRef"])
        self.assertIsNotNone(receipt)
        self.assertEqual(
            sha256(creative_input.encode("utf-8")).hexdigest(),
            receipt.creativeInputDigest,
        )
        self.assertNotIn(creative_input, repr(receipt))
        self.assertIsNone(self.workspace(self.project_a, self.series_a)["plan"])

    def test_public_generation_rejects_client_receipt_claims_before_provider(self):
        forbidden = {
            "candidateRef": "browser-minted",
            "sourceProjectVersion": 1,
            "sourceSeriesVersion": 1,
            "sourceContextDigest": "0" * 64,
            "candidateDigest": "0" * 64,
            "creativeInputDigest": "0" * 64,
            "createdAt": "2026-09-05T00:00:00.000Z",
            "receiptJson": {},
            "databaseKey": "row-1",
            "authorityRef": "authority-1",
            "provider": "client-provider",
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                status, payload = self.post(
                    PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
                    {
                        "projectRef": self.project_a["projectRef"],
                        "seriesRef": self.series_a["seriesRef"],
                        "creativeInput": "Reject client provenance",
                        field: value,
                    },
                )
                self.assertEqual(400, status)
                self.assertEqual("invalid_request", payload["error"]["code"])
        self.assertEqual(0, len(self.text_generation.commands))
        self.assertEqual(0, self.receipt_store.count())

    def test_repeated_generation_reuses_one_unambiguous_receipt(self):
        self.text_generation._outcomes.extend(
            [
                json.dumps(valid_candidate(), ensure_ascii=False),
                json.dumps(valid_candidate(), ensure_ascii=False),
            ]
        )
        first_status, first = self.generate(creative_input="First wording")
        second_status, second = self.generate(creative_input="Second wording")
        self.assertEqual((200, 200), (first_status, second_status))
        self.assertEqual(first["candidateRef"], second["candidateRef"])
        self.assertFalse(first["candidateReceiptReplay"])
        self.assertTrue(second["candidateReceiptReplay"])
        self.assertEqual(1, self.receipt_store.count())

    def test_receipt_write_failure_and_invalid_provider_output_never_succeed(self):
        class FailingStore(InMemorySeriesPlanCandidateReceiptStore):
            def issue(self, receipt):
                raise RuntimeError("receipt storage unavailable")

        self.receipt_service.store = FailingStore()
        status, payload = self.generate(creative_input="Cannot be issued")
        self.assertEqual(503, status)
        self.assertFalse(payload["ok"])
        self.assertEqual(
            "series_plan_candidate_receipt_unavailable",
            payload["error"]["code"],
        )
        self.assertIsNone(self.workspace(self.project_a, self.series_a)["plan"])

        self.receipt_service.store = self.receipt_store
        invalid = {"schemaVersion": "creator.series-plan.candidate.v1"}
        self.text_generation._outcomes[:] = [
            json.dumps(invalid),
            json.dumps(invalid),
        ]
        invalid_status, invalid_payload = self.generate(
            creative_input="Provider stays invalid after repair"
        )
        self.assertEqual(200, invalid_status)
        self.assertFalse(invalid_payload["ok"])
        self.assertEqual(
            "invalid_provider_output",
            invalid_payload["error"]["code"],
        )
        self.assertEqual(0, self.receipt_store.count())

    def test_fractional_provider_integer_is_repaired_not_truncated(self):
        fractional = valid_candidate()
        fractional["episodePlanItems"][0]["episodeNumber"] = 1.9
        self.text_generation._outcomes[:] = [
            json.dumps(fractional, ensure_ascii=False),
            json.dumps(valid_candidate(), ensure_ascii=False),
        ]
        status, payload = self.generate(creative_input="Repair exact integers")
        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(2, len(self.text_generation.commands))
        self.assertEqual(
            1, payload["candidate"]["episodePlanItems"][0]["episodeNumber"]
        )
        self.assertEqual(1, self.receipt_store.count())

    def test_candidate_generated_for_project_a_cannot_confirm_project_b(self) -> None:
        generated_status, generated = self.post(
            PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
            {
                "projectRef": self.project_a["projectRef"],
                "seriesRef": self.series_a["seriesRef"],
                "creativeInput": "Create the Series A plan",
            },
        )
        self.assertEqual(200, generated_status)

        status, payload = self.post(
            PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
            {
                "projectRef": self.project_b["projectRef"],
                "seriesRef": self.series_b["seriesRef"],
                "humanConfirmed": True,
                "candidate": generated["candidate"],
            },
        )
        self.assertEqual(409, status)
        self.assertIn(
            payload["error"]["code"],
            {
                "series_plan_candidate_not_issued",
                "series_plan_candidate_scope_mismatch",
            },
        )
        workspace_b = self.assembly.series_planning.get_workspace(
            WORKSPACE,
            self.project_b["projectRef"],
            self.series_b["seriesRef"],
        )
        self.assertIsNone(workspace_b["plan"])

    def test_explicit_candidate_ref_confirms_only_resolved_stored_candidate(self):
        generated_status, generated = self.generate(
            creative_input="Confirm with the explicit server reference"
        )
        self.assertEqual(200, generated_status)

        observed = {}
        original_resolve = self.receipt_service.resolve
        original_confirm = self.assembly.series_planning.confirm_candidate

        def recording_resolve(context, candidate, *, candidate_ref=None):
            observed["requestCandidate"] = candidate
            resolved = original_resolve(
                context, candidate, candidate_ref=candidate_ref
            )
            observed["resolvedCandidate"] = resolved
            return resolved

        def recording_confirm(command):
            observed["boundaryCandidate"] = command["candidate"]
            return original_confirm(command)

        self.receipt_service.resolve = recording_resolve
        self.assembly.series_planning.confirm_candidate = recording_confirm
        status, payload = self.confirm(generated)
        self.assertEqual(201, status)
        self.assertTrue(payload["ok"])
        self.assertIs(
            observed["resolvedCandidate"], observed["boundaryCandidate"]
        )
        self.assertIsNot(
            observed["requestCandidate"], observed["boundaryCandidate"]
        )
        self.assertEqual(
            generated["candidate"]["premise"],
            payload["version"]["premise"],
        )

    def test_current_frontend_body_without_candidate_ref_is_securely_supported(self):
        generated_status, generated = self.generate(
            creative_input="Use the current Frontend request body"
        )
        self.assertEqual(200, generated_status)
        status, payload = self.confirm(generated, candidate_ref=False)
        self.assertEqual(201, status)
        self.assertEqual(
            payload["plan"]["confirmedSeriesPlanVersionRef"],
            payload["version"]["seriesPlanVersionRef"],
        )

    def test_unissued_candidate_fails_without_plan(self):
        raw_status, raw = self.post(
            PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
            {
                "projectRef": self.project_a["projectRef"],
                "seriesRef": self.series_a["seriesRef"],
                "humanConfirmed": True,
                "candidate": valid_candidate(),
            },
        )
        self.assertEqual(409, raw_status)
        self.assertEqual("series_plan_candidate_not_issued", raw["error"]["code"])
        self.assertIsNone(self.workspace(self.project_a, self.series_a)["plan"])

    def test_public_confirmation_rejects_metadata_changed_and_unknown_candidates(self):
        generated_status, generated = self.generate(
            creative_input="Issue before rejecting client metadata"
        )
        self.assertEqual(200, generated_status)
        forbidden = {
            "contentProfileRef": PROFILE,
            "sourceProjectVersion": 1,
            "sourceSeriesVersion": 1,
            "sourceContextDigest": generated["sourceContextDigest"],
            "candidateDigest": generated["candidateDigest"],
            "creativeInputDigest": "0" * 64,
            "createdAt": "2026-09-05T00:00:00.000Z",
            "receiptSchema": CANDIDATE_RECEIPT_SCHEMA_VERSION,
            "receiptJson": {},
            "databaseKey": "row-1",
            "authorityRef": "authority-1",
            "provider": "client-provider",
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                status, payload = self.post(
                    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
                    {
                        "projectRef": self.project_a["projectRef"],
                        "seriesRef": self.series_a["seriesRef"],
                        "humanConfirmed": True,
                        "candidateRef": generated["candidateRef"],
                        "candidate": generated["candidate"],
                        field: value,
                    },
                )
                self.assertEqual(400, status)
                self.assertEqual("invalid_request", payload["error"]["code"])
        self.assertIsNone(self.workspace(self.project_a, self.series_a)["plan"])

        generated_status, generated = self.generate(
            creative_input="Issue before mismatch checks"
        )
        self.assertEqual(200, generated_status)
        changed = copy.deepcopy(generated["candidate"])
        changed["premise"] = "Client-edited premise"
        changed_status, changed_payload = self.confirm(
            generated, candidate=changed
        )
        self.assertEqual(409, changed_status)
        self.assertEqual(
            "series_plan_candidate_content_mismatch",
            changed_payload["error"]["code"],
        )
        unknown_status, unknown_payload = self.confirm(
            generated, candidate_ref="series-plan-candidate-unknown"
        )
        self.assertEqual(409, unknown_status)
        self.assertEqual(
            "series_plan_candidate_not_issued",
            unknown_payload["error"]["code"],
        )
        self.assertIsNone(self.workspace(self.project_a, self.series_a)["plan"])

    def test_explicit_cross_scope_receipt_is_rejected_without_plan(self):
        generated_status, generated = self.generate(
            creative_input="Series A only"
        )
        self.assertEqual(200, generated_status)
        status, payload = self.confirm(
            generated,
            project=self.project_b,
            series=self.series_b,
        )
        self.assertEqual(409, status)
        self.assertEqual(
            "series_plan_candidate_scope_mismatch", payload["error"]["code"]
        )
        self.assertIsNone(self.workspace(self.project_b, self.series_b)["plan"])

    def test_stale_project_and_nonconfirmation_are_rejected_without_plan(self):
        generated_status, generated = self.generate(
            creative_input="Invalidate this Project context"
        )
        self.assertEqual(200, generated_status)
        false_status, false_payload = self.confirm(
            generated, human_confirmed=False
        )
        self.assertEqual(409, false_status)
        self.assertEqual(
            "series_plan_not_confirmed", false_payload["error"]["code"]
        )

        self.assembly.project_context.archive_project(
            WORKSPACE, self.project_a["projectRef"]
        )
        stale_status, stale_payload = self.confirm(generated)
        self.assertEqual(409, stale_status)
        self.assertEqual(
            "series_plan_candidate_stale", stale_payload["error"]["code"]
        )
        self.assertIsNone(self.workspace(self.project_a, self.series_a)["plan"])

    def test_stale_series_version_is_rejected_without_plan(self):
        generated_status, generated = self.generate(
            creative_input="Invalidate this Series context"
        )
        self.assertEqual(200, generated_status)
        original_build = self.assembly.project_context.build_context

        def stale_series_context(*args):
            context = copy.deepcopy(original_build(*args))
            context["series"]["version"] += 1
            return context

        self.assembly.project_context.build_context = stale_series_context
        try:
            status, payload = self.confirm(generated)
        finally:
            self.assembly.project_context.build_context = original_build
        self.assertEqual(409, status)
        self.assertEqual(
            "series_plan_candidate_stale", payload["error"]["code"]
        )
        self.assertIsNone(self.workspace(self.project_a, self.series_a)["plan"])

    def test_foreign_workspace_cannot_probe_candidate_reference(self):
        generated_status, generated = self.generate(
            creative_input="Do not disclose across workspaces"
        )
        self.assertEqual(200, generated_status)
        foreign_workspace = "workspace-candidate-receipts-foreign"
        foreign_series = self.assembly.series_episode.create_series(
            {
                "workspaceRef": foreign_workspace,
                "contentProfileRef": PROFILE,
                "title": "Foreign Series",
                "plannedEpisodeCount": 4,
            }
        )
        foreign_project = self.assembly.project_context.create_project(
            {
                "workspaceRef": foreign_workspace,
                "contentProfileRef": PROFILE,
                "projectType": "series",
                "seriesRef": foreign_series["seriesRef"],
                "title": "Foreign Project",
                "plannedEpisodeCount": 4,
            }
        )
        foreign_token = secrets.token_urlsafe(48)
        foreign_server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_director_service=SeriesDirectorApplicationService(
                FakeTextGenerationCapability([])
            ),
            series_plan_candidate_receipt_service=self.receipt_service,
            series_planning_boundary=self.assembly.series_planning,
            public_authenticator=PublicApiAuthenticator.for_token(
                foreign_token, foreign_workspace
            ),
            allow_internal_routes=False,
        )
        thread = threading.Thread(
            target=foreign_server.serve_forever, daemon=True
        )
        thread.start()
        self.addCleanup(foreign_server.server_close)
        self.addCleanup(foreign_server.shutdown)
        url = f"http://127.0.0.1:{foreign_server.server_port}"

        def foreign_confirm(candidate_ref):
            body = json.dumps(
                {
                    "projectRef": foreign_project["projectRef"],
                    "seriesRef": foreign_series["seriesRef"],
                    "humanConfirmed": True,
                    "candidateRef": candidate_ref,
                    "candidate": generated["candidate"],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            http_request = request.Request(
                f"{url}{PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT}",
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {foreign_token}",
                },
            )
            with self.assertRaises(error.HTTPError) as caught:
                request.urlopen(http_request, timeout=5)
            return caught.exception.code, json.loads(
                caught.exception.read().decode("utf-8")
            )

        issued_probe = foreign_confirm(generated["candidateRef"])
        unknown_probe = foreign_confirm("series-plan-candidate-unknown")
        self.assertEqual(issued_probe, unknown_probe)
        self.assertEqual(409, issued_probe[0])
        self.assertEqual(
            "series_plan_candidate_not_issued",
            issued_probe[1]["error"]["code"],
        )
        workspace = self.assembly.series_planning.get_workspace(
            foreign_workspace,
            foreign_project["projectRef"],
            foreign_series["seriesRef"],
        )
        self.assertIsNone(workspace["plan"])

    def test_duplicate_plan_behavior_remains_owned_by_series_planning(self):
        generated_status, generated = self.generate(
            creative_input="Confirm once only"
        )
        self.assertEqual(200, generated_status)
        first_status, _ = self.confirm(generated)
        second_status, second = self.confirm(generated)
        self.assertEqual(201, first_status)
        self.assertEqual(409, second_status)
        self.assertEqual("duplicate_record", second["error"]["code"])


class CreatorSeriesPlanCandidateReceiptSqliteRestartTests(unittest.TestCase):
    @staticmethod
    def _create_series_project(assembly, suffix):
        series = assembly.series_episode.create_series(
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "title": f"SQLite Series {suffix}",
                "plannedEpisodeCount": 4,
            }
        )
        project = assembly.project_context.create_project(
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "projectType": "series",
                "seriesRef": series["seriesRef"],
                "title": f"SQLite Project {suffix}",
                "plannedEpisodeCount": 4,
            }
        )
        return series, project

    @staticmethod
    def _v5_snapshot(path):
        with sqlite3.connect(path) as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name LIKE 'v5_%' ORDER BY name"
                )
            ]
            return {
                table: connection.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
                for table in tables
            }

    @staticmethod
    def _start_server(assembly, receipt_service, capability, token):
        server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=assembly.series_episode,
            project_boundary=assembly.project_context,
            series_director_service=SeriesDirectorApplicationService(
                capability
            ),
            series_plan_candidate_receipt_service=receipt_service,
            series_planning_boundary=assembly.series_planning,
            public_authenticator=PublicApiAuthenticator.for_token(
                token, WORKSPACE
            ),
            allow_internal_routes=False,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, f"http://127.0.0.1:{server.server_port}"

    @staticmethod
    def _stop_server(server, thread, receipt_service):
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        receipt_service.store.close()

    @staticmethod
    def _post(base_url, token, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            f"{base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            response = request.urlopen(http_request, timeout=5)
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_receipt_survives_real_server_restart_and_preserves_existing_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            first_assembly = LifecycleAssembly.sqlite(
                path, initialize_or_upgrade=True
            )
            series_a, project_a = self._create_series_project(
                first_assembly, "A"
            )
            series_b, project_b = self._create_series_project(
                first_assembly, "B"
            )
            before = self._v5_snapshot(path)
            token = secrets.token_urlsafe(48)
            first_receipts = create_local_development_receipt_service(path)
            first_capability = FakeTextGenerationCapability(
                [json.dumps(valid_candidate(), ensure_ascii=False)]
            )
            first_server, first_thread, first_url = self._start_server(
                first_assembly, first_receipts, first_capability, token
            )
            try:
                generated_status, generated = self._post(
                    first_url,
                    token,
                    PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
                    {
                        "projectRef": project_a["projectRef"],
                        "seriesRef": series_a["seriesRef"],
                        "creativeInput": "Persist only its digest",
                    },
                )
                self.assertEqual(200, generated_status)
            finally:
                self._stop_server(
                    first_server, first_thread, first_receipts
                )

            self.assertEqual(before, self._v5_snapshot(path))
            second_assembly = LifecycleAssembly.sqlite(path)
            self.assertEqual(before, self._v5_snapshot(path))
            second_receipts = create_local_development_receipt_service(path)
            second_capability = FakeTextGenerationCapability([])
            second_server, second_thread, second_url = self._start_server(
                second_assembly, second_receipts, second_capability, token
            )
            try:
                foreign_status, foreign = self._post(
                    second_url,
                    token,
                    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
                    {
                        "projectRef": project_b["projectRef"],
                        "seriesRef": series_b["seriesRef"],
                        "humanConfirmed": True,
                        "candidateRef": generated["candidateRef"],
                        "candidate": generated["candidate"],
                    },
                )
                self.assertEqual(409, foreign_status)
                self.assertEqual(
                    "series_plan_candidate_scope_mismatch",
                    foreign["error"]["code"],
                )
                self.assertIsNone(
                    second_assembly.series_planning.get_workspace(
                        WORKSPACE,
                        project_b["projectRef"],
                        series_b["seriesRef"],
                    )["plan"]
                )

                confirmed_status, confirmed = self._post(
                    second_url,
                    token,
                    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
                    {
                        "projectRef": project_a["projectRef"],
                        "seriesRef": series_a["seriesRef"],
                        "humanConfirmed": True,
                        "candidateRef": generated["candidateRef"],
                        "candidate": generated["candidate"],
                    },
                )
                self.assertEqual(201, confirmed_status)
                self.assertEqual(
                    confirmed["plan"]["confirmedSeriesPlanVersionRef"],
                    confirmed["version"]["seriesPlanVersionRef"],
                )
                self.assertEqual(0, len(second_capability.commands))
            finally:
                self._stop_server(
                    second_server, second_thread, second_receipts
                )

            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    2,
                    connection.execute(
                        "SELECT schema_version FROM v5_series_planning_schema "
                        "WHERE component='series_planning'"
                    ).fetchone()[0],
                )

    def test_tampered_receipt_blocks_real_lifecycle_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            assembly = LifecycleAssembly.sqlite(
                path, initialize_or_upgrade=True
            )
            series, project = self._create_series_project(assembly, "tamper")
            context = build_series_plan_candidate_context(
                assembly.project_context.build_context(
                    WORKSPACE, project["projectRef"], series["seriesRef"]
                )
            )
            receipts = create_local_development_receipt_service(path)
            receipt, _ = receipts.issue(
                context, "tamper only the digest", valid_candidate()
            )
            receipts.store.close()
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE creator_series_plan_candidate_receipts "
                    "SET source_context_digest = ? WHERE candidate_ref = ?",
                    ("0" * 64, receipt.candidateRef),
                )
            with self.assertRaises(SeriesIntelligenceMigrationError):
                LifecycleAssembly.sqlite(path)


if __name__ == "__main__":
    unittest.main()
