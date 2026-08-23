import copy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.server import create_server
from scripts import k2_canonical_lineage_api_verify as api_verify
from scripts import k2_canonical_lineage_bootstrap as bootstrap
from services.v5_core_os.text_generation import (
    create_unconfigured_text_generation_capability,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION = (
    REPOSITORY_ROOT
    / "experiments"
    / "k2-001-canonical-bootstrap"
    / "k2-001-canonical-bootstrap.v1.json"
)
TEST_COMMIT = "b" * 40


def applied_root(parent):
    specification = bootstrap.validate_specification(SPECIFICATION)
    target = parent / "canonical"
    bootstrap.apply_bootstrap(
        specification,
        target,
        acknowledgement=bootstrap.ACKNOWLEDGEMENT,
        repository_commit=TEST_COMMIT,
    )
    receipt = json.loads(
        (target / bootstrap.RECEIPT_FILENAME).read_text(encoding="utf-8")
    )
    lifecycle = bootstrap.LifecycleAssembly.sqlite(
        target / bootstrap.DATABASE_FILENAMES["lifecycle"],
        initialize_or_upgrade=False,
    )
    production = bootstrap._episode_boundary(
        lifecycle,
        bootstrap._paths(target),
        initialize_if_missing=False,
    )
    lineage = receipt["lineage"]
    workspace = lineage["workspaceRef"]
    series_ref = lineage["series"]["seriesRef"]
    project_ref = lineage["project"]["projectRef"]
    episode_ref = lineage["episode"]["episodeRef"]
    run_ref = lineage["episodeProductionRun"]["productionRunRef"]
    responses = {
        "series": {"ok": True, "series": lifecycle.series_episode.get_series(workspace, series_ref)},
        "project": {"ok": True, "project": lifecycle.project_context.get_project(workspace, project_ref)},
        "episode": {
            "ok": True,
            "episode": lifecycle.series_episode.get_episode(workspace, series_ref, episode_ref),
        },
        "seriesPlan": {
            "ok": True,
            "workspace": lifecycle.series_planning.get_workspace(workspace, project_ref, series_ref),
        },
        "script": {
            "ok": True,
            "workspace": lifecycle.script_studio.get_workspace(workspace, series_ref, episode_ref),
        },
        "productionRun": {"ok": True, "run": production.get_run(workspace, run_ref)},
        "productionRunList": {"ok": True, "runs": production.list_runs(workspace)},
    }
    return target, receipt, responses


def getter_for(responses):
    def get_json(path, query=None):
        del query
        if path == "/creator/api/v1/episode-production-runs":
            key = "productionRunList"
        elif path.startswith("/creator/api/v1/episode-production-runs/"):
            key = "productionRun"
        elif path.startswith("/creator/api/v1/series/"):
            key = "series"
        elif path.startswith("/creator/api/v1/projects/"):
            key = "project"
        elif path.startswith("/creator/api/v1/episodes/"):
            key = "episode"
        elif path == "/creator/api/v1/series-planning-workspaces":
            key = "seriesPlan"
        elif path == "/creator/api/v1/script-workspaces":
            key = "script"
        else:
            raise AssertionError(path)
        return copy.deepcopy(responses[key])

    return get_json


class K2CanonicalLineageApiVerifyTests(unittest.TestCase):
    def test_verifier_transport_is_get_only_and_has_no_database_dependency(self):
        source = (
            REPOSITORY_ROOT / "scripts" / "k2_canonical_lineage_api_verify.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"GET"', source)
        for forbidden in (
            '"POST"',
            '"PUT"',
            '"PATCH"',
            '"DELETE"',
            "import sqlite3",
            "sqlite3.connect",
            "from tests",
            "import tests",
            "services.v4",
            "services.v3",
        ):
            self.assertNotIn(forbidden, source)

    def test_real_authenticated_loopback_http_exact_match(self):
        with tempfile.TemporaryDirectory() as directory:
            target, receipt, _ = applied_root(Path(directory))
            assembly = bootstrap.LifecycleAssembly.sqlite(
                target / bootstrap.DATABASE_FILENAMES["lifecycle"],
                initialize_or_upgrade=False,
            )
            production = bootstrap._episode_boundary(
                assembly,
                bootstrap._paths(target),
                initialize_if_missing=False,
            )
            token = "test-only-loopback-bearer"
            server = create_server(
                ("127.0.0.1", 0),
                AiDirectorService(create_unconfigured_text_generation_capability()),
                series_episode_boundary=assembly.series_episode,
                project_boundary=assembly.project_context,
                series_planning_boundary=assembly.series_planning,
                series_intelligence_boundary=assembly.series_intelligence,
                script_studio_boundary=assembly.script_studio,
                episode_production_boundary=production,
                public_authenticator=PublicApiAuthenticator.for_token(
                    token,
                    receipt["lineage"]["workspaceRef"],
                ),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                origin = api_verify._validate_origin(
                    f"http://127.0.0.1:{server.server_port}"
                )
                resources, lineage = api_verify.verify_public_api(
                    receipt,
                    api_verify._http_getter(origin, token, 5.0),
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            self.assertEqual(len(resources), api_verify.RESOURCE_COUNT)
            self.assertEqual(lineage["state"], "ROOTS_READY")

    def test_exact_public_projection_passes_and_builds_secret_free_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            target, receipt, responses = applied_root(Path(directory))
            loaded, _, loaded_digest = api_verify._load_bootstrap_receipt(target)
            self.assertEqual(loaded, receipt)
            self.assertEqual(
                loaded_digest,
                sha256((target / bootstrap.RECEIPT_FILENAME).read_bytes()).hexdigest(),
            )
            resources, lineage = api_verify.verify_public_api(
                receipt, getter_for(responses)
            )
            self.assertEqual(len(resources), api_verify.RESOURCE_COUNT)
            bootstrap_receipt_path = target / bootstrap.RECEIPT_FILENAME
            verification = api_verify.build_verification_receipt(
                receipt,
                sha256(bootstrap_receipt_path.read_bytes()).hexdigest(),
                resources,
                lineage,
                verified_at="2026-08-21T00:00:00Z",
            )
            serialized = json.dumps(verification, ensure_ascii=False, sort_keys=True)
            self.assertEqual(
                verification["api"]["authentication"],
                "SERVER_TO_SERVER_BEARER_VERIFIED_NOT_RECORDED",
            )
            self.assertNotIn("test-only-bearer", serialized)
            self.assertEqual(verification["lineage"]["state"], "ROOTS_READY")
            self.assertEqual(verification["exitState"]["p1Gate"], "NOT_PASSED")
            self.assertFalse(verification["exitState"]["publicationAllowed"])

    def test_any_payload_digest_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            _, receipt, responses = applied_root(Path(directory))
            responses["productionRun"]["run"]["payloadDigest"] = "0" * 64
            with self.assertRaises(api_verify.ApiVerificationError) as caught:
                api_verify.verify_public_api(receipt, getter_for(responses))
            self.assertEqual(
                caught.exception.code,
                "api_production_run_payloadDigest_mismatch",
            )

    def test_extra_run_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            _, receipt, responses = applied_root(Path(directory))
            responses["productionRunList"]["runs"].append(
                copy.deepcopy(responses["productionRunList"]["runs"][0])
            )
            with self.assertRaises(api_verify.ApiVerificationError) as caught:
                api_verify.verify_public_api(receipt, getter_for(responses))
            self.assertEqual(caught.exception.code, "api_production_run_count_mismatch")

    def test_database_tamper_is_rejected_before_any_api_request(self):
        with tempfile.TemporaryDirectory() as directory:
            target, _, _ = applied_root(Path(directory))
            database = target / bootstrap.DATABASE_FILENAMES["providerExperiments"]
            with database.open("ab") as handle:
                handle.write(b"tamper")
            with self.assertRaises(api_verify.ApiVerificationError) as caught:
                api_verify._load_bootstrap_receipt(target)
            self.assertEqual(caught.exception.code, "bootstrap_database_digest_mismatch")

    def test_non_loopback_origin_is_rejected(self):
        with self.assertRaises(api_verify.ApiVerificationError) as caught:
            api_verify._validate_origin("https://example.com")
        self.assertEqual(caught.exception.code, "base_url_must_be_loopback")

    def test_bearer_must_come_from_exact_environment_variable(self):
        self.assertEqual(
            api_verify._load_bearer_token(
                {api_verify.TOKEN_ENVIRONMENT_VARIABLE: "test-only-bearer"}
            ),
            "test-only-bearer",
        )
        with self.assertRaises(api_verify.ApiVerificationError) as caught:
            api_verify._load_bearer_token({})
        self.assertEqual(caught.exception.code, "bearer_token_environment_invalid")

    def test_cli_failure_does_not_write_output_or_print_token(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target, _, _ = applied_root(parent)
            output = parent / "verification.json"
            with patch.dict(
                os.environ,
                {api_verify.TOKEN_ENVIRONMENT_VARIABLE: "test-only-bearer"},
                clear=False,
            ), patch.object(
                bootstrap,
                "_resolve_repository_commit",
                return_value=TEST_COMMIT,
            ), patch.object(
                api_verify,
                "_http_getter",
                return_value=lambda _path, _query=None: (_ for _ in ()).throw(
                    api_verify.ApiVerificationError("injected_api_failure")
                ),
            ):
                from contextlib import redirect_stdout
                from io import StringIO

                captured = StringIO()
                with redirect_stdout(captured):
                    exit_code = api_verify.main(
                        [
                            "--canonical-root",
                            str(target),
                            "--output",
                            str(output),
                        ]
                    )
            self.assertEqual(exit_code, 2)
            self.assertFalse(output.exists())
            self.assertNotIn("test-only-bearer", captured.getvalue())
            self.assertIn("injected_api_failure", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
