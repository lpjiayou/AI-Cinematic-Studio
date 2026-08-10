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
from apps.creator_workspace_mvp.script_studio import (
    ScriptCandidateValidationError,
    ScriptGenerationError,
    ScriptStudioApplicationService,
)
from services.v5_core_os.series_episode import (
    SeriesEpisodePublicBoundary,
    SeriesEpisodePublicError,
    create_in_memory_boundary as create_in_memory_series_boundary,
    create_local_development_boundary_from_environment as create_local_series_boundary_from_environment,
)
from apps.creator_workspace_mvp.series_director import (
    SeriesDirectorApplicationService,
    SeriesDirectorGenerationError,
    SeriesPlanCandidateError,
)
from services.v5_core_os.project_engine import (
    ProjectPublicBoundary,
    ProjectPublicError,
    create_in_memory_boundary as create_in_memory_project_boundary,
    create_local_development_boundary_from_environment as create_local_project_boundary_from_environment,
)
from services.v5_core_os.script_studio import (
    ScriptStudioPublicBoundary,
    ScriptStudioPublicError,
    create_in_memory_boundary as create_in_memory_script_boundary,
    create_local_development_boundary_from_environment as create_local_script_boundary_from_environment,
)
from services.v5_core_os.series_planning import (
    SeriesPlanningPublicBoundary,
    SeriesPlanningPublicError,
    create_in_memory_boundary as create_in_memory_series_planning_boundary,
    create_local_development_boundary_from_environment as create_local_series_planning_boundary_from_environment,
)
from services.v4_platform import (
    ProviderConfigurationError,
    TextGenerationRequest,
    TextProvider,
    create_text_provider_from_environment,
)


AI_DIRECTOR_ENDPOINT = "/creator/internal/ai-director/plan"
SERIES_ENDPOINT = "/creator/internal/series"
PROJECTS_ENDPOINT = "/creator/internal/projects"
PROJECT_CONTEXT_ENDPOINT = "/creator/internal/project-context"
CONFIRM_PLAN_ENDPOINT = "/creator/internal/creative-plans/confirm"
EPISODES_ENDPOINT = "/creator/internal/episodes"
SCRIPT_WORKSPACE_ENDPOINT = "/creator/internal/script-studio"
SCRIPT_GENERATE_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/generate"
SCRIPT_MANUAL_VERSION_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/manual-version"
SCRIPT_REWRITE_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/rewrite-scene"
SCRIPT_CONFIRM_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/confirm"
STORYBOARD_BOOTSTRAP_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/storyboard-bootstrap"
SERIES_PLANNING_ENDPOINT = "/creator/internal/series-planning"
SERIES_PLANNING_GENERATE_ENDPOINT = f"{SERIES_PLANNING_ENDPOINT}/generate"
SERIES_PLANNING_CONFIRM_ENDPOINT = f"{SERIES_PLANNING_ENDPOINT}/confirm"
SERIES_PLANNING_MANUAL_VERSION_ENDPOINT = f"{SERIES_PLANNING_ENDPOINT}/manual-version"
SERIES_PLANNING_CONFIRM_VERSION_ENDPOINT = f"{SERIES_PLANNING_ENDPOINT}/confirm-version"
SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT = f"{SERIES_PLANNING_ENDPOINT}/m6-bootstrap"
MAX_REQUEST_BYTES = 512_000


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
        project_boundary: ProjectPublicBoundary,
        series_director_service: SeriesDirectorApplicationService,
        series_planning_boundary: SeriesPlanningPublicBoundary,
        script_studio_service: ScriptStudioApplicationService,
        script_studio_boundary: ScriptStudioPublicBoundary,
        **kwargs: Any,
    ) -> None:
        self.ai_director_service = ai_director_service
        self.series_episode_boundary = series_episode_boundary
        self.project_boundary = project_boundary
        self.series_director_service = series_director_service
        self.series_planning_boundary = series_planning_boundary
        self.script_studio_service = script_studio_service
        self.script_studio_boundary = script_studio_boundary
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in {
            AI_DIRECTOR_ENDPOINT,
            SERIES_ENDPOINT,
            PROJECTS_ENDPOINT,
            CONFIRM_PLAN_ENDPOINT,
            EPISODES_ENDPOINT,
            SCRIPT_GENERATE_ENDPOINT,
            SCRIPT_MANUAL_VERSION_ENDPOINT,
            SCRIPT_REWRITE_ENDPOINT,
            SCRIPT_CONFIRM_ENDPOINT,
            SERIES_PLANNING_GENERATE_ENDPOINT,
            SERIES_PLANNING_CONFIRM_ENDPOINT,
            SERIES_PLANNING_MANUAL_VERSION_ENDPOINT,
            SERIES_PLANNING_CONFIRM_VERSION_ENDPOINT,
        }:
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
        if path.startswith(SCRIPT_WORKSPACE_ENDPOINT):
            self._handle_script_post(path, payload)
            return
        if path.startswith(SERIES_PLANNING_ENDPOINT):
            self._handle_series_planning_post(path, payload)
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

    def do_DELETE(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        workspace_ref = query.get("workspaceRef", [""])[0]
        series_ref = query.get("seriesRef", [""])[0]
        try:
            if path.startswith(f"{EPISODES_ENDPOINT}/"):
                episode_ref = unquote(path[len(EPISODES_ENDPOINT) + 1 :])
                if not episode_ref or "/" in episode_ref:
                    self._send_application_error(404, "not_found")
                    return
                episode = self.series_episode_boundary.get_episode(
                    workspace_ref,
                    series_ref,
                    episode_ref,
                )
                if self._episode_has_script(workspace_ref, series_ref, episode_ref):
                    self._send_application_error(409, "dependent_script_exists")
                    return
                result = self.series_episode_boundary.delete_episode(
                    workspace_ref,
                    series_ref,
                    episode["episodeRef"],
                )
                self._send_json(200, {"ok": True, "deletion": result})
                return
            if path.startswith(f"{SERIES_ENDPOINT}/"):
                target_series_ref = unquote(path[len(SERIES_ENDPOINT) + 1 :])
                if not target_series_ref or "/" in target_series_ref:
                    self._send_application_error(404, "not_found")
                    return
                if self.project_boundary.get_project_for_series(workspace_ref, target_series_ref) is not None:
                    self._send_application_error(409, "dependent_project_exists")
                    return
                series = self.series_episode_boundary.get_series(workspace_ref, target_series_ref)
                for episode in series.get("episodes", []):
                    if self._episode_has_script(workspace_ref, target_series_ref, episode["episodeRef"]):
                        self._send_application_error(409, "dependent_script_exists")
                        return
                result = self.series_episode_boundary.delete_series(workspace_ref, target_series_ref)
                self._send_json(200, {"ok": True, "deletion": result})
                return
        except SeriesEpisodePublicError as exc:
            self._send_series_episode_error(exc)
            return
        except ScriptStudioPublicError as exc:
            self._send_script_studio_error(exc)
            return
        except ProjectPublicError as exc:
            self._send_project_error(exc)
            return
        except Exception:
            self._send_application_error(500, "application_error")
            return
        self._send_application_error(404, "not_found")

    def _episode_has_script(self, workspace_ref: str, series_ref: str, episode_ref: str) -> bool:
        workspace = self.script_studio_boundary.get_workspace(
            workspace_ref,
            series_ref,
            episode_ref,
        )
        return workspace.get("script") is not None

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        workspace_ref = query.get("workspaceRef", [""])[0]
        series_ref = query.get("seriesRef", [""])[0]
        episode_ref = query.get("episodeRef", [""])[0]
        try:
            if path == SCRIPT_WORKSPACE_ENDPOINT:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "workspace": self.script_studio_boundary.get_workspace(
                            workspace_ref,
                            series_ref,
                            episode_ref,
                        ),
                    },
                )
                return
            if path == STORYBOARD_BOOTSTRAP_ENDPOINT:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "bootstrap": self.script_studio_boundary.build_storyboard_bootstrap(
                            workspace_ref,
                            series_ref,
                            episode_ref,
                        ),
                    },
                )
                return
            if path == SERIES_PLANNING_ENDPOINT:
                project_ref = query.get("projectRef", [""])[0]
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "workspace": self.series_planning_boundary.get_workspace(
                            workspace_ref, project_ref, series_ref
                        ),
                    },
                )
                return
            if path == SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT:
                project_ref = query.get("projectRef", [""])[0]
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "bootstrap": self.series_planning_boundary.build_m6_bootstrap(
                            workspace_ref, project_ref, series_ref
                        ),
                    },
                )
                return
            if path == PROJECTS_ENDPOINT:
                self._send_json(
                    200,
                    {"ok": True, "projects": self.project_boundary.list_projects(workspace_ref)},
                )
                return
            if path.startswith(f"{PROJECTS_ENDPOINT}/"):
                project_ref = unquote(path[len(PROJECTS_ENDPOINT) + 1 :])
                if project_ref and "/" not in project_ref:
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "project": self.project_boundary.get_project(workspace_ref, project_ref),
                        },
                    )
                    return
            if path == PROJECT_CONTEXT_ENDPOINT:
                project_ref = query.get("projectRef", [""])[0]
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "context": self.project_boundary.build_context(
                            workspace_ref,
                            project_ref,
                            series_ref or None,
                            episode_ref or None,
                        ),
                    },
                )
                return
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
        except ScriptStudioPublicError as exc:
            self._send_script_studio_error(exc)
            return
        except ProjectPublicError as exc:
            self._send_project_error(exc)
            return
        except SeriesPlanningPublicError as exc:
            self._send_series_planning_error(exc)
            return
        super().do_GET()

    def _handle_series_planning_post(self, path: str, payload: MappingLike) -> None:
        try:
            if path == SERIES_PLANNING_GENERATE_ENDPOINT:
                context = self.project_boundary.build_context(
                    payload.get("workspaceRef"),
                    payload.get("projectRef"),
                    payload.get("seriesRef"),
                )
                project = context["project"]
                series = context["series"]
                generation_context = {
                    "schemaVersion": "creator.series-director.context.v1",
                    "workspaceRef": context["workspaceRef"],
                    "contentProfileRef": context["contentProfileRef"],
                    "projectRef": context["projectRef"],
                    "projectTitle": project["title"],
                    "projectDescription": project["description"],
                    "targetPlatform": project["targetPlatform"],
                    "aspectRatio": project["aspectRatio"],
                    "plannedEpisodeCount": project["plannedEpisodeCount"],
                    "seriesRef": context["seriesRef"],
                    "seriesTitle": series["title"],
                    "seriesDescription": series["description"],
                    "createdEpisodeCount": len(series.get("episodes", [])),
                }
                candidate = self.series_director_service.generate(
                    generation_context, payload.get("creativeInput")
                )
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "kind": "candidate-series-plan",
                        "confirmationRequired": True,
                        "candidate": candidate,
                    },
                )
                return
            if path == SERIES_PLANNING_CONFIRM_ENDPOINT:
                result = self.series_planning_boundary.confirm_candidate(payload)
            elif path == SERIES_PLANNING_MANUAL_VERSION_ENDPOINT:
                result = self.series_planning_boundary.create_manual_version(payload)
            else:
                result = {"plan": self.series_planning_boundary.confirm_version(payload)}
            self._send_json(201, {"ok": True, **result})
        except SeriesPlanCandidateError:
            self._send_application_error(400, "invalid_series_plan_candidate")
        except SeriesDirectorGenerationError as exc:
            self._log_series_director_error(exc)
            self._send_series_director_product_error(200, exc)
        except ProjectPublicError as exc:
            self._send_project_error(exc)
        except SeriesPlanningPublicError as exc:
            self._send_series_planning_error(exc)

    def _handle_script_post(self, path: str, payload: MappingLike) -> None:
        try:
            if path == SCRIPT_GENERATE_ENDPOINT:
                scope = self._script_scope(payload)
                bootstrap = self.series_episode_boundary.build_script_studio_bootstrap(
                    scope["workspaceRef"],
                    scope["seriesRef"],
                    scope["episodeRef"],
                )
                content = self.script_studio_service.generate(bootstrap)
                result = self.script_studio_boundary.create_version(
                    {**scope, "changeKind": "ai-generation", "content": content}
                )
            elif path == SCRIPT_MANUAL_VERSION_ENDPOINT:
                result = self.script_studio_boundary.create_version(
                    {
                        **self._script_scope(payload),
                        "scriptRef": payload.get("scriptRef"),
                        "baseScriptVersionRef": payload.get("baseScriptVersionRef"),
                        "changeKind": "manual-edit",
                        "content": payload.get("content"),
                    }
                )
            elif path == SCRIPT_REWRITE_ENDPOINT:
                scope = self._script_scope(payload)
                workspace = self.script_studio_boundary.get_workspace(
                    scope["workspaceRef"], scope["seriesRef"], scope["episodeRef"]
                )
                script_ref = payload.get("scriptRef")
                base_ref = payload.get("baseScriptVersionRef")
                version = next(
                    (
                        item
                        for item in workspace["versions"]
                        if item["scriptVersionRef"] == base_ref
                    ),
                    None,
                )
                if workspace["script"] is None or workspace["script"]["scriptRef"] != script_ref or version is None:
                    raise ScriptStudioPublicError("not_found", 404)
                content = self.script_studio_service.rewrite_scene(
                    bootstrap=workspace["bootstrap"],
                    current_version=version,
                    script_scene_ref=str(payload.get("scriptSceneRef") or ""),
                    instruction=str(payload.get("instruction") or ""),
                )
                result = self.script_studio_boundary.create_version(
                    {
                        **scope,
                        "scriptRef": script_ref,
                        "baseScriptVersionRef": base_ref,
                        "changeKind": "ai-scene-rewrite",
                        "content": content,
                    }
                )
            else:
                result = self.script_studio_boundary.confirm_version(
                    {
                        **self._script_scope(payload),
                        "scriptRef": payload.get("scriptRef"),
                        "scriptVersionRef": payload.get("scriptVersionRef"),
                        "humanConfirmed": payload.get("humanConfirmed"),
                    }
                )
        except ScriptGenerationError as exc:
            self._log_script_provider_error(exc)
            self._send_script_product_error(200, exc.code)
            return
        except ScriptCandidateValidationError:
            self._send_application_error(400, "invalid_script_candidate")
            return
        except ScriptStudioPublicError as exc:
            self._send_script_studio_error(exc)
            return
        except SeriesEpisodePublicError as exc:
            self._send_series_episode_error(exc)
            return
        except Exception:
            self._send_application_error(500, "application_error")
            return
        self._send_json(201, {"ok": True, **result})

    @staticmethod
    def _script_scope(payload: MappingLike) -> MappingLike:
        return {
            "workspaceRef": payload.get("workspaceRef"),
            "seriesRef": payload.get("seriesRef"),
            "episodeRef": payload.get("episodeRef"),
        }

    def _handle_creator_post(self, path: str, payload: MappingLike) -> None:
        try:
            if path == SERIES_ENDPOINT:
                result_key = "series"
                result = self.series_episode_boundary.create_series(payload)
            elif path == PROJECTS_ENDPOINT:
                result_key = "project"
                result = self.project_boundary.create_project(payload)
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
        except ProjectPublicError as exc:
            self._send_project_error(exc)
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

    def _send_script_studio_error(self, exc: ScriptStudioPublicError) -> None:
        self._send_application_error(exc.status, exc.code)

    def _send_project_error(self, exc: ProjectPublicError) -> None:
        self._send_application_error(exc.status, exc.code)

    def _send_series_planning_error(self, exc: SeriesPlanningPublicError) -> None:
        self._send_application_error(exc.status, exc.code)

    def _send_application_error(self, status: int, code: str) -> None:
        messages = {
            "invalid_request": "请检查输入后重试。",
            "not_found": "没有找到对应内容。",
            "duplicate_record": "该集数已经存在，请检查后重试。",
            "creative_plan_not_confirmed": "请先完成人工确认。",
            "scope_mismatch": "当前工作区与内容引用不匹配。",
            "invalid_creative_plan": "创意方案未通过校验。",
            "invalid_script_candidate": "剧本候选内容未通过校验。",
            "version_conflict": "剧本版本已更新，请刷新后重试。",
            "script_not_confirmed": "请先确认一个剧本版本。",
            "dependent_script_exists": "该内容已有剧本版本，为保护制作链路暂不能删除。",
            "invalid_series_plan_candidate": "系列规划候选未通过本地结构校验。",
            "series_plan_not_confirmed": "请先完成人工确认。",
            "application_error": "暂时无法完成操作，请稍后重试。",
        }
        self._send_json(status, {"ok": False, "error": {"code": code, "message": messages.get(code, messages["application_error"])}})

    @staticmethod
    def _log_series_director_error(exc: SeriesDirectorGenerationError) -> None:
        print(
            "SERIES_DIRECTOR_PROVIDER_ERROR "
            f"category={exc.diagnostic_category} status={exc.provider_status or 'none'}",
            file=sys.stderr,
            flush=True,
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

    def _send_script_product_error(self, status: int, code: str) -> None:
        self._send_json(
            status,
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": "剧本暂时无法生成，请稍后重试。",
                },
            },
        )

    def _send_series_director_product_error(
        self, status: int, exc: SeriesDirectorGenerationError
    ) -> None:
        # Only stable schema paths and rules cross this development application
        # contract. Raw provider output, headers, credentials, and exceptions do not.
        issues = [
            {"field": field, "rule": rule}
            for field, rule, _category in exc.validation_issues[:40]
        ]
        self._send_json(
            status,
            {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": "系列规划候选暂时无法生成，请稍后重试。",
                    **({"validationIssues": issues} if issues else {}),
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

    @staticmethod
    def _log_script_provider_error(exc: ScriptGenerationError) -> None:
        status = exc.provider_status if exc.provider_status is not None else "none"
        print(
            "SCRIPT_STUDIO_PROVIDER_ERROR "
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
    project_boundary: ProjectPublicBoundary | None = None,
    series_director_service: SeriesDirectorApplicationService | None = None,
    series_planning_boundary: SeriesPlanningPublicBoundary | None = None,
    script_studio_service: ScriptStudioApplicationService | None = None,
    script_studio_boundary: ScriptStudioPublicBoundary | None = None,
) -> ThreadingHTTPServer:
    directory = (static_directory or default_static_directory()).resolve()
    series_boundary = series_episode_boundary or create_in_memory_series_boundary()
    projects = project_boundary or create_in_memory_project_boundary(series_boundary)
    planning = series_planning_boundary or create_in_memory_series_planning_boundary(projects)
    handler = partial(
        CreatorRequestHandler,
        ai_director_service=service,
        series_episode_boundary=series_boundary,
        project_boundary=projects,
        series_director_service=series_director_service or SeriesDirectorApplicationService(_UnconfiguredTextProvider()),
        series_planning_boundary=planning,
        script_studio_service=script_studio_service or ScriptStudioApplicationService(_UnconfiguredTextProvider()),
        script_studio_boundary=script_studio_boundary or create_in_memory_script_boundary(series_boundary),
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
    return create_local_series_boundary_from_environment()


def capability_services_from_environment() -> tuple[AiDirectorService, ScriptStudioApplicationService, SeriesDirectorApplicationService]:
    try:
        provider: TextProvider = create_text_provider_from_environment()
    except ProviderConfigurationError:
        provider = _UnconfiguredTextProvider()
    return AiDirectorService(provider), ScriptStudioApplicationService(provider), SeriesDirectorApplicationService(provider)


def main() -> None:
    series_boundary = series_episode_boundary_from_environment()
    project_boundary = create_local_project_boundary_from_environment(series_boundary)
    ai_director_service, script_service, series_director_service = capability_services_from_environment()
    series_planning_boundary = create_local_series_planning_boundary_from_environment(project_boundary)
    server = create_server(
        ("127.0.0.1", 8765),
        ai_director_service,
        series_episode_boundary=series_boundary,
        project_boundary=project_boundary,
        series_director_service=series_director_service,
        series_planning_boundary=series_planning_boundary,
        script_studio_service=script_service,
        script_studio_boundary=create_local_script_boundary_from_environment(series_boundary),
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
