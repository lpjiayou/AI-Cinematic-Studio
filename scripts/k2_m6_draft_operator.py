#!/usr/bin/env python3
"""Create only reviewed K2 M6 draft candidates through the public API.

The operator is deliberately narrower than the M6 public surface.  It can create one
Series Bible candidate or, after that Bible is independently confirmed, one Character
Continuity candidate.  It never calls a confirmation, baseline activation, Identity
Lock or provider endpoint.

The Creator bearer credential is read only from ``K2_CREATOR_API_BEARER_TOKEN``.  It
is never accepted on the command line, printed, serialized or included in a digest.
Only a validated loopback Creator origin is accepted, and redirects are not followed.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.v5_core_os.series_intelligence import (  # noqa: E402
    M6ExternalAuthorityConfigurationError,
    m6_external_authorities_from_environment,
)
from services.v5_core_os.series_intelligence.errors import (  # noqa: E402
    AuthorityUnavailableError,
)


CANDIDATE_SCHEMA_VERSION = "k2.m6-draft-candidate.v1"
RECEIPT_SCHEMA_VERSION = "k2.m6-draft-operator-receipt.v1"
PACKAGE_ID = "k2-001-m6-draft-v1"
TOKEN_ENVIRONMENT_VARIABLE = "K2_CREATOR_API_BEARER_TOKEN"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_CANDIDATE = (
    REPOSITORY_ROOT
    / "experiments"
    / "k2-001-m6-draft"
    / "k2-001-m6-draft-candidate.v1.json"
)
MAX_INPUT_BYTES = 512_000
MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 10.0
PUBLIC_PREFIX = "/creator/api/v1"
M5_BOOTSTRAP_PATH = f"{PUBLIC_PREFIX}/series-planning-workspaces/m6-bootstrap"
M6_WORKSPACE_PATH = f"{PUBLIC_PREFIX}/series-intelligence-workspaces"
M6_BIBLE_VERSION_PATH = f"{PUBLIC_PREFIX}/series-intelligence/bible-versions"
M6_CHARACTER_VERSION_PATH = f"{PUBLIC_PREFIX}/series-intelligence/character-versions"
REF_PATTERN = re.compile(r"^[^\s\x00-\x1f\x7f]{1,240}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_BIBLE_COLLECTIONS = {
    "worldRules": "worldRuleRef",
    "glossaryTerms": "glossaryTermRef",
    "locations": "locationRef",
    "factions": "factionRef",
    "props": "propRef",
    "timelineEvents": "timelineEventRef",
    "visualConstraints": "visualConstraintRef",
    "prohibitedNarrativePatterns": "prohibitedNarrativePatternRef",
}
_CHARACTER_REQUIRED_FIELDS = {
    "characterRef",
    "name",
    "background",
    "motivation",
    "belief",
    "conflict",
    "goal",
    "personality",
    "behaviorRules",
    "dialogueRules",
    "forbiddenBehavior",
    "visualIdentityRules",
    "locationRefs",
    "propRefs",
    "timelineEventRefs",
}


class M6DraftOperatorError(RuntimeError):
    """Stable failure code that contains no credential or response material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ApiOrigin:
    scheme: str
    hostname: str
    port: int


@dataclass(frozen=True, slots=True)
class DraftCandidate:
    path: Path
    sha256: str
    value: Mapping[str, Any]

    @property
    def scope(self) -> Mapping[str, str]:
        return self.value["scope"]


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise M6DraftOperatorError("non_canonical_json_value") from None


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise M6DraftOperatorError("file_digest_failed") from None
    return digest.hexdigest()


def _reject_json_constant(value: str) -> None:
    del value
    raise ValueError


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _load_json_object(path: Path, code: str) -> Mapping[str, Any]:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        raise M6DraftOperatorError(code) from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or not payload
        or len(payload) > MAX_INPUT_BYTES
    ):
        raise M6DraftOperatorError(code)
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError):
        raise M6DraftOperatorError(code) from None
    if not isinstance(value, Mapping):
        raise M6DraftOperatorError(code)
    return value


def _fields(value: Any, expected: set[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise M6DraftOperatorError(code)
    return value


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise M6DraftOperatorError(code)
    return value


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise M6DraftOperatorError(code)
    return value


def _ref(value: Any, code: str) -> str:
    if not isinstance(value, str) or REF_PATTERN.fullmatch(value) is None:
        raise M6DraftOperatorError(code)
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8000:
        raise M6DraftOperatorError(code)
    return value


def _sha256(value: Any, code: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise M6DraftOperatorError(code)
    return value


def _positive_ordinal(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise M6DraftOperatorError(code)
    return value


def _validate_ref_list(value: Any, known: set[str], code: str) -> None:
    items = _list(value, code)
    if any(not isinstance(item, str) or item not in known for item in items):
        raise M6DraftOperatorError(code)


def _validate_bible_content(value: Any) -> Mapping[str, Any]:
    content = _fields(value, set(_BIBLE_COLLECTIONS), "bible_content_fields_invalid")
    refs: dict[str, set[str]] = {}
    for field, ref_field in _BIBLE_COLLECTIONS.items():
        items = _list(content.get(field), f"bible_{field}_invalid")
        if not items:
            raise M6DraftOperatorError(f"bible_{field}_empty")
        observed: set[str] = set()
        for item in items:
            record = _mapping(item, f"bible_{field}_invalid")
            item_ref = _ref(record.get(ref_field), f"bible_{ref_field}_invalid")
            if item_ref in observed:
                raise M6DraftOperatorError(f"bible_{ref_field}_duplicated")
            observed.add(item_ref)
        refs[field] = observed
    for item in content["timelineEvents"]:
        event = _mapping(item, "bible_timeline_event_invalid")
        if event.get("locationRef") not in refs["locations"]:
            raise M6DraftOperatorError("bible_timeline_location_invalid")
        _validate_ref_list(
            event.get("factionRefs"), refs["factions"], "bible_timeline_factions_invalid"
        )
        _validate_ref_list(
            event.get("propRefs"), refs["props"], "bible_timeline_props_invalid"
        )
    return content


def _validate_character_template(
    value: Any, bible_content: Mapping[str, Any]
) -> Mapping[str, Any]:
    content = _fields(
        value,
        {"characters", "stateIntervals", "relationships", "identityBindings"},
        "character_content_fields_invalid",
    )
    if content.get("identityBindings") != []:
        raise M6DraftOperatorError("identity_bindings_must_be_empty")
    locations = {item["locationRef"] for item in bible_content["locations"]}
    props = {item["propRef"] for item in bible_content["props"]}
    timeline_events = {
        item["timelineEventRef"] for item in bible_content["timelineEvents"]
    }
    characters = _list(content.get("characters"), "characters_invalid")
    if not characters:
        raise M6DraftOperatorError("characters_empty")
    character_refs: set[str] = set()
    for item in characters:
        record = _fields(item, _CHARACTER_REQUIRED_FIELDS, "character_fields_invalid")
        character_ref = _ref(record.get("characterRef"), "character_ref_invalid")
        if character_ref in character_refs:
            raise M6DraftOperatorError("character_ref_duplicated")
        character_refs.add(character_ref)
        for field in (
            "name",
            "background",
            "motivation",
            "belief",
            "conflict",
            "goal",
            "personality",
        ):
            _text(record.get(field), f"character_{field}_invalid")
        for field in (
            "behaviorRules",
            "dialogueRules",
            "forbiddenBehavior",
            "visualIdentityRules",
        ):
            values = _list(record.get(field), f"character_{field}_invalid")
            if not values or any(not isinstance(entry, str) or not entry.strip() for entry in values):
                raise M6DraftOperatorError(f"character_{field}_invalid")
        _validate_ref_list(
            record.get("locationRefs"), locations, "character_location_refs_invalid"
        )
        _validate_ref_list(
            record.get("propRefs"), props, "character_prop_refs_invalid"
        )
        _validate_ref_list(
            record.get("timelineEventRefs"),
            timeline_events,
            "character_timeline_refs_invalid",
        )
    interval_refs: set[str] = set()
    for item in _list(content.get("stateIntervals"), "state_intervals_invalid"):
        record = _fields(
            item,
            {
                "intervalRef",
                "characterRef",
                "category",
                "startEpisodePlanItemOrdinal",
                "endEpisodePlanItemOrdinal",
                "valueRef",
            },
            "state_interval_fields_invalid",
        )
        interval_ref = _ref(record.get("intervalRef"), "state_interval_ref_invalid")
        if interval_ref in interval_refs:
            raise M6DraftOperatorError("state_interval_ref_duplicated")
        interval_refs.add(interval_ref)
        if record.get("characterRef") not in character_refs:
            raise M6DraftOperatorError("state_interval_character_invalid")
        _text(record.get("category"), "state_interval_category_invalid")
        _positive_ordinal(
            record.get("startEpisodePlanItemOrdinal"),
            "state_interval_start_ordinal_invalid",
        )
        end = record.get("endEpisodePlanItemOrdinal")
        if end is not None:
            _positive_ordinal(end, "state_interval_end_ordinal_invalid")
        _ref(record.get("valueRef"), "state_interval_value_ref_invalid")
    relationship_refs: set[str] = set()
    for item in _list(content.get("relationships"), "relationships_invalid"):
        record = _fields(
            item,
            {
                "relationshipRef",
                "fromCharacterRef",
                "toCharacterRef",
                "relationshipType",
                "startEpisodePlanItemOrdinal",
                "endEpisodePlanItemOrdinal",
            },
            "relationship_fields_invalid",
        )
        relationship_ref = _ref(
            record.get("relationshipRef"), "relationship_ref_invalid"
        )
        if relationship_ref in relationship_refs:
            raise M6DraftOperatorError("relationship_ref_duplicated")
        relationship_refs.add(relationship_ref)
        source = record.get("fromCharacterRef")
        target = record.get("toCharacterRef")
        if source not in character_refs or target not in character_refs or source == target:
            raise M6DraftOperatorError("relationship_endpoint_invalid")
        _text(record.get("relationshipType"), "relationship_type_invalid")
        _positive_ordinal(
            record.get("startEpisodePlanItemOrdinal"),
            "relationship_start_ordinal_invalid",
        )
        end = record.get("endEpisodePlanItemOrdinal")
        if end is not None:
            _positive_ordinal(end, "relationship_end_ordinal_invalid")
    return content


def validate_candidate(path: Path) -> DraftCandidate:
    resolved = path.resolve(strict=True)
    value = _fields(
        _load_json_object(resolved, "candidate_file_invalid"),
        {
            "schemaVersion",
            "packageId",
            "authorityRef",
            "authorityBundleSha256",
            "scope",
            "bibleCandidate",
            "characterCandidate",
            "exitState",
        },
        "candidate_fields_invalid",
    )
    if value.get("schemaVersion") != CANDIDATE_SCHEMA_VERSION:
        raise M6DraftOperatorError("candidate_schema_invalid")
    if value.get("packageId") != PACKAGE_ID:
        raise M6DraftOperatorError("candidate_package_invalid")
    _ref(value.get("authorityRef"), "candidate_authority_ref_invalid")
    _sha256(value.get("authorityBundleSha256"), "candidate_authority_digest_invalid")
    scope = _fields(
        value.get("scope"),
        {"businessDomain", "tenantId", "workspaceRef", "projectRef", "seriesRef"},
        "candidate_scope_fields_invalid",
    )
    for field in scope:
        _ref(scope.get(field), f"candidate_scope_{field}_invalid")
    bible = _fields(
        value.get("bibleCandidate"),
        {"operationRef", "idempotencyKey", "content"},
        "bible_candidate_fields_invalid",
    )
    _ref(bible.get("operationRef"), "bible_operation_ref_invalid")
    _ref(bible.get("idempotencyKey"), "bible_idempotency_key_invalid")
    bible_content = _validate_bible_content(bible.get("content"))
    character = _fields(
        value.get("characterCandidate"),
        {"operationRef", "idempotencyKey", "contentTemplate"},
        "character_candidate_fields_invalid",
    )
    _ref(character.get("operationRef"), "character_operation_ref_invalid")
    _ref(character.get("idempotencyKey"), "character_idempotency_key_invalid")
    _validate_character_template(character.get("contentTemplate"), bible_content)
    expected_exit = {
        "domainFact": False,
        "humanApprovalRequired": True,
        "identityLockStatus": "NOT_CREATED",
        "g2Gate": "NOT_PASSED",
        "p1Gate": "NOT_PASSED",
        "publicationAllowed": False,
    }
    if value.get("exitState") != expected_exit:
        raise M6DraftOperatorError("candidate_exit_state_invalid")
    return DraftCandidate(resolved, _file_sha256(resolved), value)


def _validate_scope_bundle(path: Path, candidate: DraftCandidate) -> tuple[Path, str]:
    if not path.is_absolute():
        raise M6DraftOperatorError("m6_bundle_must_be_absolute")
    resolved = path.resolve(strict=True)
    digest = _file_sha256(resolved)
    if digest != candidate.value["authorityBundleSha256"]:
        raise M6DraftOperatorError("m6_bundle_digest_mismatch")
    bundle = _load_json_object(resolved, "m6_bundle_invalid")
    if bundle.get("authorityRef") != candidate.value["authorityRef"]:
        raise M6DraftOperatorError("m6_bundle_authority_ref_mismatch")
    if bundle.get("approvals") != []:
        raise M6DraftOperatorError("m6_bundle_not_scope_only")
    environment = {
        "CREATOR_M6_AUTHORITY_BUNDLE_PATH": str(resolved),
        "CREATOR_M6_AUTHORITY_BUNDLE_SHA256": digest,
    }
    try:
        scope_authority, _approval_authority = m6_external_authorities_from_environment(
            environment
        )
        expected = candidate.scope
        scope = scope_authority.resolve_scope(
            expected["workspaceRef"], expected["projectRef"], expected["seriesRef"]
        )
    except (M6ExternalAuthorityConfigurationError, AuthorityUnavailableError):
        raise M6DraftOperatorError("m6_bundle_scope_invalid") from None
    actual = {
        "businessDomain": scope.business_domain,
        "tenantId": scope.tenant_id,
        "workspaceRef": scope.workspace_ref,
        "projectRef": scope.project_ref,
        "seriesRef": scope.series_ref,
    }
    if actual != candidate.scope:
        raise M6DraftOperatorError("m6_bundle_scope_mismatch")
    return resolved, digest


def _validate_origin(value: str) -> ApiOrigin:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise M6DraftOperatorError("base_url_invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise M6DraftOperatorError("base_url_invalid")
    hostname = parsed.hostname.strip("[]").casefold()
    try:
        loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if not loopback:
        raise M6DraftOperatorError("base_url_must_be_loopback")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise M6DraftOperatorError("base_url_invalid") from None
    return ApiOrigin(parsed.scheme, hostname, port)


def _load_bearer_token(environment: Mapping[str, str]) -> str:
    token = environment.get(TOKEN_ENVIRONMENT_VARIABLE, "")
    if (
        not isinstance(token, str)
        or not token
        or token != token.strip()
        or len(token.encode("utf-8")) > 4096
        or any(ord(character) < 33 for character in token)
    ):
        raise M6DraftOperatorError("bearer_token_environment_invalid")
    return token


def _decode_json_response(response: http.client.HTTPResponse) -> Mapping[str, Any]:
    content_type = response.getheader("Content-Type", "").split(";", 1)[0]
    if content_type.strip().casefold() != "application/json":
        raise M6DraftOperatorError("public_api_content_type_invalid")
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if not body or len(body) > MAX_RESPONSE_BYTES:
        raise M6DraftOperatorError("public_api_response_size_invalid")
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError):
        raise M6DraftOperatorError("public_api_json_invalid") from None
    if not isinstance(value, Mapping):
        raise M6DraftOperatorError("public_api_envelope_invalid")
    return value


def _request_json(
    origin: ApiOrigin,
    token: str,
    timeout: float,
    method: str,
    path: str,
    *,
    query: Mapping[str, str] | None = None,
    payload: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    if not path.startswith(f"{PUBLIC_PREFIX}/"):
        raise M6DraftOperatorError("public_api_path_invalid")
    if method not in {"GET", "POST"}:
        raise M6DraftOperatorError("public_api_method_invalid")
    suffix = "?" + urlencode(query) if query else ""
    body = _canonical_bytes(payload) if payload is not None else None
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    connection_class = (
        http.client.HTTPSConnection
        if origin.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_class(origin.hostname, origin.port, timeout=timeout)
    try:
        connection.request(method, path + suffix, body=body, headers=headers)
        response = connection.getresponse()
        value = _decode_json_response(response)
        expected_status = {200} if method == "GET" else {200, 201}
        if response.status not in expected_status or value.get("ok") is not True:
            error = value.get("error")
            error_code = error.get("code") if isinstance(error, Mapping) else None
            if isinstance(error_code, str) and REF_PATTERN.fullmatch(error_code):
                raise M6DraftOperatorError(f"public_api_{error_code}")
            raise M6DraftOperatorError("public_api_response_status_invalid")
        return value
    except M6DraftOperatorError:
        raise
    except (OSError, http.client.HTTPException):
        raise M6DraftOperatorError("public_api_request_failed") from None
    finally:
        connection.close()


def _bootstrap(
    origin: ApiOrigin, token: str, timeout: float, candidate: DraftCandidate
) -> Mapping[str, Any]:
    scope = candidate.scope
    envelope = _request_json(
        origin,
        token,
        timeout,
        "GET",
        M5_BOOTSTRAP_PATH,
        query={"projectRef": scope["projectRef"], "seriesRef": scope["seriesRef"]},
    )
    bootstrap = _mapping(envelope.get("bootstrap"), "m5_bootstrap_invalid")
    for field in ("workspaceRef", "projectRef", "seriesRef"):
        if bootstrap.get(field) != scope[field]:
            raise M6DraftOperatorError(f"m5_bootstrap_{field}_mismatch")
    _ref(bootstrap.get("seriesPlanRef"), "m5_series_plan_ref_invalid")
    _ref(
        bootstrap.get("seriesPlanVersionRef"),
        "m5_series_plan_version_ref_invalid",
    )
    episode_items = _list(
        bootstrap.get("episodePlanItems"), "m5_episode_plan_items_invalid"
    )
    if len(episode_items) != 1:
        raise M6DraftOperatorError("m5_episode_plan_item_count_invalid")
    item = _mapping(episode_items[0], "m5_episode_plan_item_invalid")
    _ref(item.get("episodePlanItemRef"), "m5_episode_plan_item_ref_invalid")
    return bootstrap


def _m6_workspace(
    origin: ApiOrigin, token: str, timeout: float, candidate: DraftCandidate
) -> Mapping[str, Any]:
    scope = candidate.scope
    envelope = _request_json(
        origin,
        token,
        timeout,
        "GET",
        M6_WORKSPACE_PATH,
        query={"projectRef": scope["projectRef"], "seriesRef": scope["seriesRef"]},
    )
    workspace = _mapping(envelope.get("workspace"), "m6_workspace_invalid")
    if workspace.get("scope") != scope:
        raise M6DraftOperatorError("m6_workspace_scope_mismatch")
    if workspace.get("activeBaseline") is not None:
        raise M6DraftOperatorError("m6_baseline_already_active")
    return workspace


def _normalized_bible_content(candidate: DraftCandidate) -> dict[str, Any]:
    source = candidate.value["bibleCandidate"]["content"]
    result: dict[str, Any] = {"schemaVersion": "v5.series-bible-content.v1"}
    for field, ref_field in _BIBLE_COLLECTIONS.items():
        result[field] = sorted(
            deepcopy(source[field]), key=lambda item: item[ref_field]
        )
    return result


def _episode_ref(bootstrap: Mapping[str, Any], ordinal: int) -> str:
    items = bootstrap["episodePlanItems"]
    if ordinal < 1 or ordinal > len(items):
        raise M6DraftOperatorError("episode_plan_item_ordinal_out_of_range")
    return items[ordinal - 1]["episodePlanItemRef"]


def _normalized_character_content(
    candidate: DraftCandidate, bootstrap: Mapping[str, Any]
) -> dict[str, Any]:
    template = candidate.value["characterCandidate"]["contentTemplate"]
    intervals = []
    for item in template["stateIntervals"]:
        transformed = deepcopy(item)
        start = transformed.pop("startEpisodePlanItemOrdinal")
        end = transformed.pop("endEpisodePlanItemOrdinal")
        transformed["startEpisodePlanItemRef"] = _episode_ref(bootstrap, start)
        transformed["endEpisodePlanItemRef"] = (
            _episode_ref(bootstrap, end) if end is not None else None
        )
        intervals.append(transformed)
    relationships = []
    for item in template["relationships"]:
        transformed = deepcopy(item)
        start = transformed.pop("startEpisodePlanItemOrdinal")
        end = transformed.pop("endEpisodePlanItemOrdinal")
        transformed["startEpisodePlanItemRef"] = _episode_ref(bootstrap, start)
        transformed["endEpisodePlanItemRef"] = (
            _episode_ref(bootstrap, end) if end is not None else None
        )
        relationships.append(transformed)
    return {
        "schemaVersion": "v5.character-continuity-content.v1",
        "characters": sorted(
            deepcopy(template["characters"]), key=lambda item: item["characterRef"]
        ),
        "stateIntervals": sorted(intervals, key=lambda item: item["intervalRef"]),
        "relationships": sorted(
            relationships, key=lambda item: item["relationshipRef"]
        ),
        "identityBindings": [],
    }


def _version_for_ref(
    versions: Any, ref_field: str, version_ref: Any, code: str
) -> Mapping[str, Any]:
    if not isinstance(version_ref, str) or not version_ref:
        raise M6DraftOperatorError(code)
    matches = [
        item
        for item in _list(versions, code)
        if isinstance(item, Mapping) and item.get(ref_field) == version_ref
    ]
    if len(matches) != 1:
        raise M6DraftOperatorError(code)
    return matches[0]


def _safe_result(
    root: Mapping[str, Any], version: Mapping[str, Any], phase: str, replay: bool
) -> dict[str, Any]:
    if phase == "bible-candidate":
        return {
            "seriesBibleRef": _ref(root.get("seriesBibleRef"), "bible_ref_invalid"),
            "seriesBibleVersionRef": _ref(
                version.get("seriesBibleVersionRef"), "bible_version_ref_invalid"
            ),
            "versionNumber": version.get("versionNumber"),
            "contentDigest": _sha256(
                version.get("contentDigest"), "bible_content_digest_invalid"
            ),
            "status": version.get("status"),
            "revision": root.get("revision"),
            "idempotentReplay": replay,
        }
    return {
        "characterContinuityRef": _ref(
            root.get("characterContinuityRef"), "character_continuity_ref_invalid"
        ),
        "characterContinuityVersionRef": _ref(
            version.get("characterContinuityVersionRef"),
            "character_continuity_version_ref_invalid",
        ),
        "seriesBibleRef": _ref(
            version.get("seriesBibleRef"), "character_bible_ref_invalid"
        ),
        "seriesBibleVersionRef": _ref(
            version.get("seriesBibleVersionRef"),
            "character_bible_version_ref_invalid",
        ),
        "versionNumber": version.get("versionNumber"),
        "contentDigest": _sha256(
            version.get("contentDigest"), "character_content_digest_invalid"
        ),
        "status": version.get("status"),
        "revision": root.get("revision"),
        "idempotentReplay": replay,
    }


def _existing_bible_candidate(
    workspace: Mapping[str, Any], expected_content: Mapping[str, Any]
) -> dict[str, Any] | None:
    root = workspace.get("seriesBible")
    if root is None:
        if workspace.get("seriesBibleVersions") not in ([], None):
            raise M6DraftOperatorError("m6_bible_history_inconsistent")
        return None
    root = _mapping(root, "existing_bible_root_invalid")
    if root.get("confirmedSeriesBibleVersionRef") is not None:
        raise M6DraftOperatorError("bible_already_confirmed")
    version = _version_for_ref(
        workspace.get("seriesBibleVersions"),
        "seriesBibleVersionRef",
        root.get("currentSeriesBibleVersionRef"),
        "existing_bible_version_invalid",
    )
    if version.get("status") != "CANDIDATE" or version.get("content") != expected_content:
        raise M6DraftOperatorError("existing_bible_candidate_mismatch")
    return _safe_result(root, version, "bible-candidate", True)


def _confirmed_bible(workspace: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    root = _mapping(workspace.get("seriesBible"), "confirmed_bible_required")
    version = _version_for_ref(
        workspace.get("seriesBibleVersions"),
        "seriesBibleVersionRef",
        root.get("confirmedSeriesBibleVersionRef"),
        "confirmed_bible_version_required",
    )
    if version.get("status") != "CONFIRMED" or not version.get("approvalRef"):
        raise M6DraftOperatorError("confirmed_bible_version_required")
    return root, version


def _existing_character_candidate(
    workspace: Mapping[str, Any], expected_content: Mapping[str, Any]
) -> dict[str, Any] | None:
    root = workspace.get("characterContinuity")
    if root is None:
        if workspace.get("characterContinuityVersions") not in ([], None):
            raise M6DraftOperatorError("m6_character_history_inconsistent")
        return None
    root = _mapping(root, "existing_character_root_invalid")
    if root.get("confirmedCharacterContinuityVersionRef") is not None:
        raise M6DraftOperatorError("character_already_confirmed")
    version = _version_for_ref(
        workspace.get("characterContinuityVersions"),
        "characterContinuityVersionRef",
        root.get("currentCharacterContinuityVersionRef"),
        "existing_character_version_invalid",
    )
    if version.get("status") != "CANDIDATE" or version.get("content") != expected_content:
        raise M6DraftOperatorError("existing_character_candidate_mismatch")
    return _safe_result(root, version, "character-candidate", True)


def _verify_created_result(
    value: Any,
    phase: str,
    expected_scope: Mapping[str, Any],
    expected_content: Mapping[str, Any],
    bible: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    result = _fields(value, {"root", "version"}, "created_result_invalid")
    root = _mapping(result.get("root"), "created_root_invalid")
    version = _mapping(result.get("version"), "created_version_invalid")
    for field in expected_scope:
        if root.get(field) != expected_scope[field] or version.get(field) != expected_scope[field]:
            raise M6DraftOperatorError("created_scope_mismatch")
    if version.get("status") != "CANDIDATE" or version.get("approvalRef") is not None:
        raise M6DraftOperatorError("created_candidate_status_invalid")
    if version.get("content") != expected_content:
        raise M6DraftOperatorError("created_candidate_content_mismatch")
    if not isinstance(version.get("versionNumber"), int) or version["versionNumber"] < 1:
        raise M6DraftOperatorError("created_version_number_invalid")
    if not isinstance(root.get("revision"), int) or root["revision"] < 1:
        raise M6DraftOperatorError("created_revision_invalid")
    if phase == "bible-candidate":
        if root.get("confirmedSeriesBibleVersionRef") is not None:
            raise M6DraftOperatorError("created_bible_confirmation_invalid")
    else:
        if root.get("confirmedCharacterContinuityVersionRef") is not None:
            raise M6DraftOperatorError("created_character_confirmation_invalid")
        if bible is None:
            raise M6DraftOperatorError("confirmed_bible_required")
        bible_root, bible_version = bible
        if (
            version.get("seriesBibleRef") != bible_root.get("seriesBibleRef")
            or version.get("seriesBibleVersionRef")
            != bible_version.get("seriesBibleVersionRef")
            or version.get("seriesBibleVersionDigest")
            != bible_version.get("contentDigest")
        ):
            raise M6DraftOperatorError("created_character_bible_lineage_mismatch")
    return _safe_result(root, version, phase, False)


def _post_candidate(
    origin: ApiOrigin,
    token: str,
    timeout: float,
    candidate: DraftCandidate,
    phase: str,
    expected_content: Mapping[str, Any],
    bible: tuple[Mapping[str, Any], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    scope = candidate.scope
    if phase == "bible-candidate":
        definition = candidate.value["bibleCandidate"]
        path = M6_BIBLE_VERSION_PATH
        payload = {
            "projectRef": scope["projectRef"],
            "seriesRef": scope["seriesRef"],
            "operationRef": definition["operationRef"],
            "idempotencyKey": definition["idempotencyKey"],
            "candidate": True,
            "content": definition["content"],
        }
    else:
        if bible is None:
            raise M6DraftOperatorError("confirmed_bible_required")
        bible_root, bible_version = bible
        definition = candidate.value["characterCandidate"]
        path = M6_CHARACTER_VERSION_PATH
        content = deepcopy(expected_content)
        content.pop("schemaVersion", None)
        payload = {
            "projectRef": scope["projectRef"],
            "seriesRef": scope["seriesRef"],
            "operationRef": definition["operationRef"],
            "idempotencyKey": definition["idempotencyKey"],
            "candidate": True,
            "seriesBibleRef": bible_root["seriesBibleRef"],
            "seriesBibleVersionRef": bible_version["seriesBibleVersionRef"],
            "content": content,
        }
    envelope = _request_json(
        origin, token, timeout, "POST", path, payload=payload
    )
    return _verify_created_result(
        envelope.get("result"),
        phase,
        scope,
        expected_content,
        bible,
    )


def _receipt(
    candidate: DraftCandidate,
    bundle_digest: str,
    phase: str,
    bootstrap: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    exit_state = {
        "seriesBibleStatus": (
            "CANDIDATE" if phase == "bible-candidate" else "CONFIRMED"
        ),
        "characterContinuityStatus": (
            "NOT_CREATED" if phase == "bible-candidate" else "CANDIDATE"
        ),
        "m6BaselineStatus": "NOT_CREATED",
        "identityLockStatus": "NOT_CREATED",
        "g2Gate": "NOT_PASSED",
        "p1Gate": "NOT_PASSED",
        "publicationAllowed": False,
    }
    return {
        "schemaVersion": RECEIPT_SCHEMA_VERSION,
        "phase": phase,
        "observedAt": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "packageId": candidate.value["packageId"],
        "inputDigests": {
            "candidateSha256": candidate.sha256,
            "m6AuthorityBundleSha256": bundle_digest,
        },
        "scope": dict(candidate.scope),
        "source": {
            "seriesPlanRef": bootstrap["seriesPlanRef"],
            "seriesPlanVersionRef": bootstrap["seriesPlanVersionRef"],
            "episodePlanItemRefs": [
                item["episodePlanItemRef"] for item in bootstrap["episodePlanItems"]
            ],
        },
        "result": dict(result),
        "exitState": exit_state,
    }


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> str:
    if not path.is_absolute():
        raise M6DraftOperatorError("receipt_path_must_be_absolute")
    parent = path.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise M6DraftOperatorError("receipt_parent_invalid")
    if path.exists() or path.is_symlink():
        raise M6DraftOperatorError("receipt_already_exists")
    payload = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    temporary = parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise M6DraftOperatorError("receipt_write_failed") from None
    return sha256(payload).hexdigest()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight or create one fail-closed K2 M6 Bible/Character candidate "
            "through the authenticated loopback Creator Public API."
        )
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=("bible-candidate", "character-candidate"),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("CREATOR_CORE_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument("--m6-bundle", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the one candidate write after all read-only preflight checks pass.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        if not isinstance(args.timeout, float) or not (0.1 <= args.timeout <= 60.0):
            raise M6DraftOperatorError("timeout_invalid")
        if args.apply and args.output is None:
            raise M6DraftOperatorError("receipt_output_required_for_apply")
        if not args.apply and args.output is not None:
            raise M6DraftOperatorError("receipt_output_requires_apply")
        candidate = validate_candidate(args.candidate)
        _bundle_path, bundle_digest = _validate_scope_bundle(
            args.m6_bundle, candidate
        )
        origin = _validate_origin(args.base_url)
        token = _load_bearer_token(os.environ)
        bootstrap = _bootstrap(origin, token, args.timeout, candidate)
        workspace = _m6_workspace(origin, token, args.timeout, candidate)

        bible: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None
        if args.phase == "bible-candidate":
            if workspace.get("characterContinuity") is not None:
                raise M6DraftOperatorError("character_continuity_already_exists")
            expected_content = _normalized_bible_content(candidate)
            existing = _existing_bible_candidate(workspace, expected_content)
        else:
            bible = _confirmed_bible(workspace)
            expected_content = _normalized_character_content(candidate, bootstrap)
            existing = _existing_character_candidate(workspace, expected_content)

        action = "VERIFY_EXISTING" if existing is not None else "CREATE_CANDIDATE"
        if not args.apply:
            print("K2_M6_DRAFT_PREFLIGHT=PASS")
            print(f"K2_M6_DRAFT_PHASE={args.phase}")
            print(f"K2_M6_DRAFT_ACTION={action}")
            print(f"K2_M6_CANDIDATE_SHA256={candidate.sha256}")
            print(f"K2_M6_AUTHORITY_BUNDLE_SHA256={bundle_digest}")
            print("K2_M6_DRAFT_APPLY_REQUIRED=true")
            return 0

        result = existing or _post_candidate(
            origin,
            token,
            args.timeout,
            candidate,
            args.phase,
            expected_content,
            bible,
        )
        refreshed = _m6_workspace(origin, token, args.timeout, candidate)
        if args.phase == "bible-candidate":
            verified = _existing_bible_candidate(refreshed, expected_content)
        else:
            _confirmed_bible(refreshed)
            verified = _existing_character_candidate(refreshed, expected_content)
        if verified is None:
            raise M6DraftOperatorError("post_write_readback_missing")
        result = {**verified, "idempotentReplay": bool(existing)}
        receipt = _receipt(
            candidate, bundle_digest, args.phase, bootstrap, result
        )
        output = args.output.resolve(strict=False)
        receipt_digest = _write_receipt(output, receipt)
        print("K2_M6_DRAFT_APPLY=PASS")
        print(f"K2_M6_DRAFT_PHASE={args.phase}")
        print(f"K2_M6_DRAFT_RECEIPT={output}")
        print(f"K2_M6_DRAFT_RECEIPT_SHA256={receipt_digest}")
        print("G2_GATE=NOT_PASSED")
        print("P1_GATE=NOT_PASSED")
        print("PUBLICATION_ALLOWED=false")
        return 0
    except (
        M6DraftOperatorError,
        M6ExternalAuthorityConfigurationError,
        OSError,
    ) as exc:
        code = exc.code if isinstance(exc, M6DraftOperatorError) else "operator_failure"
        print(f"K2 M6 draft operator failed: {code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
