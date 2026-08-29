"""Series-scoped immutable VoiceLock roots, versions, and confirmations.

Voice identity is deliberately independent from the production-run-scoped G2
IdentityLock.  A VoiceLock root is unique for one character inside one exact
Workspace/Project/Series scope.  Semantic versions are append-only; confirmation
is a separate digest-pinned fact, so confirming a candidate never rewrites it.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol

from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
    _idempotency_key,
    _required_ref,
    _utc_now,
)


VOICE_LOCK_SCHEMA_VERSION = "v5.voice-lock.v1"
VOICE_LOCK_VERSION_SCHEMA_VERSION = "v5.voice-lock-version.v1"
VOICE_LOCK_CONFIRMATION_SCHEMA_VERSION = "v5.voice-lock-confirmation.v1"
VOICE_LOCK_OPERATION_SCHEMA_VERSION = "v5.voice-lock-operation.v1"
VOICE_LOCK_STORE_SCHEMA_VERSION = 1
VOICE_GENDERS = frozenset({"female", "male"})
DEFAULT_LANGUAGE_CODE = "zh-CN"


class VoiceLockConflictError(EpisodeProductionError):
    code = "voice_lock_conflict"


class VoiceLockImmutableError(EpisodeProductionError):
    code = "voice_lock_immutable"


class VoiceLockNotConfirmedError(EpisodeProductionError):
    code = "voice_lock_not_confirmed"


def _scope(
    workspace_ref: Any, project_ref: Any, series_ref: Any
) -> tuple[str, str, str]:
    return (
        _required_ref(workspace_ref, "workspaceRef"),
        _required_ref(project_ref, "projectRef"),
        _required_ref(series_ref, "seriesRef"),
    )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _number(value: Any, field: str, *, positive: bool = False) -> int | float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (positive and value <= 0)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _closed_command(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    operation: str,
) -> None:
    if (
        not isinstance(value, Mapping)
        or not required.issubset(value)
        or set(value) - required - optional
    ):
        raise EpisodeProductionError(
            f"command fields do not match the {operation} contract"
        )


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


def _validate_sealed(value: Mapping[str, Any], field: str) -> None:
    if not isinstance(value, Mapping):
        raise RepositoryUnavailableError(f"{field} is invalid")
    unsigned = deepcopy(dict(value))
    supplied = unsigned.pop("payloadDigest", None)
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise RepositoryUnavailableError(f"{field} digest verification failed")


_ROOT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "voiceRef",
        "characterRef",
        "currentVoiceLockVersionRef",
        "confirmedVoiceLockVersionRef",
        "confirmedVoiceLockDigest",
        "revision",
        "createdAt",
        "updatedAt",
        "payloadDigest",
    }
)
_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "voiceRef",
        "voiceLockVersionRef",
        "versionNumber",
        "parentVoiceLockVersionRef",
        "parentVoiceLockDigest",
        "characterRef",
        "engineFamily",
        "voiceId",
        "gender",
        "apparentAge",
        "pitchSemitones",
        "rateScale",
        "timbreDescriptor",
        "languageCode",
        "state",
        "immutable",
        "createdAt",
        "payloadDigest",
    }
)
_CONFIRMATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "voiceLockConfirmationRef",
        "voiceRef",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "characterRef",
        "state",
        "createdAt",
        "payloadDigest",
    }
)
_OPERATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "idempotencyKey",
        "operationKind",
        "requestDigest",
        "response",
        "createdAt",
        "payloadDigest",
    }
)


def _validate_root(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ROOT_FIELDS:
        raise RepositoryUnavailableError("VoiceLock root fields are invalid")
    _validate_sealed(value, "VoiceLock root")
    scope = _scope(
        value.get("workspaceRef"), value.get("projectRef"), value.get("seriesRef")
    )
    _required_ref(value.get("voiceRef"), "voiceRef")
    _required_ref(value.get("characterRef"), "characterRef")
    _required_ref(
        value.get("currentVoiceLockVersionRef"), "currentVoiceLockVersionRef"
    )
    confirmed_ref = value.get("confirmedVoiceLockVersionRef")
    confirmed_digest = value.get("confirmedVoiceLockDigest")
    if (confirmed_ref is None) != (confirmed_digest is None):
        raise RepositoryUnavailableError("VoiceLock confirmation pointer is incomplete")
    if confirmed_ref is not None:
        _required_ref(confirmed_ref, "confirmedVoiceLockVersionRef")
        if not isinstance(confirmed_digest, str) or len(confirmed_digest) != 64:
            raise RepositoryUnavailableError("VoiceLock confirmation digest is invalid")
    _positive_int(value.get("revision"), "revision")
    if value.get("schemaVersion") != VOICE_LOCK_SCHEMA_VERSION:
        raise RepositoryUnavailableError("VoiceLock root schema is unsupported")
    _text(value.get("createdAt"), "createdAt")
    _text(value.get("updatedAt"), "updatedAt")
    result = deepcopy(dict(value))
    if tuple(result[field] for field in ("workspaceRef", "projectRef", "seriesRef")) != scope:
        raise RepositoryUnavailableError("VoiceLock root scope is invalid")
    return result


def _validate_version(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _VERSION_FIELDS:
        raise RepositoryUnavailableError("VoiceLockVersion fields are invalid")
    _validate_sealed(value, "VoiceLockVersion")
    _scope(value.get("workspaceRef"), value.get("projectRef"), value.get("seriesRef"))
    for field in ("voiceRef", "voiceLockVersionRef", "characterRef"):
        _required_ref(value.get(field), field)
    version_number = _positive_int(value.get("versionNumber"), "versionNumber")
    parent_ref = value.get("parentVoiceLockVersionRef")
    parent_digest = value.get("parentVoiceLockDigest")
    if version_number == 1:
        if parent_ref is not None or parent_digest is not None:
            raise RepositoryUnavailableError("initial VoiceLockVersion has a parent")
    else:
        _required_ref(parent_ref, "parentVoiceLockVersionRef")
        if not isinstance(parent_digest, str) or len(parent_digest) != 64:
            raise RepositoryUnavailableError("VoiceLockVersion parent digest is invalid")
    if value.get("schemaVersion") != VOICE_LOCK_VERSION_SCHEMA_VERSION:
        raise RepositoryUnavailableError("VoiceLockVersion schema is unsupported")
    gender = value.get("gender")
    if not isinstance(gender, str) or gender not in VOICE_GENDERS:
        raise RepositoryUnavailableError("VoiceLockVersion gender is invalid")
    _required_ref(value.get("engineFamily"), "engineFamily")
    _required_ref(value.get("voiceId"), "voiceId")
    _positive_int(value.get("apparentAge"), "apparentAge")
    _number(value.get("pitchSemitones"), "pitchSemitones")
    _number(value.get("rateScale"), "rateScale", positive=True)
    _text(value.get("timbreDescriptor"), "timbreDescriptor")
    _required_ref(value.get("languageCode"), "languageCode")
    if value.get("state") != "CANDIDATE" or value.get("immutable") is not True:
        raise RepositoryUnavailableError("VoiceLockVersion lifecycle is invalid")
    _text(value.get("createdAt"), "createdAt")
    return deepcopy(dict(value))


def _validate_confirmation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONFIRMATION_FIELDS:
        raise RepositoryUnavailableError("VoiceLockConfirmation fields are invalid")
    _validate_sealed(value, "VoiceLockConfirmation")
    _scope(value.get("workspaceRef"), value.get("projectRef"), value.get("seriesRef"))
    for field in (
        "voiceLockConfirmationRef",
        "voiceRef",
        "voiceLockVersionRef",
        "characterRef",
    ):
        _required_ref(value.get(field), field)
    digest = value.get("voiceLockDigest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RepositoryUnavailableError("VoiceLockConfirmation digest is invalid")
    if (
        value.get("schemaVersion") != VOICE_LOCK_CONFIRMATION_SCHEMA_VERSION
        or value.get("state") != "CONFIRMED"
    ):
        raise RepositoryUnavailableError("VoiceLockConfirmation lifecycle is invalid")
    _text(value.get("createdAt"), "createdAt")
    return deepcopy(dict(value))


def validate_confirmed_voice_lock_bundle(value: Any) -> dict[str, Any]:
    """Validate the exact public bundle consumed by downstream M12 services."""

    required_fields = {
        "voiceLock",
        "voiceLockVersion",
        "voiceLockConfirmation",
    }
    if not isinstance(value, Mapping) or set(value) not in (
        required_fields,
        required_fields | {"idempotentReplay"},
    ):
        raise RepositoryUnavailableError(
            "confirmed VoiceLock bundle fields are invalid"
        )
    if "idempotentReplay" in value and not isinstance(
        value["idempotentReplay"], bool
    ):
        raise RepositoryUnavailableError(
            "confirmed VoiceLock replay metadata is invalid"
        )
    root = _validate_root(value["voiceLock"])
    version = _validate_version(value["voiceLockVersion"])
    confirmation = _validate_confirmation(value["voiceLockConfirmation"])
    scope = (root["workspaceRef"], root["projectRef"], root["seriesRef"])
    if (
        tuple(version[field] for field in ("workspaceRef", "projectRef", "seriesRef"))
        != scope
        or tuple(
            confirmation[field]
            for field in ("workspaceRef", "projectRef", "seriesRef")
        )
        != scope
        or version["voiceRef"] != root["voiceRef"]
        or confirmation["voiceRef"] != root["voiceRef"]
        or version["characterRef"] != root["characterRef"]
        or confirmation["characterRef"] != root["characterRef"]
        or root["confirmedVoiceLockVersionRef"]
        != version["voiceLockVersionRef"]
        or root["confirmedVoiceLockDigest"] != version["payloadDigest"]
        or confirmation["voiceLockVersionRef"]
        != version["voiceLockVersionRef"]
        or confirmation["voiceLockDigest"] != version["payloadDigest"]
    ):
        raise RepositoryUnavailableError(
            "confirmed VoiceLock bundle lineage is inconsistent"
        )
    return {
        "voiceLock": root,
        "voiceLockVersion": version,
        "voiceLockConfirmation": confirmation,
    }


def _validate_response(operation_kind: str, response: Mapping[str, Any]) -> None:
    if not isinstance(operation_kind, str):
        raise RepositoryUnavailableError("VoiceLock operation response is invalid")
    expected = {
        "create-voice-lock": {"voiceLock", "voiceLockVersion"},
        "create-voice-lock-version": {"voiceLock", "voiceLockVersion"},
        "confirm-voice-lock": {
            "voiceLock",
            "voiceLockVersion",
            "voiceLockConfirmation",
        },
    }.get(operation_kind)
    if expected is None or not isinstance(response, Mapping) or set(response) != expected:
        raise RepositoryUnavailableError("VoiceLock operation response is invalid")
    root = _validate_root(response["voiceLock"])
    version = _validate_version(response["voiceLockVersion"])
    root_scope = tuple(
        root[field] for field in ("workspaceRef", "projectRef", "seriesRef")
    )
    version_scope = tuple(
        version[field] for field in ("workspaceRef", "projectRef", "seriesRef")
    )
    if (
        root_scope != version_scope
        or root["voiceRef"] != version["voiceRef"]
        or root["characterRef"] != version["characterRef"]
        or root["currentVoiceLockVersionRef"]
        != version["voiceLockVersionRef"]
    ):
        raise RepositoryUnavailableError("VoiceLock operation lineage is invalid")
    if operation_kind == "create-voice-lock" and (
        version["versionNumber"] != 1
        or root["confirmedVoiceLockVersionRef"] is not None
        or root["confirmedVoiceLockDigest"] is not None
    ):
        raise RepositoryUnavailableError("initial VoiceLock lineage is invalid")
    if operation_kind == "create-voice-lock-version" and (
        version["versionNumber"] <= 1
        or version["parentVoiceLockVersionRef"]
        != root["confirmedVoiceLockVersionRef"]
        or version["parentVoiceLockDigest"]
        != root["confirmedVoiceLockDigest"]
    ):
        raise RepositoryUnavailableError("successor VoiceLock lineage is invalid")
    if operation_kind == "confirm-voice-lock":
        validate_confirmed_voice_lock_bundle(response)


def _validate_operation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OPERATION_FIELDS:
        raise RepositoryUnavailableError("VoiceLock operation fields are invalid")
    _validate_sealed(value, "VoiceLock operation")
    _scope(value.get("workspaceRef"), value.get("projectRef"), value.get("seriesRef"))
    _idempotency_key(value.get("idempotencyKey"))
    request_digest = value.get("requestDigest")
    if not isinstance(request_digest, str) or len(request_digest) != 64:
        raise RepositoryUnavailableError("VoiceLock request digest is invalid")
    operation_kind = value.get("operationKind")
    _validate_response(operation_kind, value.get("response"))
    response_root = value["response"]["voiceLock"]
    if tuple(
        value[field] for field in ("workspaceRef", "projectRef", "seriesRef")
    ) != tuple(
        response_root[field]
        for field in ("workspaceRef", "projectRef", "seriesRef")
    ):
        raise RepositoryUnavailableError("VoiceLock operation scope is inconsistent")
    _text(value.get("createdAt"), "createdAt")
    if value.get("schemaVersion") != VOICE_LOCK_OPERATION_SCHEMA_VERSION:
        raise RepositoryUnavailableError("VoiceLock operation schema is unsupported")
    return deepcopy(dict(value))


def _validate_write_inputs(
    *,
    root: Mapping[str, Any],
    operation: Mapping[str, Any],
    version: Mapping[str, Any] | None = None,
    confirmation: Mapping[str, Any] | None = None,
) -> None:
    response = operation["response"]
    if response.get("voiceLock") != root:
        raise RepositoryUnavailableError("VoiceLock write root is inconsistent")
    if version is not None and response.get("voiceLockVersion") != version:
        raise RepositoryUnavailableError("VoiceLockVersion write is inconsistent")
    if (
        confirmation is not None
        and response.get("voiceLockConfirmation") != confirmation
    ):
        raise RepositoryUnavailableError(
            "VoiceLockConfirmation write is inconsistent"
        )


def _traits(command: Mapping[str, Any]) -> dict[str, Any]:
    gender = command.get("gender")
    if not isinstance(gender, str) or gender not in VOICE_GENDERS:
        raise EpisodeProductionError("gender is invalid")
    return {
        "engineFamily": _required_ref(command.get("engineFamily"), "engineFamily"),
        "voiceId": _required_ref(command.get("voiceId"), "voiceId"),
        "gender": gender,
        "apparentAge": _positive_int(command.get("apparentAge"), "apparentAge"),
        "pitchSemitones": _number(
            command.get("pitchSemitones"), "pitchSemitones"
        ),
        "rateScale": _number(command.get("rateScale"), "rateScale", positive=True),
        "timbreDescriptor": _text(
            command.get("timbreDescriptor"), "timbreDescriptor"
        ),
        "languageCode": _required_ref(
            command.get("languageCode", DEFAULT_LANGUAGE_CODE), "languageCode"
        ),
    }


class VoiceLockRepository(Protocol):
    def get_root_by_ref(
        self, scope: tuple[str, str, str], voice_ref: str
    ) -> dict[str, Any] | None: ...

    def get_root_by_character(
        self, scope: tuple[str, str, str], character_ref: str
    ) -> dict[str, Any] | None: ...

    def get_version(
        self, scope: tuple[str, str, str], voice_ref: str, version_ref: str
    ) -> dict[str, Any] | None: ...

    def list_versions(
        self, scope: tuple[str, str, str], voice_ref: str
    ) -> list[dict[str, Any]]: ...

    def get_confirmation(
        self, scope: tuple[str, str, str], voice_ref: str, version_ref: str
    ) -> dict[str, Any] | None: ...

    def get_operation(
        self, scope: tuple[str, str, str], idempotency_key: str
    ) -> dict[str, Any] | None: ...

    def create_voice_lock(
        self,
        root: Mapping[str, Any],
        version: Mapping[str, Any],
        operation: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]: ...

    def create_voice_lock_version(
        self,
        root: Mapping[str, Any],
        version: Mapping[str, Any],
        operation: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> tuple[dict[str, Any], bool]: ...

    def confirm_voice_lock(
        self,
        root: Mapping[str, Any],
        confirmation: Mapping[str, Any],
        operation: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> tuple[dict[str, Any], bool]: ...


def _operation_replay(
    operation: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[dict[str, Any], bool]:
    stored = _validate_operation(operation)
    if (
        stored["operationKind"] != expected["operationKind"]
        or stored["requestDigest"] != expected["requestDigest"]
    ):
        raise IdempotencyConflictError("VoiceLock idempotency content changed")
    return deepcopy(dict(stored["response"])), True


class InMemoryVoiceLockAdapter:
    def __init__(self) -> None:
        self._roots: dict[tuple[str, ...], dict[str, Any]] = {}
        self._characters: dict[tuple[str, ...], str] = {}
        self._versions: dict[tuple[str, ...], dict[str, Any]] = {}
        self._confirmations: dict[tuple[str, ...], dict[str, Any]] = {}
        self._confirmation_refs: set[tuple[str, ...]] = set()
        self._operations: dict[tuple[str, ...], dict[str, Any]] = {}
        self._lock = RLock()

    @staticmethod
    def _root_key(scope: tuple[str, str, str], voice_ref: str) -> tuple[str, ...]:
        return (*scope, voice_ref)

    @staticmethod
    def _version_key(
        scope: tuple[str, str, str], voice_ref: str, version_ref: str
    ) -> tuple[str, ...]:
        return (*scope, voice_ref, version_ref)

    def get_root_by_ref(self, scope, voice_ref):
        with self._lock:
            value = self._roots.get(self._root_key(scope, voice_ref))
            return None if value is None else _validate_root(value)

    def get_root_by_character(self, scope, character_ref):
        with self._lock:
            voice_ref = self._characters.get((*scope, character_ref))
            if voice_ref is None:
                return None
            return _validate_root(self._roots[self._root_key(scope, voice_ref)])

    def get_version(self, scope, voice_ref, version_ref):
        with self._lock:
            value = self._versions.get(
                self._version_key(scope, voice_ref, version_ref)
            )
            return None if value is None else _validate_version(value)

    def list_versions(self, scope, voice_ref):
        with self._lock:
            values = [
                _validate_version(value)
                for key, value in self._versions.items()
                if key[:4] == (*scope, voice_ref)
            ]
            return sorted(values, key=lambda item: item["versionNumber"])

    def get_confirmation(self, scope, voice_ref, version_ref):
        with self._lock:
            value = self._confirmations.get((*scope, voice_ref, version_ref))
            return None if value is None else _validate_confirmation(value)

    def get_operation(self, scope, idempotency_key):
        with self._lock:
            value = self._operations.get((*scope, idempotency_key))
            return None if value is None else _validate_operation(value)

    def _existing_operation(self, operation):
        scope = (
            operation["workspaceRef"],
            operation["projectRef"],
            operation["seriesRef"],
        )
        return self._operations.get((*scope, operation["idempotencyKey"]))

    def create_voice_lock(self, root, version, operation):
        selected_root = _validate_root(root)
        selected_version = _validate_version(version)
        selected_operation = _validate_operation(operation)
        _validate_write_inputs(
            root=selected_root,
            version=selected_version,
            operation=selected_operation,
        )
        scope = (
            selected_root["workspaceRef"],
            selected_root["projectRef"],
            selected_root["seriesRef"],
        )
        with self._lock:
            replay = self._existing_operation(selected_operation)
            if replay is not None:
                return _operation_replay(replay, selected_operation)
            root_key = self._root_key(scope, selected_root["voiceRef"])
            character_key = (*scope, selected_root["characterRef"])
            version_key = self._version_key(
                scope,
                selected_root["voiceRef"],
                selected_version["voiceLockVersionRef"],
            )
            if (
                root_key in self._roots
                or character_key in self._characters
                or version_key in self._versions
            ):
                raise VoiceLockConflictError(
                    "character already has a VoiceLock in this series"
                )
            self._roots[root_key] = deepcopy(selected_root)
            self._characters[character_key] = selected_root["voiceRef"]
            self._versions[version_key] = deepcopy(selected_version)
            self._operations[(*scope, selected_operation["idempotencyKey"])] = (
                deepcopy(selected_operation)
            )
            return deepcopy(dict(selected_operation["response"])), False

    def create_voice_lock_version(
        self, root, version, operation, *, expected_revision
    ):
        selected_root = _validate_root(root)
        selected_version = _validate_version(version)
        selected_operation = _validate_operation(operation)
        _validate_write_inputs(
            root=selected_root,
            version=selected_version,
            operation=selected_operation,
        )
        scope = (
            selected_root["workspaceRef"],
            selected_root["projectRef"],
            selected_root["seriesRef"],
        )
        with self._lock:
            replay = self._existing_operation(selected_operation)
            if replay is not None:
                return _operation_replay(replay, selected_operation)
            root_key = self._root_key(scope, selected_root["voiceRef"])
            current = self._roots.get(root_key)
            if current is None:
                raise RecordNotFoundError("VoiceLock was not found")
            if current["revision"] != expected_revision:
                raise StaleInputError("VoiceLock revision changed")
            version_key = self._version_key(
                scope,
                selected_root["voiceRef"],
                selected_version["voiceLockVersionRef"],
            )
            if version_key in self._versions:
                raise VoiceLockImmutableError(
                    "VoiceLockVersion cannot be overwritten"
                )
            self._versions[version_key] = deepcopy(selected_version)
            self._roots[root_key] = deepcopy(selected_root)
            self._operations[(*scope, selected_operation["idempotencyKey"])] = (
                deepcopy(selected_operation)
            )
            return deepcopy(dict(selected_operation["response"])), False

    def confirm_voice_lock(
        self, root, confirmation, operation, *, expected_revision
    ):
        selected_root = _validate_root(root)
        selected_confirmation = _validate_confirmation(confirmation)
        selected_operation = _validate_operation(operation)
        _validate_write_inputs(
            root=selected_root,
            confirmation=selected_confirmation,
            operation=selected_operation,
        )
        scope = (
            selected_root["workspaceRef"],
            selected_root["projectRef"],
            selected_root["seriesRef"],
        )
        with self._lock:
            replay = self._existing_operation(selected_operation)
            if replay is not None:
                return _operation_replay(replay, selected_operation)
            root_key = self._root_key(scope, selected_root["voiceRef"])
            current = self._roots.get(root_key)
            if current is None:
                raise RecordNotFoundError("VoiceLock was not found")
            if current["revision"] != expected_revision:
                raise StaleInputError("VoiceLock revision changed")
            confirmation_key = (
                *scope,
                selected_confirmation["voiceRef"],
                selected_confirmation["voiceLockVersionRef"],
            )
            confirmation_ref_key = (
                *scope,
                selected_confirmation["voiceLockConfirmationRef"],
            )
            if confirmation_key in self._confirmations:
                raise VoiceLockImmutableError("VoiceLockVersion is already confirmed")
            if confirmation_ref_key in self._confirmation_refs:
                raise VoiceLockConflictError(
                    "VoiceLockConfirmation identity already exists"
                )
            self._confirmations[confirmation_key] = deepcopy(selected_confirmation)
            self._confirmation_refs.add(confirmation_ref_key)
            self._roots[root_key] = deepcopy(selected_root)
            self._operations[(*scope, selected_operation["idempotencyKey"])] = (
                deepcopy(selected_operation)
            )
            return deepcopy(dict(selected_operation["response"])), False


def _json_dump(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_load(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise RepositoryUnavailableError(f"{field} is invalid")
    try:
        result = json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RepositoryUnavailableError(f"{field} is invalid") from exc
    if not isinstance(result, dict) or _json_dump(result) != value:
        raise RepositoryUnavailableError(f"{field} is not canonical")
    return result


class SqliteVoiceLockAdapter:
    """Local-development durable VoiceLock repository."""

    _TABLES = {
        "v5_voice_lock_schema",
        "v5_voice_locks",
        "v5_voice_lock_versions",
        "v5_voice_lock_confirmations",
        "v5_voice_lock_operations",
    }
    _COLUMNS = {
        "v5_voice_lock_schema": (
            ("component", "TEXT", 0, 1),
            ("schema_version", "INTEGER", 1, 0),
        ),
        "v5_voice_locks": (
            ("workspace_ref", "TEXT", 1, 1),
            ("project_ref", "TEXT", 1, 2),
            ("series_ref", "TEXT", 1, 3),
            ("voice_ref", "TEXT", 1, 4),
            ("character_ref", "TEXT", 1, 0),
            ("current_version_ref", "TEXT", 1, 0),
            ("confirmed_version_ref", "TEXT", 0, 0),
            ("confirmed_version_digest", "TEXT", 0, 0),
            ("revision", "INTEGER", 1, 0),
            ("payload_json", "TEXT", 1, 0),
            ("payload_digest", "TEXT", 1, 0),
        ),
        "v5_voice_lock_versions": (
            ("workspace_ref", "TEXT", 1, 1),
            ("project_ref", "TEXT", 1, 2),
            ("series_ref", "TEXT", 1, 3),
            ("voice_ref", "TEXT", 1, 4),
            ("voice_lock_version_ref", "TEXT", 1, 5),
            ("version_number", "INTEGER", 1, 0),
            ("parent_version_ref", "TEXT", 0, 0),
            ("parent_version_digest", "TEXT", 0, 0),
            ("character_ref", "TEXT", 1, 0),
            ("payload_json", "TEXT", 1, 0),
            ("payload_digest", "TEXT", 1, 0),
        ),
        "v5_voice_lock_confirmations": (
            ("workspace_ref", "TEXT", 1, 1),
            ("project_ref", "TEXT", 1, 2),
            ("series_ref", "TEXT", 1, 3),
            ("voice_lock_confirmation_ref", "TEXT", 1, 4),
            ("voice_ref", "TEXT", 1, 0),
            ("voice_lock_version_ref", "TEXT", 1, 0),
            ("voice_lock_digest", "TEXT", 1, 0),
            ("payload_json", "TEXT", 1, 0),
            ("payload_digest", "TEXT", 1, 0),
        ),
        "v5_voice_lock_operations": (
            ("workspace_ref", "TEXT", 1, 1),
            ("project_ref", "TEXT", 1, 2),
            ("series_ref", "TEXT", 1, 3),
            ("idempotency_key", "TEXT", 1, 4),
            ("operation_kind", "TEXT", 1, 0),
            ("request_digest", "TEXT", 1, 0),
            ("payload_json", "TEXT", 1, 0),
            ("payload_digest", "TEXT", 1, 0),
        ),
    }
    _UNIQUE_KEYS = {
        "v5_voice_lock_schema": {
            ("component",),
        },
        "v5_voice_locks": {
            ("workspace_ref", "project_ref", "series_ref", "voice_ref"),
            ("workspace_ref", "project_ref", "series_ref", "character_ref"),
        },
        "v5_voice_lock_versions": {
            (
                "workspace_ref",
                "project_ref",
                "series_ref",
                "voice_ref",
                "voice_lock_version_ref",
            ),
            (
                "workspace_ref",
                "project_ref",
                "series_ref",
                "voice_ref",
                "version_number",
            ),
        },
        "v5_voice_lock_confirmations": {
            (
                "workspace_ref",
                "project_ref",
                "series_ref",
                "voice_lock_confirmation_ref",
            ),
            (
                "workspace_ref",
                "project_ref",
                "series_ref",
                "voice_ref",
                "voice_lock_version_ref",
            ),
        },
        "v5_voice_lock_operations": {
            ("workspace_ref", "project_ref", "series_ref", "idempotency_key"),
        },
    }
    _FOREIGN_KEYS = {
        "v5_voice_lock_schema": (),
        "v5_voice_locks": (),
        "v5_voice_lock_versions": (
            ("v5_voice_locks", "workspace_ref", "workspace_ref", "RESTRICT"),
            ("v5_voice_locks", "project_ref", "project_ref", "RESTRICT"),
            ("v5_voice_locks", "series_ref", "series_ref", "RESTRICT"),
            ("v5_voice_locks", "voice_ref", "voice_ref", "RESTRICT"),
        ),
        "v5_voice_lock_confirmations": (
            ("v5_voice_lock_versions", "workspace_ref", "workspace_ref", "RESTRICT"),
            ("v5_voice_lock_versions", "project_ref", "project_ref", "RESTRICT"),
            ("v5_voice_lock_versions", "series_ref", "series_ref", "RESTRICT"),
            ("v5_voice_lock_versions", "voice_ref", "voice_ref", "RESTRICT"),
            (
                "v5_voice_lock_versions",
                "voice_lock_version_ref",
                "voice_lock_version_ref",
                "RESTRICT",
            ),
        ),
        "v5_voice_lock_operations": (),
    }

    def __init__(
        self, database_path: Path | str, *, initialize_if_missing: bool = True
    ) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_or_validate(initialize_if_missing)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=10, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE v5_voice_lock_schema ("
            "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO v5_voice_lock_schema VALUES ('voice_lock', ?) ",
            (VOICE_LOCK_STORE_SCHEMA_VERSION,),
        )
        connection.execute(
            """CREATE TABLE v5_voice_locks (
            workspace_ref TEXT NOT NULL,
            project_ref TEXT NOT NULL,
            series_ref TEXT NOT NULL,
            voice_ref TEXT NOT NULL,
            character_ref TEXT NOT NULL,
            current_version_ref TEXT NOT NULL,
            confirmed_version_ref TEXT,
            confirmed_version_digest TEXT,
            revision INTEGER NOT NULL CHECK(revision > 0),
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, project_ref, series_ref, voice_ref),
            UNIQUE(workspace_ref, project_ref, series_ref, character_ref)
            )"""
        )
        connection.execute(
            """CREATE TABLE v5_voice_lock_versions (
            workspace_ref TEXT NOT NULL,
            project_ref TEXT NOT NULL,
            series_ref TEXT NOT NULL,
            voice_ref TEXT NOT NULL,
            voice_lock_version_ref TEXT NOT NULL,
            version_number INTEGER NOT NULL CHECK(version_number > 0),
            parent_version_ref TEXT,
            parent_version_digest TEXT,
            character_ref TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, project_ref, series_ref, voice_ref,
                        voice_lock_version_ref),
            UNIQUE(workspace_ref, project_ref, series_ref, voice_ref, version_number),
            FOREIGN KEY(workspace_ref, project_ref, series_ref, voice_ref)
              REFERENCES v5_voice_locks(workspace_ref, project_ref, series_ref,
                                        voice_ref) ON DELETE RESTRICT
            )"""
        )
        connection.execute(
            """CREATE TABLE v5_voice_lock_confirmations (
            workspace_ref TEXT NOT NULL,
            project_ref TEXT NOT NULL,
            series_ref TEXT NOT NULL,
            voice_lock_confirmation_ref TEXT NOT NULL,
            voice_ref TEXT NOT NULL,
            voice_lock_version_ref TEXT NOT NULL,
            voice_lock_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, project_ref, series_ref,
                        voice_lock_confirmation_ref),
            UNIQUE(workspace_ref, project_ref, series_ref, voice_ref,
                   voice_lock_version_ref),
            FOREIGN KEY(workspace_ref, project_ref, series_ref, voice_ref,
                        voice_lock_version_ref)
              REFERENCES v5_voice_lock_versions(workspace_ref, project_ref,
                                                 series_ref, voice_ref,
                                                 voice_lock_version_ref)
              ON DELETE RESTRICT
            )"""
        )
        connection.execute(
            """CREATE TABLE v5_voice_lock_operations (
            workspace_ref TEXT NOT NULL,
            project_ref TEXT NOT NULL,
            series_ref TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            operation_kind TEXT NOT NULL,
            request_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, project_ref, series_ref, idempotency_key)
            )"""
        )

    @classmethod
    def _validate_schema(cls, connection: sqlite3.Connection) -> None:
        def schema_objects(selected: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
            return tuple(
                tuple(row)
                for row in selected.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
                )
            )

        expected_connection = sqlite3.connect(":memory:")
        try:
            cls._create_schema(expected_connection)
            expected_objects = schema_objects(expected_connection)
        finally:
            expected_connection.close()
        if schema_objects(connection) != expected_objects:
            raise RepositoryUnavailableError(
                "VoiceLock repository schema objects changed"
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        if [tuple(row) for row in integrity] != [("ok",)]:
            raise RepositoryUnavailableError(
                "VoiceLock repository integrity check failed"
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RepositoryUnavailableError(
                "VoiceLock repository foreign keys are inconsistent"
            )
        for table in sorted(cls._TABLES):
            columns = tuple(
                (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
                for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if columns != cls._COLUMNS[table]:
                raise RepositoryUnavailableError(
                    "VoiceLock repository columns changed"
                )
            unique_keys = {
                tuple(
                    str(item[2])
                    for item in connection.execute(
                        f"PRAGMA index_info({str(index[1])})"
                    )
                )
                for index in connection.execute(f"PRAGMA index_list({table})")
                if int(index[2]) == 1
            }
            if unique_keys != cls._UNIQUE_KEYS[table]:
                raise RepositoryUnavailableError(
                    "VoiceLock repository unique constraints changed"
                )
            foreign_keys = tuple(
                (
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    str(row[6]).upper(),
                )
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")
            )
            if foreign_keys != cls._FOREIGN_KEYS[table]:
                raise RepositoryUnavailableError(
                    "VoiceLock repository foreign keys changed"
                )

    def _initialize_or_validate(self, initialize_if_missing: bool) -> None:
        connection = self._connect()
        try:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if not tables:
                if not initialize_if_missing:
                    raise RepositoryUnavailableError(
                        "VoiceLock repository is not initialized"
                    )
                connection.execute("BEGIN IMMEDIATE")
                self._create_schema(connection)
                self._validate_schema(connection)
                connection.commit()
                return
            if tables != self._TABLES:
                raise RepositoryUnavailableError("VoiceLock repository schema changed")
            marker = connection.execute(
                "SELECT schema_version FROM v5_voice_lock_schema "
                "WHERE component='voice_lock'"
            ).fetchone()
            if (
                marker is None
                or marker["schema_version"] != VOICE_LOCK_STORE_SCHEMA_VERSION
            ):
                raise RepositoryUnavailableError(
                    "VoiceLock repository version is unsupported"
                )
            self._validate_schema(connection)
        except EpisodeProductionError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError(
                "VoiceLock repository initialization failed"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _root_from_row(row: sqlite3.Row) -> dict[str, Any]:
        value = _validate_root(_json_load(row["payload_json"], "VoiceLock root"))
        if (
            row["payload_digest"] != value["payloadDigest"]
            or (
                row["workspace_ref"],
                row["project_ref"],
                row["series_ref"],
                row["voice_ref"],
                row["character_ref"],
                row["current_version_ref"],
                row["confirmed_version_ref"],
                row["confirmed_version_digest"],
                row["revision"],
            )
            != (
                value["workspaceRef"],
                value["projectRef"],
                value["seriesRef"],
                value["voiceRef"],
                value["characterRef"],
                value["currentVoiceLockVersionRef"],
                value["confirmedVoiceLockVersionRef"],
                value["confirmedVoiceLockDigest"],
                value["revision"],
            )
        ):
            raise RepositoryUnavailableError("VoiceLock root projection changed")
        return value

    @staticmethod
    def _version_from_row(row: sqlite3.Row) -> dict[str, Any]:
        value = _validate_version(
            _json_load(row["payload_json"], "VoiceLockVersion")
        )
        if (
            row["payload_digest"] != value["payloadDigest"]
            or (
                row["workspace_ref"],
                row["project_ref"],
                row["series_ref"],
                row["voice_ref"],
                row["voice_lock_version_ref"],
                row["version_number"],
                row["parent_version_ref"],
                row["parent_version_digest"],
                row["character_ref"],
            )
            != (
                value["workspaceRef"],
                value["projectRef"],
                value["seriesRef"],
                value["voiceRef"],
                value["voiceLockVersionRef"],
                value["versionNumber"],
                value["parentVoiceLockVersionRef"],
                value["parentVoiceLockDigest"],
                value["characterRef"],
            )
        ):
            raise RepositoryUnavailableError("VoiceLockVersion projection changed")
        return value

    @staticmethod
    def _confirmation_from_row(row: sqlite3.Row) -> dict[str, Any]:
        value = _validate_confirmation(
            _json_load(row["payload_json"], "VoiceLockConfirmation")
        )
        if (
            (
                row["workspace_ref"],
                row["project_ref"],
                row["series_ref"],
                row["voice_lock_confirmation_ref"],
                row["voice_ref"],
                row["voice_lock_version_ref"],
                row["voice_lock_digest"],
                row["payload_digest"],
            )
            != (
                value["workspaceRef"],
                value["projectRef"],
                value["seriesRef"],
                value["voiceLockConfirmationRef"],
                value["voiceRef"],
                value["voiceLockVersionRef"],
                value["voiceLockDigest"],
                value["payloadDigest"],
            )
        ):
            raise RepositoryUnavailableError(
                "VoiceLockConfirmation projection changed"
            )
        return value

    @staticmethod
    def _operation_from_row(row: sqlite3.Row) -> dict[str, Any]:
        value = _validate_operation(
            _json_load(row["payload_json"], "VoiceLock operation")
        )
        if (
            (
                row["workspace_ref"],
                row["project_ref"],
                row["series_ref"],
                row["idempotency_key"],
                row["operation_kind"],
                row["request_digest"],
                row["payload_digest"],
            )
            != (
                value["workspaceRef"],
                value["projectRef"],
                value["seriesRef"],
                value["idempotencyKey"],
                value["operationKind"],
                value["requestDigest"],
                value["payloadDigest"],
            )
        ):
            raise RepositoryUnavailableError("VoiceLock operation projection changed")
        return value

    def get_root_by_ref(self, scope, voice_ref):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_voice_locks WHERE workspace_ref=? AND "
                "project_ref=? AND series_ref=? AND voice_ref=?",
                (*scope, voice_ref),
            ).fetchone()
            return None if row is None else self._root_from_row(row)
        except EpisodeProductionError:
            raise
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("VoiceLock read failed") from exc
        finally:
            connection.close()

    def get_root_by_character(self, scope, character_ref):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_voice_locks WHERE workspace_ref=? AND "
                "project_ref=? AND series_ref=? AND character_ref=?",
                (*scope, character_ref),
            ).fetchone()
            return None if row is None else self._root_from_row(row)
        except EpisodeProductionError:
            raise
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("VoiceLock read failed") from exc
        finally:
            connection.close()

    def get_version(self, scope, voice_ref, version_ref):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_voice_lock_versions WHERE workspace_ref=? "
                "AND project_ref=? AND series_ref=? AND voice_ref=? "
                "AND voice_lock_version_ref=?",
                (*scope, voice_ref, version_ref),
            ).fetchone()
            return None if row is None else self._version_from_row(row)
        except EpisodeProductionError:
            raise
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("VoiceLockVersion read failed") from exc
        finally:
            connection.close()

    def list_versions(self, scope, voice_ref):
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM v5_voice_lock_versions WHERE workspace_ref=? "
                "AND project_ref=? AND series_ref=? AND voice_ref=? "
                "ORDER BY version_number",
                (*scope, voice_ref),
            ).fetchall()
            return [self._version_from_row(row) for row in rows]
        except EpisodeProductionError:
            raise
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("VoiceLockVersion read failed") from exc
        finally:
            connection.close()

    def get_confirmation(self, scope, voice_ref, version_ref):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_voice_lock_confirmations WHERE workspace_ref=? "
                "AND project_ref=? AND series_ref=? AND voice_ref=? "
                "AND voice_lock_version_ref=?",
                (*scope, voice_ref, version_ref),
            ).fetchone()
            return None if row is None else self._confirmation_from_row(row)
        except EpisodeProductionError:
            raise
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError(
                "VoiceLockConfirmation read failed"
            ) from exc
        finally:
            connection.close()

    def get_operation(self, scope, idempotency_key):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_voice_lock_operations WHERE workspace_ref=? "
                "AND project_ref=? AND series_ref=? AND idempotency_key=?",
                (*scope, idempotency_key),
            ).fetchone()
            return None if row is None else self._operation_from_row(row)
        except EpisodeProductionError:
            raise
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("VoiceLock operation read failed") from exc
        finally:
            connection.close()

    @staticmethod
    def _insert_version(
        connection: sqlite3.Connection, version: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO v5_voice_lock_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                version["workspaceRef"],
                version["projectRef"],
                version["seriesRef"],
                version["voiceRef"],
                version["voiceLockVersionRef"],
                version["versionNumber"],
                version["parentVoiceLockVersionRef"],
                version["parentVoiceLockDigest"],
                version["characterRef"],
                _json_dump(version),
                version["payloadDigest"],
            ),
        )

    @staticmethod
    def _insert_operation(
        connection: sqlite3.Connection, operation: Mapping[str, Any]
    ) -> None:
        connection.execute(
            "INSERT INTO v5_voice_lock_operations VALUES (?,?,?,?,?,?,?,?)",
            (
                operation["workspaceRef"],
                operation["projectRef"],
                operation["seriesRef"],
                operation["idempotencyKey"],
                operation["operationKind"],
                operation["requestDigest"],
                _json_dump(operation),
                operation["payloadDigest"],
            ),
        )

    @staticmethod
    def _operation_in_connection(connection, operation):
        return connection.execute(
            "SELECT * FROM v5_voice_lock_operations WHERE workspace_ref=? "
            "AND project_ref=? AND series_ref=? AND idempotency_key=?",
            (
                operation["workspaceRef"],
                operation["projectRef"],
                operation["seriesRef"],
                operation["idempotencyKey"],
            ),
        ).fetchone()

    @staticmethod
    def _insert_root(connection, root):
        connection.execute(
            "INSERT INTO v5_voice_locks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                root["workspaceRef"],
                root["projectRef"],
                root["seriesRef"],
                root["voiceRef"],
                root["characterRef"],
                root["currentVoiceLockVersionRef"],
                root["confirmedVoiceLockVersionRef"],
                root["confirmedVoiceLockDigest"],
                root["revision"],
                _json_dump(root),
                root["payloadDigest"],
            ),
        )

    @staticmethod
    def _update_root(connection, root, expected_revision):
        cursor = connection.execute(
            "UPDATE v5_voice_locks SET current_version_ref=?, "
            "confirmed_version_ref=?, confirmed_version_digest=?, revision=?, "
            "payload_json=?, payload_digest=? WHERE workspace_ref=? AND "
            "project_ref=? AND series_ref=? AND voice_ref=? AND revision=?",
            (
                root["currentVoiceLockVersionRef"],
                root["confirmedVoiceLockVersionRef"],
                root["confirmedVoiceLockDigest"],
                root["revision"],
                _json_dump(root),
                root["payloadDigest"],
                root["workspaceRef"],
                root["projectRef"],
                root["seriesRef"],
                root["voiceRef"],
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise StaleInputError("VoiceLock revision changed")

    def _write(self, action):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            result = action(connection)
            connection.commit()
            return result
        except EpisodeProductionError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise VoiceLockConflictError("VoiceLock durable identity exists") from exc
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError("VoiceLock write failed") from exc
        finally:
            connection.close()

    def create_voice_lock(self, root, version, operation):
        selected_root = _validate_root(root)
        selected_version = _validate_version(version)
        selected_operation = _validate_operation(operation)
        _validate_write_inputs(
            root=selected_root,
            version=selected_version,
            operation=selected_operation,
        )

        def action(connection):
            replay = self._operation_in_connection(connection, selected_operation)
            if replay is not None:
                return _operation_replay(
                    self._operation_from_row(replay), selected_operation
                )
            self._insert_root(connection, selected_root)
            self._insert_version(connection, selected_version)
            self._insert_operation(connection, selected_operation)
            return deepcopy(dict(selected_operation["response"])), False

        return self._write(action)

    def create_voice_lock_version(
        self, root, version, operation, *, expected_revision
    ):
        selected_root = _validate_root(root)
        selected_version = _validate_version(version)
        selected_operation = _validate_operation(operation)
        _validate_write_inputs(
            root=selected_root,
            version=selected_version,
            operation=selected_operation,
        )

        def action(connection):
            replay = self._operation_in_connection(connection, selected_operation)
            if replay is not None:
                return _operation_replay(
                    self._operation_from_row(replay), selected_operation
                )
            self._insert_version(connection, selected_version)
            self._update_root(connection, selected_root, expected_revision)
            self._insert_operation(connection, selected_operation)
            return deepcopy(dict(selected_operation["response"])), False

        return self._write(action)

    def confirm_voice_lock(
        self, root, confirmation, operation, *, expected_revision
    ):
        selected_root = _validate_root(root)
        selected_confirmation = _validate_confirmation(confirmation)
        selected_operation = _validate_operation(operation)
        _validate_write_inputs(
            root=selected_root,
            confirmation=selected_confirmation,
            operation=selected_operation,
        )

        def action(connection):
            replay = self._operation_in_connection(connection, selected_operation)
            if replay is not None:
                return _operation_replay(
                    self._operation_from_row(replay), selected_operation
                )
            connection.execute(
                "INSERT INTO v5_voice_lock_confirmations VALUES "
                "(?,?,?,?,?,?,?,?,?)",
                (
                    selected_confirmation["workspaceRef"],
                    selected_confirmation["projectRef"],
                    selected_confirmation["seriesRef"],
                    selected_confirmation["voiceLockConfirmationRef"],
                    selected_confirmation["voiceRef"],
                    selected_confirmation["voiceLockVersionRef"],
                    selected_confirmation["voiceLockDigest"],
                    _json_dump(selected_confirmation),
                    selected_confirmation["payloadDigest"],
                ),
            )
            self._update_root(connection, selected_root, expected_revision)
            self._insert_operation(connection, selected_operation)
            return deepcopy(dict(selected_operation["response"])), False

        return self._write(action)


class K2VoiceLockService:
    _TRAIT_FIELDS = frozenset(
        {
            "engineFamily",
            "voiceId",
            "gender",
            "apparentAge",
            "pitchSemitones",
            "rateScale",
            "timbreDescriptor",
        }
    )
    _SCOPE_FIELDS = frozenset({"workspaceRef", "projectRef", "seriesRef"})

    def __init__(
        self,
        repository: VoiceLockRepository,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self._ref_factory = ref_factory
        self._clock = clock

    def _replay(
        self,
        scope: tuple[str, str, str],
        key: str,
        operation_kind: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        stored = self.repository.get_operation(scope, key)
        if stored is None:
            return None
        response, _ = _operation_replay(
            stored,
            {
                "operationKind": operation_kind,
                "requestDigest": request_digest,
            },
        )
        return {**response, "idempotentReplay": True}

    def _operation(
        self,
        *,
        scope: tuple[str, str, str],
        key: str,
        operation_kind: str,
        request_digest: str,
        response: Mapping[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        return _sealed(
            {
                "schemaVersion": VOICE_LOCK_OPERATION_SCHEMA_VERSION,
                "workspaceRef": scope[0],
                "projectRef": scope[1],
                "seriesRef": scope[2],
                "idempotencyKey": key,
                "operationKind": operation_kind,
                "requestDigest": request_digest,
                "response": deepcopy(dict(response)),
                "createdAt": created_at,
            }
        )

    def create_voice_lock(self, command: Mapping[str, Any]) -> dict[str, Any]:
        required = (
            self._SCOPE_FIELDS
            | self._TRAIT_FIELDS
            | frozenset({"characterRef", "idempotencyKey"})
        )
        _closed_command(
            command,
            required=required,
            optional=frozenset({"languageCode"}),
            operation="create VoiceLock",
        )
        scope = _scope(
            command.get("workspaceRef"),
            command.get("projectRef"),
            command.get("seriesRef"),
        )
        character_ref = _required_ref(command.get("characterRef"), "characterRef")
        key = _idempotency_key(command.get("idempotencyKey"))
        traits = _traits(command)
        request_digest = _digest(
            {
                "operationKind": "create-voice-lock",
                "scope": list(scope),
                "characterRef": character_ref,
                "voice": traits,
            }
        )
        replay = self._replay(
            scope, key, "create-voice-lock", request_digest
        )
        if replay is not None:
            return replay
        if self.repository.get_root_by_character(scope, character_ref) is not None:
            raise VoiceLockConflictError(
                "character already has a VoiceLock in this series"
            )
        voice_ref = _required_ref(self._ref_factory("voice-lock"), "voiceRef")
        version_ref = _required_ref(
            self._ref_factory("voice-lock-version"), "voiceLockVersionRef"
        )
        now = _text(self._clock(), "createdAt")
        version = _sealed(
            {
                "schemaVersion": VOICE_LOCK_VERSION_SCHEMA_VERSION,
                "workspaceRef": scope[0],
                "projectRef": scope[1],
                "seriesRef": scope[2],
                "voiceRef": voice_ref,
                "voiceLockVersionRef": version_ref,
                "versionNumber": 1,
                "parentVoiceLockVersionRef": None,
                "parentVoiceLockDigest": None,
                "characterRef": character_ref,
                **traits,
                "state": "CANDIDATE",
                "immutable": True,
                "createdAt": now,
            }
        )
        root = _sealed(
            {
                "schemaVersion": VOICE_LOCK_SCHEMA_VERSION,
                "workspaceRef": scope[0],
                "projectRef": scope[1],
                "seriesRef": scope[2],
                "voiceRef": voice_ref,
                "characterRef": character_ref,
                "currentVoiceLockVersionRef": version_ref,
                "confirmedVoiceLockVersionRef": None,
                "confirmedVoiceLockDigest": None,
                "revision": 1,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        response = {"voiceLock": root, "voiceLockVersion": version}
        operation = self._operation(
            scope=scope,
            key=key,
            operation_kind="create-voice-lock",
            request_digest=request_digest,
            response=response,
            created_at=now,
        )
        stored, replayed = self.repository.create_voice_lock(
            root, version, operation
        )
        return {**stored, "idempotentReplay": replayed}

    def create_voice_lock_version(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        required = (
            self._SCOPE_FIELDS
            | self._TRAIT_FIELDS
            | frozenset(
                {
                    "voiceRef",
                    "baseVoiceLockVersionRef",
                    "baseVoiceLockDigest",
                    "expectedRevision",
                    "idempotencyKey",
                }
            )
        )
        _closed_command(
            command,
            required=required,
            optional=frozenset({"languageCode"}),
            operation="create VoiceLockVersion",
        )
        scope = _scope(
            command.get("workspaceRef"),
            command.get("projectRef"),
            command.get("seriesRef"),
        )
        voice_ref = _required_ref(command.get("voiceRef"), "voiceRef")
        base_ref = _required_ref(
            command.get("baseVoiceLockVersionRef"), "baseVoiceLockVersionRef"
        )
        base_digest = command.get("baseVoiceLockDigest")
        if not isinstance(base_digest, str) or len(base_digest) != 64:
            raise EpisodeProductionError("baseVoiceLockDigest is invalid")
        expected_revision = _positive_int(
            command.get("expectedRevision"), "expectedRevision"
        )
        key = _idempotency_key(command.get("idempotencyKey"))
        traits = _traits(command)
        request_digest = _digest(
            {
                "operationKind": "create-voice-lock-version",
                "scope": list(scope),
                "voiceRef": voice_ref,
                "baseVoiceLockVersionRef": base_ref,
                "baseVoiceLockDigest": base_digest,
                "expectedRevision": expected_revision,
                "voice": traits,
            }
        )
        replay = self._replay(
            scope, key, "create-voice-lock-version", request_digest
        )
        if replay is not None:
            return replay
        root = self.repository.get_root_by_ref(scope, voice_ref)
        if root is None:
            raise RecordNotFoundError("VoiceLock was not found")
        if root["revision"] != expected_revision:
            raise StaleInputError("VoiceLock revision changed")
        if (
            root["currentVoiceLockVersionRef"]
            != root["confirmedVoiceLockVersionRef"]
            or root["confirmedVoiceLockVersionRef"] != base_ref
            or root["confirmedVoiceLockDigest"] != base_digest
        ):
            raise VoiceLockNotConfirmedError(
                "successor requires the current confirmed VoiceLockVersion"
            )
        parent = self.repository.get_version(scope, voice_ref, base_ref)
        confirmation = self.repository.get_confirmation(scope, voice_ref, base_ref)
        if (
            parent is None
            or confirmation is None
            or parent["payloadDigest"] != base_digest
            or confirmation["voiceLockDigest"] != base_digest
        ):
            raise VoiceLockNotConfirmedError(
                "confirmed VoiceLockVersion lineage is unavailable"
            )
        version_ref = _required_ref(
            self._ref_factory("voice-lock-version"), "voiceLockVersionRef"
        )
        now = _text(self._clock(), "createdAt")
        version = _sealed(
            {
                "schemaVersion": VOICE_LOCK_VERSION_SCHEMA_VERSION,
                "workspaceRef": scope[0],
                "projectRef": scope[1],
                "seriesRef": scope[2],
                "voiceRef": voice_ref,
                "voiceLockVersionRef": version_ref,
                "versionNumber": parent["versionNumber"] + 1,
                "parentVoiceLockVersionRef": parent["voiceLockVersionRef"],
                "parentVoiceLockDigest": parent["payloadDigest"],
                "characterRef": root["characterRef"],
                **traits,
                "state": "CANDIDATE",
                "immutable": True,
                "createdAt": now,
            }
        )
        updated_root = _sealed(
            {
                key_name: value
                for key_name, value in root.items()
                if key_name != "payloadDigest"
            }
            | {
                "currentVoiceLockVersionRef": version_ref,
                "revision": expected_revision + 1,
                "updatedAt": now,
            }
        )
        response = {
            "voiceLock": updated_root,
            "voiceLockVersion": version,
        }
        operation = self._operation(
            scope=scope,
            key=key,
            operation_kind="create-voice-lock-version",
            request_digest=request_digest,
            response=response,
            created_at=now,
        )
        stored, replayed = self.repository.create_voice_lock_version(
            updated_root,
            version,
            operation,
            expected_revision=expected_revision,
        )
        return {**stored, "idempotentReplay": replayed}

    def confirm_voice_lock(self, command: Mapping[str, Any]) -> dict[str, Any]:
        required = self._SCOPE_FIELDS | frozenset(
            {
                "voiceRef",
                "voiceLockVersionRef",
                "voiceLockDigest",
                "expectedRevision",
                "idempotencyKey",
            }
        )
        _closed_command(
            command,
            required=required,
            operation="confirm VoiceLock",
        )
        scope = _scope(
            command.get("workspaceRef"),
            command.get("projectRef"),
            command.get("seriesRef"),
        )
        voice_ref = _required_ref(command.get("voiceRef"), "voiceRef")
        version_ref = _required_ref(
            command.get("voiceLockVersionRef"), "voiceLockVersionRef"
        )
        voice_digest = command.get("voiceLockDigest")
        if not isinstance(voice_digest, str) or len(voice_digest) != 64:
            raise EpisodeProductionError("voiceLockDigest is invalid")
        expected_revision = _positive_int(
            command.get("expectedRevision"), "expectedRevision"
        )
        key = _idempotency_key(command.get("idempotencyKey"))
        request_digest = _digest(
            {
                "operationKind": "confirm-voice-lock",
                "scope": list(scope),
                "voiceRef": voice_ref,
                "voiceLockVersionRef": version_ref,
                "voiceLockDigest": voice_digest,
                "expectedRevision": expected_revision,
            }
        )
        replay = self._replay(
            scope, key, "confirm-voice-lock", request_digest
        )
        if replay is not None:
            return replay
        root = self.repository.get_root_by_ref(scope, voice_ref)
        if root is None:
            raise RecordNotFoundError("VoiceLock was not found")
        if root["revision"] != expected_revision:
            raise StaleInputError("VoiceLock revision changed")
        if root["currentVoiceLockVersionRef"] != version_ref:
            raise VoiceLockImmutableError(
                "only the current VoiceLockVersion may be confirmed"
            )
        if self.repository.get_confirmation(scope, voice_ref, version_ref) is not None:
            raise VoiceLockImmutableError("VoiceLockVersion is already confirmed")
        version = self.repository.get_version(scope, voice_ref, version_ref)
        if version is None:
            raise RecordNotFoundError("VoiceLockVersion was not found")
        if (
            version["payloadDigest"] != voice_digest
            or version["characterRef"] != root["characterRef"]
        ):
            raise StaleInputError("VoiceLockVersion digest changed")
        now = _text(self._clock(), "createdAt")
        confirmation = _sealed(
            {
                "schemaVersion": VOICE_LOCK_CONFIRMATION_SCHEMA_VERSION,
                "workspaceRef": scope[0],
                "projectRef": scope[1],
                "seriesRef": scope[2],
                "voiceLockConfirmationRef": _required_ref(
                    self._ref_factory("voice-lock-confirmation"),
                    "voiceLockConfirmationRef",
                ),
                "voiceRef": voice_ref,
                "voiceLockVersionRef": version_ref,
                "voiceLockDigest": voice_digest,
                "characterRef": root["characterRef"],
                "state": "CONFIRMED",
                "createdAt": now,
            }
        )
        updated_root = _sealed(
            {
                key_name: value
                for key_name, value in root.items()
                if key_name != "payloadDigest"
            }
            | {
                "confirmedVoiceLockVersionRef": version_ref,
                "confirmedVoiceLockDigest": voice_digest,
                "revision": expected_revision + 1,
                "updatedAt": now,
            }
        )
        response = {
            "voiceLock": updated_root,
            "voiceLockVersion": version,
            "voiceLockConfirmation": confirmation,
        }
        operation = self._operation(
            scope=scope,
            key=key,
            operation_kind="confirm-voice-lock",
            request_digest=request_digest,
            response=response,
            created_at=now,
        )
        stored, replayed = self.repository.confirm_voice_lock(
            updated_root,
            confirmation,
            operation,
            expected_revision=expected_revision,
        )
        return {**stored, "idempotentReplay": replayed}

    @staticmethod
    def _require_complete_version_lineage(
        root: Mapping[str, Any], versions: list[Mapping[str, Any]]
    ) -> None:
        if not versions:
            raise RepositoryUnavailableError("VoiceLock version lineage is incomplete")
        root_scope = tuple(
            root[field] for field in ("workspaceRef", "projectRef", "seriesRef")
        )
        previous: Mapping[str, Any] | None = None
        for expected_number, version in enumerate(versions, start=1):
            if (
                version["versionNumber"] != expected_number
                or tuple(
                    version[field]
                    for field in ("workspaceRef", "projectRef", "seriesRef")
                )
                != root_scope
                or version["voiceRef"] != root["voiceRef"]
                or version["characterRef"] != root["characterRef"]
            ):
                raise RepositoryUnavailableError(
                    "VoiceLock version lineage is incomplete"
                )
            if previous is not None and (
                version["parentVoiceLockVersionRef"]
                != previous["voiceLockVersionRef"]
                or version["parentVoiceLockDigest"] != previous["payloadDigest"]
            ):
                raise RepositoryUnavailableError(
                    "VoiceLock version lineage is incomplete"
                )
            previous = version
        if versions[-1]["voiceLockVersionRef"] != root["currentVoiceLockVersionRef"]:
            raise RepositoryUnavailableError("VoiceLock version lineage is incomplete")

    def get_voice_lock(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        voice_ref: str,
    ) -> dict[str, Any]:
        scope = _scope(workspace_ref, project_ref, series_ref)
        selected_voice_ref = _required_ref(voice_ref, "voiceRef")
        root = self.repository.get_root_by_ref(scope, selected_voice_ref)
        if root is None:
            raise RecordNotFoundError("VoiceLock was not found")
        versions = self.repository.list_versions(scope, selected_voice_ref)
        self._require_complete_version_lineage(root, versions)
        confirmed = None
        if root["confirmedVoiceLockVersionRef"] is not None:
            version = self.repository.get_version(
                scope, selected_voice_ref, root["confirmedVoiceLockVersionRef"]
            )
            confirmation = self.repository.get_confirmation(
                scope, selected_voice_ref, root["confirmedVoiceLockVersionRef"]
            )
            if (
                version is None
                or confirmation is None
                or version["payloadDigest"] != root["confirmedVoiceLockDigest"]
                or confirmation["voiceLockDigest"]
                != root["confirmedVoiceLockDigest"]
            ):
                raise RepositoryUnavailableError(
                    "VoiceLock confirmed lineage is incomplete"
                )
            confirmed = {
                "voiceLockVersion": version,
                "voiceLockConfirmation": confirmation,
            }
        return {
            "voiceLock": root,
            "voiceLockVersions": versions,
            "confirmed": confirmed,
        }

    def get_confirmed_voice_lock(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        character_ref: str,
    ) -> dict[str, Any]:
        scope = _scope(workspace_ref, project_ref, series_ref)
        selected_character_ref = _required_ref(character_ref, "characterRef")
        root = self.repository.get_root_by_character(scope, selected_character_ref)
        if root is None:
            raise RecordNotFoundError("VoiceLock was not found")
        versions = self.repository.list_versions(scope, root["voiceRef"])
        self._require_complete_version_lineage(root, versions)
        version_ref = root["confirmedVoiceLockVersionRef"]
        if version_ref is None:
            raise VoiceLockNotConfirmedError("VoiceLock is not confirmed")
        version = self.repository.get_version(scope, root["voiceRef"], version_ref)
        confirmation = self.repository.get_confirmation(
            scope, root["voiceRef"], version_ref
        )
        if (
            version is None
            or confirmation is None
            or version["characterRef"] != selected_character_ref
            or version["payloadDigest"] != root["confirmedVoiceLockDigest"]
            or confirmation["voiceLockDigest"]
            != root["confirmedVoiceLockDigest"]
            or confirmation["characterRef"] != selected_character_ref
        ):
            raise RepositoryUnavailableError(
                "confirmed VoiceLock lineage is inconsistent"
            )
        return validate_confirmed_voice_lock_bundle({
            "voiceLock": root,
            "voiceLockVersion": version,
            "voiceLockConfirmation": confirmation,
        })


__all__ = [
    "DEFAULT_LANGUAGE_CODE",
    "InMemoryVoiceLockAdapter",
    "K2VoiceLockService",
    "SqliteVoiceLockAdapter",
    "VOICE_GENDERS",
    "VOICE_LOCK_CONFIRMATION_SCHEMA_VERSION",
    "VOICE_LOCK_SCHEMA_VERSION",
    "VOICE_LOCK_VERSION_SCHEMA_VERSION",
    "VoiceLockConflictError",
    "VoiceLockImmutableError",
    "VoiceLockNotConfirmedError",
    "VoiceLockRepository",
    "validate_confirmed_voice_lock_bundle",
]
