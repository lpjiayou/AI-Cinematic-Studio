"""Authenticated HTTP adapter; all facts/actions stay with the original Operator."""
import json
from urllib.parse import parse_qs, unquote

from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceError
from .public_contract import PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT


def handle_generation_workspace(handler, parsed):
    prefix = PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT + "/"
    if not parsed.path.startswith(prefix):
        return False
    parts = parsed.path[len(prefix):].split("/")
    if len(parts) < 2 or parts[1] != "generation":
        return False
    try:
        if len(parts) not in {2, 3} or (len(parts) == 3 and parts[2] != "content"):
            raise GenerationWorkspaceError("not_found", 404)
        run_ref = unquote(parts[0])
        if not run_ref or any(c in run_ref for c in "/\\\x00") or run_ref in {".", ".."}:
            raise GenerationWorkspaceError("invalid_request", 400)
        boundary = handler.generation_workspace_boundary
        if boundary is None:
            raise GenerationWorkspaceError("generation_operator_unavailable", 503)
        fields = {"projectRef", "seriesRef", "episodeRef"}
        if handler.command == "GET":
            query = parse_qs(parsed.query, keep_blank_values=True)
            expected = fields | ({"mediaJobRef", "sha256"} if len(parts) == 3 else set())
            if set(query) != expected or any(len(v) != 1 or not v[0] for v in query.values()):
                raise GenerationWorkspaceError("invalid_request", 400)
            payload = {k: v[0] for k, v in query.items()}
        else:
            if handler.command != "POST" or len(parts) != 2:
                raise GenerationWorkspaceError("method_not_allowed", 405)
            if parsed.query or handler.headers.get_content_type() != "application/json":
                raise GenerationWorkspaceError("invalid_request", 400)
            size = int(handler.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise GenerationWorkspaceError("invalid_request", 400)
            def unique(items):
                value = dict(items)
                if len(value) != len(items):
                    raise ValueError("duplicate field")
                return value
            payload = json.loads(handler.rfile.read(size), object_pairs_hook=unique)
            if not isinstance(payload, dict) or set(payload) != fields | {
                    "operation", "mediaJobRef", "expectedJobRevision", "approvedPlanDigest"}:
                raise GenerationWorkspaceError("invalid_request", 400)
        scope = {k: payload[k] for k in fields}
        scope.update(workspaceRef=handler._authenticated_workspace_ref(), productionRunRef=run_ref)
        credential = handler._authenticated_credential_ref()
        if handler.command == "POST":
            boundary.start(scope, credential, {k: v for k, v in payload.items() if k not in fields})
            handler._send_json(202, {"ok": True, "accepted": True})
        elif len(parts) == 3:
            result = boundary.content(scope, payload["mediaJobRef"], payload["sha256"])
            handler.send_response(200)
            handler.send_header("Content-Type", result["mediaType"])
            handler.send_header("Content-Length", str(len(result["content"])))
            handler.send_header("Content-Disposition", 'inline; filename="generation-result.mp4"')
            handler.send_header("Cache-Control", "private, no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.end_headers()
            handler.wfile.write(result["content"])
        else:
            handler._send_json(200, {"ok": True, "generation": boundary.project(scope, credential)})
    except GenerationWorkspaceError as exc:
        handler._send_application_error(exc.status, exc.code)
    except (ValueError, TypeError, KeyError, UnicodeError):
        handler._send_application_error(400, "invalid_request")
    except Exception:
        # Never expose native paths, SQL, Owner documents or transport exceptions.
        handler._send_application_error(503, "generation_operator_unavailable")
    return True
