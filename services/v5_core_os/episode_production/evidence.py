"""Append-only evidence journal for the authorized K2 production gates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Mapping, Protocol, Sequence

from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
    _idempotency_key,
    _required_ref,
)


EVIDENCE_SCHEMA_VERSION = 2
ROOTS_READY = "ROOTS_READY"
ALLOWED_EVIDENCE_RECORD_KINDS = frozenset(
    {
        "Candidate",
        "TechnicalValidation",
        "SemanticVisualQCDecision",
        "HumanSelectionDecision",
        "AssetAdmission",
        "AssetVersion",
    }
)
K2_STATES = (
    ROOTS_READY,
    "AUTHORITY_READY",
    "SCRIPT_VALIDATED",
    "SHOTS_COMPILED",
    "ASSETS_READY",
    "MEDIA_READY",
    "PREVIEW_READY",
    "QC_READY",
    "REAL_IMAGE_PLAN_READY",
    "REAL_IMAGE_READY",
    "REAL_VIDEO_PLAN_READY",
    "REAL_VIDEO_READY",
    "REAL_PREVIEW_READY",
    "REAL_QC_READY",
    "APPROVAL_READY",
    "MASTER_READY",
)

ALLOWED_K2_STATE_TRANSITIONS = frozenset(
    {
        (K2_STATES[index], K2_STATES[index + 1])
        for index in range(K2_STATES.index("QC_READY"))
    }
    | {
        # The accepted deterministic G2-G6 path remains valid for runs that do
        # not enter a real-media revision.
        ("QC_READY", "APPROVAL_READY"),
        # A same-run, append-only image-first revision.  Candidate execution
        # and technical verification do not advance these states; only the
        # corresponding plan/admission evidence gates do.
        ("QC_READY", "REAL_IMAGE_PLAN_READY"),
        ("REAL_IMAGE_PLAN_READY", "REAL_IMAGE_READY"),
        ("REAL_IMAGE_READY", "REAL_VIDEO_PLAN_READY"),
        ("REAL_VIDEO_PLAN_READY", "REAL_VIDEO_READY"),
        ("REAL_VIDEO_READY", "REAL_PREVIEW_READY"),
        ("REAL_PREVIEW_READY", "REAL_QC_READY"),
        ("REAL_QC_READY", "APPROVAL_READY"),
        ("APPROVAL_READY", "MASTER_READY"),
    }
)


class InvalidStateTransitionError(EpisodeProductionError):
    code = "invalid_state_transition"


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    factKind: str
    factRef: str
    factVersion: int
    payload: Mapping[str, Any]
    payloadDigest: str


@dataclass(frozen=True, slots=True)
class GateAppend:
    workspaceRef: str
    productionRunRef: str
    gateName: str
    idempotencyKey: str
    rootPayloadDigest: str
    requestDigest: str
    fromState: str
    toState: str
    createdAt: str
    facts: Sequence[EvidenceFact]


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Append-only canonical evidence that does not advance production state."""

    workspaceRef: str
    productionRunRef: str
    recordKind: str
    recordRef: str
    recordVersion: int
    idempotencyKey: str
    requestDigest: str
    createdAt: str
    payload: Mapping[str, Any]
    payloadDigest: str


class EpisodeProductionEvidenceRepository(Protocol):
    def current_state(self, workspace_ref: str, run_ref: str) -> str: ...
    def get_gate(self, workspace_ref: str, run_ref: str, gate_name: str) -> dict[str, Any] | None: ...
    def list_gates(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]: ...
    def append_gate(self, gate: GateAppend) -> tuple[dict[str, Any], bool]: ...
    def get_record(
        self, workspace_ref: str, run_ref: str, record_ref: str, record_version: int
    ) -> dict[str, Any] | None: ...
    def list_records(
        self, workspace_ref: str, run_ref: str, *, record_kind: str | None = None
    ) -> list[dict[str, Any]]: ...
    def append_record(self, record: EvidenceRecord) -> tuple[dict[str, Any], bool]: ...
    def append_records(
        self,
        records: Sequence[EvidenceRecord],
        *,
        expected_record_journal_head: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]: ...
    def record_journal_head(self, workspace_ref: str, run_ref: str) -> str: ...
    def append_records_and_gate(
        self,
        records: Sequence[EvidenceRecord],
        gate: GateAppend,
        *,
        expected_record_journal_head: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], bool]: ...


def _gate_mapping(gate: GateAppend) -> dict[str, Any]:
    return {
        "workspaceRef": gate.workspaceRef,
        "productionRunRef": gate.productionRunRef,
        "gateName": gate.gateName,
        "idempotencyKey": gate.idempotencyKey,
        "rootPayloadDigest": gate.rootPayloadDigest,
        "requestDigest": gate.requestDigest,
        "fromState": gate.fromState,
        "toState": gate.toState,
        "createdAt": gate.createdAt,
        "facts": [
            {
                "factKind": fact.factKind,
                "factRef": fact.factRef,
                "factVersion": fact.factVersion,
                "payload": deepcopy(dict(fact.payload)),
                "payloadDigest": fact.payloadDigest,
            }
            for fact in gate.facts
        ],
    }


def _record_mapping(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "workspaceRef": record.workspaceRef,
        "productionRunRef": record.productionRunRef,
        "recordKind": record.recordKind,
        "recordRef": record.recordRef,
        "recordVersion": record.recordVersion,
        "idempotencyKey": record.idempotencyKey,
        "requestDigest": record.requestDigest,
        "createdAt": record.createdAt,
        "payload": deepcopy(dict(record.payload)),
        "payloadDigest": record.payloadDigest,
    }


def _validate_digest(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")


def _optional_record_journal_head(value: str | None) -> str | None:
    if value is None:
        return None
    _validate_digest(value, "expectedRecordJournalHead")
    return value


def _record_journal_head_value(
    workspace_ref: str,
    run_ref: str,
    *,
    record_count: int,
    latest_sequence: int | None,
    latest_record_ref: str | None,
    latest_record_version: int | None,
    latest_payload_digest: str | None,
) -> str:
    """Seal an opaque compare-and-swap token for one append-only record journal."""

    _required_ref(workspace_ref, "workspaceRef")
    _required_ref(run_ref, "productionRunRef")
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 0:
        raise RepositoryUnavailableError("record journal count is invalid")
    if record_count == 0:
        if any(
            value is not None
            for value in (
                latest_sequence,
                latest_record_ref,
                latest_record_version,
                latest_payload_digest,
            )
        ):
            raise RepositoryUnavailableError("empty record journal head is invalid")
        latest: dict[str, Any] | None = None
    else:
        if (
            isinstance(latest_sequence, bool)
            or not isinstance(latest_sequence, int)
            or latest_sequence < 1
            or isinstance(latest_record_version, bool)
            or not isinstance(latest_record_version, int)
            or latest_record_version < 1
            or latest_sequence != record_count
        ):
            raise RepositoryUnavailableError("record journal sequence is invalid")
        latest = {
            "sequence": latest_sequence,
            "recordRef": _required_ref(latest_record_ref, "recordRef"),
            "recordVersion": latest_record_version,
            "payloadDigest": latest_payload_digest,
        }
        try:
            _validate_digest(latest_payload_digest, "payloadDigest")
        except EpisodeProductionError as exc:
            raise RepositoryUnavailableError("record journal digest is invalid") from exc
    return _digest(
        {
            "schemaVersion": "v5.episode-production-record-journal-head.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": run_ref,
            "recordCount": record_count,
            "latestRecord": latest,
        }
    )


def _validate_record(record: EvidenceRecord) -> None:
    _required_ref(record.workspaceRef, "workspaceRef")
    _required_ref(record.productionRunRef, "productionRunRef")
    _required_ref(record.recordKind, "recordKind")
    if record.recordKind not in ALLOWED_EVIDENCE_RECORD_KINDS:
        raise EpisodeProductionError("recordKind is not authorized")
    _required_ref(record.recordRef, "recordRef")
    _idempotency_key(record.idempotencyKey)
    if (
        isinstance(record.recordVersion, bool)
        or not isinstance(record.recordVersion, int)
        or record.recordVersion < 1
    ):
        raise EpisodeProductionError("recordVersion is invalid")
    if not isinstance(record.payload, Mapping):
        raise EpisodeProductionError("record payload must be an object")
    _validate_digest(record.requestDigest, "requestDigest")
    _validate_digest(record.payloadDigest, "payloadDigest")
    digest_payload = dict(record.payload)
    embedded_digest = digest_payload.pop("payloadDigest", None)
    if embedded_digest is not None and embedded_digest != record.payloadDigest:
        raise EpisodeProductionError("record embedded payload digest is invalid")
    if _digest(digest_payload) != record.payloadDigest:
        raise EpisodeProductionError("record payload digest is invalid")


def _validate_gate(gate: GateAppend) -> None:
    _required_ref(gate.workspaceRef, "workspaceRef")
    _required_ref(gate.productionRunRef, "productionRunRef")
    _required_ref(gate.gateName, "gateName")
    _idempotency_key(gate.idempotencyKey)
    for field, value in (
        ("rootPayloadDigest", gate.rootPayloadDigest),
        ("requestDigest", gate.requestDigest),
    ):
        _validate_digest(value, field)
    if gate.fromState not in K2_STATES or gate.toState not in K2_STATES:
        raise InvalidStateTransitionError("unknown K2 state")
    if (gate.fromState, gate.toState) not in ALLOWED_K2_STATE_TRANSITIONS:
        raise InvalidStateTransitionError("K2 state transition is not allowed")
    kinds = [fact.factKind for fact in gate.facts]
    if not kinds or len(kinds) != len(set(kinds)):
        raise EpisodeProductionError("gate facts must have unique kinds")
    for fact in gate.facts:
        _required_ref(fact.factKind, "factKind")
        _required_ref(fact.factRef, "factRef")
        if (
            isinstance(fact.factVersion, bool)
            or not isinstance(fact.factVersion, int)
            or fact.factVersion < 1
        ):
            raise EpisodeProductionError("factVersion is invalid")
        if not isinstance(fact.payload, Mapping):
            raise EpisodeProductionError("fact payload must be an object")
        digest_payload = dict(fact.payload)
        embedded_digest = digest_payload.pop("payloadDigest", None)
        if embedded_digest is not None and embedded_digest != fact.payloadDigest:
            raise EpisodeProductionError("fact embedded payload digest is invalid")
        if _digest(digest_payload) != fact.payloadDigest:
            raise EpisodeProductionError("fact payload digest is invalid")


def _gate_from_mapping(value: Mapping[str, Any]) -> GateAppend:
    facts = value.get("facts")
    if not isinstance(facts, list):
        raise RepositoryUnavailableError("episode evidence facts are invalid")
    try:
        gate = GateAppend(
            workspaceRef=value["workspaceRef"],
            productionRunRef=value["productionRunRef"],
            gateName=value["gateName"],
            idempotencyKey=value["idempotencyKey"],
            rootPayloadDigest=value["rootPayloadDigest"],
            requestDigest=value["requestDigest"],
            fromState=value["fromState"],
            toState=value["toState"],
            createdAt=value["createdAt"],
            facts=tuple(
                EvidenceFact(
                    factKind=fact["factKind"],
                    factRef=fact["factRef"],
                    factVersion=fact["factVersion"],
                    payload=fact["payload"],
                    payloadDigest=fact["payloadDigest"],
                )
                for fact in facts
                if isinstance(fact, Mapping)
            ),
        )
        if len(gate.facts) != len(facts):
            raise KeyError("fact")
        _validate_gate(gate)
        return gate
    except (KeyError, TypeError, EpisodeProductionError) as exc:
        raise RepositoryUnavailableError(
            "episode evidence digest verification failed"
        ) from exc


class InMemoryEpisodeProductionEvidenceAdapter:
    def __init__(self) -> None:
        self._gates: dict[tuple[str, str, str], GateAppend] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._transitions: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self._gate_order: dict[tuple[str, str], list[str]] = {}
        self._records: dict[tuple[str, str, str, int], EvidenceRecord] = {}
        self._record_idempotency: dict[
            tuple[str, str, str], tuple[str, int]
        ] = {}
        self._record_order: dict[tuple[str, str], list[tuple[str, int]]] = {}
        self._lock = RLock()

    def current_state(self, workspace_ref: str, run_ref: str) -> str:
        with self._lock:
            transitions = self._transitions.get((workspace_ref, run_ref), [])
            return transitions[-1][1] if transitions else ROOTS_READY

    def get_gate(
        self, workspace_ref: str, run_ref: str, gate_name: str
    ) -> dict[str, Any] | None:
        with self._lock:
            gate = self._gates.get((workspace_ref, run_ref, gate_name))
            return None if gate is None else _gate_mapping(gate)

    def list_gates(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        with self._lock:
            names = self._gate_order.get((workspace_ref, run_ref), [])
            return [
                _gate_mapping(self._gates[(workspace_ref, run_ref, name)])
                for name in names
            ]

    def append_gate(self, gate: GateAppend) -> tuple[dict[str, Any], bool]:
        _validate_gate(gate)
        with self._lock:
            replay_key = (gate.workspaceRef, gate.productionRunRef, gate.idempotencyKey)
            replay_name = self._idempotency.get(replay_key)
            if replay_name is not None:
                if replay_name != gate.gateName:
                    raise IdempotencyConflictError(
                        "gate idempotency key belongs to another gate"
                    )
                replay = self._gates[(gate.workspaceRef, gate.productionRunRef, replay_name)]
                if replay.requestDigest != gate.requestDigest:
                    raise IdempotencyConflictError("gate idempotency content changed")
                return _gate_mapping(replay), True
            key = (gate.workspaceRef, gate.productionRunRef, gate.gateName)
            if key in self._gates:
                raise InvalidStateTransitionError("gate was already recorded")
            if self.current_state(gate.workspaceRef, gate.productionRunRef) != gate.fromState:
                raise InvalidStateTransitionError("production run state changed")
            self._gates[key] = deepcopy(gate)
            self._idempotency[replay_key] = gate.gateName
            self._transitions.setdefault(
                (gate.workspaceRef, gate.productionRunRef), []
            ).append((gate.fromState, gate.toState))
            self._gate_order.setdefault(
                (gate.workspaceRef, gate.productionRunRef), []
            ).append(gate.gateName)
            return _gate_mapping(gate), False

    def get_record(
        self, workspace_ref: str, run_ref: str, record_ref: str, record_version: int
    ) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(
                (workspace_ref, run_ref, record_ref, record_version)
            )
            return None if record is None else _record_mapping(record)

    def list_records(
        self, workspace_ref: str, run_ref: str, *, record_kind: str | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            keys = self._record_order.get((workspace_ref, run_ref), [])
            records = [
                self._records[(workspace_ref, run_ref, record_ref, record_version)]
                for record_ref, record_version in keys
            ]
            if record_kind is not None:
                records = [item for item in records if item.recordKind == record_kind]
            return [_record_mapping(item) for item in records]

    def append_record(self, record: EvidenceRecord) -> tuple[dict[str, Any], bool]:
        stored, replayed = self.append_records((record,))
        return stored[0], replayed

    def append_records(
        self,
        records: Sequence[EvidenceRecord],
        *,
        expected_record_journal_head: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not records:
            raise EpisodeProductionError("record batch is empty")
        for record in records:
            _validate_record(record)
        scope = {(item.workspaceRef, item.productionRunRef) for item in records}
        identities = {(item.recordRef, item.recordVersion) for item in records}
        idempotency = {item.idempotencyKey for item in records}
        if len(scope) != 1 or len(identities) != len(records) or len(idempotency) != len(records):
            raise EpisodeProductionError("record batch is invalid")
        expected_head = _optional_record_journal_head(
            expected_record_journal_head
        )
        with self._lock:
            workspace_ref, run_ref = next(iter(scope))
            current_head = self.record_journal_head(workspace_ref, run_ref)
            replayed: list[EvidenceRecord] = []
            new_count = 0
            for record in records:
                replay_key = (
                    record.workspaceRef,
                    record.productionRunRef,
                    record.idempotencyKey,
                )
                replay_identity = self._record_idempotency.get(replay_key)
                if replay_identity is None:
                    key = (
                        record.workspaceRef,
                        record.productionRunRef,
                        record.recordRef,
                        record.recordVersion,
                    )
                    if key in self._records:
                        raise IdempotencyConflictError(
                            "record version was already recorded"
                        )
                    new_count += 1
                    continue
                if replay_identity != (record.recordRef, record.recordVersion):
                    raise IdempotencyConflictError(
                        "record idempotency key belongs to another record"
                    )
                replay = self._records[
                    (
                        record.workspaceRef,
                        record.productionRunRef,
                        replay_identity[0],
                        replay_identity[1],
                    )
                ]
                if replay.requestDigest != record.requestDigest:
                    raise IdempotencyConflictError("record idempotency content changed")
                replayed.append(replay)
            if replayed and new_count:
                raise IdempotencyConflictError("record batch is partially present")
            if replayed:
                return [_record_mapping(item) for item in replayed], True
            if expected_head is not None and current_head != expected_head:
                raise StaleInputError("record journal head changed")
            for record in records:
                key = (
                    record.workspaceRef,
                    record.productionRunRef,
                    record.recordRef,
                    record.recordVersion,
                )
                replay_key = (
                    record.workspaceRef,
                    record.productionRunRef,
                    record.idempotencyKey,
                )
                self._records[key] = deepcopy(record)
                self._record_idempotency[replay_key] = (
                    record.recordRef,
                    record.recordVersion,
                )
                self._record_order.setdefault(
                    (record.workspaceRef, record.productionRunRef), []
                ).append((record.recordRef, record.recordVersion))
            return [_record_mapping(item) for item in records], False

    def record_journal_head(self, workspace_ref: str, run_ref: str) -> str:
        with self._lock:
            order = self._record_order.get((workspace_ref, run_ref), [])
            if not order:
                return _record_journal_head_value(
                    workspace_ref,
                    run_ref,
                    record_count=0,
                    latest_sequence=None,
                    latest_record_ref=None,
                    latest_record_version=None,
                    latest_payload_digest=None,
                )
            record_ref, record_version = order[-1]
            latest = self._records[
                (workspace_ref, run_ref, record_ref, record_version)
            ]
            return _record_journal_head_value(
                workspace_ref,
                run_ref,
                record_count=len(order),
                latest_sequence=len(order),
                latest_record_ref=latest.recordRef,
                latest_record_version=latest.recordVersion,
                latest_payload_digest=latest.payloadDigest,
            )

    def append_records_and_gate(
        self,
        records: Sequence[EvidenceRecord],
        gate: GateAppend,
        *,
        expected_record_journal_head: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
        """Append non-transition records and their transition gate atomically."""

        if not records:
            raise EpisodeProductionError("record batch is empty")
        _validate_gate(gate)
        for record in records:
            _validate_record(record)
        expected_head = _optional_record_journal_head(
            expected_record_journal_head
        )
        if any(
            record.workspaceRef != gate.workspaceRef
            or record.productionRunRef != gate.productionRunRef
            for record in records
        ):
            raise EpisodeProductionError("record and gate scopes do not match")
        with self._lock:
            current_head = self.record_journal_head(
                gate.workspaceRef, gate.productionRunRef
            )
            snapshot = (
                deepcopy(self._gates),
                deepcopy(self._idempotency),
                deepcopy(self._transitions),
                deepcopy(self._gate_order),
                deepcopy(self._records),
                deepcopy(self._record_idempotency),
                deepcopy(self._record_order),
            )
            try:
                stored_records, records_replayed = self.append_records(records)
                stored_gate, gate_replayed = self.append_gate(gate)
                if records_replayed != gate_replayed:
                    raise IdempotencyConflictError(
                        "atomic record and gate batch is partially present"
                    )
                if (
                    not records_replayed
                    and expected_head is not None
                    and current_head != expected_head
                ):
                    raise StaleInputError("record journal head changed")
                return stored_records, stored_gate, records_replayed
            except BaseException:
                (
                    self._gates,
                    self._idempotency,
                    self._transitions,
                    self._gate_order,
                    self._records,
                    self._record_idempotency,
                    self._record_order,
                ) = snapshot
                raise


class SqliteEpisodeProductionEvidenceAdapter:
    """Dedicated additive local evidence DB; no accepted lifecycle schema is changed."""

    _TABLES = {
        "v5_episode_production_evidence_schema",
        "v5_episode_production_gates",
        "v5_episode_production_facts",
        "v5_episode_production_transitions",
        "v5_episode_production_records",
    }
    _COLUMNS = {
        "v5_episode_production_evidence_schema": (
            "component", "schema_version",
        ),
        "v5_episode_production_gates": (
            "workspace_ref", "production_run_ref", "gate_name",
            "idempotency_key", "root_payload_digest", "request_digest",
            "from_state", "to_state", "created_at",
        ),
        "v5_episode_production_facts": (
            "workspace_ref", "production_run_ref", "gate_name", "fact_kind",
            "fact_ref", "fact_version", "payload_json", "payload_digest",
        ),
        "v5_episode_production_transitions": (
            "workspace_ref", "production_run_ref", "sequence", "gate_name",
            "from_state", "to_state", "evidence_digest", "created_at",
        ),
        "v5_episode_production_records": (
            "workspace_ref", "production_run_ref", "sequence", "record_kind",
            "record_ref", "record_version", "idempotency_key", "request_digest",
            "payload_json", "payload_digest", "created_at",
        ),
    }

    def __init__(self, database_path: Path | str, *, initialize_if_missing: bool) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_or_validate(initialize_if_missing)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE v5_episode_production_evidence_schema ("
            "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO v5_episode_production_evidence_schema VALUES "
            f"('episode_production_evidence', {EVIDENCE_SCHEMA_VERSION})"
        )
        connection.execute(
            """CREATE TABLE v5_episode_production_gates (
            workspace_ref TEXT NOT NULL,
            production_run_ref TEXT NOT NULL,
            gate_name TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            root_payload_digest TEXT NOT NULL,
            request_digest TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, production_run_ref, gate_name),
            UNIQUE(workspace_ref, production_run_ref, idempotency_key)
            )"""
        )
        connection.execute(
            """CREATE TABLE v5_episode_production_facts (
            workspace_ref TEXT NOT NULL,
            production_run_ref TEXT NOT NULL,
            gate_name TEXT NOT NULL,
            fact_kind TEXT NOT NULL,
            fact_ref TEXT NOT NULL,
            fact_version INTEGER NOT NULL CHECK(fact_version > 0),
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, production_run_ref, fact_kind, fact_ref, fact_version),
            UNIQUE(workspace_ref, production_run_ref, gate_name, fact_kind),
            FOREIGN KEY(workspace_ref, production_run_ref, gate_name)
              REFERENCES v5_episode_production_gates(workspace_ref, production_run_ref, gate_name)
              ON DELETE RESTRICT
            )"""
        )
        connection.execute(
            """CREATE TABLE v5_episode_production_transitions (
            workspace_ref TEXT NOT NULL,
            production_run_ref TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence > 0),
            gate_name TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            evidence_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, production_run_ref, sequence),
            UNIQUE(workspace_ref, production_run_ref, gate_name),
            FOREIGN KEY(workspace_ref, production_run_ref, gate_name)
              REFERENCES v5_episode_production_gates(workspace_ref, production_run_ref, gate_name)
              ON DELETE RESTRICT
            )"""
        )
        connection.execute(
            """CREATE TABLE v5_episode_production_records (
            workspace_ref TEXT NOT NULL,
            production_run_ref TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence > 0),
            record_kind TEXT NOT NULL,
            record_ref TEXT NOT NULL,
            record_version INTEGER NOT NULL CHECK(record_version > 0),
            idempotency_key TEXT NOT NULL,
            request_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, production_run_ref, sequence),
            UNIQUE(workspace_ref, production_run_ref, record_ref, record_version),
            UNIQUE(workspace_ref, production_run_ref, idempotency_key)
            )"""
        )

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        connection.execute(
            """CREATE TABLE v5_episode_production_records (
            workspace_ref TEXT NOT NULL,
            production_run_ref TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence > 0),
            record_kind TEXT NOT NULL,
            record_ref TEXT NOT NULL,
            record_version INTEGER NOT NULL CHECK(record_version > 0),
            idempotency_key TEXT NOT NULL,
            request_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(workspace_ref, production_run_ref, sequence),
            UNIQUE(workspace_ref, production_run_ref, record_ref, record_version),
            UNIQUE(workspace_ref, production_run_ref, idempotency_key)
            )"""
        )
        connection.execute(
            "UPDATE v5_episode_production_evidence_schema SET schema_version=2 "
            "WHERE component='episode_production_evidence' AND schema_version=1"
        )

    @staticmethod
    def _table_names(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }

    @staticmethod
    def _normalized_schema_sql(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RepositoryUnavailableError("episode evidence DDL is unavailable")
        return " ".join(value.split())

    @classmethod
    def _schema_signature(
        cls, connection: sqlite3.Connection, tables: set[str]
    ) -> dict[str, Any]:
        signature: dict[str, Any] = {}
        for table in sorted(tables):
            ddl_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if ddl_row is None:
                raise RepositoryUnavailableError(
                    "episode evidence table DDL is unavailable"
                )
            columns = tuple(
                (
                    str(row[1]),
                    str(row[2]).upper(),
                    int(row[3]),
                    row[4],
                    int(row[5]),
                )
                for row in connection.execute(f"PRAGMA table_info({table})")
            )
            foreign_keys = tuple(
                tuple(row)
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")
            )
            indexes: list[tuple[int, str, int, tuple[str, ...]]] = []
            for row in connection.execute(f"PRAGMA index_list({table})"):
                index_name = str(row[1])
                indexes.append(
                    (
                        int(row[2]),
                        str(row[3]),
                        int(row[4]),
                        tuple(
                            str(item[2])
                            for item in connection.execute(
                                f"PRAGMA index_info({index_name})"
                            )
                        ),
                    )
                )
            signature[table] = {
                "sql": cls._normalized_schema_sql(ddl_row[0]),
                "columns": columns,
                "foreignKeys": foreign_keys,
                # SQLite auto-index names are implementation details.  Their
                # uniqueness/origin/partial flags and exact column order are not.
                "indexes": tuple(sorted(indexes, key=repr)),
            }
        return signature

    @classmethod
    def _expected_schema_signature(cls, version: int) -> dict[str, Any]:
        expected = sqlite3.connect(":memory:", isolation_level=None)
        try:
            expected.execute("PRAGMA foreign_keys = ON")
            expected.execute("BEGIN IMMEDIATE")
            cls._create_schema(expected)
            if version == 1:
                expected.execute("DROP TABLE v5_episode_production_records")
                expected.execute(
                    "UPDATE v5_episode_production_evidence_schema "
                    "SET schema_version=1"
                )
            expected.commit()
            tables = (
                cls._TABLES
                if version == EVIDENCE_SCHEMA_VERSION
                else cls._TABLES - {"v5_episode_production_records"}
            )
            return cls._schema_signature(expected, set(tables))
        finally:
            expected.close()

    @staticmethod
    def _preserved_v1_rows(
        connection: sqlite3.Connection,
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                tuple(row)
                for row in connection.execute(
                    f"SELECT rowid,* FROM {table} ORDER BY rowid"
                )
            )
            for table in (
                "v5_episode_production_gates",
                "v5_episode_production_facts",
                "v5_episode_production_transitions",
            )
        }

    @classmethod
    def _validate_schema(cls, connection: sqlite3.Connection, version: int) -> None:
        if version not in {1, EVIDENCE_SCHEMA_VERSION}:
            raise RepositoryUnavailableError("episode evidence schema is unsupported")
        expected_tables = (
            cls._TABLES
            if version == EVIDENCE_SCHEMA_VERSION
            else cls._TABLES - {"v5_episode_production_records"}
        )
        tables = cls._table_names(connection)
        if tables != expected_tables:
            raise RepositoryUnavailableError("episode evidence schema is unsupported")
        if cls._schema_signature(connection, tables) != cls._expected_schema_signature(
            version
        ):
            raise RepositoryUnavailableError(
                "episode evidence DDL or constraints are unsupported"
            )
        marker = connection.execute(
            "SELECT component,schema_version "
            "FROM v5_episode_production_evidence_schema"
        ).fetchall()
        if [tuple(row) for row in marker] != [
            ("episode_production_evidence", version)
        ]:
            raise RepositoryUnavailableError("episode evidence marker is unsupported")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RepositoryUnavailableError(
                "episode evidence foreign keys are invalid"
            )
        if [tuple(row) for row in connection.execute("PRAGMA integrity_check")] != [
            ("ok",)
        ]:
            raise RepositoryUnavailableError(
                "episode evidence integrity check failed"
            )

        # Decode every durable payload before the store becomes usable.  This
        # verifies the embedded/canonical digests, not merely SQLite structure.
        gate_rows = connection.execute(
            "SELECT * FROM v5_episode_production_gates ORDER BY rowid"
        ).fetchall()
        for row in gate_rows:
            cls._decode_gate(connection, row)
        orphaned = connection.execute(
            "SELECT COUNT(*) FROM v5_episode_production_gates g "
            "LEFT JOIN v5_episode_production_transitions t USING "
            "(workspace_ref,production_run_ref,gate_name) "
            "WHERE t.gate_name IS NULL"
        ).fetchone()[0]
        if orphaned:
            raise RepositoryUnavailableError(
                "episode evidence gate transition is missing"
            )
        transition_rows = connection.execute(
            "SELECT t.workspace_ref,t.production_run_ref,t.sequence,"
            "t.from_state,t.to_state,t.evidence_digest,"
            "g.from_state AS gate_from_state,g.to_state AS gate_to_state,"
            "g.request_digest "
            "FROM v5_episode_production_transitions t "
            "JOIN v5_episode_production_gates g USING "
            "(workspace_ref,production_run_ref,gate_name) "
            "ORDER BY t.workspace_ref,t.production_run_ref,t.sequence"
        ).fetchall()
        if any(
            row["from_state"] != row["gate_from_state"]
            or row["to_state"] != row["gate_to_state"]
            or row["evidence_digest"] != row["request_digest"]
            for row in transition_rows
        ):
            raise RepositoryUnavailableError(
                "episode evidence transition lineage is invalid"
            )
        expected_transition: dict[tuple[str, str], tuple[int, str]] = {}
        for row in transition_rows:
            scope = (str(row["workspace_ref"]), str(row["production_run_ref"]))
            expected_sequence, expected_from_state = expected_transition.get(
                scope, (1, ROOTS_READY)
            )
            if (
                int(row["sequence"]) != expected_sequence
                or row["from_state"] != expected_from_state
            ):
                raise RepositoryUnavailableError(
                    "episode evidence transition journal is invalid"
                )
            expected_transition[scope] = (
                expected_sequence + 1,
                str(row["to_state"]),
            )
        if version == EVIDENCE_SCHEMA_VERSION:
            record_rows = connection.execute(
                "SELECT * FROM v5_episode_production_records "
                "ORDER BY workspace_ref,production_run_ref,sequence"
            ).fetchall()
            expected_record_sequence: dict[tuple[str, str], int] = {}
            for row in record_rows:
                cls._decode_record(row)
                scope = (
                    str(row["workspace_ref"]),
                    str(row["production_run_ref"]),
                )
                expected_sequence = expected_record_sequence.get(scope, 1)
                if int(row["sequence"]) != expected_sequence:
                    raise RepositoryUnavailableError(
                        "episode evidence record journal is invalid"
                    )
                expected_record_sequence[scope] = expected_sequence + 1

    def _initialize_or_validate(self, initialize_if_missing: bool) -> None:
        existed = self.database_path.exists() and self.database_path.stat().st_size > 0
        if not existed and not initialize_if_missing:
            raise RepositoryUnavailableError("episode evidence initialization is required")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                tables = self._table_names(connection)
                if not tables:
                    self._create_schema(connection)
                    self._validate_schema(connection, EVIDENCE_SCHEMA_VERSION)
                elif tables == self._TABLES - {"v5_episode_production_records"}:
                    self._validate_schema(connection, 1)
                    preserved_rows = self._preserved_v1_rows(connection)
                    self._migrate_v1_to_v2(connection)
                    self._validate_schema(connection, EVIDENCE_SCHEMA_VERSION)
                    if self._preserved_v1_rows(connection) != preserved_rows:
                        raise RepositoryUnavailableError(
                            "episode evidence migration changed accepted rows"
                        )
                elif tables == self._TABLES:
                    self._validate_schema(connection, EVIDENCE_SCHEMA_VERSION)
                else:
                    raise RepositoryUnavailableError(
                        "episode evidence schema is unsupported"
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode evidence database is unavailable") from exc
        finally:
            connection.close()

    @staticmethod
    def _decode_gate(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        facts = connection.execute(
            "SELECT fact_kind,fact_ref,fact_version,payload_json,payload_digest "
            "FROM v5_episode_production_facts WHERE workspace_ref=? "
            "AND production_run_ref=? AND gate_name=? ORDER BY fact_kind",
            (row["workspace_ref"], row["production_run_ref"], row["gate_name"]),
        ).fetchall()
        decoded_facts: list[dict[str, Any]] = []
        try:
            for fact in facts:
                payload = json.loads(fact["payload_json"])
                if not isinstance(payload, dict):
                    raise ValueError("fact payload must be an object")
                decoded_facts.append(
                    {
                        "factKind": fact["fact_kind"],
                        "factRef": fact["fact_ref"],
                        "factVersion": fact["fact_version"],
                        "payload": payload,
                        "payloadDigest": fact["payload_digest"],
                    }
                )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RepositoryUnavailableError(
                "episode evidence payload is invalid"
            ) from exc
        value = {
            "workspaceRef": row["workspace_ref"],
            "productionRunRef": row["production_run_ref"],
            "gateName": row["gate_name"],
            "idempotencyKey": row["idempotency_key"],
            "rootPayloadDigest": row["root_payload_digest"],
            "requestDigest": row["request_digest"],
            "fromState": row["from_state"],
            "toState": row["to_state"],
            "createdAt": row["created_at"],
            "facts": decoded_facts,
        }
        _gate_from_mapping(value)
        return value

    def current_state(self, workspace_ref: str, run_ref: str) -> str:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT to_state FROM v5_episode_production_transitions "
                "WHERE workspace_ref=? AND production_run_ref=? ORDER BY sequence DESC LIMIT 1",
                (workspace_ref, run_ref),
            ).fetchone()
            return ROOTS_READY if row is None else str(row["to_state"])
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode evidence read failed") from exc
        finally:
            connection.close()

    def get_gate(
        self, workspace_ref: str, run_ref: str, gate_name: str
    ) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_episode_production_gates WHERE workspace_ref=? "
                "AND production_run_ref=? AND gate_name=?",
                (workspace_ref, run_ref, gate_name),
            ).fetchone()
            return None if row is None else self._decode_gate(connection, row)
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode evidence read failed") from exc
        finally:
            connection.close()

    def list_gates(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT g.* FROM v5_episode_production_gates g "
                "JOIN v5_episode_production_transitions t USING "
                "(workspace_ref,production_run_ref,gate_name) "
                "WHERE g.workspace_ref=? AND g.production_run_ref=? ORDER BY t.sequence",
                (workspace_ref, run_ref),
            ).fetchall()
            return [self._decode_gate(connection, row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode evidence read failed") from exc
        finally:
            connection.close()

    def append_gate(self, gate: GateAppend) -> tuple[dict[str, Any], bool]:
        _validate_gate(gate)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = connection.execute(
                "SELECT * FROM v5_episode_production_gates WHERE workspace_ref=? "
                "AND production_run_ref=? AND idempotency_key=?",
                (gate.workspaceRef, gate.productionRunRef, gate.idempotencyKey),
            ).fetchone()
            if replay is not None:
                if replay["gate_name"] != gate.gateName:
                    raise IdempotencyConflictError(
                        "gate idempotency key belongs to another gate"
                    )
                if replay["request_digest"] != gate.requestDigest:
                    raise IdempotencyConflictError("gate idempotency content changed")
                result = self._decode_gate(connection, replay)
                connection.rollback()
                return result, True
            current = connection.execute(
                "SELECT sequence,to_state FROM v5_episode_production_transitions "
                "WHERE workspace_ref=? AND production_run_ref=? ORDER BY sequence DESC LIMIT 1",
                (gate.workspaceRef, gate.productionRunRef),
            ).fetchone()
            current_state = ROOTS_READY if current is None else str(current["to_state"])
            if current_state != gate.fromState:
                raise InvalidStateTransitionError("production run state changed")
            connection.execute(
                "INSERT INTO v5_episode_production_gates VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    gate.workspaceRef, gate.productionRunRef, gate.gateName,
                    gate.idempotencyKey, gate.rootPayloadDigest, gate.requestDigest,
                    gate.fromState, gate.toState, gate.createdAt,
                ),
            )
            for fact in gate.facts:
                connection.execute(
                    "INSERT INTO v5_episode_production_facts VALUES (?,?,?,?,?,?,?,?)",
                    (
                        gate.workspaceRef, gate.productionRunRef, gate.gateName,
                        fact.factKind, fact.factRef, fact.factVersion,
                        json.dumps(
                            fact.payload, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False,
                        ),
                        fact.payloadDigest,
                    ),
                )
            sequence = 1 if current is None else int(current["sequence"]) + 1
            evidence_digest = gate.requestDigest
            connection.execute(
                "INSERT INTO v5_episode_production_transitions VALUES (?,?,?,?,?,?,?,?)",
                (
                    gate.workspaceRef, gate.productionRunRef, sequence, gate.gateName,
                    gate.fromState, gate.toState, evidence_digest, gate.createdAt,
                ),
            )
            stored = connection.execute(
                "SELECT * FROM v5_episode_production_gates WHERE workspace_ref=? "
                "AND production_run_ref=? AND gate_name=?",
                (gate.workspaceRef, gate.productionRunRef, gate.gateName),
            ).fetchone()
            if stored is None:
                raise RepositoryUnavailableError("stored gate could not be read")
            result = self._decode_gate(connection, stored)
            connection.commit()
            return result, False
        except EpisodeProductionError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise InvalidStateTransitionError("episode evidence constraint failed") from exc
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError("episode evidence write failed") from exc
        finally:
            connection.close()

    @staticmethod
    def _decode_record(row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                raise ValueError("record payload must be an object")
            record = EvidenceRecord(
                workspaceRef=row["workspace_ref"],
                productionRunRef=row["production_run_ref"],
                recordKind=row["record_kind"],
                recordRef=row["record_ref"],
                recordVersion=row["record_version"],
                idempotencyKey=row["idempotency_key"],
                requestDigest=row["request_digest"],
                createdAt=row["created_at"],
                payload=payload,
                payloadDigest=row["payload_digest"],
            )
            _validate_record(record)
            return _record_mapping(record)
        except (json.JSONDecodeError, TypeError, ValueError, EpisodeProductionError) as exc:
            raise RepositoryUnavailableError(
                "episode evidence record verification failed"
            ) from exc

    def get_record(
        self, workspace_ref: str, run_ref: str, record_ref: str, record_version: int
    ) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_episode_production_records WHERE workspace_ref=? "
                "AND production_run_ref=? AND record_ref=? AND record_version=?",
                (workspace_ref, run_ref, record_ref, record_version),
            ).fetchone()
            return None if row is None else self._decode_record(row)
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode evidence record read failed") from exc
        finally:
            connection.close()

    def list_records(
        self, workspace_ref: str, run_ref: str, *, record_kind: str | None = None
    ) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            query = (
                "SELECT * FROM v5_episode_production_records WHERE workspace_ref=? "
                "AND production_run_ref=?"
            )
            parameters: list[Any] = [workspace_ref, run_ref]
            if record_kind is not None:
                query += " AND record_kind=?"
                parameters.append(record_kind)
            query += " ORDER BY sequence"
            rows = connection.execute(query, tuple(parameters)).fetchall()
            return [self._decode_record(row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode evidence record read failed") from exc
        finally:
            connection.close()

    def append_record(self, record: EvidenceRecord) -> tuple[dict[str, Any], bool]:
        stored, replayed = self.append_records((record,))
        return stored[0], replayed

    def append_records(
        self,
        records: Sequence[EvidenceRecord],
        *,
        expected_record_journal_head: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not records:
            raise EpisodeProductionError("record batch is empty")
        for record in records:
            _validate_record(record)
        scope = {(item.workspaceRef, item.productionRunRef) for item in records}
        identities = {(item.recordRef, item.recordVersion) for item in records}
        idempotency = {item.idempotencyKey for item in records}
        if len(scope) != 1 or len(identities) != len(records) or len(idempotency) != len(records):
            raise EpisodeProductionError("record batch is invalid")
        expected_head = _optional_record_journal_head(
            expected_record_journal_head
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            workspace_ref, run_ref = next(iter(scope))
            current_head = self._record_journal_head_in_connection(
                connection, workspace_ref, run_ref
            )
            replays: list[sqlite3.Row] = []
            new_count = 0
            for record in records:
                replay = connection.execute(
                    "SELECT * FROM v5_episode_production_records WHERE workspace_ref=? "
                    "AND production_run_ref=? AND idempotency_key=?",
                    (record.workspaceRef, record.productionRunRef, record.idempotencyKey),
                ).fetchone()
                if replay is None:
                    existing_identity = connection.execute(
                        "SELECT 1 FROM v5_episode_production_records WHERE workspace_ref=? "
                        "AND production_run_ref=? AND record_ref=? AND record_version=?",
                        (
                            record.workspaceRef,
                            record.productionRunRef,
                            record.recordRef,
                            record.recordVersion,
                        ),
                    ).fetchone()
                    if existing_identity is not None:
                        raise IdempotencyConflictError(
                            "record version was already recorded"
                        )
                    new_count += 1
                    continue
                if (
                    replay["record_ref"] != record.recordRef
                    or replay["record_version"] != record.recordVersion
                ):
                    raise IdempotencyConflictError(
                        "record idempotency key belongs to another record"
                    )
                if replay["request_digest"] != record.requestDigest:
                    raise IdempotencyConflictError("record idempotency content changed")
                replays.append(replay)
            if replays and new_count:
                raise IdempotencyConflictError("record batch is partially present")
            if replays:
                result = [self._decode_record(item) for item in replays]
                connection.rollback()
                return result, True
            if expected_head is not None and current_head != expected_head:
                raise StaleInputError("record journal head changed")
            current = connection.execute(
                "SELECT MAX(sequence) FROM v5_episode_production_records "
                "WHERE workspace_ref=? AND production_run_ref=?",
                (records[0].workspaceRef, records[0].productionRunRef),
            ).fetchone()[0]
            sequence = 1 if current is None else int(current) + 1
            result: list[dict[str, Any]] = []
            for offset, record in enumerate(records):
                item_sequence = sequence + offset
                connection.execute(
                    "INSERT INTO v5_episode_production_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        record.workspaceRef,
                        record.productionRunRef,
                        item_sequence,
                        record.recordKind,
                        record.recordRef,
                        record.recordVersion,
                        record.idempotencyKey,
                        record.requestDigest,
                        json.dumps(
                            record.payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                        record.payloadDigest,
                        record.createdAt,
                    ),
                )
                stored = connection.execute(
                    "SELECT * FROM v5_episode_production_records WHERE workspace_ref=? "
                    "AND production_run_ref=? AND sequence=?",
                    (record.workspaceRef, record.productionRunRef, item_sequence),
                ).fetchone()
                if stored is None:
                    raise RepositoryUnavailableError("stored record could not be read")
                result.append(self._decode_record(stored))
            connection.commit()
            return result, False
        except EpisodeProductionError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise IdempotencyConflictError("episode evidence record constraint failed") from exc
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError("episode evidence record write failed") from exc
        finally:
            connection.close()

    @classmethod
    def _record_journal_head_in_connection(
        cls,
        connection: sqlite3.Connection,
        workspace_ref: str,
        run_ref: str,
    ) -> str:
        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM v5_episode_production_records "
                "WHERE workspace_ref=? AND production_run_ref=?",
                (workspace_ref, run_ref),
            ).fetchone()[0]
        )
        latest = connection.execute(
            "SELECT * FROM v5_episode_production_records WHERE workspace_ref=? "
            "AND production_run_ref=? ORDER BY sequence DESC LIMIT 1",
            (workspace_ref, run_ref),
        ).fetchone()
        if latest is None:
            return _record_journal_head_value(
                workspace_ref,
                run_ref,
                record_count=count,
                latest_sequence=None,
                latest_record_ref=None,
                latest_record_version=None,
                latest_payload_digest=None,
            )
        decoded = cls._decode_record(latest)
        return _record_journal_head_value(
            workspace_ref,
            run_ref,
            record_count=count,
            latest_sequence=int(latest["sequence"]),
            latest_record_ref=decoded["recordRef"],
            latest_record_version=decoded["recordVersion"],
            latest_payload_digest=decoded["payloadDigest"],
        )

    def record_journal_head(self, workspace_ref: str, run_ref: str) -> str:
        _required_ref(workspace_ref, "workspaceRef")
        _required_ref(run_ref, "productionRunRef")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            head = self._record_journal_head_in_connection(
                connection, workspace_ref, run_ref
            )
            connection.rollback()
            return head
        except EpisodeProductionError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError(
                "episode evidence record journal read failed"
            ) from exc
        finally:
            connection.close()

    def append_records_and_gate(
        self,
        records: Sequence[EvidenceRecord],
        gate: GateAppend,
        *,
        expected_record_journal_head: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
        """Commit an admission record set and its state transition together."""

        if not records:
            raise EpisodeProductionError("record batch is empty")
        _validate_gate(gate)
        for record in records:
            _validate_record(record)
        expected_head = _optional_record_journal_head(
            expected_record_journal_head
        )
        scope = {(item.workspaceRef, item.productionRunRef) for item in records}
        identities = {(item.recordRef, item.recordVersion) for item in records}
        idempotency = {item.idempotencyKey for item in records}
        if (
            scope != {(gate.workspaceRef, gate.productionRunRef)}
            or len(identities) != len(records)
            or len(idempotency) != len(records)
        ):
            raise EpisodeProductionError("record and gate batch is invalid")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_head = self._record_journal_head_in_connection(
                connection, gate.workspaceRef, gate.productionRunRef
            )
            gate_replay = connection.execute(
                "SELECT * FROM v5_episode_production_gates WHERE workspace_ref=? "
                "AND production_run_ref=? AND idempotency_key=?",
                (gate.workspaceRef, gate.productionRunRef, gate.idempotencyKey),
            ).fetchone()
            if gate_replay is not None and (
                gate_replay["gate_name"] != gate.gateName
                or gate_replay["request_digest"] != gate.requestDigest
            ):
                raise IdempotencyConflictError("gate idempotency content changed")

            record_replays: list[sqlite3.Row] = []
            for record in records:
                replay = connection.execute(
                    "SELECT * FROM v5_episode_production_records WHERE workspace_ref=? "
                    "AND production_run_ref=? AND idempotency_key=?",
                    (record.workspaceRef, record.productionRunRef, record.idempotencyKey),
                ).fetchone()
                if replay is None:
                    existing_identity = connection.execute(
                        "SELECT 1 FROM v5_episode_production_records WHERE workspace_ref=? "
                        "AND production_run_ref=? AND record_ref=? AND record_version=?",
                        (
                            record.workspaceRef,
                            record.productionRunRef,
                            record.recordRef,
                            record.recordVersion,
                        ),
                    ).fetchone()
                    if existing_identity is not None:
                        raise IdempotencyConflictError(
                            "record version was already recorded"
                        )
                    continue
                if (
                    replay["record_ref"] != record.recordRef
                    or replay["record_version"] != record.recordVersion
                    or replay["request_digest"] != record.requestDigest
                ):
                    raise IdempotencyConflictError(
                        "record idempotency content changed"
                    )
                record_replays.append(replay)

            records_replayed = len(record_replays) == len(records)
            if record_replays and not records_replayed:
                raise IdempotencyConflictError("record batch is partially present")
            if (gate_replay is not None) != records_replayed:
                raise IdempotencyConflictError(
                    "atomic record and gate batch is partially present"
                )
            if gate_replay is not None:
                stored_gate = self._decode_gate(connection, gate_replay)
                stored_records = [
                    self._decode_record(row) for row in record_replays
                ]
                connection.rollback()
                return stored_records, stored_gate, True

            if expected_head is not None and current_head != expected_head:
                raise StaleInputError("record journal head changed")

            existing_gate = connection.execute(
                "SELECT 1 FROM v5_episode_production_gates WHERE workspace_ref=? "
                "AND production_run_ref=? AND gate_name=?",
                (gate.workspaceRef, gate.productionRunRef, gate.gateName),
            ).fetchone()
            if existing_gate is not None:
                raise InvalidStateTransitionError("gate was already recorded")
            transition = connection.execute(
                "SELECT sequence,to_state FROM v5_episode_production_transitions "
                "WHERE workspace_ref=? AND production_run_ref=? "
                "ORDER BY sequence DESC LIMIT 1",
                (gate.workspaceRef, gate.productionRunRef),
            ).fetchone()
            current_state = (
                ROOTS_READY if transition is None else str(transition["to_state"])
            )
            if current_state != gate.fromState:
                raise InvalidStateTransitionError("production run state changed")

            current_record_sequence = connection.execute(
                "SELECT MAX(sequence) FROM v5_episode_production_records "
                "WHERE workspace_ref=? AND production_run_ref=?",
                (gate.workspaceRef, gate.productionRunRef),
            ).fetchone()[0]
            record_sequence = (
                1 if current_record_sequence is None else int(current_record_sequence) + 1
            )
            stored_records: list[dict[str, Any]] = []
            for offset, record in enumerate(records):
                sequence = record_sequence + offset
                connection.execute(
                    "INSERT INTO v5_episode_production_records "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        record.workspaceRef,
                        record.productionRunRef,
                        sequence,
                        record.recordKind,
                        record.recordRef,
                        record.recordVersion,
                        record.idempotencyKey,
                        record.requestDigest,
                        json.dumps(
                            record.payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                        record.payloadDigest,
                        record.createdAt,
                    ),
                )
                stored = connection.execute(
                    "SELECT * FROM v5_episode_production_records "
                    "WHERE workspace_ref=? AND production_run_ref=? AND sequence=?",
                    (record.workspaceRef, record.productionRunRef, sequence),
                ).fetchone()
                if stored is None:
                    raise RepositoryUnavailableError(
                        "stored record could not be read"
                    )
                stored_records.append(self._decode_record(stored))

            connection.execute(
                "INSERT INTO v5_episode_production_gates VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    gate.workspaceRef,
                    gate.productionRunRef,
                    gate.gateName,
                    gate.idempotencyKey,
                    gate.rootPayloadDigest,
                    gate.requestDigest,
                    gate.fromState,
                    gate.toState,
                    gate.createdAt,
                ),
            )
            for fact in gate.facts:
                connection.execute(
                    "INSERT INTO v5_episode_production_facts VALUES (?,?,?,?,?,?,?,?)",
                    (
                        gate.workspaceRef,
                        gate.productionRunRef,
                        gate.gateName,
                        fact.factKind,
                        fact.factRef,
                        fact.factVersion,
                        json.dumps(
                            fact.payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                        fact.payloadDigest,
                    ),
                )
            transition_sequence = (
                1 if transition is None else int(transition["sequence"]) + 1
            )
            connection.execute(
                "INSERT INTO v5_episode_production_transitions "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    gate.workspaceRef,
                    gate.productionRunRef,
                    transition_sequence,
                    gate.gateName,
                    gate.fromState,
                    gate.toState,
                    gate.requestDigest,
                    gate.createdAt,
                ),
            )
            stored_gate_row = connection.execute(
                "SELECT * FROM v5_episode_production_gates WHERE workspace_ref=? "
                "AND production_run_ref=? AND gate_name=?",
                (gate.workspaceRef, gate.productionRunRef, gate.gateName),
            ).fetchone()
            if stored_gate_row is None:
                raise RepositoryUnavailableError("stored gate could not be read")
            stored_gate = self._decode_gate(connection, stored_gate_row)
            connection.commit()
            return stored_records, stored_gate, False
        except EpisodeProductionError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise IdempotencyConflictError(
                "atomic episode evidence constraint failed"
            ) from exc
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError(
                "atomic episode evidence write failed"
            ) from exc
        finally:
            connection.close()
