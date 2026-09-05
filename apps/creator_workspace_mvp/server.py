"""Creator Core public HTTP/API server."""

from __future__ import annotations

from functools import partial
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from typing import Any, Mapping
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

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
)
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicBoundary,
    EpisodeProductionPublicError,
    create_in_memory_boundary as create_in_memory_episode_production_boundary,
    create_local_development_boundary_from_environment as create_episode_production_boundary_from_environment,
)
from apps.creator_workspace_mvp.series_director import (
    SeriesDirectorApplicationService,
    SeriesDirectorGenerationError,
    SeriesPlanCandidateError,
)
from apps.creator_workspace_mvp.series_plan_candidate_receipts import (
    CANDIDATE_RECEIPT_SCHEMA_VERSION,
    SeriesPlanCandidateReceiptError,
    SeriesPlanCandidateReceiptService,
    build_series_plan_candidate_context,
    create_in_memory_receipt_service,
    create_local_development_receipt_service_from_environment,
)
from apps.creator_workspace_mvp.public_contract import (
    CAPABILITIES_ENDPOINT,
    PUBLIC_API_PREFIX,
    PUBLIC_AI_DIRECTOR_ENDPOINT,
    PUBLIC_CONFIRM_PLAN_ENDPOINT,
    PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
    PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT,
    PUBLIC_EPISODES_ENDPOINT,
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
    PUBLIC_EXECUTION_METHOD_PLAN_RESOURCE,
    PUBLIC_EXPLICIT_AUDIO_REQUIREMENT_ROUTE_RESOURCE,
    PUBLIC_METHOD_AWARE_INPUT_PLAN_RESOURCE,
    PUBLIC_METHOD_AWARE_RESOURCES,
    PUBLIC_METHOD_AWARE_VIDEO_ROUTE_RESOURCE,
    PUBLIC_M6_BASELINE_ACTIVATE_ENDPOINT,
    PUBLIC_M6_BIBLE_CANDIDATE_ENDPOINT,
    PUBLIC_M6_BIBLE_CONFIRM_ENDPOINT,
    PUBLIC_M6_BIBLE_VERSION_ENDPOINT,
    PUBLIC_M6_CHARACTER_CANDIDATE_ENDPOINT,
    PUBLIC_M6_CHARACTER_CONFIRM_ENDPOINT,
    PUBLIC_M6_CHARACTER_VERSION_ENDPOINT,
    PUBLIC_PROJECT_CONTEXT_ENDPOINT,
    PUBLIC_PROJECTS_ENDPOINT,
    PUBLIC_SCRIPT_CONFIRM_ENDPOINT,
    PUBLIC_SCRIPT_GENERATE_ENDPOINT,
    PUBLIC_SCRIPT_REVIEWED_IMPORT_ENDPOINT,
    PUBLIC_SCRIPT_REVIEWED_ACCEPT_ENDPOINT,
    PUBLIC_SCRIPT_MANUAL_VERSION_ENDPOINT,
    PUBLIC_SCRIPT_REWRITE_ENDPOINT,
    PUBLIC_SCRIPT_WORKSPACE_ENDPOINT,
    PUBLIC_SERIES_ENDPOINT,
    PUBLIC_SERIES_INTELLIGENCE_WORKSPACE_ENDPOINT,
    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
    PUBLIC_SERIES_PLANNING_CONFIRM_VERSION_ENDPOINT,
    PUBLIC_SERIES_PLANNING_ENDPOINT,
    PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
    PUBLIC_SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT,
    PUBLIC_SERIES_PLANNING_MANUAL_VERSION_ENDPOINT,
    PUBLIC_STORYBOARD_BOOTSTRAP_ENDPOINT,
    capability_payload,
)
from services.v5_core_os.canonical_registration import (
    CanonicalRegistrationPublicBoundary,
    CanonicalRegistrationPublicError,
)
from apps.creator_workspace_mvp.public_auth import (
    PublicApiAuthenticator,
    PublicApiPrincipal,
    public_server_configuration_from_environment,
)
from apps.creator_workspace_mvp.strict_json import (
    PUBLIC_JSON_DECODE_ERRORS,
    PUBLIC_JSON_ENCODE_ERRORS,
    dump_public_json,
    load_public_json,
)
from services.v5_core_os.project_engine import (
    ProjectPublicBoundary,
    ProjectPublicError,
    create_in_memory_boundary as create_in_memory_project_boundary,
)
from services.v5_core_os.script_studio import (
    ScriptStudioPublicBoundary,
    ScriptStudioPublicError,
    create_in_memory_boundary as create_in_memory_script_boundary,
)
from services.v5_core_os.series_planning import (
    SeriesPlanningPublicBoundary,
    SeriesPlanningPublicError,
    create_in_memory_boundary as create_in_memory_series_planning_boundary,
)
from services.v5_core_os.series_intelligence.public import (
    SeriesIntelligencePublicBoundary,
    SeriesIntelligencePublicError,
)
from services.v5_core_os.text_generation import (
    create_text_generation_capability_from_environment,
    create_unconfigured_text_generation_capability,
)


AI_DIRECTOR_ENDPOINT = "/creator/internal/ai-director/plan"
SERIES_ENDPOINT = "/creator/internal/series"
PROJECTS_ENDPOINT = "/creator/internal/projects"
PROJECT_CONTEXT_ENDPOINT = "/creator/internal/project-context"
CONFIRM_PLAN_ENDPOINT = "/creator/internal/creative-plans/confirm"
EPISODES_ENDPOINT = "/creator/internal/episodes"
SCRIPT_WORKSPACE_ENDPOINT = "/creator/internal/script-studio"
SCRIPT_GENERATE_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/generate"
SCRIPT_REVIEWED_IMPORT_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/reviewed-import"
SCRIPT_REVIEWED_ACCEPT_ENDPOINT = f"{SCRIPT_WORKSPACE_ENDPOINT}/reviewed-import/accept"
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
HEALTH_ENDPOINT = "/health"
EPISODE_PRODUCTION_SUBRESOURCES = {
    "authority-identity",
    "production-readiness",
    "provider-experiments",
    "shot-graph",
    "assets",
    "media",
    "deterministic-effects",
    "timeline",
    "timeline-versions",
    "timeline-edits",
    "render-candidates",
    "preview",
    "finalize",
    "delivery",
    "real-media-revision",
    "dynamic-media-preflight",
    "real-image-candidates",
    "real-image-selection",
    "real-image-admission",
    "real-image-successor-admission",
    "real-video-revision",
    "real-video-candidates",
    "semantic-visual-qc",
    "media-selection",
    "real-video-admission",
    "state-projection",
    PUBLIC_EXECUTION_METHOD_PLAN_RESOURCE,
    PUBLIC_METHOD_AWARE_INPUT_PLAN_RESOURCE,
    PUBLIC_METHOD_AWARE_VIDEO_ROUTE_RESOURCE,
    PUBLIC_EXPLICIT_AUDIO_REQUIREMENT_ROUTE_RESOURCE,
}

_METHOD_AWARE_WRITE_RESOURCES = PUBLIC_METHOD_AWARE_RESOURCES
_METHOD_AWARE_SCOPE_FIELDS = frozenset(
    {"projectRef", "seriesRef", "episodeRef", "idempotencyKey"}
)
_METHOD_AWARE_FORBIDDEN_CLIENT_FIELDS = frozenset(
    {
        "adaptercapability",
        "adapteridentity",
        "authoritydigest",
        "executionmethod",
        "fallbackpolicy",
        "fallbackused",
        "publicationallowed",
        "rightsbinding",
        "voiceassetversion",
    }
)


def _contains_forbidden_method_aware_claim(
    value: Any, path: tuple[Any, ...] = ()
) -> bool:
    if isinstance(value, Mapping):
        for field, item in value.items():
            normalized = str(field).replace("_", "").replace("-", "").lower()
            field_path = (*path, field)
            execution_class_source_fact = (
                len(field_path) == 5
                and field_path[0] == "shots"
                and isinstance(field_path[1], int)
                and field_path[2] == "actionExecutionBeats"
                and isinstance(field_path[3], int)
                and field_path[4] == "executionClass"
            )
            if (
                normalized in _METHOD_AWARE_FORBIDDEN_CLIENT_FIELDS
                or (normalized == "executionclass" and not execution_class_source_fact)
                or "provider" in normalized
                or normalized.endswith("storagekey")
                or normalized.endswith("path")
                or _contains_forbidden_method_aware_claim(item, field_path)
            ):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(
            _contains_forbidden_method_aware_claim(item, (*path, index))
            for index, item in enumerate(value)
        )
    return False


def _valid_method_aware_public_command(resource: str, payload: Mapping[str, Any]) -> bool:
    if resource == PUBLIC_EXECUTION_METHOD_PLAN_RESOURCE:
        fields = _METHOD_AWARE_SCOPE_FIELDS | {
            "consistencyValidationVersionRef",
            "shots",
        }
        return set(payload) == fields and not _contains_forbidden_method_aware_claim(
            payload
        )
    if resource == PUBLIC_METHOD_AWARE_INPUT_PLAN_RESOURCE:
        bindings = payload.get("assetBindings")
        binding_fields = {
            "visualExecutionRequirementRef",
            "inputRequirementKey",
            "inputRole",
            "assetVersionRef",
        }
        return (
            set(payload) == (_METHOD_AWARE_SCOPE_FIELDS | {"assetBindings"})
            and isinstance(bindings, list)
            and all(
                isinstance(item, Mapping) and set(item) == binding_fields
                for item in bindings
            )
            and not _contains_forbidden_method_aware_claim(payload)
        )
    if resource == PUBLIC_METHOD_AWARE_VIDEO_ROUTE_RESOURCE:
        return set(payload) == _METHOD_AWARE_SCOPE_FIELDS and not (
            _contains_forbidden_method_aware_claim(payload)
        )
    if resource == PUBLIC_EXPLICIT_AUDIO_REQUIREMENT_ROUTE_RESOURCE:
        required = _METHOD_AWARE_SCOPE_FIELDS | {"audioRequirementRef"}
        allowed = required | {"rightsBindingRef", "voiceAssetVersionRef"}
        return required.issubset(payload) and set(payload).issubset(allowed) and not (
            _contains_forbidden_method_aware_claim(payload)
        )
    return False

_TIMELINE_WRITE_RESOURCES = frozenset({"timeline", "timeline-edits"})
_RENDER_CANDIDATE_WRITE_FIELDS = frozenset(
    {
        "operationRef",
        "idempotencyKey",
        "expectedRunVersion",
        "timelineVersionRef",
        "timelineVersionDigest",
        "compositionVersionRef",
        "compositionVersionDigest",
        "renderManifestRef",
        "renderManifestDigest",
    }
)
_DETERMINISTIC_EFFECT_WRITE_RESOURCE = "deterministic-effects"
_DETERMINISTIC_EFFECT_KINDS = frozenset(
    {
        "FLAME_EXTINGUISH",
        "SMOKE",
        "NAMEPLATE_TEXT",
        "FACE_MARK_COMPENSATION",
        "DISTANCE_STATE_TRANSITION",
    }
)
_DETERMINISTIC_EFFECT_WRITE_FIELDS = frozenset(
    {"expectedRunVersion", "idempotencyKey", "effectKind", "requirement"}
)
_DETERMINISTIC_EFFECT_FORBIDDEN_CLIENT_FIELDS = frozenset(
    {
        "absolutepath",
        "actorref",
        "approvalref",
        "argv",
        "canonicalmutations",
        "css",
        "environmentoverride",
        "filter",
        "filterexpression",
        "ffmpegargv",
        "ffmpegfilter",
        "externaldecisiondigest",
        "fontfiledigest",
        "fontlicensebindingversiondigest",
        "fontlicensebindingversionref",
        "fontpath",
        "fonttechnicalvalidationdigest",
        "fonttechnicalvalidationref",
        "html",
        "identitylock",
        "identitylockdigest",
        "identitylockref",
        "identitylockversionref",
        "identityreferencecontentdigest",
        "identityreferenceprojectiondigest",
        "identityreferenceref",
        "identityreferenceversionref",
        "identityversion",
        "identityversiondigest",
        "identityversionref",
        "language",
        "licenselocalpath",
        "markfiledigest",
        "markpath",
        "markpixeldigest",
        "modelpath",
        "networkurl",
        "path",
        "productionrunref",
        "publicationallowed",
        "pythonexpression",
        "rawassetversion",
        "rawbaseplateassetversion",
        "rawidentitylock",
        "rawidentityversion",
        "rawmaskassetversion",
        "rawrequirement",
        "rawtimelineversion",
        "rawshotversion",
        "rawsubjectlayerassetversion",
        "rawtextsource",
        "resolvedtext",
        "resolvedtextdigest",
        "rawvariantassetversion",
        "shellcommand",
        "storagebindingref",
        "storagekey",
        "svg",
        "workspaceref",
    }
)
_DETERMINISTIC_OVERLAY_SERVER_FIELDS = frozenset(
    {"baseplatefiledigest", "baseplatepixeldigest"}
)
_DISTANCE_STATE_SERVER_FIELDS = frozenset(
    {
        "baseplatefiledigest",
        "baseplatepixeldigest",
        "subjectlayerfiledigest",
        "subjectlayerpixeldigest",
        "maskfiledigest",
        "maskpixeldigest",
        "variantfilesdigest",
        "variantfiledigest",
        "variantpixeldigest",
        "variantstoragebindingref",
        "variantstoragekey",
        "variantbytesize",
        "variantmediatype",
        "variantpixelmode",
        "variantpixelformat",
        "variantwidth",
        "variantheight",
        "variantframecount",
        "variantramerate",
    }
)
_DISTANCE_STATE_FORBIDDEN_FIELDS = frozenset(
    {
        "distanceprompt",
        "distancetext",
        "naturallanguage",
        "naturallanguagedistance",
        "narrativestate",
        "physicaldistance",
        "prompt",
        "realworlddistance",
        "centimeters",
        "distanceunit",
        "meters",
        "worlddistance",
        "worldcentimeters",
        "worldmeters",
        "worldstate",
    }
)
_DISTANCE_STATE_FORBIDDEN_VALUES = frozenset(
    {
        "NATURAL_LANGUAGE",
        "UNSPECIFIED_3D",
        "WORLD_CENTIMETERS",
        "WORLD_METERS",
    }
)
_TIMELINE_FORBIDDEN_CLIENT_FIELDS = frozenset(
    {
        "absolutepath",
        "actorref",
        "approvalref",
        "argv",
        "assetversion",
        "audiocue",
        "canonicalmutations",
        "ffmpegargv",
        "ffmpegfilter",
        "filter",
        "filterexpression",
        "jsonpointer",
        "patch",
        "path",
        "publicationallowed",
        "productionrunref",
        "rawassetversion",
        "rawaudiocue",
        "rawrequirement",
        "rawtimelineversion",
        "requirement",
        "shellcommand",
        "sql",
        "storagekey",
        "workspaceref",
    }
)


def _contains_forbidden_timeline_client_claim(value: Any) -> bool:
    if isinstance(value, Mapping):
        for field, item in value.items():
            normalized = str(field).replace("_", "").replace("-", "").lower()
            if normalized in _TIMELINE_FORBIDDEN_CLIENT_FIELDS or any(
                marker in normalized
                for marker in (
                    "absolutepath",
                    "canonicalmutations",
                    "expression",
                    "ffmpeg",
                    "filter",
                    "inputpath",
                    "internalpath",
                    "outputpath",
                    "python",
                    "shell",
                    "sql",
                    "storagekey",
                )
            ):
                return True
            if _contains_forbidden_timeline_client_claim(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_timeline_client_claim(item) for item in value)
    return False


def _contains_forbidden_deterministic_effect_claim(
    value: Any, *, effect_kind: str | None = None
) -> bool:
    if effect_kind == "DISTANCE_STATE_TRANSITION" and isinstance(value, float):
        # Python's JSON decoder accepts NaN/Infinity by default.  Reject every
        # E4 float, finite or otherwise, before it reaches V5 authority.  The
        # older deterministic-effect contracts retain their frozen semantics.
        return True
    if isinstance(value, Mapping):
        if effect_kind is None and isinstance(value.get("effectKind"), str):
            effect_kind = value["effectKind"]
        for field, item in value.items():
            normalized = str(field).replace("_", "").replace("-", "").lower()
            if (
                normalized in _DETERMINISTIC_EFFECT_FORBIDDEN_CLIENT_FIELDS
                or (
                    effect_kind
                    in {"NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"}
                    and normalized in _DETERMINISTIC_OVERLAY_SERVER_FIELDS
                )
                or (
                    effect_kind == "DISTANCE_STATE_TRANSITION"
                    and (
                        normalized in _DISTANCE_STATE_SERVER_FIELDS
                        or normalized in _DISTANCE_STATE_FORBIDDEN_FIELDS
                        or (
                            normalized == "metric"
                            and (
                                not isinstance(item, str)
                                or item
                                not in {
                                    "SCREEN_EUCLIDEAN_PIXELS",
                                    "RELATIVE_SCALE_PERMILLE",
                                }
                            )
                        )
                        or (
                            normalized == "coordinatespace"
                            and (
                                not isinstance(item, str)
                                or item
                                not in {
                                    "CANVAS_PIXELS",
                                    "NORMALIZED_PERMILLE",
                                }
                            )
                        )
                        or "worlddistance" in normalized
                        or "worldmeter" in normalized
                        or "worldcentimeter" in normalized
                        or "realworld" in normalized
                        or "physicaldistance" in normalized
                        or "naturallanguage" in normalized
                        or "expression" in normalized
                        or "random" in normalized
                    )
                )
                or normalized.endswith("path")
                or normalized.endswith("storagekey")
                or normalized.endswith("argv")
                or "filter" in normalized
                or any(
                    marker in normalized
                    for marker in (
                        "absolutepath",
                        "ffmpegfilter",
                        "inputpath",
                        "internalpath",
                        "outputpath",
                    )
                )
                or _contains_forbidden_deterministic_effect_claim(
                    item, effect_kind=effect_kind
                )
            ):
                return True
    elif isinstance(value, (list, tuple)):
        return any(
            _contains_forbidden_deterministic_effect_claim(
                item, effect_kind=effect_kind
            )
            for item in value
        )
    elif (
        effect_kind == "DISTANCE_STATE_TRANSITION"
        and isinstance(value, str)
        and value.strip().upper() in _DISTANCE_STATE_FORBIDDEN_VALUES
    ):
        return True
    return False


PUBLIC_EXACT_ALIASES = {
    PUBLIC_AI_DIRECTOR_ENDPOINT: AI_DIRECTOR_ENDPOINT,
    PUBLIC_CONFIRM_PLAN_ENDPOINT: CONFIRM_PLAN_ENDPOINT,
    PUBLIC_SERIES_ENDPOINT: SERIES_ENDPOINT,
    PUBLIC_PROJECTS_ENDPOINT: PROJECTS_ENDPOINT,
    PUBLIC_PROJECT_CONTEXT_ENDPOINT: PROJECT_CONTEXT_ENDPOINT,
    PUBLIC_EPISODES_ENDPOINT: EPISODES_ENDPOINT,
    PUBLIC_SCRIPT_WORKSPACE_ENDPOINT: SCRIPT_WORKSPACE_ENDPOINT,
    PUBLIC_SCRIPT_GENERATE_ENDPOINT: SCRIPT_GENERATE_ENDPOINT,
    PUBLIC_SCRIPT_REVIEWED_IMPORT_ENDPOINT: SCRIPT_REVIEWED_IMPORT_ENDPOINT,
    PUBLIC_SCRIPT_REVIEWED_ACCEPT_ENDPOINT: SCRIPT_REVIEWED_ACCEPT_ENDPOINT,
    PUBLIC_SCRIPT_MANUAL_VERSION_ENDPOINT: SCRIPT_MANUAL_VERSION_ENDPOINT,
    PUBLIC_SCRIPT_REWRITE_ENDPOINT: SCRIPT_REWRITE_ENDPOINT,
    PUBLIC_SCRIPT_CONFIRM_ENDPOINT: SCRIPT_CONFIRM_ENDPOINT,
    PUBLIC_STORYBOARD_BOOTSTRAP_ENDPOINT: STORYBOARD_BOOTSTRAP_ENDPOINT,
    PUBLIC_SERIES_PLANNING_ENDPOINT: SERIES_PLANNING_ENDPOINT,
    PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT: SERIES_PLANNING_GENERATE_ENDPOINT,
    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT: SERIES_PLANNING_CONFIRM_ENDPOINT,
    PUBLIC_SERIES_PLANNING_MANUAL_VERSION_ENDPOINT: SERIES_PLANNING_MANUAL_VERSION_ENDPOINT,
    PUBLIC_SERIES_PLANNING_CONFIRM_VERSION_ENDPOINT: SERIES_PLANNING_CONFIRM_VERSION_ENDPOINT,
    PUBLIC_SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT: SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT,
}

PUBLIC_PREFIX_ALIASES = (
    (PUBLIC_PROJECTS_ENDPOINT, PROJECTS_ENDPOINT),
    (PUBLIC_SERIES_ENDPOINT, SERIES_ENDPOINT),
    (PUBLIC_EPISODES_ENDPOINT, EPISODES_ENDPOINT),
)

PUBLIC_M6_COMMAND_ENDPOINTS = {
    PUBLIC_M6_BIBLE_VERSION_ENDPOINT,
    PUBLIC_M6_BIBLE_CANDIDATE_ENDPOINT,
    PUBLIC_M6_BIBLE_CONFIRM_ENDPOINT,
    PUBLIC_M6_CHARACTER_VERSION_ENDPOINT,
    PUBLIC_M6_CHARACTER_CANDIDATE_ENDPOINT,
    PUBLIC_M6_CHARACTER_CONFIRM_ENDPOINT,
    PUBLIC_M6_BASELINE_ACTIVATE_ENDPOINT,
}


def _normalize_public_path(path: str) -> str:
    exact = PUBLIC_EXACT_ALIASES.get(path)
    if exact is not None:
        return exact
    for public_prefix, internal_prefix in PUBLIC_PREFIX_ALIASES:
        if path.startswith(f"{public_prefix}/"):
            return f"{internal_prefix}{path[len(public_prefix):]}"
    return path


def _episode_production_subresource(path: str) -> tuple[str, str] | None:
    prefix = f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
    if not path.startswith(prefix):
        return None
    relative = path[len(prefix):]
    encoded_run_ref, separator, resource = relative.rpartition("/")
    if not separator or resource not in EPISODE_PRODUCTION_SUBRESOURCES:
        return None
    run_ref = unquote(encoded_run_ref)
    if not run_ref or "/" in run_ref:
        return None
    return run_ref, resource


def _episode_export_content(path: str) -> tuple[str, str] | None:
    prefix = f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
    if not path.startswith(prefix):
        return None
    parts = path[len(prefix):].split("/")
    if len(parts) != 4 or parts[1] != "exports" or parts[3] != "content":
        return None
    run_ref, export_ref = unquote(parts[0]), unquote(parts[2])
    if not run_ref or not export_ref or "/" in run_ref or "/" in export_ref:
        return None
    return run_ref, export_ref


def _episode_preview_content(path: str) -> str | None:
    prefix = f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
    if not path.startswith(prefix):
        return None
    parts = path[len(prefix):].split("/")
    if len(parts) != 3 or parts[1:] != ["preview", "content"]:
        return None
    run_ref = unquote(parts[0])
    if not run_ref or "/" in run_ref:
        return None
    return run_ref


def _episode_render_candidate_path(
    path: str,
) -> tuple[str, str, bool] | None:
    prefix = f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
    if not path.startswith(prefix):
        return None
    parts = path[len(prefix):].split("/")
    if (
        len(parts) not in {3, 4}
        or parts[1] != "render-candidates"
        or (len(parts) == 4 and parts[3] != "content")
    ):
        return None
    run_ref, candidate_ref = unquote(parts[0]), unquote(parts[2])
    if (
        not run_ref
        or not candidate_ref
        or "/" in run_ref
        or "/" in candidate_ref
    ):
        return None
    return run_ref, candidate_ref, len(parts) == 4


class CreatorRequestHandler(BaseHTTPRequestHandler):
    server_version = "CreatorCore/1.0"

    def __init__(
        self,
        *args: Any,
        ai_director_service: AiDirectorService,
        series_episode_boundary: SeriesEpisodePublicBoundary,
        project_boundary: ProjectPublicBoundary,
        series_director_service: SeriesDirectorApplicationService,
        series_plan_candidate_receipt_service: SeriesPlanCandidateReceiptService,
        series_planning_boundary: SeriesPlanningPublicBoundary,
        series_intelligence_boundary: SeriesIntelligencePublicBoundary | None,
        script_studio_service: ScriptStudioApplicationService,
        script_studio_boundary: ScriptStudioPublicBoundary,
        episode_production_boundary: EpisodeProductionPublicBoundary,
        canonical_registration_boundary: CanonicalRegistrationPublicBoundary | None,
        public_authenticator: PublicApiAuthenticator | None,
        allow_internal_routes: bool,
        **kwargs: Any,
    ) -> None:
        self.ai_director_service = ai_director_service
        self.series_episode_boundary = series_episode_boundary
        self.project_boundary = project_boundary
        self.series_director_service = series_director_service
        self.series_plan_candidate_receipt_service = (
            series_plan_candidate_receipt_service
        )
        self.series_planning_boundary = series_planning_boundary
        self.series_intelligence_boundary = series_intelligence_boundary
        self.script_studio_service = script_studio_service
        self.script_studio_boundary = script_studio_boundary
        self.episode_production_boundary = episode_production_boundary
        self.canonical_registration_boundary = canonical_registration_boundary
        self.public_authenticator = public_authenticator
        self.allow_internal_routes = allow_internal_routes
        self.authenticated_principal: PublicApiPrincipal | None = None
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        requested_path = parsed.path
        if not self._authorize_route_class(requested_path):
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        if self._reject_client_workspace_query(requested_path, query):
            return
        path = _normalize_public_path(requested_path)
        production_subresource = _episode_production_subresource(requested_path)
        if path not in {
            AI_DIRECTOR_ENDPOINT,
            SERIES_ENDPOINT,
            PROJECTS_ENDPOINT,
            CONFIRM_PLAN_ENDPOINT,
            EPISODES_ENDPOINT,
            SCRIPT_GENERATE_ENDPOINT,
            SCRIPT_REVIEWED_IMPORT_ENDPOINT,
            SCRIPT_REVIEWED_ACCEPT_ENDPOINT,
            SCRIPT_MANUAL_VERSION_ENDPOINT,
            SCRIPT_REWRITE_ENDPOINT,
            SCRIPT_CONFIRM_ENDPOINT,
            SERIES_PLANNING_GENERATE_ENDPOINT,
            SERIES_PLANNING_CONFIRM_ENDPOINT,
            SERIES_PLANNING_MANUAL_VERSION_ENDPOINT,
            SERIES_PLANNING_CONFIRM_VERSION_ENDPOINT,
            PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
            PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
            PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT,
        } and requested_path not in PUBLIC_M6_COMMAND_ENDPOINTS and production_subresource is None:
            self._send_application_error(404, "not_found")
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
            payload = load_public_json(self.rfile.read(content_length))
        except PUBLIC_JSON_DECODE_ERRORS:
            self._send_product_error(400, "invalid_request")
            return
        if not isinstance(payload, dict):
            self._send_application_error(400, "invalid_request")
            return
        if self._is_public_path(requested_path):
            if "workspaceRef" in payload:
                self._send_application_error(
                    400, "client_workspace_scope_forbidden"
                )
                return
            if requested_path == PUBLIC_SCRIPT_REVIEWED_IMPORT_ENDPOINT:
                reviewed_import_fields = {
                    "seriesRef",
                    "episodeRef",
                    "uploadedSourceByteDigest",
                    "normalizedSourceDocumentDigest",
                    "reviewedDocumentDigest",
                    "content",
                }
                if frozenset(payload) not in {
                    frozenset(reviewed_import_fields),
                    frozenset({*reviewed_import_fields, "projectRef"}),
                }:
                    self._send_application_error(400, "invalid_request")
                    return
                payload = {
                    **payload,
                    "importedByRef": self._authenticated_credential_ref(),
                }
            elif requested_path == PUBLIC_SCRIPT_REVIEWED_ACCEPT_ENDPOINT:
                if set(payload) != {
                    "seriesRef",
                    "episodeRef",
                    "scriptRef",
                    "scriptVersionRef",
                    "idempotencyKey",
                    "approvalRef",
                }:
                    self._send_application_error(400, "invalid_request")
                    return
            elif requested_path == PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT:
                required = {"projectRef", "creativeInput"}
                if frozenset(payload) not in {
                    frozenset(required),
                    frozenset(required | {"seriesRef"}),
                }:
                    self._send_application_error(400, "invalid_request")
                    return
            elif requested_path == PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT:
                required = {
                    "projectRef",
                    "seriesRef",
                    "humanConfirmed",
                    "candidate",
                }
                if frozenset(payload) not in {
                    frozenset(required),
                    frozenset(required | {"candidateRef"}),
                }:
                    self._send_application_error(400, "invalid_request")
                    return
            elif requested_path in {
                PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
                PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT,
            }:
                if set(payload) != {
                    "registrationKey",
                    "idempotencyKey",
                    "packageDigest",
                    "contentProfileRef",
                    "series",
                    "project",
                    "creativePlan",
                    "episode",
                    "reviewedScript",
                    "acceptance",
                }:
                    self._send_application_error(400, "invalid_request")
                    return
                payload = {
                    **payload,
                    "importedByRef": self._authenticated_credential_ref(),
                }
            if production_subresource is not None and "productionRunRef" in payload:
                self._send_application_error(400, "invalid_request")
                return
            if (
                production_subresource is not None
                and production_subresource[1] in _METHOD_AWARE_WRITE_RESOURCES
                and not _valid_method_aware_public_command(
                    production_subresource[1], payload
                )
            ):
                self._send_application_error(400, "invalid_request")
                return
            if (
                production_subresource is not None
                and production_subresource[1] in _TIMELINE_WRITE_RESOURCES
            ):
                resource = production_subresource[1]
                allowed = (
                    {
                        "operationRef",
                        "idempotencyKey",
                        "expectedRunVersion",
                    }
                    if resource == "timeline"
                    else {
                        "operationRef",
                        "idempotencyKey",
                        "expectedRunVersion",
                        "parentTimelineVersionRef",
                        "parentTimelineVersionDigest",
                        "editCommand",
                    }
                )
                expected_run_version = payload.get("expectedRunVersion")
                if (
                    set(payload) != allowed
                    or isinstance(expected_run_version, bool)
                    or not isinstance(expected_run_version, int)
                    or expected_run_version < 1
                    or _contains_forbidden_timeline_client_claim(payload)
                ):
                    self._send_application_error(400, "invalid_request")
                    return
            if (
                production_subresource is not None
                and production_subresource[1] == "render-candidates"
            ):
                expected_run_version = payload.get("expectedRunVersion")
                if (
                    set(payload) != _RENDER_CANDIDATE_WRITE_FIELDS
                    or isinstance(expected_run_version, bool)
                    or not isinstance(expected_run_version, int)
                    or expected_run_version < 1
                    or _contains_forbidden_timeline_client_claim(payload)
                ):
                    self._send_application_error(400, "invalid_request")
                    return
            if (
                production_subresource is not None
                and production_subresource[1]
                == _DETERMINISTIC_EFFECT_WRITE_RESOURCE
            ):
                expected_run_version = payload.get("expectedRunVersion")
                requirement = payload.get("requirement")
                if (
                    set(payload) != _DETERMINISTIC_EFFECT_WRITE_FIELDS
                    or isinstance(expected_run_version, bool)
                    or not isinstance(expected_run_version, int)
                    or expected_run_version < 1
                    or payload.get("effectKind") not in _DETERMINISTIC_EFFECT_KINDS
                    or not isinstance(requirement, Mapping)
                    or requirement.get("effectMode") != payload.get("effectKind")
                    or _contains_forbidden_deterministic_effect_claim(
                        payload, effect_kind=payload.get("effectKind")
                    )
                ):
                    self._send_application_error(400, "invalid_request")
                    return
            if (
                production_subresource is not None
                and production_subresource[1]
                in {
                    "production-readiness",
                    "semantic-visual-qc",
                }
            ):
                actor_field = (
                    "reviewerRef"
                    if production_subresource[1] == "semantic-visual-qc"
                    else "actorRef"
                )
                if actor_field in payload:
                    self._send_application_error(400, "invalid_request")
                    return
                payload = {
                    **payload,
                    actor_field: self._authenticated_credential_ref(),
                }
            if (
                production_subresource is not None
                and production_subresource[1] == "media-selection"
                and any(
                    field == "subjectDigest"
                    or field.startswith("actor")
                    or field.startswith("authority")
                    for field in payload
                )
            ):
                self._send_application_error(400, "invalid_request")
                return
            payload = {
                **payload,
                "workspaceRef": self._authenticated_workspace_ref(),
            }
        if requested_path in PUBLIC_M6_COMMAND_ENDPOINTS:
            self._handle_series_intelligence_post(requested_path, payload)
            return
        if requested_path in {
            PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
            PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT,
        }:
            if self.canonical_registration_boundary is None:
                self._send_application_error(
                    503, "canonical_registration_unavailable"
                )
                return
            try:
                if (
                    requested_path
                    == PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT
                ):
                    result = self.canonical_registration_boundary.preflight(
                        payload
                    )
                    self._send_json(
                        200, {"ok": True, "preflight": result}
                    )
                else:
                    result = self.canonical_registration_boundary.register(
                        payload
                    )
                    self._send_json(
                        200 if result["idempotentReplay"] else 201,
                        {"ok": True, **result},
                    )
            except CanonicalRegistrationPublicError as exc:
                self._send_canonical_registration_error(exc)
            return
        if requested_path == PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT:
            try:
                result = self.episode_production_boundary.create_run(payload)
            except EpisodeProductionPublicError as exc:
                self._send_episode_production_error(exc)
                return
            self._send_json(
                200 if result["idempotentReplay"] else 201,
                {"ok": True, "run": result},
            )
            return
        if production_subresource is not None:
            run_ref, resource = production_subresource
            try:
                command = {**payload, "productionRunRef": run_ref}
                if resource == "authority-identity":
                    result = self.episode_production_boundary.authorize_and_lock(
                        command
                    )
                elif resource == "production-readiness":
                    result = self.episode_production_boundary.record_production_policy(
                        command
                    )
                elif resource == "provider-experiments":
                    result = self.episode_production_boundary.run_provider_experiment(
                        command
                    )
                elif resource == "shot-graph":
                    result = self.episode_production_boundary.compile_shot_graph(
                        command
                    )
                elif resource == "assets":
                    result = self.episode_production_boundary.resolve_assets(command)
                elif resource == "media":
                    result = self.episode_production_boundary.execute_media(command)
                elif resource == "execution-method-plan":
                    result = (
                        self.episode_production_boundary
                        .create_public_execution_method_plan(command)
                    )
                elif resource == "method-aware-input-plan":
                    result = (
                        self.episode_production_boundary
                        .create_public_method_aware_input_plan(command)
                    )
                elif resource == "method-aware-video-route":
                    result = (
                        self.episode_production_boundary
                        .create_public_method_aware_video_route(command)
                    )
                elif resource == "explicit-audio-requirement-route":
                    result = (
                        self.episode_production_boundary
                        .create_public_explicit_audio_requirement_route(command)
                    )
                elif resource == "deterministic-effects":
                    result = (
                        self.episode_production_boundary
                        .execute_deterministic_effect(command)
                    )
                elif resource == "timeline":
                    result = self.episode_production_boundary.create_timeline(command)
                elif resource == "timeline-edits":
                    result = self.episode_production_boundary.edit_timeline(command)
                elif resource == "render-candidates":
                    result = (
                        self.episode_production_boundary
                        .create_render_candidate(command)
                    )
                elif resource == "preview":
                    result = self.episode_production_boundary.compose_and_qc(command)
                elif resource == "real-media-revision":
                    result = self.episode_production_boundary.plan_real_images(
                        command
                    )
                elif resource == "dynamic-media-preflight":
                    result = (
                        self.episode_production_boundary
                        .preflight_dynamic_real_media_plan(command)
                    )
                elif resource == "real-image-selection":
                    result = self.episode_production_boundary.select_real_images(
                        command
                    )
                elif resource == "real-image-candidates":
                    result = self.episode_production_boundary.record_real_image_candidates(
                        command
                    )
                elif resource == "real-image-admission":
                    result = self.episode_production_boundary.admit_real_images(
                        command
                    )
                elif resource == "real-image-successor-admission":
                    result = self.episode_production_boundary.admit_real_image_successor(
                        command
                    )
                elif resource == "real-video-revision":
                    result = self.episode_production_boundary.plan_real_videos(
                        command
                    )
                elif resource == "real-video-candidates":
                    result = self.episode_production_boundary.record_real_video_candidates(
                        command
                    )
                elif resource == "semantic-visual-qc":
                    result = self.episode_production_boundary.record_semantic_visual_qc(
                        command
                    )
                elif resource == "media-selection":
                    result = self.episode_production_boundary.record_human_selection(
                        command
                    )
                elif resource == "real-video-admission":
                    result = self.episode_production_boundary.admit_real_videos(
                        command
                    )
                elif resource == "finalize":
                    result = self.episode_production_boundary.approve_and_finalize(
                        command
                    )
                else:
                    raise EpisodeProductionPublicError("invalid_request", 400)
            except EpisodeProductionPublicError as exc:
                self._send_episode_production_error(exc)
                return
            if resource == "dynamic-media-preflight":
                self._send_json(200, {"ok": True, "preflight": result})
            else:
                self._send_json(
                    200 if result["idempotentReplay"] else 201,
                    {"ok": True, **result},
                )
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
        response = {
            "ok": True,
            "kind": "candidate-creative-plan",
            "confirmationRequired": True,
            "plan": plan,
        }
        if requested_path == PUBLIC_AI_DIRECTOR_ENDPOINT:
            response.update(
                {
                    "sourcePlanRef": f"ai-director-candidate-{uuid4().hex}",
                    "sourcePlanVersion": 1,
                }
            )
        self._send_json(200, response)

    def do_DELETE(self) -> None:
        parsed = urlsplit(self.path)
        if not self._authorize_route_class(parsed.path):
            return
        path = _normalize_public_path(parsed.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        workspace_ref = self._workspace_from_query(parsed.path, query)
        if workspace_ref is None:
            return
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
        requested_path = parsed.path
        if not self._authorize_route_class(requested_path):
            return
        if requested_path == HEALTH_ENDPOINT:
            self._send_json(200, {"ok": True, "status": "alive"})
            return
        path = _normalize_public_path(requested_path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        workspace_ref = self._workspace_from_query(requested_path, query)
        if workspace_ref is None:
            return
        series_ref = query.get("seriesRef", [""])[0]
        episode_ref = query.get("episodeRef", [""])[0]
        if requested_path == CAPABILITIES_ENDPOINT:
            self._send_json(200, capability_payload())
            return
        try:
            if requested_path == PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "runs": self.episode_production_boundary.list_runs(workspace_ref),
                    },
                )
                return
            if requested_path.startswith(f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"):
                render_candidate_path = _episode_render_candidate_path(
                    requested_path
                )
                if render_candidate_path is not None:
                    run_ref, candidate_ref, content = render_candidate_path
                    if content:
                        result = (
                            self.episode_production_boundary
                            .get_render_candidate_content(
                                workspace_ref, run_ref, candidate_ref
                            )
                        )
                        self._send_file({**result, "cacheControl": "no-store"})
                    else:
                        result = (
                            self.episode_production_boundary
                            .get_render_candidate(
                                workspace_ref, run_ref, candidate_ref
                            )
                        )
                        self._send_json(200, {"ok": True, **result})
                    return
                preview_run_ref = _episode_preview_content(requested_path)
                if preview_run_ref is not None:
                    result = self.episode_production_boundary.get_preview_file(
                        workspace_ref, preview_run_ref
                    )
                    self._send_file(result)
                    return
                export_content = _episode_export_content(requested_path)
                if export_content is not None:
                    run_ref, export_ref = export_content
                    result = self.episode_production_boundary.get_export_file(
                        workspace_ref, run_ref, export_ref
                    )
                    self._send_file(result)
                    return
                relative = requested_path[
                    len(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT) + 1 :
                ]
                production_subresource = _episode_production_subresource(
                    requested_path
                )
                if production_subresource is not None:
                    run_ref, resource = production_subresource
                    if resource == "authority-identity":
                        result = self.episode_production_boundary.get_authority_identity(
                            workspace_ref, run_ref
                        )
                    elif resource == "production-readiness":
                        result = self.episode_production_boundary.get_production_readiness(
                            workspace_ref, run_ref
                        )
                    elif resource == "provider-experiments":
                        result = self.episode_production_boundary.list_provider_experiments(
                            workspace_ref, run_ref
                        )
                    elif resource == "shot-graph":
                        result = self.episode_production_boundary.get_shot_graph_bundle(
                            workspace_ref, run_ref
                        )
                    elif resource == "assets":
                        result = self.episode_production_boundary.get_asset_plan(
                            workspace_ref, run_ref
                        )
                    elif resource == "media":
                        result = self.episode_production_boundary.get_media_bundle(
                            workspace_ref, run_ref
                        )
                    elif resource == "execution-method-plan":
                        result = (
                            self.episode_production_boundary
                            .get_public_execution_method_plan(
                                workspace_ref,
                                query.get("projectRef", [""])[0],
                                series_ref,
                                episode_ref,
                                run_ref,
                                query.get("versionRef", [None])[0],
                            )
                        )
                    elif resource == "method-aware-input-plan":
                        result = (
                            self.episode_production_boundary
                            .get_public_method_aware_input_plan(
                                workspace_ref,
                                query.get("projectRef", [""])[0],
                                series_ref,
                                episode_ref,
                                run_ref,
                                query.get("versionRef", [None])[0],
                            )
                        )
                    elif resource == "method-aware-video-route":
                        result = (
                            self.episode_production_boundary
                            .get_public_method_aware_video_route(
                                workspace_ref,
                                query.get("projectRef", [""])[0],
                                series_ref,
                                episode_ref,
                                run_ref,
                                query.get("versionRef", [None])[0],
                            )
                        )
                    elif resource == "explicit-audio-requirement-route":
                        result = (
                            self.episode_production_boundary
                            .get_public_explicit_audio_requirement_route(
                                workspace_ref,
                                query.get("projectRef", [""])[0],
                                series_ref,
                                episode_ref,
                                run_ref,
                                query.get("versionRef", [None])[0],
                            )
                        )
                    elif resource == "deterministic-effects":
                        result = (
                            self.episode_production_boundary
                            .get_deterministic_effects(workspace_ref, run_ref)
                        )
                    elif resource == "timeline":
                        result = self.episode_production_boundary.get_timeline(
                            workspace_ref, run_ref
                        )
                    elif resource == "timeline-versions":
                        result = self.episode_production_boundary.get_timeline_versions(
                            workspace_ref, run_ref
                        )
                    elif resource == "render-candidates":
                        result = (
                            self.episode_production_boundary
                            .list_render_candidates(workspace_ref, run_ref)
                        )
                    elif resource == "real-media-revision":
                        result = self.episode_production_boundary.get_real_media_revision(
                            workspace_ref, run_ref
                        )
                    elif resource in {
                        "real-image-candidates",
                        "real-image-selection",
                        "real-image-admission",
                        "real-image-successor-admission",
                    }:
                        result = self.episode_production_boundary.get_real_media_revision(
                            workspace_ref, run_ref
                        )
                    elif resource == "real-video-revision":
                        result = self.episode_production_boundary.get_real_media_revision(
                            workspace_ref, run_ref
                        )
                    elif resource in {
                        "real-video-candidates",
                        "semantic-visual-qc",
                        "media-selection",
                        "real-video-admission",
                    }:
                        result = self.episode_production_boundary.get_real_media_revision(
                            workspace_ref, run_ref
                        )
                    elif resource == "state-projection":
                        result = self.episode_production_boundary.get_state_projection(
                            workspace_ref, run_ref
                        )
                    elif resource == "preview":
                        result = self.episode_production_boundary.get_preview_bundle(
                            workspace_ref, run_ref
                        )
                    elif resource in {"finalize", "delivery"}:
                        result = self.episode_production_boundary.get_delivery_bundle(
                            workspace_ref, run_ref
                        )
                    else:
                        raise EpisodeProductionPublicError("invalid_request", 400)
                    self._send_json(200, {"ok": True, **result})
                    return
                run_ref = unquote(relative)
                if run_ref and "/" not in run_ref:
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "run": self.episode_production_boundary.get_run(
                                workspace_ref, run_ref
                            ),
                        },
                    )
                    return
            if requested_path == PUBLIC_SERIES_INTELLIGENCE_WORKSPACE_ENDPOINT:
                if self.series_intelligence_boundary is None:
                    self._send_application_error(403, "authority_unavailable")
                    return
                project_ref = query.get("projectRef", [""])[0]
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "workspace": self.series_intelligence_boundary.get_workspace(
                            workspace_ref, project_ref, series_ref
                        ),
                    },
                )
                return
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
        except SeriesIntelligencePublicError as exc:
            self._send_series_intelligence_error(exc)
            return
        except EpisodeProductionPublicError as exc:
            self._send_episode_production_error(exc)
            return
        self._send_application_error(404, "not_found")

    def do_OPTIONS(self) -> None:
        requested_path = urlsplit(self.path).path
        if not self._authorize_route_class(requested_path):
            return
        self._send_application_error(404, "not_found")

    @staticmethod
    def _is_public_path(path: str) -> bool:
        return path == PUBLIC_API_PREFIX or path.startswith(f"{PUBLIC_API_PREFIX}/")

    @staticmethod
    def _is_internal_path(path: str) -> bool:
        return path == "/creator/internal" or path.startswith("/creator/internal/")

    def _authorize_route_class(self, path: str) -> bool:
        self.authenticated_principal = None
        if self._is_internal_path(path) and not self.allow_internal_routes:
            self._send_application_error(404, "not_found")
            return False
        if not self._is_public_path(path):
            return True
        values = self.headers.get_all("Authorization", failobj=[])
        principal = (
            self.public_authenticator.authenticate(values)
            if self.public_authenticator is not None
            else None
        )
        if principal is None:
            self._send_authentication_error()
            return False
        self.authenticated_principal = principal
        return True

    def _authenticated_workspace_ref(self) -> str:
        if self.authenticated_principal is None:
            raise RuntimeError("Authenticated public principal is required")
        return self.authenticated_principal.workspace_ref

    def _authenticated_credential_ref(self) -> str:
        if self.authenticated_principal is None:
            raise RuntimeError("Authenticated public principal is required")
        return self.authenticated_principal.credential_ref

    def _workspace_from_query(
        self, path: str, query: dict[str, list[str]]
    ) -> str | None:
        if self._is_public_path(path):
            if self._reject_client_workspace_query(path, query):
                return None
            return self._authenticated_workspace_ref()
        return query.get("workspaceRef", [""])[0]

    def _reject_client_workspace_query(
        self, path: str, query: dict[str, list[str]]
    ) -> bool:
        if self._is_public_path(path) and "workspaceRef" in query:
            self._send_application_error(
                400, "client_workspace_scope_forbidden"
            )
            return True
        return False

    def _handle_series_intelligence_post(
        self, path: str, payload: MappingLike
    ) -> None:
        if self.series_intelligence_boundary is None:
            self._send_application_error(403, "authority_unavailable")
            return
        operations = {
            PUBLIC_M6_BIBLE_VERSION_ENDPOINT: self.series_intelligence_boundary.create_bible_version,
            PUBLIC_M6_BIBLE_CANDIDATE_ENDPOINT: self.series_intelligence_boundary.submit_bible_candidate,
            PUBLIC_M6_BIBLE_CONFIRM_ENDPOINT: self.series_intelligence_boundary.confirm_bible_version,
            PUBLIC_M6_CHARACTER_VERSION_ENDPOINT: self.series_intelligence_boundary.create_character_version,
            PUBLIC_M6_CHARACTER_CANDIDATE_ENDPOINT: self.series_intelligence_boundary.submit_character_candidate,
            PUBLIC_M6_CHARACTER_CONFIRM_ENDPOINT: self.series_intelligence_boundary.confirm_character_version,
            PUBLIC_M6_BASELINE_ACTIVATE_ENDPOINT: self.series_intelligence_boundary.activate_baseline,
        }
        try:
            result = operations[path](payload)
        except SeriesIntelligencePublicError as exc:
            self._send_series_intelligence_error(exc)
            return
        except Exception:
            self._send_application_error(500, "application_error")
            return
        self._send_json(201, {"ok": True, "result": result})

    def _handle_series_planning_post(self, path: str, payload: MappingLike) -> None:
        try:
            if path == SERIES_PLANNING_GENERATE_ENDPOINT:
                context = self.project_boundary.build_context(
                    payload.get("workspaceRef"),
                    payload.get("projectRef"),
                    payload.get("seriesRef"),
                )
                candidate_context = build_series_plan_candidate_context(context)
                candidate = self.series_director_service.generate(
                    candidate_context["generationContext"],
                    payload.get("creativeInput"),
                )
                receipt, replay = (
                    self.series_plan_candidate_receipt_service.issue(
                        candidate_context,
                        payload.get("creativeInput"),
                        candidate,
                    )
                )
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "kind": "candidate-series-plan",
                        "confirmationRequired": True,
                        "candidateRef": receipt.candidateRef,
                        "candidateDigest": receipt.candidateDigest,
                        "sourceContextDigest": receipt.sourceContextDigest,
                        "candidateReceiptSchemaVersion": (
                            CANDIDATE_RECEIPT_SCHEMA_VERSION
                        ),
                        "candidateReceiptReplay": replay,
                        "candidate": candidate,
                    },
                )
                return
            if path == SERIES_PLANNING_CONFIRM_ENDPOINT:
                if payload.get("humanConfirmed") is not True:
                    raise SeriesPlanningPublicError(
                        "series_plan_not_confirmed", 409
                    )
                context = self.project_boundary.build_context(
                    payload.get("workspaceRef"),
                    payload.get("projectRef"),
                    payload.get("seriesRef"),
                )
                candidate_context = build_series_plan_candidate_context(context)
                stored_candidate = (
                    self.series_plan_candidate_receipt_service.resolve(
                        candidate_context,
                        payload.get("candidate"),
                        candidate_ref=payload.get("candidateRef"),
                    )
                )
                result = self.series_planning_boundary.confirm_candidate(
                    {
                        "workspaceRef": context["workspaceRef"],
                        "projectRef": context["projectRef"],
                        "seriesRef": context["seriesRef"],
                        "humanConfirmed": True,
                        "candidate": stored_candidate,
                    }
                )
            elif path == SERIES_PLANNING_MANUAL_VERSION_ENDPOINT:
                result = self.series_planning_boundary.create_manual_version(payload)
            else:
                result = {"plan": self.series_planning_boundary.confirm_version(payload)}
            self._send_json(201, {"ok": True, **result})
        except SeriesPlanCandidateReceiptError as exc:
            self._send_application_error(exc.status, exc.code)
        except SeriesPlanCandidateError:
            self._send_application_error(400, "invalid_series_plan_candidate")
        except SeriesDirectorGenerationError as exc:
            self._log_series_director_error(exc)
            self._send_series_director_product_error(200, exc)
        except ProjectPublicError as exc:
            self._send_project_error(exc)
        except SeriesPlanningPublicError as exc:
            self._send_series_planning_error(exc)
        except Exception:
            correlation_ref = f"series-planning-{uuid4().hex}"
            print(
                "SERIES_PLANNING_APPLICATION_ERROR "
                f"category=unexpected_exception correlation={correlation_ref}",
                file=sys.stderr,
                flush=True,
            )
            self._send_application_error(500, "application_error")

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
            elif path == SCRIPT_REVIEWED_IMPORT_ENDPOINT:
                if self.authenticated_principal is None:
                    self._send_application_error(403, "forbidden")
                    return
                result = self.script_studio_boundary.create_version(
                    {
                        **self._script_scope(payload),
                        "changeKind": "reviewed-import",
                        "uploadedSourceByteDigest": payload.get(
                            "uploadedSourceByteDigest"
                        ),
                        "normalizedSourceDocumentDigest": payload.get(
                            "normalizedSourceDocumentDigest"
                        ),
                        "reviewedDocumentDigest": payload.get(
                            "reviewedDocumentDigest"
                        ),
                        "importedByRef": payload.get("importedByRef"),
                        "content": payload.get("content"),
                    }
                )
            elif path == SCRIPT_REVIEWED_ACCEPT_ENDPOINT:
                result = self.script_studio_boundary.accept_reviewed_import(
                    {
                        **self._script_scope(payload),
                        "scriptRef": payload.get("scriptRef"),
                        "scriptVersionRef": payload.get("scriptVersionRef"),
                        "idempotencyKey": payload.get("idempotencyKey"),
                        "approvalRef": payload.get("approvalRef"),
                    }
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
        scope = {
            "workspaceRef": payload.get("workspaceRef"),
            "seriesRef": payload.get("seriesRef"),
            "episodeRef": payload.get("episodeRef"),
        }
        if payload.get("projectRef") is not None:
            scope["projectRef"] = payload.get("projectRef")
        return scope

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

    def _send_series_intelligence_error(
        self, exc: SeriesIntelligencePublicError
    ) -> None:
        self._send_application_error(exc.status, exc.code)

    def _send_episode_production_error(
        self, exc: EpisodeProductionPublicError
    ) -> None:
        self._send_application_error(exc.status, exc.code)

    def _send_canonical_registration_error(
        self, exc: CanonicalRegistrationPublicError
    ) -> None:
        self._send_application_error(exc.status, exc.code)

    def _send_application_error(self, status: int, code: str) -> None:
        messages = {
            "invalid_request": "请检查输入后重试。",
            "client_workspace_scope_forbidden": "工作区由服务身份确定，客户端不能指定。",
            "not_found": "没有找到对应内容。",
            "resource_not_found": "没有找到对应内容。",
            "duplicate_record": "该集数已经存在，请检查后重试。",
            "creative_plan_not_confirmed": "请先完成人工确认。",
            "scope_mismatch": "当前工作区与内容引用不匹配。",
            "invalid_creative_plan": "创意方案未通过校验。",
            "invalid_script_candidate": "剧本候选内容未通过校验。",
            "version_conflict": "剧本版本已更新，请刷新后重试。",
            "script_not_confirmed": "请先确认一个剧本版本。",
            "trusted_approval_required": "该导入剧本需要可信的项目负责人审批后才能确认。",
            "canonical_registration_unavailable": "请先配置显式 canonical target。",
            "dependent_script_exists": "该内容已有剧本版本，为保护制作链路暂不能删除。",
            "invalid_series_plan_candidate": "系列规划候选未通过本地结构校验。",
            "series_scope_required": "系列规划候选需要已关联的系列项目。",
            "series_plan_candidate_not_issued": "该系列规划候选未由当前服务签发。",
            "series_plan_candidate_scope_mismatch": "该系列规划候选不属于当前项目与系列。",
            "series_plan_candidate_stale": "项目或系列已更新，请重新生成候选。",
            "series_plan_candidate_content_mismatch": "候选内容与服务端签发记录不一致。",
            "series_plan_candidate_receipt_ambiguous": "候选签发记录不唯一，请重新生成候选。",
            "series_plan_candidate_receipt_unavailable": "候选签发记录暂时不可用，请稍后重试。",
            "series_plan_not_confirmed": "请先完成人工确认。",
            "authority_unavailable": "当前工作区尚未连接 M6 权限与身份授权。",
            "identity_binding_denied": "当前身份不能绑定这组系列智能数据。",
            "idempotency_conflict": "相同操作标识对应了不同内容，请刷新后重试。",
            "confirmation_required": "请先完成人工确认。",
            "stale_source": "上游系列规划已更新，请刷新后重新确认。",
            "invalid_reference": "内容引用无效，请刷新后重试。",
            "lifecycle_unavailable": "内容生命周期服务暂时不可用。",
            "upstream_not_confirmed": "请先确认系列规划、集数绑定和剧本版本。",
            "execution_not_authorized": "当前镜头结构仅供预检，尚未获得媒体执行授权。",
            "legacy_asset_resolution_write_disabled": "旧版 G4 仅支持历史读取与精确重放。",
            "legacy_media_execution_write_disabled": "旧版 G5 仅支持历史读取与精确重放。",
            "authority_required": "请先连接并完成 M6 权威与身份参考授权。",
            "invalid_state_transition": "当前制作状态不能执行该操作，请刷新后重试。",
            "stale_input": "上游权威版本已变化，请重新建立本次单集制作链。",
            "episode_production_unavailable": "单集制作根服务暂时不可用。",
            "approval_required": "请先通过已连接的外部审批权限完成四项显式审批。",
            "approval_rejected": "存在未通过的审批决定，当前候选不能形成成片。",
            "worker_unavailable": "制作执行服务暂时不可用。",
            "artifact_verification_failed": "媒体文件未通过完整性与可播放性校验。",
            "application_error": "暂时无法完成操作，请稍后重试。",
        }
        self._send_json(status, {"ok": False, "error": {"code": code, "message": messages.get(code, messages["application_error"])}})

    def _send_authentication_error(self) -> None:
        self._send_json(
            401,
            {
                "ok": False,
                "error": {
                    "code": "authentication_required",
                    "message": "Creator Core 身份验证失败。",
                },
            },
            extra_headers={"WWW-Authenticate": "Bearer"},
        )

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

    def _send_json(
        self,
        status: int,
        payload: MappingLike,
        *,
        extra_headers: MappingLike | None = None,
    ) -> None:
        try:
            body = dump_public_json(payload)
        except PUBLIC_JSON_ENCODE_ERRORS:
            status = 500
            extra_headers = None
            body = dump_public_json(
                {
                    "ok": False,
                    "error": {
                        "code": "application_error",
                        "message": "暂时无法完成操作，请稍后重试。",
                    },
                }
            )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra_headers or {}).items():
            self.send_header(str(name), str(value))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, artifact: MappingLike) -> None:
        path = artifact.get("path")
        if not isinstance(path, Path) or not path.is_file():
            self._send_application_error(404, "resource_not_found")
            return
        body = path.read_bytes()
        if (
            len(body) != artifact.get("byteSize")
            or sha256(body).hexdigest() != artifact.get("sha256")
        ):
            self._send_application_error(422, "artifact_verification_failed")
            return
        file_name = str(artifact.get("fileName", "episode.mp4")).replace('"', "")
        self.send_response(200)
        self.send_header("Content-Type", str(artifact.get("mediaType", "video/mp4")))
        self.send_header("Content-Length", str(len(body)))
        disposition = (
            "inline"
            if artifact.get("contentDisposition") == "inline"
            else "attachment"
        )
        self.send_header(
            "Content-Disposition", f'{disposition}; filename="{file_name}"'
        )
        self.send_header(
            "Cache-Control", str(artifact.get("cacheControl", "private, no-store"))
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Do not emit request bodies, authorization headers, or provider errors.
        return


MappingLike = dict[str, Any]


def create_server(
    address: tuple[str, int],
    service: AiDirectorService,
    series_episode_boundary: SeriesEpisodePublicBoundary | None = None,
    project_boundary: ProjectPublicBoundary | None = None,
    series_director_service: SeriesDirectorApplicationService | None = None,
    series_plan_candidate_receipt_service: SeriesPlanCandidateReceiptService | None = None,
    series_planning_boundary: SeriesPlanningPublicBoundary | None = None,
    series_intelligence_boundary: SeriesIntelligencePublicBoundary | None = None,
    script_studio_service: ScriptStudioApplicationService | None = None,
    script_studio_boundary: ScriptStudioPublicBoundary | None = None,
    episode_production_boundary: EpisodeProductionPublicBoundary | None = None,
    public_authenticator: PublicApiAuthenticator | None = None,
    allow_internal_routes: bool = True,
    canonical_registration_boundary: CanonicalRegistrationPublicBoundary | None = None,
) -> ThreadingHTTPServer:
    series_boundary = series_episode_boundary or create_in_memory_series_boundary()
    projects = project_boundary or create_in_memory_project_boundary(series_boundary)
    planning = series_planning_boundary or create_in_memory_series_planning_boundary(projects)
    scripts = script_studio_boundary or create_in_memory_script_boundary(series_boundary)
    assembly = series_boundary._lifecycle_assembly_or_none()
    registration = canonical_registration_boundary or (
        assembly.canonical_registration if assembly is not None else None
    )
    production = episode_production_boundary or create_in_memory_episode_production_boundary(
        project_boundary=projects,
        series_episode_boundary=series_boundary,
        series_planning_boundary=planning,
        script_studio_boundary=scripts,
    )
    default_text_generation = create_unconfigured_text_generation_capability()
    handler = partial(
        CreatorRequestHandler,
        ai_director_service=service,
        series_episode_boundary=series_boundary,
        project_boundary=projects,
        series_director_service=series_director_service
        or SeriesDirectorApplicationService(default_text_generation),
        series_plan_candidate_receipt_service=(
            series_plan_candidate_receipt_service
            or create_in_memory_receipt_service()
        ),
        series_planning_boundary=planning,
        series_intelligence_boundary=series_intelligence_boundary,
        script_studio_service=script_studio_service
        or ScriptStudioApplicationService(default_text_generation),
        script_studio_boundary=scripts,
        episode_production_boundary=production,
        canonical_registration_boundary=registration,
        public_authenticator=public_authenticator,
        allow_internal_routes=allow_internal_routes,
    )
    server = ThreadingHTTPServer(address, handler)
    server.daemon_threads = True
    return server


def service_from_environment() -> AiDirectorService:
    return AiDirectorService(create_text_generation_capability_from_environment())


def series_episode_boundary_from_environment() -> SeriesEpisodePublicBoundary:
    from services.v5_core_os.lifecycle_integrity import LifecycleAssembly

    return LifecycleAssembly.sqlite_from_environment().series_episode


def capability_services_from_environment() -> tuple[AiDirectorService, ScriptStudioApplicationService, SeriesDirectorApplicationService]:
    text_generation = create_text_generation_capability_from_environment()
    return (
        AiDirectorService(text_generation),
        ScriptStudioApplicationService(text_generation),
        SeriesDirectorApplicationService(text_generation),
    )


def main() -> None:
    host, port, public_authenticator, allow_internal_routes = (
        public_server_configuration_from_environment()
    )
    series_boundary = series_episode_boundary_from_environment()
    assembly = series_boundary._lifecycle_assembly_or_none()
    if assembly is None:
        raise RuntimeError("Creator SQLite lifecycle assembly is required")
    project_boundary = assembly.project_context
    ai_director_service, script_service, series_director_service = capability_services_from_environment()
    candidate_receipt_service = (
        create_local_development_receipt_service_from_environment()
    )
    series_planning_boundary = assembly.series_planning
    episode_production_boundary = create_episode_production_boundary_from_environment(
        project_boundary=project_boundary,
        series_episode_boundary=series_boundary,
        series_planning_boundary=series_planning_boundary,
        script_studio_boundary=assembly.script_studio,
    )
    server = create_server(
        (host, port),
        ai_director_service,
        series_episode_boundary=series_boundary,
        project_boundary=project_boundary,
        series_director_service=series_director_service,
        series_plan_candidate_receipt_service=candidate_receipt_service,
        series_planning_boundary=series_planning_boundary,
        series_intelligence_boundary=assembly.series_intelligence,
        script_studio_service=script_service,
        script_studio_boundary=assembly.script_studio,
        episode_production_boundary=episode_production_boundary,
        canonical_registration_boundary=assembly.canonical_registration,
        public_authenticator=public_authenticator,
        allow_internal_routes=allow_internal_routes,
    )
    route_mode = "loopback-compatible" if allow_internal_routes else "public-only"
    print(f"Creator Core API available at http://{host}:{port} ({route_mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
