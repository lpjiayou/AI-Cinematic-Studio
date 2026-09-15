"""Explicit CPU-only browser host using the real image-video runtime/Operator.

Run with a test-owned ACS_UI_FIXTURE_TOKEN. All databases, staged input and
provider metadata are disposable test fixtures. Opening this host sends zero
requests to the loopback provider; only an explicit browser action creates and
executes an independent user-input Job. No GPU or private deployment is read.
"""
from contextlib import ExitStack
from hashlib import sha256
import json
import os
import signal
from threading import Thread

from apps.creator_workspace_mvp.generation_dispatch_operator import open_generation_workspace_server
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from tests.integration.test_generation_dispatch_live_result_cpu import synthetic_png
from tests.integration.test_image_video_operator import ImageVideoOperatorTests
from tests.support.comfyui_loopback_fixtures import LoopbackComfyUI


def main():
    ImageVideoOperatorTests.setUpClass()
    case = ImageVideoOperatorTests()
    with ExitStack() as cleanup, LoopbackComfyUI(frames=case.frames, output_node="41", start_number=1) as provider:
        cleanup.callback(case.doCleanups)
        fixture = case.fixture(provider)
        fixture.operator_context.__exit__(None, None, None)
        image = fixture.root / "test-only-browser-upload.png"
        image.write_bytes(synthetic_png(1))
        with open_generation_workspace_server(deployment=fixture.deployment,
                media_job_ref=fixture.job["jobRef"], allowed_credential_refs={"test-ui-writer"},
                public_authenticator=PublicApiAuthenticator.for_token(
                    os.environ["ACS_UI_FIXTURE_TOKEN"], fixture.scope["workspaceRef"],
                    credential_ref="test-ui-writer")) as server:
            image_video = server.RequestHandlerClass.keywords["image_video_boundary"]
            original = server.RequestHandlerClass.keywords["generation_workspace_boundary"]

            def stop(_signal, _frame):
                Thread(target=server.shutdown, daemon=True).start()

            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            print(json.dumps({"classification": "CPU_FIXTURE_ONLY_NOT_GPU_EVIDENCE",
                "port": server.server_port, "pid": os.getpid(), "scope": fixture.scope,
                "databaseRoot": str(fixture.root), "originalMediaJobRef": fixture.job["jobRef"],
                "testUploadPath": str(image), "testUploadSha256": sha256(image.read_bytes()).hexdigest(),
                "loopbackPostsAtStartup": provider.complete_post_count,
                "formalDatabaseTouched": False, "gpuAccessed": False}), flush=True)
            try:
                server.serve_forever()
            finally:
                image_video.close()
                history = image_video.workspace(fixture.scope, "test-ui-writer")
                print(json.dumps({"classification": "CPU_FIXTURE_ONLY_NOT_GPU_EVIDENCE",
                    "loopbackPosts": provider.complete_post_count,
                    "loopbackNativeFramesRead": provider.view_count,
                    "generations": history["generations"],
                    "originalJobState": original.project(fixture.scope, "test-ui-writer")["state"],
                    "formalDatabaseTouched": False, "gpuAccessed": False}), flush=True)


if __name__ == "__main__":
    main()
