"""Authenticated, bounded image/description adapter for the existing Operator.

This adapter owns no Job, authorization, file storage or generation lifecycle.
The injected application boundary enforces policy, image bytes and idempotency.
"""

import json
import re
import socket
from urllib.parse import parse_qs, unquote

from services.v5_core_os.episode_production.generation_workspace import (
    GenerationWorkspaceError,
)
from services.v5_core_os.episode_production.generation_dispatch_contracts import DispatchError

from .public_contract import PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT


IMAGE_VIDEO_RESOURCE = "image-video-generations"
RUNTIME_ENVIRONMENT_RESOURCE = "runtime-environment"
MAX_IMAGE_VIDEO_REQUEST_BYTES = 12 * 1024 * 1024
IMAGE_VIDEO_BODY_TIMEOUT_SECONDS = 15
_SCOPE_FIELDS = frozenset({"projectRef", "seriesRef", "episodeRef"})
_COMMAND_FIELDS = frozenset({
    "description", "imageBase64", "imageMediaType", "idempotencyKey",
    "expectedPolicyDigest",
})


def _reference(value):
    if (not isinstance(value, str) or not value or len(value) > 256
            or value != value.strip() or value in {".", ".."}
            or any(character in "/\\" or ord(character) < 32
                   or ord(character) == 127 for character in value)):
        raise GenerationWorkspaceError("invalid_request", 400)
    return value


def _unique_object(items):
    value = dict(items)
    if len(value) != len(items):
        raise GenerationWorkspaceError("invalid_request", 400)
    return value


def _invalid_constant(_value):
    raise GenerationWorkspaceError("invalid_request", 400)


def _read_command(handler):
    # Framing is closed before reading; do not consume an unbounded body or accept
    # alternate framing that a reverse proxy could interpret differently.
    if handler.headers.get_all("Transfer-Encoding", failobj=[]):
        raise GenerationWorkspaceError("invalid_request", 400)
    lengths = handler.headers.get_all("Content-Length", failobj=[])
    if (len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0])):
        raise GenerationWorkspaceError("invalid_request", 400)
    size = int(lengths[0])
    if size <= 0:
        raise GenerationWorkspaceError("invalid_request", 400)
    if size > MAX_IMAGE_VIDEO_REQUEST_BYTES:
        raise GenerationWorkspaceError("payload_too_large", 413)
    content_types = handler.headers.get_all("Content-Type", failobj=[])
    if (len(content_types) != 1
            or handler.headers.get_content_type() != "application/json"
            or handler.headers.get_content_charset("utf-8").lower() != "utf-8"):
        raise GenerationWorkspaceError("unsupported_media_type", 415)
    if handler.headers.get_all("Content-Encoding", failobj=[]):
        raise GenerationWorkspaceError("unsupported_media_type", 415)
    original_timeout = handler.connection.gettimeout()
    handler.connection.settimeout(
        min(original_timeout, IMAGE_VIDEO_BODY_TIMEOUT_SECONDS)
        if original_timeout is not None else IMAGE_VIDEO_BODY_TIMEOUT_SECONDS
    )
    try:
        body = handler.rfile.read(size)
    except (socket.timeout, TimeoutError) as exc:
        raise GenerationWorkspaceError("request_timeout", 408) from exc
    finally:
        handler.connection.settimeout(original_timeout)
    if len(body) != size:
        raise GenerationWorkspaceError("invalid_request", 400)
    payload = json.loads(
        body.decode("utf-8"), object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    if (not isinstance(payload, dict)
            or set(payload) != _SCOPE_FIELDS | _COMMAND_FIELDS
            or any(not isinstance(value, str) or not value for value in payload.values())):
        raise GenerationWorkspaceError("invalid_request", 400)
    return payload


def handle_image_video(handler, parsed):
    prefix = PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT + "/"
    if not parsed.path.startswith(prefix):
        return False
    parts = parsed.path[len(prefix):].split("/")
    if len(parts) < 2 or parts[1] != IMAGE_VIDEO_RESOURCE:
        return False
    try:
        if (len(parts) not in {2, 3, 4}
                or (len(parts) == 4 and parts[3] != "content")):
            raise GenerationWorkspaceError("not_found", 404)
        run_ref = _reference(unquote(parts[0], errors="strict"))
        environment_request = len(parts) == 3 and parts[2] == RUNTIME_ENVIRONMENT_RESOURCE
        generation_ref = (_reference(unquote(parts[2], errors="strict"))
            if len(parts) >= 3 and not environment_request else None)
        if handler.command not in {"GET", "POST"} or (
                handler.command == "POST" and len(parts) != 2):
            raise GenerationWorkspaceError("method_not_allowed", 405)
        # _authorize_route_class runs before this adapter. Scope is always injected
        # from that authenticated principal, never from an upload or query string.
        workspace_ref = handler._authenticated_workspace_ref()
        credential_ref = handler._authenticated_credential_ref()
        boundary = handler.image_video_boundary
        if boundary is None:
            raise GenerationWorkspaceError("image_video_unavailable", 503)
        if handler.command == "POST":
            if parsed.query:
                raise GenerationWorkspaceError("invalid_request", 400)
            payload = _read_command(handler)
        else:
            query = parse_qs(
                parsed.query, keep_blank_values=True, strict_parsing=True,
                encoding="utf-8", errors="strict", max_num_fields=8,
            )
            expected = _SCOPE_FIELDS | ({"sha256"} if len(parts) == 4 else set())
            if (set(query) != expected
                    or any(len(values) != 1 or not values[0] for values in query.values())):
                raise GenerationWorkspaceError("invalid_request", 400)
            payload = {key: values[0] for key, values in query.items()}
        scope = {key: _reference(payload[key]) for key in _SCOPE_FIELDS}
        scope.update(workspaceRef=workspace_ref, productionRunRef=run_ref)
        if handler.command == "POST":
            command = {key: payload[key] for key in _COMMAND_FIELDS}
            result = boundary.create(scope, credential_ref, command)
            handler._send_json(202, {"ok": True, "generation": result})
        elif len(parts) == 2:
            handler._send_json(200, {
                "ok": True, "workspace": boundary.workspace(scope, credential_ref),
            })
        elif environment_request:
            handler._send_json(200, {
                "ok": True, "environment": boundary.environment(scope, credential_ref),
            })
        elif len(parts) == 3:
            handler._send_json(200, {
                "ok": True, "generation": boundary.get(scope, credential_ref, generation_ref),
            })
        else:
            digest = payload["sha256"]
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise GenerationWorkspaceError("invalid_request", 400)
            result = boundary.content(scope, credential_ref, generation_ref, digest)
            if (result.get("mediaType") != "video/mp4"
                    or not isinstance(result.get("content"), bytes)):
                raise GenerationWorkspaceError("generation_result_unavailable", 503)
            handler.send_response(200)
            handler.send_header("Content-Type", "video/mp4")
            handler.send_header("Content-Length", str(len(result["content"])))
            handler.send_header("Content-Disposition", 'inline; filename="generation-result.mp4"')
            handler.send_header("Cache-Control", "private, no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.end_headers()
            handler.wfile.write(result["content"])
    except GenerationWorkspaceError as exc:
        handler._send_application_error(exc.status, exc.code)
    except DispatchError as exc:
        # Registered domain failures precede ValueError (their base class).
        # Only this closed public mapping is exposed, never raw exception text.
        status, code = {
            "OUTSIDE_VALIDITY_WINDOW": (409, "generation_policy_expired"),
            "SCOPE_MISMATCH": (404, "generation_target_not_found"),
            "APPROVAL_UNAVAILABLE": (403, "generation_operation_not_authorized"),
            "APPROVAL_PLAN_MISMATCH": (409, "generation_binding_changed"),
            "IDEMPOTENCY_CONFLICT": (409, "idempotency_conflict"),
            "INVALID_CLOSED_SCHEMA": (400, "invalid_request"),
            "SOURCE_CHANGED": (409, "generation_binding_changed"),
            "SNAPSHOT_CHANGED": (409, "generation_binding_changed"),
        }.get(exc.code, (503, "image_video_unavailable"))
        handler._send_application_error(status, code)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        handler._send_application_error(400, "invalid_request")
    except Exception:
        # Never expose local paths, raw provider responses or credential material.
        handler._send_application_error(503, "image_video_unavailable")
    return True
