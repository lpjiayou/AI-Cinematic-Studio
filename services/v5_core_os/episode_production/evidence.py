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
    _digest,
    _idempotency_key,
    _required_ref,
)


EVIDENCE_SCHEMA_VERSION = 1
ROOTS_READY = "ROOTS_READY"
K2_STATES = (
    ROOTS_READY,
    "AUTHORITY_READY",
    "SCRIPT_VALIDATED",
    "SHOTS_COMPILED",
    "ASSETS_READY",
    "MEDIA_READY",
    "PREVIEW_READY",
    "QC_READY",
    "APPROVAL_READY",
    "MASTER_READY",
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


class EpisodeProductionEvidenceRepository(Protocol):
    def current_state(self, workspace_ref: str, run_ref: str) -> str: ...
    def get_gate(self, workspace_ref: str, run_ref: str, gate_name: str) -> dict[str, Any] | None: ...
    def list_gates(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]: ...
    def append_gate(self, gate: GateAppend) -> tuple[dict[str, Any], bool]: ...


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


def _validate_gate(gate: GateAppend) -> None:
    _required_ref(gate.workspaceRef, "workspaceRef")
    _required_ref(gate.productionRunRef, "productionRunRef")
    _required_ref(gate.gateName, "gateName")
    _idempotency_key(gate.idempotencyKey)
    for field, value in (
        ("rootPayloadDigest", gate.rootPayloadDigest),
        ("requestDigest", gate.requestDigest),
    ):
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise EpisodeProductionError(f"{field} is invalid")
    if gate.fromState not in K2_STATES or gate.toState not in K2_STATES:
        raise InvalidStateTransitionError("unknown K2 state")
    if K2_STATES.index(gate.toState) != K2_STATES.index(gate.fromState) + 1:
        raise InvalidStateTransitionError("K2 states must advance exactly once")
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
            ordered = [
                gate
                for (scope, production, _), gate in self._gates.items()
                if scope == workspace_ref and production == run_ref
            ]
            ordered.sort(key=lambda item: K2_STATES.index(item.toState))
            return [_gate_mapping(item) for item in ordered]

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
            return _gate_mapping(gate), False


class SqliteEpisodeProductionEvidenceAdapter:
    """Dedicated additive local evidence DB; no accepted lifecycle schema is changed."""

    _TABLES = {
        "v5_episode_production_evidence_schema",
        "v5_episode_production_gates",
        "v5_episode_production_facts",
        "v5_episode_production_transitions",
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
            "('episode_production_evidence', 1)"
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

    def _initialize_or_validate(self, initialize_if_missing: bool) -> None:
        existed = self.database_path.exists() and self.database_path.stat().st_size > 0
        if not existed and not initialize_if_missing:
            raise RepositoryUnavailableError("episode evidence initialization is required")
        connection = self._connect()
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if not tables:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._create_schema(connection)
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                tables = set(self._TABLES)
            if tables != self._TABLES:
                raise RepositoryUnavailableError("episode evidence schema is unsupported")
            for table, expected in self._COLUMNS.items():
                actual = tuple(
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                )
                if actual != expected:
                    raise RepositoryUnavailableError(
                        "episode evidence columns are unsupported"
                    )
            marker = connection.execute(
                "SELECT component,schema_version FROM v5_episode_production_evidence_schema"
            ).fetchall()
            if [tuple(row) for row in marker] != [
                ("episode_production_evidence", EVIDENCE_SCHEMA_VERSION)
            ]:
                raise RepositoryUnavailableError("episode evidence marker is unsupported")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise RepositoryUnavailableError("episode evidence foreign keys are invalid")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RepositoryUnavailableError("episode evidence integrity check failed")
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
