"""Explicit CPU-only browser fixture. Never imports private deployment inputs.

Run only via python -m with a test-owned auth token in the environment. Creates
temporary databases; one fixture-owned loopback submission on an explicit click.
"""
import json
import os
import signal
from threading import Thread
import unittest

from apps.creator_workspace_mvp.generation_dispatch_operator import open_generation_workspace_server
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from tests.integration import test_generation_dispatch_d1_operator_cpu as original_tests
from tests.support.comfyui_loopback_fixtures import LoopbackComfyUI


def main():
    case = unittest.TestCase()
    original_tests.D1OperatorCpuTests.setUpClass()
    case.tools = original_tests.D1OperatorCpuTests.tools
    with LoopbackComfyUI(frames=original_tests.D1OperatorCpuTests.frames, output_node="41", start_number=1) as provider:
        f = original_tests.D1OperatorCpuTests.fixture(case, provider)
        f.operator_context.__exit__(None, None, None)
        context = open_generation_workspace_server(deployment=f.deployment, media_job_ref=f.job["jobRef"],
            allowed_credential_refs={"ui-fixture-writer"},
            public_authenticator=PublicApiAuthenticator.for_token(os.environ["ACS_UI_FIXTURE_TOKEN"],
                f.scope["workspaceRef"], credential_ref="ui-fixture-writer"))
        server = context.__enter__()
        boundary = server.RequestHandlerClass.keywords["generation_workspace_boundary"]
        def stop(signum, frame):
            Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        print(json.dumps({"classification": "CPU_FIXTURE_ONLY", "port": server.server_port,
            "pid": os.getpid(), "scope": f.scope, "databaseRoot": str(f.root),
            "mediaJobRef": f.job["jobRef"]}), flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close(); boundary.close()
            print(json.dumps({"classification": "CPU_FIXTURE_ONLY", "loopbackPosts": provider.complete_post_count,
                "finalJobState": boundary.project(f.scope, "ui-fixture-writer")["state"], "formalDatabaseTouched": False}), flush=True)
            context.__exit__(None, None, None)
            case.doCleanups()


if __name__ == "__main__":
    main()
