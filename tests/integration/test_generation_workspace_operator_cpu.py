"""Original Operator → fixture-owned loopback → original artifact → public playback.

No real GPU, deployment or formal data. This is CPU integration evidence only.
"""
from hashlib import sha256
import json
import secrets
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceBoundary, GenerationWorkspaceError
from tests.integration import test_generation_dispatch_d1_operator_cpu as original_tests
from tests.support.comfyui_loopback_fixtures import LoopbackComfyUI


class GenerationWorkspaceOperatorCpuTests(unittest.TestCase):
    def test_original_operator_one_send_playback_and_restart(self):
        original_tests.D1OperatorCpuTests.setUpClass()
        self.tools = original_tests.D1OperatorCpuTests.tools
        with LoopbackComfyUI(frames=original_tests.D1OperatorCpuTests.frames, output_node="41", start_number=1) as server:
            f = original_tests.D1OperatorCpuTests.fixture(self, server)
            runs = f.operator.public_boundaries()["episode_production_boundary"]
            boundary = GenerationWorkspaceBoundary(operator=f.operator, media_job_ref=f.job["jobRef"],
                run_reader=runs, allowed_credential_refs={"test-ui-writer"})
            before = boundary.project(f.scope, "test-ui-writer")
            self.assertTrue(before["canExecute"])
            self.assertEqual(server.complete_post_count, 0)
            command = {"operation": "EXECUTE_APPROVED", "mediaJobRef": before["mediaJobRef"],
                "expectedJobRevision": before["jobRevision"], "approvedPlanDigest": before["approvedPlanDigest"]}
            boundary.start(f.scope, "test-ui-writer", command)
            boundary.close()
            result = boundary.project(f.scope, "test-ui-writer")
            self.assertEqual(result["state"], "SUCCEEDED", result)
            self.assertEqual(server.complete_post_count, 1)
            content = boundary.content(f.scope, result["mediaJobRef"], result["artifact"]["sha256"])
            self.assertEqual(sha256(content["content"]).hexdigest(), result["artifact"]["sha256"])
            self.assertEqual(result["artifact"]["durationFrames"], 48)
            self.assertEqual(result["artifact"]["frameRate"], 24)
            with self.assertRaises(GenerationWorkspaceError):
                boundary.start(f.scope, "test-ui-writer", command)
            artifact = f.jobs()[0]["artifact"]
            from pathlib import Path
            path = Path(artifact["internalPath"])
            # Release the original process/store guard, reopen from the existing
            # deployment through the production HTTP host seam, never reseed.
            f.operator_context.__exit__(None, None, None)
            from apps.creator_workspace_mvp.generation_dispatch_operator import open_generation_workspace_server
            from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
            token = secrets.token_urlsafe(32)
            auth = PublicApiAuthenticator.for_token(token, f.scope["workspaceRef"], "test-ui-writer")
            with open_generation_workspace_server(deployment=f.deployment, media_job_ref=result["mediaJobRef"],
                    public_authenticator=auth, allowed_credential_refs={"test-ui-writer"}) as http:
                worker = Thread(target=http.serve_forever, daemon=True); worker.start()
                try:
                    base = f"http://127.0.0.1:{http.server_port}/creator/api/v1/episode-production-runs/{f.scope['productionRunRef']}/generation"
                    scope_query = {k: f.scope[k] for k in ("projectRef", "seriesRef", "episodeRef")}
                    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
                    with urlopen(Request(base + "?" + urlencode(scope_query), headers=headers), timeout=10) as response:
                        self.assertEqual(json.load(response)["generation"], result)
                    media_url = base + "/content?" + urlencode({**scope_query, "mediaJobRef": result["mediaJobRef"], "sha256": artifact["sha256"]})
                    with urlopen(Request(media_url, headers=headers), timeout=10) as response:
                        self.assertEqual(response.read(), content["content"])
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(Request(base, headers=headers, data=json.dumps({**scope_query, **command}).encode()), timeout=10)
                    self.assertEqual(rejected.exception.code, 409); rejected.exception.close()
                    path.write_bytes(b"test-only-corrupted-video")
                    with self.assertRaises(HTTPError) as corrupt:
                        urlopen(Request(media_url, headers=headers), timeout=10)
                    self.assertEqual(corrupt.exception.code, 409); corrupt.exception.close()
                finally:
                    http.shutdown(); worker.join(5)
                    self.assertFalse(worker.is_alive())
            self.assertEqual(server.complete_post_count, 1)
            print("UI_ORIGINAL_OPERATOR_CPU: sends=1 frames=48 fps=24 host_reopen=PASS HTTP_playback=PASS tamper=REJECTED")
