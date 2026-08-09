"""Same-origin Creator Workspace server and AI Director application endpoint."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from apps.creator_workspace_mvp.ai_director import (
    AiDirectorService,
    BriefValidationError,
    CreativeBrief,
    PlanGenerationError,
    PlanValidationError,
    validate_plan,
)
from services.v5_core_os.series_episode import (
    SeriesEpisodePublicBoundary,
    SeriesEpisodePublicError,
    create_in_memory_boundary,
    create_local_development_boundary_from_environment,
)
from services.v4_platform import (
    ProviderConfigurationError,
    TextGenerationRequest,
    TextProvider,
    create_text_provider_from_environment,
)


AI_DIRECTOR_ENDPOINT = "/creator/internal/ai-director/plan"
SERIES_ENDPOINT = "/creator/internal/series"
CONFIRM_PLAN_ENDPOINT = "/creator/internal/creative-plans/confirm"
EPISODES_ENDPOINT = "/creator/internal/episodes"
MAX_REQUEST_BYTES = 64_000


class _UnconfiguredTextProvider:
    def generate(self, generation_request: TextGenerationRequest) -> str:
        raise ProviderConfigurationError("provider credential is required")


class CreatorRequestHandler(SimpleHTTPRequestHandler):
    server_version = "CreatorWorkspace/1.0"

    def __init__(
        self,
        *args: Any,
        ai_director_service: AiDirectorService,
        series_episode_boundary: SeriesEpisodePublicBoundary,
        **kwargs: Any,
    ) -> None:
        self.ai_director_service = ai_director_service
        self.series_episode_boundary = series_episode_boundary
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in {AI_DIRECTOR_ENDPOINT, SERIES_ENDPOINT, CONFIRM_PLAN_ENDPOINT, EPISODES_ENDPOINT}:
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
        if not isinstance(payload, dict):
            self._send_application_error(400, "invalid_request")
            return
        if path != AI_DIRECTOR_ENDPOINT:
            self._handle_creator_post(path, payload)
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

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        workspace_ref = query.get("workspaceRef", [""])[0]
        series_ref = query.get("seriesRef", [""])[0]
        try:
            if path == SERIES_ENDPOINT:
                self._send_json(200, {"ok": True, "series": self.series_episode_boundary.list_series(workspace_ref)})
                return
            if path.startswith(f"{SERIES_ENDPOINT}/"):
                series_ref = unquote(path[len(SERIES_ENDPOINT) + 1 :])
                if "/" not in series_ref:
                    self._send_json(200, {"ok": True, "series": self.series_episode_boundary.get_series(workspace_ref, series_ref)})
                    return
            if path.startswith(f"{EPISODES_ENDPOINT}/"):
                suffix = unquote(path[len(EPISODES_ENDPOINT) + 1 :])
                if suffix.endswith("/script-studio-bootstrap"):
                    episode_ref = suffix[: -len("/script-studio-bootstrap")]
                    if episode_ref and "/" not in episode_ref:
                        self._send_json(200, {"ok": True, "bootstrap": self.series_episode_boundary.build_script_studio_bootstrap(workspace_ref, series_ref, episode_ref)})
                        return
                elif suffix and "/" not in suffix:
                    self._send_json(200, {"ok": True, "episode": self.series_episode_boundary.get_episode(workspace_ref, series_ref, suffix)})
                    return
        except SeriesEpisodePublicError as exc:
            self._send_series_episode_error(exc)
            return
        super().do_GET()

    def _handle_creator_post(self, path: str, payload: MappingLike) -> None:
        try:
            if path == SERIES_ENDPOINT:
                result_key = "series"
                result = self.series_episode_boundary.create_series(payload)
            elif path == CONFIRM_PLAN_ENDPOINT:
                result_key = "confirmedPlan"
                brief_value = payload.get("brief")
                brief = CreativeBrief.from_mapping(brief_value if isinstance(brief_value, dict) else {})
                plan = validate_plan(payload.get("plan"), brief)
                result = self.series_episode_boundary.confirm_creative_plan(
                    {
                        "workspaceRef": payload.get("workspaceRef"),
                        "humanConfirmed": payload.get("humanConfirmed"),
                        "sourcePlanRef": payload.get("sourcePlanRef"),
                        "sourcePlanSchemaVersion": plan["schemaVersion"],
                        "sourcePlanVersion": payload.get("sourcePlanVersion"),
                        "brief": brief_value,
                        "sourcePlan": plan,
                    }
                )
            else:
                result_key = "episode"
                result = self.series_episode_boundary.create_episode(payload)
        except SeriesEpisodePublicError as exc:
            self._send_series_episode_error(exc)
            return
        except (BriefValidationError, PlanValidationError):
            self._send_application_error(400, "invalid_creative_plan")
            return
        except Exception:
            self._send_application_error(500, "application_error")
            return
        self._send_json(201, {"ok": True, result_key: result})

    def _send_series_episode_error(self, exc: SeriesEpisodePublicError) -> None:
        self._send_application_error(exc.status, exc.code)

    def _send_application_error(self, status: int, code: str) -> None:
        messages = {
            "invalid_request": "请检查输入后重试。",
            "not_found": "没有找到对应内容。",
            "duplicate_record": "该集数已经存在，请检查后重试。",
            "creative_plan_not_confirmed": "请先完成人工确认。",
            "scope_mismatch": "当前工作区与内容引用不匹配。",
            "invalid_creative_plan": "创意方案未通过校验。",
            "application_error": "暂时无法完成操作，请稍后重试。",
        }
        self._send_json(status, {"ok": False, "error": {"code": code, "message": messages.get(code, messages["application_error"])}})

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
    series_episode_boundary: SeriesEpisodePublicBoundary | None = None,
) -> ThreadingHTTPServer:
    directory = (static_directory or default_static_directory()).resolve()
    handler = partial(
        CreatorRequestHandler,
        ai_director_service=service,
        series_episode_boundary=series_episode_boundary or create_in_memory_boundary(),
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


def series_episode_boundary_from_environment() -> SeriesEpisodePublicBoundary:
    return create_local_development_boundary_from_environment()


def main() -> None:
    server = create_server(
        ("127.0.0.1", 8765),
        service_from_environment(),
        series_episode_boundary=series_episode_boundary_from_environment(),
    )
    print("Creator Workspace available at http://127.0.0.1:8765")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
