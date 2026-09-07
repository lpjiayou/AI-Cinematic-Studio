"""Bounded application recovery metadata; ScriptStudioService still owns facts."""

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Mapping
from uuid import uuid4

from .foundation import (
    ScriptStudioError, ScriptStudioService, _required_ref, _validate_bootstrap,
    _normalize_content, normalize_m6_consumer_binding,
)


SCHEMA = "creator.script-generation-command.v1"
SCOPE_FIELDS = frozenset({"workspaceRef", "seriesRef", "episodeRef"})
CONTENT_FIELDS = ("title", "logline", "synopsis", "targetDurationSec", "scenes")
STATES = frozenset({"PENDING", "RESULT_READY", "COMPLETED", "FAILED"})
FAILURES = frozenset({"invalid_provider_output"})
RECORD_FIELDS = frozenset({
    "schemaVersion", "workspaceRef", "seriesRef", "episodeRef", "projectRef", "keyed",
    "identityDigest", "requestDigest", "sourceDigest", "source", "state", "result",
    "resultDigest", "response", "failureCode", "createdAt", "updatedAt", "version", "rowDigest",
})


class GenerationRecoveryError(ScriptStudioError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class GenerationStorageError(GenerationRecoveryError):
    def __init__(self):
        super().__init__("script_generation_storage_unavailable", 503)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("nonfinite JSON value")

    value = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    canonical(value)  # Also rejects overflowing numeric literals and invalid encoding.
    return value


def validate_key(value):
    if (not isinstance(value, str) or not 0 < len(value) <= 200 or value != value.strip()
            or not value.isprintable() or "/" in value or "\\" in value or value in {".", ".."}):
        raise GenerationRecoveryError("invalid_request", 400)
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise GenerationRecoveryError("invalid_request", 400) from None
    return value


def scope_of(command):
    if not isinstance(command, Mapping):
        raise GenerationRecoveryError("invalid_request", 400)
    allowed = SCOPE_FIELDS | {"projectRef", "idempotencyKey"}
    if not SCOPE_FIELDS <= set(command) or set(command) - allowed:
        raise GenerationRecoveryError("invalid_request", 400)
    result = {}
    for field in SCOPE_FIELDS | ({"projectRef"} if "projectRef" in command else set()):
        if not isinstance(command[field], str):
            raise GenerationRecoveryError("invalid_request", 400)
        result[field] = _required_ref(command[field], field)
    if "idempotencyKey" in command:
        validate_key(command["idempotencyKey"])
    return result


def request_digest(scope):
    return digest({"schemaVersion": "creator.script-generation-request.v1", "scope": scope})


def command_identity(scope, key):
    return digest({"schemaVersion": "creator.script-generation-identity.v1",
                   "workspaceRef": scope["workspaceRef"], "operation": "SCRIPT_GENERATION", "key": key})


def normalized_result(value, bootstrap):
    # Initial scenes have no refs. Actual business refs are allocated only by V5
    # when it commits the Script; validation-only refs are discarded here.
    counter = iter(range(10000))
    content = _normalize_content(strict_json(canonical(value)), bootstrap=bootstrap,
        ref_factory=lambda _: "validation-scene-" + str(next(counter)))
    for scene in content["scenes"]:
        scene.pop("scriptSceneRef")
    return content


def seal(record):
    result = deepcopy(record)
    result.pop("rowDigest", None)
    result["rowDigest"] = digest(result)
    return result


def validate_record(record):
    try:
        if (not isinstance(record, dict) or set(record) != RECORD_FIELDS
                or record["schemaVersion"] != SCHEMA or record["state"] not in STATES
                or type(record["keyed"]) is not bool or type(record["version"]) is not int
                or record["rowDigest"] != seal(record)["rowDigest"]):
            raise ValueError("invalid record")
        scope = {k: record[k] for k in SCOPE_FIELDS}
        if record["projectRef"] is not None:
            scope["projectRef"] = record["projectRef"]
        if scope_of(scope) != scope or record["requestDigest"] != request_digest(scope):
            raise ValueError("invalid request binding")
        for field in ("identityDigest", "requestDigest", "sourceDigest", "rowDigest"):
            if not isinstance(record[field], str) or re.fullmatch(r"[0-9a-f]{64}", record[field]) is None:
                raise ValueError("invalid digest")
        source = record["source"]
        if set(source) != {"bootstrap", "m6Context"} or digest(source) != record["sourceDigest"]:
            raise ValueError("invalid source")
        bootstrap = _validate_bootstrap(source["bootstrap"])
        if any(bootstrap[k] != record[k] for k in SCOPE_FIELDS):
            raise ValueError("foreign bootstrap")
        context = source["m6Context"]
        if record["projectRef"] is None:
            if context is not None:
                raise ValueError("v1 binding")
        else:
            if not isinstance(context, dict) or set(context) != {"m6ConsumerBinding", "applicableFacts"}:
                raise ValueError("invalid M6 context")
            binding = normalize_m6_consumer_binding(context["m6ConsumerBinding"])
            if (any(binding[k] != scope[k] for k in scope)
                    or not isinstance(context["applicableFacts"], dict)):
                raise ValueError("foreign M6 binding")
        for field in ("createdAt", "updatedAt"):
            if not isinstance(record[field], str) or re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z", record[field]) is None:
                raise ValueError("invalid time")
            datetime.fromisoformat(record[field].replace("Z", "+00:00"))
        if record["updatedAt"] < record["createdAt"]:
            raise ValueError("invalid time order")
        state = record["state"]
        if state == "PENDING":
            if record["version"] != 1 or any(record[k] is not None for k in
                    ("result", "resultDigest", "response", "failureCode")):
                raise ValueError("invalid pending")
        elif state == "FAILED":
            if (record["version"] != 2 or record["failureCode"] not in FAILURES
                    or any(record[k] is not None for k in ("result", "resultDigest", "response"))):
                raise ValueError("invalid failed")
        else:
            if (record["version"] != (2 if state == "RESULT_READY" else 3)
                    or record["failureCode"] is not None
                    or record["resultDigest"] != digest(record["result"])
                    or canonical(normalized_result(record["result"], bootstrap)) != canonical(record["result"])):
                raise ValueError("invalid legal result")
            if state == "RESULT_READY" and record["response"] is not None:
                raise ValueError("premature completion")
            if state == "COMPLETED":
                response = record["response"]
                if not isinstance(response, dict) or set(response) != {"script", "scriptVersion"}:
                    raise ValueError("invalid completion")
                version = response["scriptVersion"]
                script = response["script"]
                content = {k: deepcopy(version[k]) for k in CONTENT_FIELDS}
                for scene in content["scenes"]:
                    scene.pop("scriptSceneRef")
                if (canonical(content) != canonical(record["result"])
                        or any(version[k] != record[k] or script[k] != record[k] for k in SCOPE_FIELDS)
                        or script["scriptRef"] != version["scriptRef"]
                        or script["currentScriptVersionRef"] != version["scriptVersionRef"]
                        or script["confirmedScriptVersionRef"] is not None or script["version"] != 1
                        or script["createdAt"] != script["updatedAt"]
                        or version["createdAt"] != script["createdAt"]
                        or version["versionNumber"] != 1 or version["changeKind"] != "ai-generation"
                        or version["parentScriptVersionRef"] is not None
                        or any(version[k] != bootstrap[k] for k in
                               ("sourcePlanRef", "sourcePlanSchemaVersion", "sourcePlanVersion"))
                        or version.get("m6ConsumerBinding") != (context["m6ConsumerBinding"] if context else None)):
                    raise ValueError("invalid completion association")
        return record
    except (ValueError, TypeError, KeyError, AttributeError, StopIteration, RecursionError,
            OverflowError, UnicodeError, ScriptStudioError) as exc:
        raise GenerationStorageError() from exc


def validate_domain_association(record, script, version):
    if record["state"] != "COMPLETED":
        return
    try:
        response = record["response"]
        if (script is None or version is None
                or ScriptStudioService._version_mapping(version) != response["scriptVersion"]
                or any(getattr(script, k) != response["script"][k] for k in
                       ("schemaVersion", "workspaceRef", "seriesRef", "episodeRef", "scriptRef", "createdAt"))):
            raise ValueError("missing or changed domain association")
    except (ValueError, TypeError, KeyError, ScriptStudioError) as exc:
        raise GenerationStorageError() from exc


def validate_transition(old, new):
    validate_record(new)
    if old is None:
        if new["state"] != "PENDING":
            raise GenerationStorageError()
        return
    validate_record(old)
    allowed = {("PENDING", "RESULT_READY"), ("PENDING", "FAILED"), ("RESULT_READY", "COMPLETED")}
    mutable = {"state", "result", "resultDigest", "response", "failureCode", "updatedAt", "version", "rowDigest"}
    if ((old["state"], new["state"]) not in allowed
            or any(old[k] != new[k] for k in RECORD_FIELDS - mutable)
            or new["version"] != old["version"] + 1 or new["updatedAt"] < old["updatedAt"]
            or (old["state"] == "RESULT_READY" and any(old[k] != new[k] for k in ("result", "resultDigest")))):
        raise GenerationStorageError()


class InMemoryGenerationStore:
    """Test/development participant; enclosing Lifecycle supplies isolation/undo."""
    def __init__(self):
        self._records = {}

    def get(self, workspace, identity):
        record = self._records.get((workspace, identity))
        return deepcopy(validate_record(record)) if record is not None else None

    def pending(self, scope):
        return next((deepcopy(validate_record(r)) for r in self._records.values()
                     if all(r[k] == scope[k] for k in SCOPE_FIELDS)
                     and r["state"] in {"PENDING", "RESULT_READY"}), None)

    def save(self, record):
        key = (record["workspaceRef"], record["identityDigest"])
        validate_transition(self._records.get(key), record)
        if key not in self._records and self.pending(record) is not None:
            raise GenerationRecoveryError("script_generation_pending")
        self._records[key] = deepcopy(record)


class ScriptGenerationRecovery:
    """Invoked only inside a short V5 Script lifecycle operation."""
    def __init__(self, service, store):
        self.service, self.store = service, store

    def _source(self, scope):
        source = {"bootstrap": dict(self.service._bootstrap(
            scope["workspaceRef"], scope["seriesRef"], scope["episodeRef"])), "m6Context": None}
        if "projectRef" in scope:
            source["m6Context"] = self.service.resolve_current_m6_consumer_context(
                scope["workspaceRef"], scope["projectRef"], scope["seriesRef"], scope["episodeRef"])
        return source

    def _association(self, record):
        if record["state"] == "COMPLETED":
            v = record["response"]["scriptVersion"]
            repository = self.service.repository
            validate_domain_association(record,
                repository.get_script(record["workspaceRef"], record["seriesRef"], record["episodeRef"]),
                repository.get_version(record["workspaceRef"], v["scriptRef"], v["scriptVersionRef"]))

    def reserve(self, command):
        scope = scope_of(command)
        keyed = "idempotencyKey" in command
        identity = command_identity(scope, command["idempotencyKey"] if keyed else uuid4().hex)
        source = self._source(scope)
        record = self.store.get(scope["workspaceRef"], identity)
        if record is not None:
            if record["requestDigest"] != request_digest(scope):
                raise GenerationRecoveryError("idempotency_conflict")
            self._association(record)
            if record["state"] == "PENDING":
                raise GenerationRecoveryError("script_generation_pending")
            if record["state"] == "FAILED":
                raise GenerationRecoveryError(record["failureCode"])
            return {"state": record["state"], "identityDigest": identity, "scope": scope,
                    "response": deepcopy(record["response"])}
        if self.store.pending(scope) is not None:
            raise GenerationRecoveryError("script_generation_pending")
        if self.service.repository.get_script(scope["workspaceRef"], scope["seriesRef"], scope["episodeRef"]) is not None:
            raise GenerationRecoveryError("script_already_exists")
        now = self.service._clock()
        record = seal({"schemaVersion": SCHEMA, **scope, "projectRef": scope.get("projectRef"),
            "keyed": keyed, "identityDigest": identity, "requestDigest": request_digest(scope),
            "sourceDigest": digest(source), "source": source, "state": "PENDING", "result": None,
            "resultDigest": None, "response": None, "failureCode": None,
            "createdAt": now, "updatedAt": now, "version": 1})
        self.store.save(record)
        return {"state": "RESERVED", "identityDigest": identity, "scope": scope,
                "bootstrap": deepcopy(source["bootstrap"])}

    def _ticket(self, ticket):
        if not isinstance(ticket, Mapping) or set(ticket) != {"scope", "identityDigest"}:
            raise GenerationRecoveryError("invalid_request", 400)
        scope = scope_of(ticket["scope"])
        record = self.store.get(scope["workspaceRef"], ticket["identityDigest"])
        if record is None or record["requestDigest"] != request_digest(scope):
            raise GenerationStorageError()
        self._association(record)
        return scope, record

    def save_result(self, ticket, content):
        _, record = self._ticket(ticket)
        if record["state"] != "PENDING":
            raise GenerationRecoveryError("script_generation_pending")
        result = normalized_result(content, record["source"]["bootstrap"])
        self.store.save(seal({**record, "state": "RESULT_READY", "result": result,
            "resultDigest": digest(result), "updatedAt": self.service._clock(), "version": 2}))

    def fail(self, ticket, failure_code):
        _, record = self._ticket(ticket)
        if record["state"] != "PENDING" or failure_code not in FAILURES:
            raise GenerationStorageError()
        self.store.save(seal({**record, "state": "FAILED", "failureCode": failure_code,
                            "updatedAt": self.service._clock(), "version": 2}))

    def complete(self, ticket):
        scope, record = self._ticket(ticket)
        if record["state"] == "COMPLETED":
            return deepcopy(record["response"])
        if record["state"] != "RESULT_READY":
            raise GenerationRecoveryError("script_generation_pending")
        if digest(self._source(scope)) != record["sourceDigest"]:
            raise GenerationRecoveryError("script_generation_source_changed")
        if self.service.repository.get_script(scope["workspaceRef"], scope["seriesRef"], scope["episodeRef"]) is not None:
            raise GenerationRecoveryError("script_already_exists")
        response = self.service.create_version({**scope, "changeKind": "ai-generation", "content": record["result"]})
        # This save shares the Script transaction. A failure after the service write
        # must roll back Script, ScriptVersion AND this transition together.
        completed = seal({**record, "state": "COMPLETED", "response": response,
                          "updatedAt": self.service._clock(), "version": 3})
        self._association(completed)
        self.store.save(completed)
        return response
