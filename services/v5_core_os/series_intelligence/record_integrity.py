"""Persistence-only integrity checks for M6 durable JSON projections.

This module deliberately depends on neither the M6 service nor repository adapter.
Migration validation and durable readers can therefore share the same fail-closed
rules without making domain behaviour depend on SQLite.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any


class DurableRecordIntegrityError(RuntimeError):
    pass


_SCOPE_COLUMNS = (
    "business_domain",
    "tenant_id",
    "workspace_ref",
    "project_ref",
    "series_ref",
)
_SCOPE_FIELDS = (
    "businessDomain",
    "tenantId",
    "workspaceRef",
    "projectRef",
    "seriesRef",
)
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION_TYPES = frozenset(
    {
        "create-series-bible-version",
        "submit-series-bible-candidate",
        "confirm-series-bible-version",
        "create-character-continuity-version",
        "submit-character-continuity-candidate",
        "confirm-character-continuity-version",
        "activate-m6-baseline",
    }
)


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise DurableRecordIntegrityError("floating-point durable JSON is forbidden")
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = unicodedata.normalize("NFC", str(raw_key))
            if key in result:
                raise DurableRecordIntegrityError("duplicate normalized JSON key")
            result[key] = _canonical(raw_value)
        return result
    raise DurableRecordIntegrityError("unsupported durable JSON value")


def _dump(value: Any) -> str:
    return json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _load(raw: Any, *, require_mapping: bool = False) -> Any:
    if not isinstance(raw, str):
        raise DurableRecordIntegrityError("durable JSON must be text")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError):
        raise DurableRecordIntegrityError("durable JSON is invalid") from None
    if _dump(value) != raw:
        raise DurableRecordIntegrityError("durable JSON is not canonical")
    if require_mapping and not isinstance(value, dict):
        raise DurableRecordIntegrityError("durable JSON object is required")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()


def _camel(column: str) -> str:
    parts = column.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _scope(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        field: str(row[column])
        for column, field in zip(_SCOPE_COLUMNS, _SCOPE_FIELDS)
    }


def _same(left: Any, right: Any) -> bool:
    """Compare JSON/SQLite projections without bool/int coercion."""

    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same(one, two) for one, two in zip(left, right)
        )
    return left == right


def _record_value(record: Mapping[str, Any], column: str) -> Any:
    if column == "content_json":
        return _dump(record.get("content"))
    field = _camel(column)
    value = record.get(field)
    if value is None and column in _SCOPE_COLUMNS:
        nested = record.get("scope")
        if isinstance(nested, Mapping):
            value = nested.get(field)
    return value


def _record(row: Any) -> dict[str, Any]:
    record = _load(row["record_json"], require_mapping=True)
    assert isinstance(record, dict)
    for column in row.keys():
        if column == "record_json":
            continue
        projected = _record_value(record, column)
        if not _same(row[column], projected):
            raise DurableRecordIntegrityError("durable column projection mismatch")
    return record


def _required_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DurableRecordIntegrityError("required durable text is invalid")
    return value


def _required_digest(value: Any) -> str:
    text = _required_text(value)
    if _HEX_DIGEST.fullmatch(text) is None:
        raise DurableRecordIntegrityError("durable digest is invalid")
    return text


def _validate_source_aliases(record: Mapping[str, Any]) -> None:
    if (
        record.get("sourceSeriesPlanVersionRef")
        != record.get("seriesPlanVersionRef")
        or record.get("sourceSeriesPlanDigest")
        != record.get("seriesPlanVersionDigest")
    ):
        raise DurableRecordIntegrityError("M5 source aliases diverge")


def _validate_version_status(record: Mapping[str, Any]) -> None:
    status = record.get("status")
    confirmed_at = record.get("confirmedAt")
    approval_ref = record.get("approvalRef")
    if status == "CONFIRMED":
        _required_text(confirmed_at)
        _required_text(approval_ref)
    elif status in {"DRAFT", "CANDIDATE"}:
        if confirmed_at is not None or approval_ref is not None:
            raise DurableRecordIntegrityError("unconfirmed version has confirmation facts")
    else:
        raise DurableRecordIntegrityError("unsupported M6 version status")


def _m5_source_digest(connection: Any, row: Any, cache: dict[tuple[str, ...], str]) -> str:
    key = (
        str(row["workspace_ref"]),
        str(row["project_ref"]),
        str(row["series_ref"]),
        str(row["series_plan_ref"]),
        str(row["series_plan_version_ref"]),
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    parent = connection.execute(
        "SELECT p.content_profile_ref, v.content_json "
        "FROM v5_series_plans p JOIN v5_series_plan_versions v "
        "ON v.workspace_ref=p.workspace_ref AND v.series_plan_ref=p.series_plan_ref "
        "WHERE p.workspace_ref=? AND p.project_ref=? AND p.series_ref=? "
        "AND p.series_plan_ref=? AND v.series_plan_version_ref=?",
        key,
    ).fetchone()
    if parent is None:
        raise DurableRecordIntegrityError("M5 source lineage is unavailable")
    try:
        content = json.loads(parent["content_json"])
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError):
        raise DurableRecordIntegrityError("M5 source JSON is invalid") from None
    if not isinstance(content, dict):
        raise DurableRecordIntegrityError("M5 source content is invalid")
    required = (
        "mainArcs",
        "episodePlanItems",
        "characterArcIntents",
        "worldIntent",
        "continuityIntent",
        "foreshadowingContext",
    )
    if any(field not in content for field in required):
        raise DurableRecordIntegrityError("M5 source content is incomplete")
    snapshot = {
        "schemaVersion": "v5.series-plan.m6-source-snapshot.v1",
        "workspaceRef": key[0],
        "contentProfileRef": parent["content_profile_ref"],
        "projectRef": key[1],
        "seriesRef": key[2],
        "seriesPlanRef": key[3],
        "seriesPlanVersionRef": key[4],
        "status": "confirmed",
        **{field: content[field] for field in required},
    }
    result = _digest(snapshot)
    cache[key] = result
    return result


def _validate_bible_version(connection: Any, row: Any, record: Mapping[str, Any], cache: dict[tuple[str, ...], str]) -> None:
    if record.get("schemaVersion") != "v5.series-bible-version.v1":
        raise DurableRecordIntegrityError("Bible version schema is invalid")
    if record.get("canonicalSchemaVersion") != "canonical-json-v1":
        raise DurableRecordIntegrityError("canonical schema is invalid")
    _validate_source_aliases(record)
    _validate_version_status(record)
    source_digest = _m5_source_digest(connection, row, cache)
    if _required_digest(record.get("seriesPlanVersionDigest")) != source_digest:
        raise DurableRecordIntegrityError("Bible M5 source digest is invalid")
    expected = _digest(
        {
            "schemaVersion": record["schemaVersion"],
            "scope": _scope(row),
            "seriesPlanVersionRef": record.get("seriesPlanVersionRef"),
            "seriesPlanVersionDigest": record.get("seriesPlanVersionDigest"),
            "content": record.get("content"),
        }
    )
    if record.get("contentDigest") != expected or record.get("canonicalDigest") != expected:
        raise DurableRecordIntegrityError("Bible canonical digest is invalid")


def _validate_character_version(connection: Any, row: Any, record: Mapping[str, Any], cache: dict[tuple[str, ...], str]) -> None:
    if record.get("schemaVersion") != "v5.character-continuity-version.v1":
        raise DurableRecordIntegrityError("Character version schema is invalid")
    if record.get("canonicalSchemaVersion") != "canonical-json-v1":
        raise DurableRecordIntegrityError("canonical schema is invalid")
    _validate_source_aliases(record)
    if (
        record.get("sourceSeriesBibleVersionRef")
        != record.get("seriesBibleVersionRef")
        or record.get("sourceSeriesBibleVersionDigest")
        != record.get("seriesBibleVersionDigest")
    ):
        raise DurableRecordIntegrityError("Bible source aliases diverge")
    _validate_version_status(record)
    source_digest = _m5_source_digest(connection, row, cache)
    if _required_digest(record.get("seriesPlanVersionDigest")) != source_digest:
        raise DurableRecordIntegrityError("Character M5 source digest is invalid")
    expected = _digest(
        {
            "schemaVersion": record["schemaVersion"],
            "scope": _scope(row),
            "seriesPlanVersionRef": record.get("seriesPlanVersionRef"),
            "seriesPlanVersionDigest": record.get("seriesPlanVersionDigest"),
            "seriesBibleVersionRef": record.get("seriesBibleVersionRef"),
            "seriesBibleVersionDigest": record.get("seriesBibleVersionDigest"),
            "content": record.get("content"),
        }
    )
    if record.get("contentDigest") != expected or record.get("canonicalDigest") != expected:
        raise DurableRecordIntegrityError("Character canonical digest is invalid")


def _validate_snapshot(connection: Any, row: Any, record: Mapping[str, Any], cache: dict[tuple[str, ...], str]) -> None:
    if record.get("schemaVersion") != "v5.m6-baseline-snapshot.v1":
        raise DurableRecordIntegrityError("baseline schema is invalid")
    if record.get("canonicalSchemaVersion") != "canonical-json-v1":
        raise DurableRecordIntegrityError("canonical schema is invalid")
    if record.get("scope") != _scope(row):
        raise DurableRecordIntegrityError("baseline scope projection is invalid")
    _validate_source_aliases(record)
    if _required_digest(record.get("seriesPlanVersionDigest")) != _m5_source_digest(connection, row, cache):
        raise DurableRecordIntegrityError("baseline M5 source digest is invalid")
    if record.get("confirmedBy") != record.get("confirmedByActorRef"):
        raise DurableRecordIntegrityError("baseline actor aliases diverge")
    status = record.get("status")
    if status == "ACTIVE" and record.get("supersededAt") is not None:
        raise DurableRecordIntegrityError("active baseline is superseded")
    if status == "SUPERSEDED" and not record.get("supersededAt"):
        raise DurableRecordIntegrityError("superseded baseline lacks timestamp")
    if status not in {"ACTIVE", "SUPERSEDED"}:
        raise DurableRecordIntegrityError("unsupported baseline status")
    selected = {
        key: record.get(key)
        for key in (
            "schemaVersion",
            "scope",
            "seriesPlanRef",
            "seriesPlanVersionRef",
            "seriesPlanVersionDigest",
            "sourceSeriesPlanVersionRef",
            "sourceSeriesPlanDigest",
            "seriesBibleRef",
            "seriesBibleVersionRef",
            "seriesBibleVersionDigest",
            "characterContinuityRef",
            "characterContinuityVersionRef",
            "characterContinuityVersionDigest",
        )
    }
    expected = _digest(selected)
    if record.get("contentDigest") != expected or record.get("canonicalDigest") != expected:
        raise DurableRecordIntegrityError("baseline canonical digest is invalid")


def _identity(record: Mapping[str, Any], *fields: str) -> tuple[Any, ...]:
    nested_scope = record.get("scope")
    if not isinstance(nested_scope, Mapping):
        nested_scope = {}
    scope = tuple(
        record.get(field)
        if record.get(field) is not None
        else nested_scope.get(field)
        for field in _SCOPE_FIELDS
    )
    return (*scope, *(record.get(field) for field in fields))


def _record_scope_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    nested = record.get("scope")
    if isinstance(nested, Mapping):
        return tuple(nested.get(field) for field in _SCOPE_FIELDS)
    return _identity(record)


def _validate_root_lineage(
    roots: list[dict[str, Any]],
    versions: list[dict[str, Any]],
    *,
    root_ref: str,
    version_ref: str,
    parent_ref: str,
    current_ref: str,
    confirmed_ref: str,
) -> None:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for version in versions:
        grouped.setdefault(_identity(version, root_ref), []).append(version)
    if len(grouped) != len(roots):
        raise DurableRecordIntegrityError("M6 root/version cardinality is invalid")
    for root in roots:
        key = _identity(root, root_ref)
        items = grouped.get(key)
        if not items:
            raise DurableRecordIntegrityError("M6 root has no version")
        ordered = sorted(items, key=lambda item: item.get("versionNumber", 0))
        numbers = [item.get("versionNumber") for item in ordered]
        if numbers != list(range(1, len(ordered) + 1)):
            raise DurableRecordIntegrityError("M6 version numbers are not contiguous")
        by_ref = {item.get(version_ref): item for item in ordered}
        if len(by_ref) != len(ordered):
            raise DurableRecordIntegrityError("M6 version identity is duplicated")
        if root.get(current_ref) != ordered[-1].get(version_ref):
            raise DurableRecordIntegrityError("M6 current version is not latest")
        confirmed = root.get(confirmed_ref)
        if confirmed is not None:
            target = by_ref.get(confirmed)
            if target is None or target.get("status") != "CONFIRMED":
                raise DurableRecordIntegrityError("M6 confirmed version target is invalid")
        revision = root.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < len(ordered):
            raise DurableRecordIntegrityError("M6 root revision is invalid")
        for index, item in enumerate(ordered, start=1):
            parent = item.get(parent_ref)
            if index == 1:
                if parent is not None:
                    raise DurableRecordIntegrityError("first M6 version has a parent")
                continue
            target = by_ref.get(parent)
            if target is None:
                raise DurableRecordIntegrityError("M6 version parent is unavailable")
            target_number = target.get("versionNumber")
            if (
                isinstance(target_number, bool)
                or not isinstance(target_number, int)
                or target_number >= index
            ):
                raise DurableRecordIntegrityError("M6 version parent is self or forward")


def _without(record: Mapping[str, Any], fields: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in fields}


def _operation_fact(
    connection: Any,
    row: Any,
    table: str,
    ref_column: str,
    ref_value: Any,
) -> dict[str, Any]:
    _required_text(ref_value)
    fact = connection.execute(
        f"SELECT record_json FROM {table} WHERE "
        + " AND ".join(f"{column}=?" for column in _SCOPE_COLUMNS)
        + f" AND {ref_column}=?",
        (*tuple(row[column] for column in _SCOPE_COLUMNS), ref_value),
    ).fetchone()
    if fact is None:
        raise DurableRecordIntegrityError("operation result fact is unavailable")
    value = _load(fact["record_json"], require_mapping=True)
    assert isinstance(value, dict)
    return value


def _validate_operation_pair(
    connection: Any,
    row: Any,
    result: Mapping[str, Any],
    *,
    family: str,
) -> None:
    if set(result) != {"root", "version"}:
        raise DurableRecordIntegrityError("operation result shape is invalid")
    root = result["root"]
    version = result["version"]
    if not isinstance(root, dict) or not isinstance(version, dict):
        raise DurableRecordIntegrityError("operation result records are invalid")
    if family == "bible":
        root_table = "v5_m6_series_bibles"
        version_table = "v5_m6_series_bible_versions"
        root_ref = "seriesBibleRef"
        version_ref = "seriesBibleVersionRef"
        root_column = "series_bible_ref"
        version_column = "series_bible_version_ref"
        current_ref = "currentSeriesBibleVersionRef"
    else:
        root_table = "v5_m6_character_continuities"
        version_table = "v5_m6_character_continuity_versions"
        root_ref = "characterContinuityRef"
        version_ref = "characterContinuityVersionRef"
        root_column = "character_continuity_ref"
        version_column = "character_continuity_version_ref"
        current_ref = "currentCharacterContinuityVersionRef"
    if root.get(root_ref) != version.get(root_ref) or root.get(current_ref) != version.get(version_ref):
        raise DurableRecordIntegrityError("operation result lineage diverges")
    persisted_root = _operation_fact(
        connection, row, root_table, root_column, root.get(root_ref)
    )
    persisted_version = _operation_fact(
        connection, row, version_table, version_column, version.get(version_ref)
    )
    root_mutable = frozenset(
        {
            current_ref,
            "confirmedSeriesBibleVersionRef"
            if family == "bible"
            else "confirmedCharacterContinuityVersionRef",
            "revision",
            "updatedAt",
        }
    )
    if not _same(_without(root, root_mutable), _without(persisted_root, root_mutable)):
        raise DurableRecordIntegrityError("operation root result is not durable")
    revision = root.get("revision")
    durable_revision = persisted_root.get("revision")
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or isinstance(durable_revision, bool)
        or not isinstance(durable_revision, int)
        or revision < 1
        or revision > durable_revision
    ):
        raise DurableRecordIntegrityError("operation root revision is invalid")
    mutable = frozenset({"status", "confirmedAt", "approvalRef"})
    if not _same(
        _without(version, mutable), _without(persisted_version, mutable)
    ):
        raise DurableRecordIntegrityError("operation version result is not durable")
    ranks = {"DRAFT": 0, "CANDIDATE": 1, "CONFIRMED": 2}
    if (
        version.get("status") not in ranks
        or persisted_version.get("status") not in ranks
        or ranks[version["status"]] > ranks[persisted_version["status"]]
    ):
        raise DurableRecordIntegrityError("operation version state is impossible")


def validate_durable_operation(connection: Any, row: Any) -> dict[str, Any]:
    """Validate one operation result and its same-Scope durable fact."""

    operation_type = row["operation_type"]
    if operation_type not in _OPERATION_TYPES:
        raise DurableRecordIntegrityError("operation type is invalid")
    _required_text(row["idempotency_key"])
    _required_text(row["operation_ref"])
    _required_digest(row["input_digest"])
    result = _load(row["result_json"], require_mapping=True)
    assert isinstance(result, dict)
    if "bible" in operation_type:
        _validate_operation_pair(connection, row, result, family="bible")
        required_status = {
            "submit-series-bible-candidate": "CANDIDATE",
            "confirm-series-bible-version": "CONFIRMED",
        }.get(operation_type)
        if required_status and result["version"].get("status") != required_status:
            raise DurableRecordIntegrityError("operation result status is invalid")
        if (
            operation_type == "create-series-bible-version"
            and result["version"].get("status") not in {"DRAFT", "CANDIDATE"}
        ):
            raise DurableRecordIntegrityError("create result status is invalid")
    elif "character" in operation_type:
        _validate_operation_pair(connection, row, result, family="character")
        required_status = {
            "submit-character-continuity-candidate": "CANDIDATE",
            "confirm-character-continuity-version": "CONFIRMED",
        }.get(operation_type)
        if required_status and result["version"].get("status") != required_status:
            raise DurableRecordIntegrityError("operation result status is invalid")
        if (
            operation_type == "create-character-continuity-version"
            and result["version"].get("status") not in {"DRAFT", "CANDIDATE"}
        ):
            raise DurableRecordIntegrityError("create result status is invalid")
    else:
        snapshot_ref = result.get("m6BaselineSnapshotRef")
        persisted = _operation_fact(
            connection,
            row,
            "v5_m6_baseline_snapshots",
            "m6_baseline_snapshot_ref",
            snapshot_ref,
        )
        mutable = frozenset({"status", "supersededAt"})
        if (
            result.get("status") != "ACTIVE"
            or not _same(_without(result, mutable), _without(persisted, mutable))
            or persisted.get("status") not in {"ACTIVE", "SUPERSEDED"}
        ):
            raise DurableRecordIntegrityError("activation result is not durable")
    return result


def _validate_operations(connection: Any) -> list[tuple[Any, dict[str, Any]]]:
    operations: list[tuple[Any, dict[str, Any]]] = []
    for row in connection.execute("SELECT * FROM v5_m6_operations"):
        operations.append((row, validate_durable_operation(connection, row)))
    return operations


def validate_durable_event(connection: Any, row: Any) -> dict[str, Any]:
    """Validate one Outbox envelope and its same-Scope aggregate fact."""

    event = _load(row["event_json"], require_mapping=True)
    assert isinstance(event, dict)
    projection = {
            "business_domain": event.get("businessDomain"),
            "tenant_id": event.get("tenantId"),
            "workspace_ref": event.get("workspaceId"),
            "project_ref": event.get("projectRef"),
            "series_ref": event.get("seriesRef"),
            "event_id": event.get("eventId"),
            "event_type": event.get("eventType"),
            "event_version": event.get("eventVersion"),
            "aggregate_type": event.get("aggregateType"),
            "aggregate_ref": event.get("aggregateRef"),
            "operation_ref": event.get("operationRef"),
            "correlation_id": event.get("correlationId"),
            "causation_id": event.get("causationId"),
            "occurred_at": event.get("occurredAt"),
    }
    if any(not _same(row[column], value) for column, value in projection.items()):
        raise DurableRecordIntegrityError("Outbox projection mismatch")
    if (
        event.get("schemaVersion") != "v5.m6-series-intelligence-event.v1"
        or not _same(event.get("eventVersion"), 1)
        or event.get("aggregateType") != "M6BaselineSnapshot"
        or event.get("eventType")
        not in {"M6BaselineSuperseded", "M6BaselineConfirmed"}
        or not isinstance(event.get("payload"), dict)
    ):
        raise DurableRecordIntegrityError("Outbox envelope is invalid")
    snapshot = connection.execute(
        "SELECT activation_revision,content_digest,status FROM v5_m6_baseline_snapshots "
        "WHERE business_domain=? AND tenant_id=? AND workspace_ref=? "
        "AND project_ref=? AND series_ref=? AND m6_baseline_snapshot_ref=?",
        (*tuple(row[column] for column in _SCOPE_COLUMNS), row["aggregate_ref"]),
    ).fetchone()
    if snapshot is None:
        raise DurableRecordIntegrityError("Outbox aggregate is unavailable")
    payload = event["payload"]
    if event["eventType"] == "M6BaselineConfirmed" and (
        not _same(payload.get("m6BaselineSnapshotRef"), row["aggregate_ref"])
        or not _same(payload.get("activationRevision"), snapshot["activation_revision"])
        or not _same(payload.get("contentDigest"), snapshot["content_digest"])
    ):
        raise DurableRecordIntegrityError("confirmed Outbox payload is invalid")
    if event["eventType"] == "M6BaselineSuperseded" and (
        not _same(payload.get("supersededSnapshotRef"), row["aggregate_ref"])
        or not isinstance(payload.get("replacementSnapshotRef"), str)
        or not payload["replacementSnapshotRef"].strip()
        or snapshot["status"] != "SUPERSEDED"
    ):
        raise DurableRecordIntegrityError("superseded Outbox payload is invalid")
    return event


def _validate_outbox(connection: Any) -> list[tuple[Any, dict[str, Any]]]:
    events: list[tuple[Any, dict[str, Any]]] = []
    for row in connection.execute("SELECT * FROM v5_m6_outbox ORDER BY position"):
        event = validate_durable_event(connection, row)
        events.append((row, event))
    return events


def _validate_mutation_history(
    roots: list[dict[str, Any]],
    versions: list[dict[str, Any]],
    operations: list[tuple[Any, dict[str, Any]]],
    *,
    family: str,
) -> None:
    if family == "bible":
        root_ref = "seriesBibleRef"
        version_ref = "seriesBibleVersionRef"
        current_ref = "currentSeriesBibleVersionRef"
        confirmed_ref = "confirmedSeriesBibleVersionRef"
        create_type = "create-series-bible-version"
        submit_type = "submit-series-bible-candidate"
        confirm_type = "confirm-series-bible-version"
    else:
        root_ref = "characterContinuityRef"
        version_ref = "characterContinuityVersionRef"
        current_ref = "currentCharacterContinuityVersionRef"
        confirmed_ref = "confirmedCharacterContinuityVersionRef"
        create_type = "create-character-continuity-version"
        submit_type = "submit-character-continuity-candidate"
        confirm_type = "confirm-character-continuity-version"
    family_types = {create_type, submit_type, confirm_type}
    family_operations = [
        (row, result)
        for row, result in operations
        if row["operation_type"] in family_types
    ]
    grouped: dict[tuple[Any, ...], list[tuple[Any, dict[str, Any]]]] = {}
    for row, result in family_operations:
        operation_root = result.get("root")
        if not isinstance(operation_root, dict):
            raise DurableRecordIntegrityError("operation root result is invalid")
        grouped.setdefault(_identity(operation_root, root_ref), []).append(
            (row, result)
        )
    durable_versions = {
        _identity(version, root_ref, version_ref): version for version in versions
    }
    if len(grouped) != len(roots):
        raise DurableRecordIntegrityError("M6 mutation history cardinality is invalid")
    for root in roots:
        key = _identity(root, root_ref)
        history = grouped.get(key)
        if not history:
            raise DurableRecordIntegrityError("M6 root mutation history is missing")
        try:
            history.sort(key=lambda item: item[1]["root"]["revision"])
        except (KeyError, TypeError):
            raise DurableRecordIntegrityError("M6 operation revision is invalid") from None
        revisions = [item[1]["root"].get("revision") for item in history]
        if revisions != list(range(1, root["revision"] + 1)):
            raise DurableRecordIntegrityError("M6 mutation revisions are incomplete")
        current: Any = None
        confirmed: Any = None
        states: dict[Any, str] = {}
        created: set[Any] = set()
        for row, result in history:
            operation_type = row["operation_type"]
            operation_root = result["root"]
            operation_version = result["version"]
            ref = operation_version.get(version_ref)
            if operation_type == create_type:
                if ref in created:
                    raise DurableRecordIntegrityError("M6 version has duplicate create history")
                expected_number = len(created) + 1
                if not _same(operation_version.get("versionNumber"), expected_number):
                    raise DurableRecordIntegrityError("M6 create history is out of order")
                status = operation_version.get("status")
                if status not in {"DRAFT", "CANDIDATE"}:
                    raise DurableRecordIntegrityError("M6 create history status is invalid")
                created.add(ref)
                states[ref] = status
                current = ref
            elif operation_type == submit_type:
                if ref != current or states.get(ref) != "DRAFT":
                    raise DurableRecordIntegrityError("M6 submit history is invalid")
                states[ref] = "CANDIDATE"
            elif operation_type == confirm_type:
                if ref != current or states.get(ref) != "CANDIDATE":
                    raise DurableRecordIntegrityError("M6 confirmation history is invalid")
                states[ref] = "CONFIRMED"
                confirmed = ref
            if (
                operation_root.get(current_ref) != current
                or operation_root.get(confirmed_ref) != confirmed
                or operation_version.get("status") != states.get(ref)
            ):
                raise DurableRecordIntegrityError("M6 operation history projection diverges")
        if current != root.get(current_ref) or confirmed != root.get(confirmed_ref):
            raise DurableRecordIntegrityError("M6 root history does not reach durable state")
        expected_refs = {
            version.get(version_ref)
            for version in versions
            if _identity(version, root_ref) == key
        }
        if created != expected_refs:
            raise DurableRecordIntegrityError("M6 version create history is incomplete")
        for ref, status in states.items():
            durable = durable_versions.get((*key, ref))
            if durable is None or durable.get("status") != status:
                raise DurableRecordIntegrityError("M6 version history does not reach durable state")


def _validate_activation_closure(
    snapshots: list[dict[str, Any]],
    operations: list[tuple[Any, dict[str, Any]]],
    events: list[tuple[Any, dict[str, Any]]],
) -> None:
    activation_operations = [
        (row, result)
        for row, result in operations
        if row["operation_type"] == "activate-m6-baseline"
    ]
    by_operation: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row, result in activation_operations:
        key = (*tuple(row[column] for column in _SCOPE_COLUMNS), row["operation_ref"])
        by_operation.setdefault(key, []).append(result)

    grouped_snapshots: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        grouped_snapshots.setdefault(_record_scope_key(snapshot), []).append(snapshot)
    used_positions: set[int] = set()
    for scope, scoped_snapshots in grouped_snapshots.items():
        ordered = sorted(scoped_snapshots, key=lambda item: item.get("activationRevision", 0))
        revisions = [item.get("activationRevision") for item in ordered]
        if revisions != list(range(1, len(ordered) + 1)):
            raise DurableRecordIntegrityError("M6 activation revisions are incomplete")
        for index, snapshot in enumerate(ordered):
            expected_status = "ACTIVE" if index == len(ordered) - 1 else "SUPERSEDED"
            if snapshot.get("status") != expected_status:
                raise DurableRecordIntegrityError("M6 snapshot lifecycle is invalid")
            snapshot_ref = snapshot.get("m6BaselineSnapshotRef")
            confirmed = [
                (row, event)
                for row, event in events
                if tuple(row[column] for column in _SCOPE_COLUMNS) == scope
                and row["event_type"] == "M6BaselineConfirmed"
                and row["aggregate_ref"] == snapshot_ref
            ]
            if len(confirmed) != 1:
                raise DurableRecordIntegrityError("snapshot originating event is missing or duplicated")
            confirmed_row, _confirmed_event = confirmed[0]
            used_positions.add(confirmed_row["position"])
            operation_key = (*scope, confirmed_row["operation_ref"])
            candidates = by_operation.get(operation_key, [])
            if not any(
                result.get("m6BaselineSnapshotRef") == snapshot_ref
                for result in candidates
            ):
                raise DurableRecordIntegrityError("confirmed event has no activation operation")
            if index == 0:
                continue
            old_ref = ordered[index - 1].get("m6BaselineSnapshotRef")
            superseded = [
                (row, event)
                for row, event in events
                if tuple(row[column] for column in _SCOPE_COLUMNS) == scope
                and row["event_type"] == "M6BaselineSuperseded"
                and row["aggregate_ref"] == old_ref
                and event["payload"].get("replacementSnapshotRef") == snapshot_ref
            ]
            if len(superseded) != 1:
                raise DurableRecordIntegrityError("snapshot replacement event is missing or duplicated")
            superseded_row, _superseded_event = superseded[0]
            used_positions.add(superseded_row["position"])
            if (
                superseded_row["operation_ref"] != confirmed_row["operation_ref"]
                or superseded_row["position"] + 1 != confirmed_row["position"]
            ):
                raise DurableRecordIntegrityError("snapshot replacement event order is invalid")

    if len(used_positions) != len(events):
        raise DurableRecordIntegrityError("orphan or duplicate M6 Outbox event")


def validate_durable_record(
    connection: Any, table: str, row: Any
) -> dict[str, Any]:
    """Validate one already-scoped durable fact without scanning other Scope rows."""

    record = _record(row)
    source_cache: dict[tuple[str, ...], str] = {}
    if table == "v5_m6_series_bibles":
        if record.get("schemaVersion") != "v5.series-bible.v1":
            raise DurableRecordIntegrityError("M6 root schema is invalid")
    elif table == "v5_m6_series_bible_versions":
        _load(row["content_json"])
        _validate_bible_version(connection, row, record, source_cache)
    elif table == "v5_m6_character_continuities":
        if record.get("schemaVersion") != "v5.character-continuity.v1":
            raise DurableRecordIntegrityError("M6 root schema is invalid")
    elif table == "v5_m6_character_continuity_versions":
        _load(row["content_json"])
        _validate_character_version(connection, row, record, source_cache)
    elif table == "v5_m6_baseline_snapshots":
        _validate_snapshot(connection, row, record, source_cache)
    else:
        raise DurableRecordIntegrityError("unsupported durable record table")
    return record


def validate_durable_rows(connection: Any) -> None:
    """Validate every durable JSON record and its constrained projection."""

    source_cache: dict[tuple[str, ...], str] = {}
    root_specs = (
        ("v5_m6_series_bibles", "v5.series-bible.v1", "bible"),
        (
            "v5_m6_character_continuities",
            "v5.character-continuity.v1",
            "character",
        ),
    )
    roots: dict[str, list[dict[str, Any]]] = {"bible": [], "character": []}
    for table, schema, family in root_specs:
        for row in connection.execute(f"SELECT * FROM {table}"):
            record = _record(row)
            if record.get("schemaVersion") != schema:
                raise DurableRecordIntegrityError("M6 root schema is invalid")
            roots[family].append(record)
    bible_versions: list[dict[str, Any]] = []
    for row in connection.execute("SELECT * FROM v5_m6_series_bible_versions"):
        record = _record(row)
        _load(row["content_json"])
        _validate_bible_version(connection, row, record, source_cache)
        bible_versions.append(record)
    character_versions: list[dict[str, Any]] = []
    for row in connection.execute("SELECT * FROM v5_m6_character_continuity_versions"):
        record = _record(row)
        _load(row["content_json"])
        _validate_character_version(connection, row, record, source_cache)
        character_versions.append(record)
    _validate_root_lineage(
        roots["bible"],
        bible_versions,
        root_ref="seriesBibleRef",
        version_ref="seriesBibleVersionRef",
        parent_ref="parentSeriesBibleVersionRef",
        current_ref="currentSeriesBibleVersionRef",
        confirmed_ref="confirmedSeriesBibleVersionRef",
    )
    _validate_root_lineage(
        roots["character"],
        character_versions,
        root_ref="characterContinuityRef",
        version_ref="characterContinuityVersionRef",
        parent_ref="parentCharacterContinuityVersionRef",
        current_ref="currentCharacterContinuityVersionRef",
        confirmed_ref="confirmedCharacterContinuityVersionRef",
    )
    snapshots: list[dict[str, Any]] = []
    for row in connection.execute("SELECT * FROM v5_m6_baseline_snapshots"):
        record = _record(row)
        _validate_snapshot(connection, row, record, source_cache)
        snapshots.append(record)
    operations = _validate_operations(connection)
    _validate_mutation_history(
        roots["bible"], bible_versions, operations, family="bible"
    )
    _validate_mutation_history(
        roots["character"], character_versions, operations, family="character"
    )
    events = _validate_outbox(connection)
    _validate_activation_closure(snapshots, operations, events)
