"""Authoritative K2 EpisodeProductionRun root and frozen manifest."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4


RUN_SCHEMA_VERSION = "v5.episode-production-run.v1"
MANIFEST_SCHEMA_VERSION = "k2.golden-episode.manifest.v1"
MANIFEST_SCHEMA_VERSION_V2 = "k2.golden-episode.manifest.v2"
OUTPUT_PROFILE_SCHEMA_VERSION_V2 = "k2.episode-output-profile.v2"
UPSTREAM_SCHEMA_VERSION = "v5.episode-production-upstream.v1"
ROOTS_READY = "ROOTS_READY"
LOCAL_EVIDENCE = "LOCAL_EVIDENCE"
PORTRAIT_ASPECT_RATIOS = frozenset({"9:16", "portrait"})
VISIBLE_IDENTITY_BINDING_MODES = frozenset({"BODY_ONLY", "FACE_LOCK"})
VISIBLE_IDENTITY_MODES = frozenset({"NONE", "BODY_ONLY", "FACE_LOCK", "MIXED"})
DIALOGUE_SYNC_MODES = frozenset(
    {"NONE", "OFF_CAMERA_OR_NON_VISIBLE_MOUTH", "VERIFIED_LIP_SYNC"}
)
DIALOGUE_SOURCE_MODES = frozenset({"NARRATION", "DIALOGUE", "SFX_OR_SILENCE"})
# Closed set used by every EP01-03 row in the repository-reviewed K2-002
# v1.4 repository-reviewed rebase candidate package.
K2_002_EDITORIAL_SHOT_SIZE_CODES = frozenset({"ECU", "CU", "MCU", "MS", "WS"})
CONTROLLED_EXTENSION_ALGORITHM_REF = "controlled-horizontal-edge-extension-v1"
CONTROLLED_EXTENSION_ALGORITHM = {
    "schemaVersion": "k2.controlled-extension-algorithm.v1",
    "controlledExtensionAlgorithmRef": CONTROLLED_EXTENSION_ALGORITHM_REF,
    "sourceWidth": 704,
    "targetWidth": 720,
    "leftExtensionPixels": 8,
    "rightExtensionPixels": 8,
    "cropAllowed": False,
    "stretchAllowed": False,
}
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_IDEMPOTENCY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class EpisodeProductionError(ValueError):
    code = "invalid_request"


class RecordNotFoundError(EpisodeProductionError):
    code = "not_found"


class ScopeMismatchError(EpisodeProductionError):
    code = "scope_mismatch"


class UpstreamNotReadyError(EpisodeProductionError):
    code = "upstream_not_confirmed"


class ExecutionNotAuthorizedError(EpisodeProductionError):
    code = "execution_not_authorized"


class IdempotencyConflictError(EpisodeProductionError):
    code = "idempotency_conflict"


class StaleInputError(EpisodeProductionError):
    code = "stale_input"


class RepositoryUnavailableError(EpisodeProductionError):
    code = "episode_production_unavailable"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not _REF.fullmatch(value):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _idempotency_key(value: Any) -> str:
    if not isinstance(value, str) or value != value.strip() or not _IDEMPOTENCY.fullmatch(value):
        raise EpisodeProductionError("idempotencyKey is invalid")
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        loaded = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EpisodeProductionError("value is not canonical JSON") from exc
    if not isinstance(loaded, dict):
        raise EpisodeProductionError("value must be an object")
    return raw


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _positive_int(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EpisodeProductionError(f"{field} is invalid")
    if value < 1 or value > maximum:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _duration_frames(value: Any, frame_rate: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EpisodeProductionError(f"{field} is invalid")
    try:
        frames = Decimal(str(value)) * Decimal(frame_rate)
    except (InvalidOperation, ValueError):
        raise EpisodeProductionError(f"{field} is invalid") from None
    integral = frames.to_integral_value()
    if frames != integral or integral <= 0:
        raise EpisodeProductionError(f"{field} must align to whole frames")
    return int(integral)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _editorial_shot_size(value: Any, field: str) -> str:
    normalized = _required_text(value, field)
    if normalized not in K2_002_EDITORIAL_SHOT_SIZE_CODES:
        raise EpisodeProductionError(f"{field} is not a K2-002 editorial shot size")
    return normalized


def _postprocess_requirements(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise EpisodeProductionError(f"{field} is invalid")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(item, Mapping) or set(item) != {
            "requirementKey", "type", "inputAssetRequirementKeys", "status"
        }:
            raise EpisodeProductionError(f"{item_field} is invalid")
        requirement_key = _required_ref(
            item.get("requirementKey"), f"{item_field}.requirementKey"
        )
        requirement_type = _required_ref(item.get("type"), f"{item_field}.type")
        raw_input_keys = item.get("inputAssetRequirementKeys")
        if (
            not isinstance(raw_input_keys, list)
            or not raw_input_keys
            or not all(isinstance(key, str) for key in raw_input_keys)
            or len(raw_input_keys) != len(set(raw_input_keys))
        ):
            raise EpisodeProductionError(f"{item_field} is invalid")
        input_keys = [
            _required_ref(key, f"{item_field}.inputAssetRequirementKeys")
            for key in raw_input_keys
        ]
        if item.get("status") != "NOT_READY" or requirement_key in seen:
            raise EpisodeProductionError(f"{item_field} is invalid")
        seen.add(requirement_key)
        result.append(
            {
                "requirementKey": requirement_key,
                "type": requirement_type,
                "inputAssetRequirementKeys": input_keys,
                "status": "NOT_READY",
            }
        )
    return result


def _dialogue_requirement(
    value: Any,
    field: str,
    *,
    scene_characters: list[str],
    visible_identity_bindings: list[dict[str, str]],
    dialogue_sync_mode: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "speaker", "text", "sourceMode"
    }:
        raise EpisodeProductionError(f"{field} is invalid")
    source_mode = value.get("sourceMode")
    if source_mode not in DIALOGUE_SOURCE_MODES:
        raise EpisodeProductionError(f"{field}.sourceMode is invalid")
    speaker = value.get("speaker")
    text = value.get("text")
    if speaker is not None and (
        not isinstance(speaker, str) or speaker != speaker.strip() or not speaker
    ):
        raise EpisodeProductionError(f"{field}.speaker is invalid")
    if (
        not isinstance(text, str)
        or text != text.strip()
        or not text
    ):
        raise EpisodeProductionError(f"{field}.text is invalid")
    if source_mode == "DIALOGUE":
        if speaker is None or speaker not in scene_characters:
            raise EpisodeProductionError(f"{field}.speaker is unresolved")
        if dialogue_sync_mode == "NONE":
            raise EpisodeProductionError(f"{field} requires a dialogue sync mode")
        if dialogue_sync_mode == "VERIFIED_LIP_SYNC" and (
            speaker
            not in {
                item["characterName"]
                for item in visible_identity_bindings
                if item["bindingMode"] == "FACE_LOCK"
            }
        ):
            raise EpisodeProductionError(
                f"{field} verified lip sync speaker is not face locked"
            )
    elif source_mode == "NARRATION":
        if (
            speaker is None
            or speaker not in scene_characters
            or dialogue_sync_mode != "OFF_CAMERA_OR_NON_VISIBLE_MOUTH"
        ):
            raise EpisodeProductionError(f"{field} narration sync is invalid")
    else:
        if speaker is not None or dialogue_sync_mode != "NONE":
            raise EpisodeProductionError(f"{field} SFX/silence sync is invalid")
    return {
        "speaker": speaker,
        "text": text,
        "sourceMode": source_mode,
    }


def _output_profile_v2(*, portrait: bool) -> dict[str, Any]:
    if not portrait:
        return {
            "schemaVersion": OUTPUT_PROFILE_SCHEMA_VERSION_V2,
            "orientation": "LANDSCAPE",
            "targetAspectRatio": "16:9",
            "width": 1280,
            "height": 720,
            "aspectRatio": "16:9",
            "frameRate": 24,
            "container": "mp4",
            "generationCanvas": {
                "width": 1280, "height": 720, "aspectRatio": "16:9"
            },
            "editMaster": {
                "width": 1280, "height": 720, "aspectRatio": "16:9"
            },
            "releaseMaster": {
                "width": 1920, "height": 1080, "aspectRatio": "16:9"
            },
            "controlledExtensionAlgorithmRef": None,
            "controlledExtensionAlgorithmDigest": None,
            "controlledExtensionAlgorithm": None,
        }
    algorithm = deepcopy(CONTROLLED_EXTENSION_ALGORITHM)
    return {
        "schemaVersion": OUTPUT_PROFILE_SCHEMA_VERSION_V2,
        "orientation": "PORTRAIT",
        "targetAspectRatio": "9:16",
        # Compatibility aliases identify the model-generation canvas.  The exact
        # 9:16 edit and release profiles remain separate authoritative targets.
        "width": 704,
        "height": 1280,
        "aspectRatio": "11:20",
        "frameRate": 24,
        "container": "mp4",
        "generationCanvas": {
            "width": 704, "height": 1280, "aspectRatio": "11:20"
        },
        "editMaster": {
            "width": 720, "height": 1280, "aspectRatio": "9:16"
        },
        "releaseMaster": {
            "width": 1080, "height": 1920, "aspectRatio": "9:16"
        },
        "controlledExtensionAlgorithmRef": CONTROLLED_EXTENSION_ALGORITHM_REF,
        "controlledExtensionAlgorithmDigest": _digest(algorithm),
        "controlledExtensionAlgorithm": algorithm,
    }


def _read_upstream(operation: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
    try:
        result = operation()
    except Exception as exc:
        status = getattr(exc, "status", None)
        code = str(getattr(exc, "code", ""))
        if status == 404 or code == "not_found":
            raise RecordNotFoundError("upstream record was not found") from None
        if status == 409 or code in {
            "script_not_confirmed",
            "series_plan_not_confirmed",
            "creative_plan_not_confirmed",
        }:
            raise UpstreamNotReadyError("upstream record is not confirmed") from None
        if status == 400 or code == "scope_mismatch":
            raise ScopeMismatchError("upstream scope does not match") from None
        raise
    if not isinstance(result, Mapping):
        raise RepositoryUnavailableError("upstream projection is unavailable")
    return result


@dataclass(frozen=True, slots=True)
class EpisodeProductionRunRecord:
    schemaVersion: str
    workspaceRef: str
    productionRunRef: str
    idempotencyKey: str
    contentProfileRef: str
    projectRef: str
    seriesRef: str
    episodeRef: str
    seriesPlanRef: str
    seriesPlanVersionRef: str
    episodePlanItemRef: str
    scriptRef: str
    scriptVersionRef: str
    manifestJson: str
    upstreamSnapshotJson: str
    upstreamDigest: str
    payloadDigest: str
    state: str
    createdAt: str
    updatedAt: str
    version: int


class EpisodeProductionRepository(Protocol):
    def create(self, record: EpisodeProductionRunRecord) -> EpisodeProductionRunRecord: ...
    def get(self, workspace_ref: str, run_ref: str) -> EpisodeProductionRunRecord | None: ...
    def get_by_idempotency(
        self, workspace_ref: str, idempotency_key: str
    ) -> EpisodeProductionRunRecord | None: ...
    def list(self, workspace_ref: str) -> list[EpisodeProductionRunRecord]: ...


class InMemoryEpisodeProductionAdapter:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], EpisodeProductionRunRecord] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._lock = RLock()

    def create(self, record: EpisodeProductionRunRecord) -> EpisodeProductionRunRecord:
        with self._lock:
            key = (record.workspaceRef, record.productionRunRef)
            replay_key = (record.workspaceRef, record.idempotencyKey)
            if key in self._records or replay_key in self._idempotency:
                raise IdempotencyConflictError("EpisodeProductionRun already exists")
            self._records[key] = record
            self._idempotency[replay_key] = record.productionRunRef
            return record

    def get(self, workspace_ref: str, run_ref: str) -> EpisodeProductionRunRecord | None:
        with self._lock:
            return self._records.get((workspace_ref, run_ref))

    def get_by_idempotency(
        self, workspace_ref: str, idempotency_key: str
    ) -> EpisodeProductionRunRecord | None:
        with self._lock:
            run_ref = self._idempotency.get((workspace_ref, idempotency_key))
            return None if run_ref is None else self._records[(workspace_ref, run_ref)]

    def list(self, workspace_ref: str) -> list[EpisodeProductionRunRecord]:
        with self._lock:
            return sorted(
                (item for (scope, _), item in self._records.items() if scope == workspace_ref),
                key=lambda item: (item.createdAt, item.productionRunRef),
            )


class SqliteEpisodeProductionAdapter:
    """Dedicated additive local-evidence store; never mutates the lifecycle database."""

    _TABLES = {"v5_episode_production_schema", "v5_episode_production_runs"}

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
            "CREATE TABLE v5_episode_production_schema ("
            "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO v5_episode_production_schema VALUES "
            "('episode_production', 1)"
        )
        connection.execute(
            """CREATE TABLE v5_episode_production_runs (
            workspace_ref TEXT NOT NULL,
            production_run_ref TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            content_profile_ref TEXT NOT NULL,
            project_ref TEXT NOT NULL,
            series_ref TEXT NOT NULL,
            episode_ref TEXT NOT NULL,
            series_plan_ref TEXT NOT NULL,
            series_plan_version_ref TEXT NOT NULL,
            episode_plan_item_ref TEXT NOT NULL,
            script_ref TEXT NOT NULL,
            script_version_ref TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            upstream_snapshot_json TEXT NOT NULL,
            upstream_digest TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state = 'ROOTS_READY'),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version > 0),
            PRIMARY KEY(workspace_ref, production_run_ref),
            UNIQUE(workspace_ref, idempotency_key)
            )"""
        )
        connection.execute(
            "CREATE INDEX ix_episode_production_episode ON "
            "v5_episode_production_runs(workspace_ref, episode_ref)"
        )

    def _initialize_or_validate(self, initialize_if_missing: bool) -> None:
        existed = self.database_path.exists() and self.database_path.stat().st_size > 0
        if not existed and not initialize_if_missing:
            raise RepositoryUnavailableError("episode production initialization is required")
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
                raise RepositoryUnavailableError("episode production schema is unsupported")
            marker = connection.execute(
                "SELECT component,schema_version FROM v5_episode_production_schema"
            ).fetchall()
            if [tuple(row) for row in marker] != [("episode_production", 1)]:
                raise RepositoryUnavailableError("episode production marker is unsupported")
            columns = tuple(
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(v5_episode_production_runs)"
                )
            )
            expected = (
                "workspace_ref", "production_run_ref", "schema_version",
                "idempotency_key", "content_profile_ref", "project_ref",
                "series_ref", "episode_ref", "series_plan_ref",
                "series_plan_version_ref", "episode_plan_item_ref", "script_ref",
                "script_version_ref", "manifest_json", "upstream_snapshot_json",
                "upstream_digest", "payload_digest", "state", "created_at",
                "updated_at", "version",
            )
            if columns != expected:
                raise RepositoryUnavailableError("episode production columns are unsupported")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RepositoryUnavailableError("episode production integrity check failed")
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode production database is unavailable") from exc
        finally:
            connection.close()

    @staticmethod
    def _record(row: sqlite3.Row) -> EpisodeProductionRunRecord:
        return EpisodeProductionRunRecord(
            row["schema_version"], row["workspace_ref"], row["production_run_ref"],
            row["idempotency_key"], row["content_profile_ref"], row["project_ref"],
            row["series_ref"], row["episode_ref"], row["series_plan_ref"],
            row["series_plan_version_ref"], row["episode_plan_item_ref"],
            row["script_ref"], row["script_version_ref"], row["manifest_json"],
            row["upstream_snapshot_json"], row["upstream_digest"],
            row["payload_digest"], row["state"], row["created_at"],
            row["updated_at"], row["version"],
        )

    def create(self, record: EpisodeProductionRunRecord) -> EpisodeProductionRunRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO v5_episode_production_runs VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.workspaceRef, record.productionRunRef, record.schemaVersion,
                    record.idempotencyKey, record.contentProfileRef, record.projectRef,
                    record.seriesRef, record.episodeRef, record.seriesPlanRef,
                    record.seriesPlanVersionRef, record.episodePlanItemRef,
                    record.scriptRef, record.scriptVersionRef, record.manifestJson,
                    record.upstreamSnapshotJson, record.upstreamDigest,
                    record.payloadDigest, record.state, record.createdAt,
                    record.updatedAt, record.version,
                ),
            )
            connection.commit()
            return record
        except sqlite3.IntegrityError:
            connection.rollback()
            raise IdempotencyConflictError("EpisodeProductionRun already exists") from None
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError("episode production write failed") from exc
        finally:
            connection.close()

    def get(self, workspace_ref: str, run_ref: str) -> EpisodeProductionRunRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_episode_production_runs "
                "WHERE workspace_ref=? AND production_run_ref=?",
                (workspace_ref, run_ref),
            ).fetchone()
            return None if row is None else self._record(row)
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode production read failed") from exc
        finally:
            connection.close()

    def get_by_idempotency(
        self, workspace_ref: str, idempotency_key: str
    ) -> EpisodeProductionRunRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_episode_production_runs "
                "WHERE workspace_ref=? AND idempotency_key=?",
                (workspace_ref, idempotency_key),
            ).fetchone()
            return None if row is None else self._record(row)
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode production read failed") from exc
        finally:
            connection.close()

    def list(self, workspace_ref: str) -> list[EpisodeProductionRunRecord]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM v5_episode_production_runs WHERE workspace_ref=? "
                "ORDER BY created_at,production_run_ref",
                (workspace_ref,),
            ).fetchall()
            return [self._record(row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("episode production read failed") from exc
        finally:
            connection.close()


class EpisodeProductionService:
    def __init__(
        self,
        repository: EpisodeProductionRepository,
        *,
        project_reader: Any,
        series_reader: Any,
        planning_reader: Any,
        script_reader: Any,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.project_reader = project_reader
        self.series_reader = series_reader
        self.planning_reader = planning_reader
        self.script_reader = script_reader
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _mapping(record: EpisodeProductionRunRecord, *, replay: bool = False) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "productionRunRef": record.productionRunRef,
            "idempotencyKey": record.idempotencyKey,
            "contentProfileRef": record.contentProfileRef,
            "projectRef": record.projectRef,
            "seriesRef": record.seriesRef,
            "episodeRef": record.episodeRef,
            "seriesPlanRef": record.seriesPlanRef,
            "seriesPlanVersionRef": record.seriesPlanVersionRef,
            "episodePlanItemRef": record.episodePlanItemRef,
            "scriptRef": record.scriptRef,
            "scriptVersionRef": record.scriptVersionRef,
            "manifest": json.loads(record.manifestJson),
            "upstreamSnapshot": json.loads(record.upstreamSnapshotJson),
            "upstreamDigest": record.upstreamDigest,
            "payloadDigest": record.payloadDigest,
            "state": record.state,
            "createdAt": record.createdAt,
            "updatedAt": record.updatedAt,
            "version": record.version,
            "idempotentReplay": replay,
        }

    def _resolve(self, command: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        project_ref = _required_ref(command.get("projectRef"), "projectRef")
        series_ref = _required_ref(command.get("seriesRef"), "seriesRef")
        episode_ref = _required_ref(command.get("episodeRef"), "episodeRef")
        context = _read_upstream(
            lambda: self.project_reader.build_context(
                workspace, project_ref, series_ref, episode_ref
            )
        )
        project = context.get("project")
        series = context.get("series")
        episode = context.get("episode")
        if not all(isinstance(value, Mapping) for value in (project, series, episode)):
            raise RepositoryUnavailableError("project context is incomplete")
        if context.get("contentProfileRef") != project.get("contentProfileRef"):
            raise ScopeMismatchError("content profile scope is inconsistent")
        authoritative_series = _read_upstream(
            lambda: self.series_reader.get_series(workspace, series_ref)
        )
        authoritative_episode = _read_upstream(
            lambda: self.series_reader.get_episode(workspace, series_ref, episode_ref)
        )
        if (
            authoritative_series.get("seriesRef") != series.get("seriesRef")
            or authoritative_series.get("workspaceRef") != workspace
            or authoritative_episode.get("episodeRef") != episode.get("episodeRef")
            or authoritative_episode.get("seriesRef") != series_ref
            or authoritative_episode.get("workspaceRef") != workspace
        ):
            raise ScopeMismatchError("project and series authority projections disagree")
        if project.get("status") != "active" or series.get("status") != "active":
            raise UpstreamNotReadyError("project and series must be active")
        project_aspect_ratio = project.get("aspectRatio")
        if project_aspect_ratio not in {"16:9", *PORTRAIT_ASPECT_RATIOS}:
            raise UpstreamNotReadyError("K2 project output contract is unsupported")
        portrait = project_aspect_ratio in PORTRAIT_ASPECT_RATIOS

        planning = _read_upstream(
            lambda: self.planning_reader.get_workspace(workspace, project_ref, series_ref)
        )
        plan = planning.get("plan")
        versions = planning.get("versions")
        if not isinstance(plan, Mapping) or not isinstance(versions, list):
            raise UpstreamNotReadyError("confirmed Series Plan is required")
        confirmed_plan_version_ref = plan.get("confirmedSeriesPlanVersionRef")
        if plan.get("status") != "confirmed" or not isinstance(confirmed_plan_version_ref, str):
            raise UpstreamNotReadyError("confirmed Series Plan version is required")
        selected_plan = next(
            (
                item for item in versions
                if isinstance(item, Mapping)
                and item.get("seriesPlanVersionRef") == confirmed_plan_version_ref
            ),
            None,
        )
        if not isinstance(selected_plan, Mapping):
            raise UpstreamNotReadyError("confirmed Series Plan version is unavailable")
        bindings = selected_plan.get("episodePlanItemBindings")
        if not isinstance(bindings, list):
            raise UpstreamNotReadyError("confirmed Episode Plan binding is required")
        binding = next(
            (
                item for item in bindings
                if isinstance(item, Mapping) and item.get("episodeRef") == episode_ref
            ),
            None,
        )
        if not isinstance(binding, Mapping):
            raise UpstreamNotReadyError("Episode is not bound to the confirmed Series Plan")
        item_ref = _required_ref(binding.get("episodePlanItemRef"), "episodePlanItemRef")
        plan_items = selected_plan.get("episodePlanItems")
        if not isinstance(plan_items, list):
            raise RepositoryUnavailableError("Series Plan items are unavailable")
        plan_item = next(
            (
                item for item in plan_items
                if isinstance(item, Mapping) and item.get("episodePlanItemRef") == item_ref
            ),
            None,
        )
        if not isinstance(plan_item, Mapping):
            raise ScopeMismatchError("Episode Plan binding is inconsistent")
        if plan_item.get("episodeNumber") != episode.get("episodeNumber"):
            raise ScopeMismatchError("Episode Plan number is inconsistent")

        script_workspace = _read_upstream(
            lambda: self.script_reader.get_workspace(workspace, series_ref, episode_ref)
        )
        script = script_workspace.get("script")
        script_versions = script_workspace.get("versions")
        if not isinstance(script, Mapping) or not isinstance(script_versions, list):
            raise UpstreamNotReadyError("confirmed ScriptVersion is required")
        confirmed_script_ref = script.get("confirmedScriptVersionRef")
        if not isinstance(confirmed_script_ref, str):
            raise UpstreamNotReadyError("confirmed ScriptVersion is required")
        script_version = next(
            (
                item for item in script_versions
                if isinstance(item, Mapping)
                and item.get("scriptVersionRef") == confirmed_script_ref
            ),
            None,
        )
        if not isinstance(script_version, Mapping):
            raise UpstreamNotReadyError("confirmed ScriptVersion is unavailable")
        scenes = script_version.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise UpstreamNotReadyError("confirmed ScriptVersion has no scenes")

        characters = sorted(
            {
                name.strip()
                for scene in scenes
                if isinstance(scene, Mapping)
                for name in scene.get("characters", [])
                if isinstance(name, str) and name.strip()
            }
        )
        if len(characters) < 2:
            raise UpstreamNotReadyError("K2 requires at least two named characters")
        target_duration = script_version.get("targetDurationSec")
        if isinstance(target_duration, bool) or not isinstance(target_duration, (int, float)):
            raise RepositoryUnavailableError("confirmed duration is unavailable")
        if target_duration <= 0 or target_duration > 3600:
            raise UpstreamNotReadyError("confirmed duration is outside K2 limits")

        explicit_shot_budgets = command.get("shotBudgets")
        shots_value = command.get("shotsPerScene")
        normalized_shot_budgets: list[dict[str, Any]] | None = None
        if portrait and explicit_shot_budgets is None:
            raise EpisodeProductionError(
                "portrait K2 runs require explicit v2 shotBudgets"
            )
        if explicit_shot_budgets is not None and not portrait:
            raise EpisodeProductionError(
                "K2-002 v2 shotBudgets require the portrait output contract"
            )
        if explicit_shot_budgets is None:
            if not isinstance(shots_value, list) or len(shots_value) != len(scenes):
                raise EpisodeProductionError("shotsPerScene must match confirmed scenes")
            shots_per_scene = [
                _positive_int(value, f"shotsPerScene[{index}]", maximum=12)
                for index, value in enumerate(shots_value)
            ]
        else:
            if not isinstance(explicit_shot_budgets, list) or not explicit_shot_budgets:
                raise EpisodeProductionError("shotBudgets must not be empty")
            scenes_by_ref: dict[str, tuple[int, Mapping[str, Any]]] = {}
            for index, scene in enumerate(scenes):
                if not isinstance(scene, Mapping):
                    raise RepositoryUnavailableError("confirmed scene is invalid")
                scene_ref = _required_ref(
                    scene.get("scriptSceneRef"), f"scenes[{index}].scriptSceneRef"
                )
                if scene_ref in scenes_by_ref:
                    raise RepositoryUnavailableError("confirmed scene identity is ambiguous")
                scenes_by_ref[scene_ref] = (index, scene)
            normalized_shot_budgets = []
            counts = [0 for _ in scenes]
            frame_totals = [0 for _ in scenes]
            dialogue_by_scene: list[list[dict[str, Any]]] = [
                [] for _ in scenes
            ]
            narration_by_scene: list[list[str]] = [[] for _ in scenes]
            expected_sequence: list[tuple[int, int]] = []
            for index, item in enumerate(explicit_shot_budgets):
                field = f"shotBudgets[{index}]"
                if not isinstance(item, Mapping) or set(item) != {
                    "scriptSceneRef", "sceneOrder", "durationFrames",
                    "editorialShotSize",
                    "visibleIdentityBindings",
                    "actionBeat", "dialogueSyncMode", "dialogueRequirement",
                    "postprocessRequirements",
                }:
                    raise EpisodeProductionError(f"{field} is invalid")
                scene_ref = _required_ref(
                    item.get("scriptSceneRef"), f"{field}.scriptSceneRef"
                )
                scene_entry = scenes_by_ref.get(scene_ref)
                if scene_entry is None:
                    raise EpisodeProductionError(f"{field}.scriptSceneRef is unresolved")
                scene_index, scene = scene_entry
                scene_order = _positive_int(
                    item.get("sceneOrder"), f"{field}.sceneOrder", maximum=120
                )
                counts[scene_index] += 1
                if scene_order != counts[scene_index]:
                    raise EpisodeProductionError(
                        "shotBudgets scene order must be contiguous and script ordered"
                    )
                expected_sequence.append((scene_index, scene_order))
                if expected_sequence != sorted(expected_sequence):
                    raise EpisodeProductionError(
                        "shotBudgets must follow confirmed Script scene order"
                    )
                duration_frames = _positive_int(
                    item.get("durationFrames"), f"{field}.durationFrames", maximum=216000
                )
                frame_totals[scene_index] += duration_frames
                editorial_shot_size = _editorial_shot_size(
                    item.get("editorialShotSize"),
                    f"{field}.editorialShotSize",
                )
                raw_identity_bindings = item.get("visibleIdentityBindings")
                if not isinstance(raw_identity_bindings, list):
                    raise EpisodeProductionError(
                        f"{field}.visibleIdentityBindings is invalid"
                    )
                visible_identity_bindings: list[dict[str, str]] = []
                visible_names: set[str] = set()
                for binding_index, binding in enumerate(raw_identity_bindings):
                    binding_field = (
                        f"{field}.visibleIdentityBindings[{binding_index}]"
                    )
                    if not isinstance(binding, Mapping) or set(binding) != {
                        "characterName", "bindingMode"
                    }:
                        raise EpisodeProductionError(f"{binding_field} is invalid")
                    character_name = binding.get("characterName")
                    binding_mode = binding.get("bindingMode")
                    if (
                        not isinstance(character_name, str)
                        or character_name != character_name.strip()
                        or not character_name
                        or character_name in visible_names
                        or character_name not in scene.get("characters", [])
                        or binding_mode not in VISIBLE_IDENTITY_BINDING_MODES
                    ):
                        raise EpisodeProductionError(f"{binding_field} is invalid")
                    visible_names.add(character_name)
                    visible_identity_bindings.append(
                        {
                            "characterName": character_name,
                            "bindingMode": binding_mode,
                        }
                    )
                binding_modes = {
                    item["bindingMode"] for item in visible_identity_bindings
                }
                visible_mode = (
                    "NONE"
                    if not binding_modes
                    else (
                        next(iter(binding_modes))
                        if len(binding_modes) == 1
                        else "MIXED"
                    )
                )
                dialogue_sync_mode = item.get("dialogueSyncMode")
                if dialogue_sync_mode not in DIALOGUE_SYNC_MODES:
                    raise EpisodeProductionError(f"{field}.dialogueSyncMode is invalid")
                if dialogue_sync_mode == "VERIFIED_LIP_SYNC":
                    raise EpisodeProductionError(
                        f"{field}.dialogueSyncMode requires trusted lip-sync evidence"
                    )
                action_beat = _required_text(
                    item.get("actionBeat"), f"{field}.actionBeat"
                )
                dialogue_requirement = _dialogue_requirement(
                    item.get("dialogueRequirement"),
                    f"{field}.dialogueRequirement",
                    scene_characters=list(scene.get("characters", [])),
                    visible_identity_bindings=visible_identity_bindings,
                    dialogue_sync_mode=dialogue_sync_mode,
                )
                if dialogue_requirement["sourceMode"] == "DIALOGUE":
                    dialogue_by_scene[scene_index].append(dialogue_requirement)
                elif dialogue_requirement["sourceMode"] == "NARRATION":
                    narration_by_scene[scene_index].append(
                        dialogue_requirement["text"]
                    )
                postprocess_requirements = _postprocess_requirements(
                    item.get("postprocessRequirements"),
                    f"{field}.postprocessRequirements",
                )
                normalized_shot_budgets.append(
                    {
                        "scriptSceneRef": scene_ref,
                        "sceneOrder": scene_order,
                        "durationFrames": duration_frames,
                        "editorialShotSize": editorial_shot_size,
                        "visibleIdentityBindings": visible_identity_bindings,
                        "actionBeat": action_beat,
                        "dialogueSyncMode": dialogue_sync_mode,
                        "dialogueRequirement": dialogue_requirement,
                        "postprocessRequirements": postprocess_requirements,
                    }
                )
            if any(count < 1 or count > 12 for count in counts):
                raise EpisodeProductionError(
                    "shotBudgets must provide 1 to 12 shots for every Script scene"
                )
            for index, scene in enumerate(scenes):
                expected_frames = _duration_frames(
                    scene.get("estimatedDurationSec"),
                    24,
                    f"scenes[{index}].estimatedDurationSec",
                )
                if frame_totals[index] != expected_frames:
                    raise EpisodeProductionError(
                        f"shotBudgets for scenes[{index}] do not match its duration"
                    )
                expected_dialogue = []
                raw_dialogue = scene.get("dialogue")
                if not isinstance(raw_dialogue, list):
                    raise RepositoryUnavailableError(
                        f"scenes[{index}].dialogue is invalid"
                    )
                for line_index, line in enumerate(raw_dialogue):
                    if not isinstance(line, Mapping):
                        raise RepositoryUnavailableError(
                            f"scenes[{index}].dialogue[{line_index}] is invalid"
                        )
                    expected_dialogue.append(
                        {
                            "speaker": line.get("speaker"),
                            "text": line.get("text"),
                            "sourceMode": "DIALOGUE",
                        }
                    )
                raw_narration = scene.get("narration")
                if not isinstance(raw_narration, list) or not all(
                    isinstance(text, str) for text in raw_narration
                ):
                    raise RepositoryUnavailableError(
                        f"scenes[{index}].narration is invalid"
                    )
                if dialogue_by_scene[index] != expected_dialogue:
                    raise EpisodeProductionError(
                        f"shotBudgets for scenes[{index}] do not map Script dialogue exactly"
                    )
                if narration_by_scene[index] != raw_narration:
                    raise EpisodeProductionError(
                        f"shotBudgets for scenes[{index}] do not map Script narration exactly"
                    )
            if sum(frame_totals) != _duration_frames(
                target_duration, 24, "targetDurationSec"
            ):
                raise EpisodeProductionError(
                    "shotBudgets do not match the confirmed Script duration"
                )
            if shots_value is not None:
                if not isinstance(shots_value, list) or list(shots_value) != counts:
                    raise EpisodeProductionError(
                        "shotsPerScene does not match explicit shotBudgets"
                    )
            shots_per_scene = counts
        if sum(shots_per_scene) > 120:
            raise EpisodeProductionError("K2 shot budget exceeds 120")
        scene_budgets = []
        for index, (scene, shot_count) in enumerate(zip(scenes, shots_per_scene)):
            if not isinstance(scene, Mapping):
                raise RepositoryUnavailableError("confirmed scene is invalid")
            scene_budget = {
                    "scriptSceneRef": _required_ref(
                        scene.get("scriptSceneRef"), f"scenes[{index}].scriptSceneRef"
                    ),
                    "sceneNumber": _positive_int(
                        scene.get("sceneNumber"), f"scenes[{index}].sceneNumber", maximum=500
                    ),
                    "shotCount": shot_count,
                }
            if normalized_shot_budgets is not None:
                scene_budget["durationFrames"] = frame_totals[index]
            scene_budgets.append(scene_budget)
        manifest_schema = (
            MANIFEST_SCHEMA_VERSION_V2
            if portrait or normalized_shot_budgets is not None
            else MANIFEST_SCHEMA_VERSION
        )
        output = (
            _output_profile_v2(portrait=portrait)
            if manifest_schema == MANIFEST_SCHEMA_VERSION_V2
            else {
                "width": 1280,
                "height": 720,
                "frameRate": 24,
                "aspectRatio": "16:9",
                "container": "mp4",
            }
        )
        manifest = {
            "schemaVersion": manifest_schema,
            "executionMode": LOCAL_EVIDENCE,
            "title": str(episode.get("title") or "").strip(),
            "episodeNumber": episode.get("episodeNumber"),
            "targetDurationSec": target_duration,
            "expectedSceneCount": len(scenes),
            "expectedShotCount": sum(shots_per_scene),
            "requiredCharacterNames": characters,
            "sceneBudgets": scene_budgets,
            "output": output,
            "publicationAllowed": False,
        }
        if normalized_shot_budgets is not None:
            manifest["shotBudgets"] = normalized_shot_budgets
            manifest["shotPlanAuthorityState"] = (
                "LOCAL_STRUCTURAL_REPRESENTATION_ONLY"
            )
            manifest["shotPlanApprovalState"] = "NOT_VERIFIED"
            manifest["cameraContractState"] = "NOT_READY"
            manifest["dispatchAllowed"] = False
        upstream = {
            "schemaVersion": UPSTREAM_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "contentProfileRef": context.get("contentProfileRef"),
            "project": {"projectRef": project_ref, "version": project.get("version")},
            "series": {"seriesRef": series_ref, "version": series.get("version")},
            "episode": {
                "episodeRef": episode_ref,
                "version": episode.get("version"),
                "creativePlanRef": episode.get("creativePlanRef"),
            },
            "seriesPlan": {
                "seriesPlanRef": plan.get("seriesPlanRef"),
                "planVersion": plan.get("version"),
                "seriesPlanVersionRef": confirmed_plan_version_ref,
                "versionNumber": selected_plan.get("versionNumber"),
                "versionDigest": _digest(dict(selected_plan)),
                "episodePlanItemRef": item_ref,
            },
            "script": {
                "scriptRef": script.get("scriptRef"),
                "scriptVersion": script.get("version"),
                "scriptVersionRef": confirmed_script_ref,
                "versionNumber": script_version.get("versionNumber"),
                "versionDigest": _digest(dict(script_version)),
            },
        }
        return manifest, upstream

    def create_run(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping):
            raise EpisodeProductionError("command must be an object")
        base_fields = {
            "workspaceRef", "projectRef", "seriesRef", "episodeRef",
            "idempotencyKey",
        }
        allowed_contracts = {
            frozenset({*base_fields, "shotsPerScene"}),
            frozenset({*base_fields, "shotBudgets"}),
            frozenset({*base_fields, "shotsPerScene", "shotBudgets"}),
        }
        if frozenset(command) not in allowed_contracts:
            raise EpisodeProductionError("command fields do not match the K2 contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        key = _idempotency_key(command.get("idempotencyKey"))
        manifest, upstream = self._resolve(command)
        upstream_digest = _digest(upstream)
        payload = {
            "workspaceRef": workspace,
            "projectRef": command.get("projectRef"),
            "seriesRef": command.get("seriesRef"),
            "episodeRef": command.get("episodeRef"),
            "manifest": manifest,
            "upstreamDigest": upstream_digest,
        }
        payload_digest = _digest(payload)
        existing = self.repository.get_by_idempotency(workspace, key)
        if existing is not None:
            if existing.payloadDigest != payload_digest:
                raise IdempotencyConflictError("idempotency key has different content")
            return self._mapping(existing, replay=True)
        now = self._clock()
        record = EpisodeProductionRunRecord(
            RUN_SCHEMA_VERSION,
            workspace,
            _required_ref(self._ref_factory("episode-production-run"), "productionRunRef"),
            key,
            _required_ref(upstream.get("contentProfileRef"), "contentProfileRef"),
            _required_ref(command.get("projectRef"), "projectRef"),
            _required_ref(command.get("seriesRef"), "seriesRef"),
            _required_ref(command.get("episodeRef"), "episodeRef"),
            _required_ref(upstream["seriesPlan"].get("seriesPlanRef"), "seriesPlanRef"),
            _required_ref(
                upstream["seriesPlan"].get("seriesPlanVersionRef"),
                "seriesPlanVersionRef",
            ),
            _required_ref(
                upstream["seriesPlan"].get("episodePlanItemRef"),
                "episodePlanItemRef",
            ),
            _required_ref(upstream["script"].get("scriptRef"), "scriptRef"),
            _required_ref(
                upstream["script"].get("scriptVersionRef"), "scriptVersionRef"
            ),
            _canonical_json(manifest),
            _canonical_json(upstream),
            upstream_digest,
            payload_digest,
            ROOTS_READY,
            now,
            now,
            1,
        )
        try:
            stored = self.repository.create(record)
        except IdempotencyConflictError:
            replay = self.repository.get_by_idempotency(workspace, key)
            if replay is None or replay.payloadDigest != payload_digest:
                raise
            return self._mapping(replay, replay=True)
        return self._mapping(stored)

    def get_run(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        record = self.repository.get(
            workspace, _required_ref(run_ref, "productionRunRef")
        )
        if record is None:
            raise RecordNotFoundError("EpisodeProductionRun was not found")
        return self._mapping(record)

    def verify_run_current(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        current = self.get_run(workspace_ref, run_ref)
        manifest = current.get("manifest")
        budgets = manifest.get("sceneBudgets") if isinstance(manifest, Mapping) else None
        if not isinstance(budgets, list) or not budgets:
            raise RepositoryUnavailableError("stored K2 manifest is incomplete")
        command = {
            "workspaceRef": current["workspaceRef"],
            "projectRef": current["projectRef"],
            "seriesRef": current["seriesRef"],
            "episodeRef": current["episodeRef"],
            "idempotencyKey": current["idempotencyKey"],
        }
        shot_budgets = manifest.get("shotBudgets")
        if shot_budgets is None:
            command["shotsPerScene"] = [item.get("shotCount") for item in budgets]
        else:
            command["shotBudgets"] = deepcopy(shot_budgets)
        resolved_manifest, upstream = self._resolve(command)
        upstream_digest = _digest(upstream)
        payload_digest = _digest(
            {
                "workspaceRef": current["workspaceRef"],
                "projectRef": current["projectRef"],
                "seriesRef": current["seriesRef"],
                "episodeRef": current["episodeRef"],
                "manifest": resolved_manifest,
                "upstreamDigest": upstream_digest,
            }
        )
        if payload_digest != current["payloadDigest"]:
            raise StaleInputError("frozen K2 roots no longer match authoritative inputs")
        return current

    def list_runs(self, workspace_ref: str) -> list[dict[str, Any]]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        return [self._mapping(item) for item in self.repository.list(workspace)]
