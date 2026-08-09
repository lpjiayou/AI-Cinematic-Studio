"""Same-origin Creator Workspace server and AI Director application endpoint."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit

from apps.creator_workspace_mvp.ai_director import (
    AiDirectorService,
    BriefValidationError,
    PlanGenerationError,
)
from services.v4_platform import (
    ProviderConfigurationError,
    TextGenerationRequest,
    TextProvider,
    create_text_provider_from_environment,
)


AI_DIRECTOR_ENDPOINT = "/creator/internal/ai-director/plan"
MAX_REQUEST_BYTES = 64_000


class _UnconfiguredTextProvider:
    def generate(self, generation_request: TextGenerationRequest) -> str:
        raise ProviderConfigurationError("provider credential is required")


class CreatorRequestHandler(SimpleHTTPRequestHandler):
    server_version = "CreatorWorkspace/1.0"

    def __init__(self, *args: Any, ai_director_service: AiDirectorService, **kwargs: Any) -> None:
        self.ai_director_service = ai_director_service
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != AI_DIRECTOR_ENDPOINT:
            self._send_json(404, {"ok": False, "error": {"code": "not_found"}})
            return
        if self.headers.get_content_type() != "application/json":
            self._send_product_error(415, "unsupported_media_type")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_product_error(400, "invalid_request")
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_product_error(400, "invalid_request")
            return
        try:
            plan = self.ai_director_service.generate(payload.get("brief", {}))
        except BriefValidationError as exc:
            self._send_json(
                400,
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_brief",
                        "message": "请检查创意输入后重试。",
                        "fields": exc.field_errors,
                    },
                },
            )
            return
        except PlanGenerationError as exc:
            # The same-origin application contract carries capability failures in
            # a stable product envelope. Provider transport status never crosses
            # into the browser contract or produces a browser resource error.
            self._log_provider_error(exc)
            self._send_product_error(200, exc.code)
            return
        self._send_json(
            200,
            {
                "ok": True,
                "kind": "candidate-creative-plan",
                "confirmationRequired": True,
                "plan": plan,
            },
        )

    def _send_product_error(self, status: int, code: str) -> None:
        self._send_json(
            status,
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": "导演方案暂时无法生成，请稍后重试。",
                },
            },
        )

    @staticmethod
    def _log_provider_error(exc: PlanGenerationError) -> None:
        status = exc.provider_status if exc.provider_status is not None else "none"
        print(
            "AI_DIRECTOR_PROVIDER_ERROR "
            f"category={exc.diagnostic_category} "
            f"status={status} "
            f"exception={exc.exception_name}",
            file=sys.stderr,
            flush=True,
        )

    def _send_json(self, status: int, payload: MappingLike) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Do not emit request bodies, authorization headers, or provider errors.
        return


MappingLike = dict[str, Any]


def default_static_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "creator-workspace-mvp"


def create_server(
    address: tuple[str, int],
    service: AiDirectorService,
    static_directory: Path | None = None,
) -> ThreadingHTTPServer:
    directory = (static_directory or default_static_directory()).resolve()
    handler = partial(
        CreatorRequestHandler,
        ai_director_service=service,
        directory=str(directory),
    )
    server = ThreadingHTTPServer(address, handler)
    server.daemon_threads = True
    return server


def service_from_environment() -> AiDirectorService:
    try:
        provider: TextProvider = create_text_provider_from_environment()
    except ProviderConfigurationError:
        provider = _UnconfiguredTextProvider()
    return AiDirectorService(provider)


def main() -> None:
    server = create_server(("127.0.0.1", 8765), service_from_environment())
    print("Creator Workspace available at http://127.0.0.1:8765")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
