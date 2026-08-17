"""Authoritative K2 EpisodeProductionRun root and frozen manifest."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from datetime import datetime, timezone
from uuid import uuid4


RUN_SCHEMA_VERSION = "v5.episode-production-run.v1"
MANIFEST_SCHEMA_VERSION = "k2.golden-episode.manifest.v1"
UPSTREAM_SCHEMA_VERSION = "v5.episode-production-upstream.v1"
ROOTS_READY = "ROOTS_READY"
LOCAL_EVIDENCE = "LOCAL_EVIDENCE"
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
        if project.get("aspectRatio") != "16:9":
            raise UpstreamNotReadyError("K2 requires the frozen 16:9 output contract")

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

        shots_value = command.get("shotsPerScene")
        if not isinstance(shots_value, list) or len(shots_value) != len(scenes):
            raise EpisodeProductionError("shotsPerScene must match confirmed scenes")
        shots_per_scene = [
            _positive_int(value, f"shotsPerScene[{index}]", maximum=12)
            for index, value in enumerate(shots_value)
        ]
        if sum(shots_per_scene) > 120:
            raise EpisodeProductionError("K2 shot budget exceeds 120")
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
        scene_budgets = []
        for index, (scene, shot_count) in enumerate(zip(scenes, shots_per_scene)):
            if not isinstance(scene, Mapping):
                raise RepositoryUnavailableError("confirmed scene is invalid")
            scene_budgets.append(
                {
                    "scriptSceneRef": _required_ref(
                        scene.get("scriptSceneRef"), f"scenes[{index}].scriptSceneRef"
                    ),
                    "sceneNumber": _positive_int(
                        scene.get("sceneNumber"), f"scenes[{index}].sceneNumber", maximum=500
                    ),
                    "shotCount": shot_count,
                }
            )
        manifest = {
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "executionMode": LOCAL_EVIDENCE,
            "title": str(episode.get("title") or "").strip(),
            "episodeNumber": episode.get("episodeNumber"),
            "targetDurationSec": target_duration,
            "expectedSceneCount": len(scenes),
            "expectedShotCount": sum(shots_per_scene),
            "requiredCharacterNames": characters,
            "sceneBudgets": scene_budgets,
            "output": {
                "width": 1280,
                "height": 720,
                "frameRate": 24,
                "aspectRatio": "16:9",
                "container": "mp4",
            },
            "publicationAllowed": False,
        }
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
        allowed = {
            "workspaceRef", "projectRef", "seriesRef", "episodeRef",
            "idempotencyKey", "shotsPerScene",
        }
        if set(command) != allowed:
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
            "shotsPerScene": [item.get("shotCount") for item in budgets],
        }
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
