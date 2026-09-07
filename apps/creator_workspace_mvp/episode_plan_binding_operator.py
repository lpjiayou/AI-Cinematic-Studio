"""Controlled, Core-only M5 binding application; authoritative readback recovery."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import stat
from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_planning.public import SeriesPlanningPublicError


SCOPE_FIELDS = frozenset({"workspaceRef", "projectRef", "seriesRef"})
COMMAND_FIELDS = SCOPE_FIELDS | {
    "targetRef", "seriesPlanRef", "expectedPlanVersion", "sourceSeriesPlanVersionRef",
    "sourceContentDigest", "episodePlanItemBindings", "operationAuthorizationRef",
}
CONTENT_FIELDS = frozenset({
    "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs",
    "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
    "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions",
})
V1 = "v5.series-plan-version.v1"
V2 = "v5.series-plan-version.v2"


class BindingOperatorError(ValueError):
    """Safe operator code; deliberately carries no paths or underlying exceptions."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _ref(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BindingOperatorError("INVALID_REQUEST")
    return value


def _finite_tree(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise BindingOperatorError("INVALID_REQUEST")
    if isinstance(value, dict):
        for item in value.values():
            _finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _finite_tree(item)


def load_operator_json(value: str | bytes) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise BindingOperatorError("INVALID_REQUEST")
            result[key] = item
        return result

    try:
        if len(value) > 1_000_000:
            raise BindingOperatorError("INVALID_REQUEST")
        result = json.loads(value, object_pairs_hook=unique)
        if not isinstance(result, dict):
            raise BindingOperatorError("INVALID_REQUEST")
        _finite_tree(result)
        return result
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise BindingOperatorError("INVALID_REQUEST") from None


def regular_file_path(value: str) -> Path:
    try:
        path = Path(_ref(value))
        if not path.is_absolute() or ".." in path.parts:
            raise BindingOperatorError("TARGET_UNAVAILABLE")
        for ancestor in reversed(path.parents):
            mode = ancestor.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise BindingOperatorError("TARGET_UNAVAILABLE")
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise BindingOperatorError("TARGET_UNAVAILABLE")
        return path
    except (OSError, TypeError, ValueError):
        raise BindingOperatorError("TARGET_UNAVAILABLE") from None


def source_content_digest(version: Mapping[str, Any]) -> str:
    """Hash the public immutable content, including existing v2 bindings."""
    content = {field: version[field] for field in CONTENT_FIELDS}
    if version["schemaVersion"] == V2:
        content["episodePlanItemBindings"] = version["episodePlanItemBindings"]
    return sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class EpisodePlanBindingOperator:
    def __init__(self, controlled_config: Mapping[str, Any]):
        config = deepcopy(controlled_config)
        if not isinstance(config, dict) or set(config) != {
            "targetRef", "databasePath", "allowedScopes",
        }:
            raise BindingOperatorError("INVALID_CONFIGURATION")
        _finite_tree(config)
        _ref(config["targetRef"])
        scopes = config["allowedScopes"]
        if not isinstance(scopes, list) or not scopes:
            raise BindingOperatorError("INVALID_CONFIGURATION")
        identities = set()
        for scope in scopes:
            if not isinstance(scope, dict) or set(scope) != SCOPE_FIELDS | {"operationAuthorizationRefs"}:
                raise BindingOperatorError("INVALID_CONFIGURATION")
            identity = tuple(_ref(scope[field]) for field in sorted(SCOPE_FIELDS))
            authorizations = scope["operationAuthorizationRefs"]
            if (identity in identities or not isinstance(authorizations, list)
                    or not authorizations or len({_ref(ref) for ref in authorizations}) != len(authorizations)):
                raise BindingOperatorError("INVALID_CONFIGURATION")
            identities.add(identity)
        self.config = config
        self.path = regular_file_path(config["databasePath"])
        metadata = self.path.lstat()
        self.file_identity = (metadata.st_dev, metadata.st_ino)
        try:
            # Existing public composition validates only: never initialize or migrate.
            self.assembly = LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False)
            self._check_target()
        except Exception:
            raise BindingOperatorError("TARGET_UNAVAILABLE") from None

    def _check_target(self) -> None:
        metadata = regular_file_path(self.config["databasePath"]).lstat()
        if (metadata.st_dev, metadata.st_ino) != self.file_identity:
            raise BindingOperatorError("TARGET_UNAVAILABLE")

    def _command(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != COMMAND_FIELDS:
            raise BindingOperatorError("INVALID_REQUEST")
        command = deepcopy(dict(value))
        _finite_tree(command)
        for field in SCOPE_FIELDS | {"targetRef", "seriesPlanRef", "sourceSeriesPlanVersionRef", "operationAuthorizationRef"}:
            _ref(command[field])
        if type(command["expectedPlanVersion"]) is not int or command["expectedPlanVersion"] < 1:
            raise BindingOperatorError("INVALID_REQUEST")
        digest = command["sourceContentDigest"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise BindingOperatorError("INVALID_REQUEST")
        if command["targetRef"] != self.config["targetRef"]:
            raise BindingOperatorError("TARGET_UNAVAILABLE")
        allowed = any(all(scope[field] == command[field] for field in SCOPE_FIELDS)
                      and command["operationAuthorizationRef"] in scope["operationAuthorizationRefs"]
                      for scope in self.config["allowedScopes"])
        if not allowed:
            raise BindingOperatorError("SCOPE_FORBIDDEN")
        bindings = command["episodePlanItemBindings"]
        if not isinstance(bindings, list):
            raise BindingOperatorError("INVALID_REQUEST")
        episodes, items = set(), set()
        for binding in bindings:
            if not isinstance(binding, dict) or set(binding) != {"episodeRef", "episodePlanItemRef"}:
                raise BindingOperatorError("INVALID_REQUEST")
            episode, item = _ref(binding["episodeRef"]), _ref(binding["episodePlanItemRef"])
            if episode in episodes or item in items:
                raise BindingOperatorError("INVALID_REQUEST")
            episodes.add(episode)
            items.add(item)
        return command

    def _read(self, command):
        self._check_target()
        workspace = self.assembly.series_planning.get_workspace(
            command["workspaceRef"], command["projectRef"], command["seriesRef"])
        plan, versions = workspace.get("plan"), workspace.get("versions")
        if not isinstance(plan, dict) or not isinstance(versions, list):
            raise BindingOperatorError("UNRESOLVED_OUTCOME")
        scope = {field: command[field] for field in SCOPE_FIELDS | {"seriesPlanRef"}}
        if any(plan.get(field) != value for field, value in scope.items()):
            raise BindingOperatorError("CONFLICT")
        source_matches = [v for v in versions if v.get("seriesPlanVersionRef") == command["sourceSeriesPlanVersionRef"]]
        if len(source_matches) != 1:
            raise BindingOperatorError("UNRESOLVED_OUTCOME")
        source = source_matches[0]
        if (source.get("schemaVersion") not in {V1, V2}
                or any(source.get(field) != value for field, value in scope.items())
                or source.get("contentProfileRef") != plan.get("contentProfileRef")
                or source_content_digest(source) != command["sourceContentDigest"]):
            raise BindingOperatorError("CONFLICT")
        items = source["episodePlanItems"]
        positions = {item["episodePlanItemRef"]: index for index, item in enumerate(items)}
        if len(positions) != len(items):
            raise BindingOperatorError("UNRESOLVED_OUTCOME")
        for binding in command["episodePlanItemBindings"]:
            if binding["episodePlanItemRef"] not in positions:
                raise BindingOperatorError("INVALID_REQUEST")
            context = self.assembly.project_context.build_context(
                command["workspaceRef"], command["projectRef"], command["seriesRef"], binding["episodeRef"])
            if (context.get("episode", {}).get("episodeRef") != binding["episodeRef"]
                    or context.get("contentProfileRef") != plan.get("contentProfileRef")):
                raise BindingOperatorError("CONFLICT")
        bindings = sorted(command["episodePlanItemBindings"],
                          key=lambda b: (positions[b["episodePlanItemRef"]], b["episodeRef"]))
        self._check_target()
        if (plan.get("version") == command["expectedPlanVersion"]
                and plan.get("currentSeriesPlanVersionRef") == source["seriesPlanVersionRef"]):
            return plan, source, bindings, None
        matches = [v for v in versions if (
            all(v.get(field) == value for field, value in scope.items())
            and v.get("contentProfileRef") == source["contentProfileRef"]
            and v.get("schemaVersion") == V2
            and v.get("parentSeriesPlanVersionRef") == source["seriesPlanVersionRef"]
            and v.get("changeKind") == "episode-plan-item-binding"
            and v.get("versionNumber") == source["versionNumber"] + 1
            and v.get("episodePlanItemBindings") == bindings
            and all(v.get(field) == source[field] for field in CONTENT_FIELDS))]
        if (len(matches) != 1 or plan.get("version") != command["expectedPlanVersion"] + 1
                or plan.get("currentSeriesPlanVersionRef") != matches[0]["seriesPlanVersionRef"]
                or any(v.get("versionNumber", 0) > matches[0]["versionNumber"] for v in versions)):
            raise BindingOperatorError("CONFLICT")
        return plan, source, bindings, matches[0]

    @staticmethod
    def _receipt(command, plan, version, *, created=False, status):
        ref = version["seriesPlanVersionRef"] if version is not None else None
        return {"ok": True, "status": status, "targetRef": command["targetRef"],
                "operationAuthorizationRef": command["operationAuthorizationRef"],
                "BINDING_VERSION_CREATED": created,
                "BINDING_VERSION_CURRENT": ref is not None and plan["currentSeriesPlanVersionRef"] == ref,
                "BINDING_VERSION_CONFIRMED": ref is not None and plan["confirmedSeriesPlanVersionRef"] == ref,
                "plan": plan, "version": version}

    def execute(self, value: Mapping[str, Any], *, apply: bool = False) -> dict[str, Any]:
        if type(apply) is not bool:
            raise BindingOperatorError("INVALID_REQUEST")
        command = self._command(value)
        try:
            plan, source, bindings, recovered = self._read(command)
            if recovered is not None:
                return self._receipt(command, plan, recovered,
                    status="BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK")
            if not apply:
                return self._receipt(command, plan, None, status="PREFLIGHT_READY")
            # Revalidate the caller's unchanged expectation immediately before CAS.
            plan, source, bindings, recovered = self._read(command)
            if recovered is not None:
                return self._receipt(command, plan, recovered,
                    status="BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK")
            write_command = {field: command[field] for field in SCOPE_FIELDS | {"seriesPlanRef", "expectedPlanVersion"}}
            write_command["episodePlanItemBindings"] = bindings
            try:
                written = self.assembly.series_planning.create_episode_plan_item_binding_version(write_command)
            except Exception:
                # A response can be lost after commit. Never issue a second write.
                try:
                    observed, _, _, recovered = self._read(command)
                    if recovered is not None:
                        return self._receipt(command, observed, recovered,
                            status="BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK")
                except Exception:
                    pass
                raise BindingOperatorError("UNRESOLVED_OUTCOME") from None
            observed, _, _, recovered = self._read(command)
            if recovered is None or recovered != written["version"]:
                raise BindingOperatorError("UNRESOLVED_OUTCOME")
            # Preserve the actual successful command response (including draft).
            # Recovery above returns the current authoritative read projection,
            # never a reconstruction of this first acknowledgement.
            return self._receipt(command, written["plan"], recovered,
                                 created=True, status="BINDING_VERSION_CREATED")
        except BindingOperatorError:
            raise
        except SeriesPlanningPublicError as exc:
            raise BindingOperatorError("CONFLICT" if exc.status in {400, 404, 409} else "UNRESOLVED_OUTCOME") from None
        except Exception:
            raise BindingOperatorError("UNRESOLVED_OUTCOME") from None
