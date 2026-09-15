import json
import secrets
from threading import Thread
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

from apps.creator_workspace_mvp.server import create_server
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from tests.unit.test_generation_workspace import TestOnlyOperator, SCOPE
from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceBoundary
from types import SimpleNamespace


class GenerationWorkspaceHttpTests(unittest.TestCase):
    def setUp(self):
        self.operator = TestOnlyOperator()
        self.boundary = GenerationWorkspaceBoundary(operator=self.operator, media_job_ref="job-test",
            run_reader=SimpleNamespace(get_run=lambda workspace, run: dict(SCOPE)), allowed_credential_refs={"credential-test"})
        self.token = secrets.token_urlsafe(32)
        auth = PublicApiAuthenticator.for_token(self.token, SCOPE["workspaceRef"], credential_ref="credential-test")
        self.server = create_server(("127.0.0.1", 0), object(), public_authenticator=auth,
            allow_internal_routes=False, generation_workspace_boundary=self.boundary)
        Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.addCleanup(self.boundary.close); self.addCleanup(self.operator.release.set)
        self.base = f"http://127.0.0.1:{self.server.server_port}/creator/api/v1/episode-production-runs/run-test/generation"
        self.query = {k: v for k, v in SCOPE.items() if k in {"projectRef", "seriesRef", "episodeRef"}}

    def call(self, *, query=None, body=None, auth=True, suffix=""):
        url = self.base + suffix + (("?" + urlencode(query)) if query is not None else "")
        headers = {"Content-Type": "application/json"}
        if auth: headers["Authorization"] = "Bearer " + self.token
        req = Request(url, headers=headers, data=None if body is None else json.dumps(body).encode())
        try: response = urlopen(req, timeout=5)
        except HTTPError as exc: response = exc
        with response:
            return response.status, json.loads(response.read())

    def test_authenticated_get_is_closed_and_no_send(self):
        self.assertEqual(self.call(query=self.query, auth=False)[0], 401)
        status, body = self.call(query=self.query)
        self.assertEqual(status, 200)
        self.assertEqual(body["generation"]["mediaJobRef"], "job-test")
        self.assertEqual(self.operator.calls, [])
        self.assertEqual(self.call(query={**self.query, "workspaceRef": "forged"})[0], 400)
        self.assertEqual(self.call(query={**self.query, "projectRef": "other"})[0], 404)
        self.assertEqual(self.call(query=self.query, suffix="/private")[0], 404)

    def test_exact_post_duplicate_and_read_after_completion(self):
        body = {**self.query, "operation": "EXECUTE_APPROVED", "mediaJobRef": "job-test", "expectedJobRevision": 1, "approvedPlanDigest": "a" * 64}
        self.assertEqual(self.call(body={**body, "grant": {}})[0], 400)
        self.assertEqual(self.call(body=body)[0], 202)
        self.assertTrue(self.operator.entered.wait(5))
        self.assertEqual(self.call(body=body)[0], 202)
        self.operator.release.set(); self.boundary.close()
        self.assertEqual(self.call(query=self.query)[1]["generation"]["state"], "UNKNOWN")
        self.assertEqual(self.call(body=body)[0], 409)
        self.assertEqual(self.operator.calls, ["execute"])

    def test_missing_host_binding_is_unavailable_not_demo(self):
        self.server.RequestHandlerClass.keywords["generation_workspace_boundary"] = None
        self.assertEqual(self.call(query=self.query)[0], 503)

    def test_bounded_operator_host_does_not_open_unrelated_mutations(self):
        self.server.RequestHandlerClass.keywords["generation_only"] = True
        root = self.base.split("/episode-production-runs/")[0]
        for method, path in (("POST", "/projects"), ("POST", "/ai-director/candidates"), ("DELETE", "/series/series-test")):
            request = Request(root + path, method=method, data=b"{}" if method == "POST" else None,
                headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            with caught.exception as response:
                self.assertEqual(response.status, 403)
                self.assertEqual(json.loads(response.read())["error"]["code"], "generation_operation_not_authorized")
        self.assertEqual(self.operator.calls, [])
