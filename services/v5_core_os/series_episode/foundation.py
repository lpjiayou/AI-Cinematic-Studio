"""V5-owned Series/Episode service, repository port, and local adapters."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4


CONTENT_PROFILE_REF_SCHEMA_VERSION = "v5.content-profile-ref.v1"
SERIES_SCHEMA_VERSION = "v5.series.v1"
CONFIRMED_PLAN_SCHEMA_VERSION = "v5.confirmed-creative-plan.v1"
PLAN_BINDING_SCHEMA_VERSION = "v5.confirmed-creative-plan-binding.v1"
EPISODE_SCHEMA_VERSION = "v5.episode.v1"
SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION = "creator.script-studio.bootstrap-input.v1"
SQLITE_SCHEMA_VERSION = 1
AI_DIRECTOR_PLAN_SCHEMA_VERSION = "creator.ai-director.plan.v1"


class SeriesEpisodeError(ValueError):
    code = "invalid_request"


class RecordNotFoundError(SeriesEpisodeError):
    code = "not_found"


class DuplicateRecordError(SeriesEpisodeError):
    code = "duplicate_record"


class UnconfirmedPlanError(SeriesEpisodeError):
    code = "creative_plan_not_confirmed"


class ScopeMismatchError(SeriesEpisodeError):
    code = "scope_mismatch"


class LifecycleUnavailableError(SeriesEpisodeError):
    """Lifecycle dependency state could not be read safely."""

    code = "lifecycle_unavailable"


class DependentRecordError(SeriesEpisodeError):
    """Deletion was rejected by the authoritative lifecycle boundary."""

    def __init__(self, code: str) -> None:
        if code not in {
            "dependent_project_exists",
            "dependent_script_exists",
            "dependent_series_plan_exists",
            "dependent_series_plan_binding_exists",
            "dependent_m6_series_intelligence_exists",
        }:
            raise ValueError("unsupported dependency error")
        super().__init__(code)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_text(value: Any, field: str, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    if not text:
        raise SeriesEpisodeError(f"{field} is required")
    if len(text) > limit:
        raise SeriesEpisodeError(f"{field} is too long")
    return text


def _required_ref(value: Any, field: str) -> str:
    text = _required_text(value, field, limit=200)
    if not text.isprintable() or any(character.isspace() for character in text):
        raise SeriesEpisodeError(f"{field} is invalid")
    return text


def _optional_ref(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    return _required_ref(value, field)


def _positive_int(value: Any, field: str, *, maximum: int = 100_000) -> int:
    if isinstance(value, bool):
        raise SeriesEpisodeError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise SeriesEpisodeError(f"{field} must be an integer") from exc
    if result < 1 or result > maximum:
        raise SeriesEpisodeError(f"{field} is out of range")
    return result


def _json_copy(value: Mapping[str, Any], field: str) -> str:
    try:
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SeriesEpisodeError(f"{field} must be JSON-compatible") from exc


def _validate_confirmed_source_plan(value: Any, schema_version: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SeriesEpisodeError("sourcePlan must be an object")
    if schema_version != AI_DIRECTOR_PLAN_SCHEMA_VERSION:
        raise SeriesEpisodeError("sourcePlanSchemaVersion is invalid")
    if value.get("schemaVersion") != schema_version:
        raise SeriesEpisodeError("sourcePlan schema does not match sourcePlanSchemaVersion")
    required = {
        "schemaVersion",
        "creativeInterpretation",
        "storyDirection",
        "scriptDraft",
        "storyboardPlan",
        "visualStyle",
        "productionPlan",
    }
    if set(value) != required:
        raise SeriesEpisodeError("sourcePlan fields do not match the accepted contract")
    storyboard = value.get("storyboardPlan")
    production = value.get("productionPlan")
    if not isinstance(storyboard, list) or not storyboard or not isinstance(production, Mapping):
        raise SeriesEpisodeError("sourcePlan content is invalid")
    if production.get("shotCount") != len(storyboard):
        raise SeriesEpisodeError("sourcePlan shot count is invalid")
    return value


@dataclass(frozen=True)
class SeriesRecord:
    schemaVersion: str
    workspaceRef: str
    seriesRef: str
    contentProfileRef: str
    title: str
    description: str
    status: str
    plannedEpisodeCount: int
    createdAt: str
    updatedAt: str
    version: int


@dataclass(frozen=True)
class ConfirmedCreativePlanRecord:
    schemaVersion: str
    workspaceRef: str
    creativePlanRef: str
    sourcePlanRef: str
    sourcePlanSchemaVersion: str
    sourcePlanVersion: int
    briefJson: str
    sourcePlanJson: str
    confirmationStatus: str
    confirmedAt: str
    version: int


@dataclass(frozen=True)
class EpisodeRecord:
    schemaVersion: str
    workspaceRef: str
    episodeRef: str
    seriesRef: str
    episodeNumber: int
    seasonNumber: int
    volumeNumber: int
    title: str
    status: str
    canonicalProjectRef: str | None
    creativePlanRef: str
    createdAt: str
    updatedAt: str
    version: int


@dataclass(frozen=True)
class ConfirmedCreativePlanBinding:
    schemaVersion: str
    workspaceRef: str
    seriesRef: str
    episodeRef: str
    creativePlanRef: str
    sourcePlanRef: str
    sourcePlanSchemaVersion: str
    sourcePlanVersion: int
    briefJson: str
    sourcePlanJson: str
    boundAt: str
    version: int


class SeriesEpisodeRepository(Protocol):
    def create_series(self, record: SeriesRecord) -> SeriesRecord: ...
    def get_series(self, workspace_ref: str, series_ref: str) -> SeriesRecord | None: ...
    def list_series(self, workspace_ref: str | None = None) -> list[SeriesRecord]: ...
    def store_confirmed_plan(self, record: ConfirmedCreativePlanRecord) -> ConfirmedCreativePlanRecord: ...
    def get_confirmed_plan(self, workspace_ref: str, creative_plan_ref: str) -> ConfirmedCreativePlanRecord | None: ...
    def create_episode_with_binding(
        self,
        episode: EpisodeRecord,
        binding: ConfirmedCreativePlanBinding,
    ) -> tuple[EpisodeRecord, ConfirmedCreativePlanBinding]: ...
    def get_episode(self, workspace_ref: str, series_ref: str, episode_ref: str) -> EpisodeRecord | None: ...
    def list_episodes(
        self,
        workspace_ref: str | None = None,
        series_ref: str | None = None,
    ) -> list[EpisodeRecord]: ...
    def get_plan_binding(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> ConfirmedCreativePlanBinding | None: ...
    def delete_episode(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> EpisodeRecord: ...
    def delete_series(
        self,
        workspace_ref: str,
        series_ref: str,
    ) -> tuple[SeriesRecord, list[EpisodeRecord]]: ...


class InMemorySeriesEpisodeAdapter:
    """Deterministic V5 repository adapter for tests only."""

    def __init__(self) -> None:
        self._series: dict[tuple[str, str], SeriesRecord] = {}
        self._plans: dict[tuple[str, str], ConfirmedCreativePlanRecord] = {}
        self._episodes: dict[tuple[str, str, str], EpisodeRecord] = {}
        self._bindings: dict[tuple[str, str, str], ConfirmedCreativePlanBinding] = {}
        self._lock = RLock()

    def create_series(self, record: SeriesRecord) -> SeriesRecord:
        key = (record.workspaceRef, record.seriesRef)
        with self._lock:
            if key in self._series:
                raise DuplicateRecordError("seriesRef already exists in workspace")
            self._series[key] = record
            return record

    def get_series(self, workspace_ref: str, series_ref: str) -> SeriesRecord | None:
        return self._series.get((workspace_ref, series_ref))

    def list_series(self, workspace_ref: str | None = None) -> list[SeriesRecord]:
        records = self._series.values()
        if workspace_ref is not None:
            records = [record for record in records if record.workspaceRef == workspace_ref]
        return sorted(records, key=lambda item: (item.workspaceRef, item.createdAt, item.seriesRef))

    def store_confirmed_plan(self, record: ConfirmedCreativePlanRecord) -> ConfirmedCreativePlanRecord:
        key = (record.workspaceRef, record.creativePlanRef)
        with self._lock:
            if key in self._plans:
                raise DuplicateRecordError("creativePlanRef already exists in workspace")
            self._plans[key] = record
            return record

    def get_confirmed_plan(self, workspace_ref: str, creative_plan_ref: str) -> ConfirmedCreativePlanRecord | None:
        return self._plans.get((workspace_ref, creative_plan_ref))

    def create_episode_with_binding(
        self,
        episode: EpisodeRecord,
        binding: ConfirmedCreativePlanBinding,
    ) -> tuple[EpisodeRecord, ConfirmedCreativePlanBinding]:
        episode_key = (episode.workspaceRef, episode.seriesRef, episode.episodeRef)
        series_key = (episode.workspaceRef, episode.seriesRef)
        plan_key = (episode.workspaceRef, episode.creativePlanRef)
        with self._lock:
            if series_key not in self._series:
                raise RecordNotFoundError("series was not found")
            if plan_key not in self._plans:
                raise UnconfirmedPlanError("confirmed creative plan was not found")
            if episode_key in self._episodes or episode_key in self._bindings:
                raise DuplicateRecordError("episodeRef already exists in workspace")
            if any(
                item.workspaceRef == episode.workspaceRef
                and item.seriesRef == episode.seriesRef
                and item.episodeNumber == episode.episodeNumber
                for item in self._episodes.values()
            ):
                raise DuplicateRecordError("episode number already exists in series")
            if (
                binding.workspaceRef != episode.workspaceRef
                or binding.seriesRef != episode.seriesRef
                or binding.episodeRef != episode.episodeRef
                or binding.creativePlanRef != episode.creativePlanRef
            ):
                raise ScopeMismatchError("episode and plan binding do not match")
            self._episodes[episode_key] = episode
            self._bindings[episode_key] = binding
            return episode, binding

    def get_episode(self, workspace_ref: str, series_ref: str, episode_ref: str) -> EpisodeRecord | None:
        return self._episodes.get((workspace_ref, series_ref, episode_ref))

    def list_episodes(
        self,
        workspace_ref: str | None = None,
        series_ref: str | None = None,
    ) -> list[EpisodeRecord]:
        records = self._episodes.values()
        if workspace_ref is not None:
            records = [record for record in records if record.workspaceRef == workspace_ref]
        if series_ref is not None:
            records = [record for record in records if record.seriesRef == series_ref]
        return sorted(records, key=lambda item: (item.workspaceRef, item.seriesRef, item.episodeNumber))

    def get_plan_binding(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> ConfirmedCreativePlanBinding | None:
        return self._bindings.get((workspace_ref, series_ref, episode_ref))

    def delete_episode(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> EpisodeRecord:
        key = (workspace_ref, series_ref, episode_ref)
        with self._lock:
            record = self._episodes.get(key)
            if record is None:
                raise RecordNotFoundError("episode was not found")
            self._bindings.pop(key, None)
            del self._episodes[key]
            return record

    def delete_series(
        self,
        workspace_ref: str,
        series_ref: str,
    ) -> tuple[SeriesRecord, list[EpisodeRecord]]:
        series_key = (workspace_ref, series_ref)
        with self._lock:
            record = self._series.get(series_key)
            if record is None:
                raise RecordNotFoundError("series was not found")
            episodes = [
                item
                for item in self._episodes.values()
                if item.workspaceRef == workspace_ref and item.seriesRef == series_ref
            ]
            for episode in episodes:
                key = (workspace_ref, series_ref, episode.episodeRef)
                self._bindings.pop(key, None)
                self._episodes.pop(key, None)
            del self._series[series_key]
            return record, sorted(episodes, key=lambda item: item.episodeNumber)


class SqliteSeriesEpisodeAdapter:
    """SQLite local-development durable adapter; it is not a production database."""

    def __init__(self, database_path: Path | str, *, lifecycle_state=None) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._lifecycle_state = lifecycle_state
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise RuntimeError("SQLite foreign key enforcement unavailable")
        return connection

    @contextmanager
    def _session(self):
        shared = self._lifecycle_state.connection_or_none() if self._lifecycle_state else None
        if shared is not None:
            yield shared
            return
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_session(self):
        shared = self._lifecycle_state.connection_or_none() if self._lifecycle_state else None
        if shared is not None:
            yield shared
            return
        if self._lifecycle_state is not None:
            raise RuntimeError("valid lifecycle lease is required")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS v5_series_episode_schema (
                    component TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v5_series (
                    workspace_ref TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    content_profile_ref TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    planned_episode_count INTEGER NOT NULL CHECK(planned_episode_count > 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, series_ref)
                );
                CREATE TABLE IF NOT EXISTS v5_confirmed_creative_plans (
                    workspace_ref TEXT NOT NULL,
                    creative_plan_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    source_plan_ref TEXT NOT NULL,
                    source_plan_schema_version TEXT NOT NULL,
                    source_plan_version INTEGER NOT NULL,
                    brief_json TEXT NOT NULL,
                    source_plan_json TEXT NOT NULL,
                    confirmation_status TEXT NOT NULL CHECK(confirmation_status = 'confirmed'),
                    confirmed_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, creative_plan_ref)
                );
                CREATE TABLE IF NOT EXISTS v5_episode_projects (
                    workspace_ref TEXT NOT NULL,
                    episode_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    episode_number INTEGER NOT NULL CHECK(episode_number > 0),
                    season_number INTEGER NOT NULL CHECK(season_number > 0),
                    volume_number INTEGER NOT NULL CHECK(volume_number > 0),
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    canonical_project_ref TEXT,
                    creative_plan_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, series_ref, episode_ref),
                    UNIQUE(workspace_ref, series_ref, episode_number),
                    FOREIGN KEY(workspace_ref, series_ref)
                        REFERENCES v5_series(workspace_ref, series_ref) ON DELETE RESTRICT,
                    FOREIGN KEY(workspace_ref, creative_plan_ref)
                        REFERENCES v5_confirmed_creative_plans(workspace_ref, creative_plan_ref) ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS v5_episode_plan_bindings (
                    workspace_ref TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    episode_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    creative_plan_ref TEXT NOT NULL,
                    source_plan_ref TEXT NOT NULL,
                    source_plan_schema_version TEXT NOT NULL,
                    source_plan_version INTEGER NOT NULL,
                    brief_json TEXT NOT NULL,
                    source_plan_json TEXT NOT NULL,
                    bound_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, series_ref, episode_ref),
                    FOREIGN KEY(workspace_ref, series_ref, episode_ref)
                        REFERENCES v5_episode_projects(workspace_ref, series_ref, episode_ref) ON DELETE RESTRICT,
                    FOREIGN KEY(workspace_ref, creative_plan_ref)
                        REFERENCES v5_confirmed_creative_plans(workspace_ref, creative_plan_ref) ON DELETE RESTRICT
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO v5_series_episode_schema VALUES (?, ?)",
                ("series_episode", SQLITE_SCHEMA_VERSION),
            )
            row = connection.execute(
                "SELECT schema_version FROM v5_series_episode_schema WHERE component = ?",
                ("series_episode",),
            ).fetchone()
            if row is None or row["schema_version"] not in {SQLITE_SCHEMA_VERSION, 2}:
                raise RuntimeError("unsupported Series/Episode local-development schema version")

    @staticmethod
    def _series(row: sqlite3.Row) -> SeriesRecord:
        return SeriesRecord(
            row["schema_version"], row["workspace_ref"], row["series_ref"],
            row["content_profile_ref"], row["title"], row["description"],
            row["status"], row["planned_episode_count"], row["created_at"],
            row["updated_at"], row["version"],
        )

    @staticmethod
    def _plan(row: sqlite3.Row) -> ConfirmedCreativePlanRecord:
        return ConfirmedCreativePlanRecord(
            row["schema_version"], row["workspace_ref"], row["creative_plan_ref"],
            row["source_plan_ref"], row["source_plan_schema_version"],
            row["source_plan_version"], row["brief_json"], row["source_plan_json"],
            row["confirmation_status"], row["confirmed_at"], row["version"],
        )

    @staticmethod
    def _episode(row: sqlite3.Row) -> EpisodeRecord:
        return EpisodeRecord(
            row["schema_version"], row["workspace_ref"], row["episode_ref"],
            row["series_ref"], row["episode_number"], row["season_number"],
            row["volume_number"], row["title"], row["status"],
            row["canonical_project_ref"], row["creative_plan_ref"],
            row["created_at"], row["updated_at"], row["version"],
        )

    @staticmethod
    def _binding(row: sqlite3.Row) -> ConfirmedCreativePlanBinding:
        return ConfirmedCreativePlanBinding(
            row["schema_version"], row["workspace_ref"], row["series_ref"], row["episode_ref"],
            row["creative_plan_ref"], row["source_plan_ref"],
            row["source_plan_schema_version"], row["source_plan_version"],
            row["brief_json"], row["source_plan_json"], row["bound_at"], row["version"],
        )

    def create_series(self, record: SeriesRecord) -> SeriesRecord:
        try:
            with self._lock, self._write_session() as connection:
                connection.execute(
                    "INSERT INTO v5_series VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.workspaceRef, record.seriesRef, record.schemaVersion,
                        record.contentProfileRef, record.title, record.description,
                        record.status, record.plannedEpisodeCount, record.createdAt,
                        record.updatedAt, record.version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecordError("series already exists in workspace") from exc
        return record

    def get_series(self, workspace_ref: str, series_ref: str) -> SeriesRecord | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_series WHERE workspace_ref = ? AND series_ref = ?",
                (workspace_ref, series_ref),
            ).fetchone()
        return self._series(row) if row else None

    def list_series(self, workspace_ref: str | None = None) -> list[SeriesRecord]:
        with self._session() as connection:
            if workspace_ref is None:
                rows = connection.execute(
                    "SELECT * FROM v5_series ORDER BY workspace_ref, created_at, series_ref"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM v5_series WHERE workspace_ref = ? ORDER BY created_at, series_ref",
                    (workspace_ref,),
                ).fetchall()
        return [self._series(row) for row in rows]

    def store_confirmed_plan(self, record: ConfirmedCreativePlanRecord) -> ConfirmedCreativePlanRecord:
        try:
            with self._lock, self._write_session() as connection:
                connection.execute(
                    "INSERT INTO v5_confirmed_creative_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.workspaceRef, record.creativePlanRef, record.schemaVersion,
                        record.sourcePlanRef, record.sourcePlanSchemaVersion,
                        record.sourcePlanVersion, record.briefJson, record.sourcePlanJson,
                        record.confirmationStatus, record.confirmedAt, record.version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecordError("creative plan already exists in workspace") from exc
        return record

    def get_confirmed_plan(self, workspace_ref: str, creative_plan_ref: str) -> ConfirmedCreativePlanRecord | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_confirmed_creative_plans WHERE workspace_ref = ? AND creative_plan_ref = ?",
                (workspace_ref, creative_plan_ref),
            ).fetchone()
        return self._plan(row) if row else None

    def create_episode_with_binding(
        self,
        episode: EpisodeRecord,
        binding: ConfirmedCreativePlanBinding,
    ) -> tuple[EpisodeRecord, ConfirmedCreativePlanBinding]:
        try:
            with self._lock, self._write_session() as connection:
                connection.execute(
                    "INSERT INTO v5_episode_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        episode.workspaceRef, episode.episodeRef, episode.schemaVersion,
                        episode.seriesRef, episode.episodeNumber, episode.seasonNumber,
                        episode.volumeNumber, episode.title, episode.status,
                        episode.canonicalProjectRef, episode.creativePlanRef,
                        episode.createdAt, episode.updatedAt, episode.version,
                    ),
                )
                connection.execute(
                    "INSERT INTO v5_episode_plan_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        binding.workspaceRef, binding.seriesRef, binding.episodeRef, binding.schemaVersion,
                        binding.creativePlanRef, binding.sourcePlanRef,
                        binding.sourcePlanSchemaVersion, binding.sourcePlanVersion,
                        binding.briefJson, binding.sourcePlanJson, binding.boundAt,
                        binding.version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if self.get_series(episode.workspaceRef, episode.seriesRef) is None:
                raise RecordNotFoundError("series was not found") from exc
            if self.get_confirmed_plan(episode.workspaceRef, episode.creativePlanRef) is None:
                raise UnconfirmedPlanError("confirmed creative plan was not found") from exc
            raise DuplicateRecordError("episode or immutable plan binding already exists") from exc
        return episode, binding

    def get_episode(self, workspace_ref: str, series_ref: str, episode_ref: str) -> EpisodeRecord | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_episode_projects WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?",
                (workspace_ref, series_ref, episode_ref),
            ).fetchone()
        return self._episode(row) if row else None

    def list_episodes(
        self,
        workspace_ref: str | None = None,
        series_ref: str | None = None,
    ) -> list[EpisodeRecord]:
        clauses: list[str] = []
        values: list[str] = []
        if workspace_ref is not None:
            clauses.append("workspace_ref = ?")
            values.append(workspace_ref)
        if series_ref is not None:
            clauses.append("series_ref = ?")
            values.append(series_ref)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT * FROM v5_episode_projects{where} ORDER BY workspace_ref, series_ref, episode_number",
                values,
            ).fetchall()
        return [self._episode(row) for row in rows]

    def get_plan_binding(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> ConfirmedCreativePlanBinding | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_episode_plan_bindings WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?",
                (workspace_ref, series_ref, episode_ref),
            ).fetchone()
        return self._binding(row) if row else None

    def delete_episode(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> EpisodeRecord:
        with self._lock, self._write_session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_episode_projects WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?",
                (workspace_ref, series_ref, episode_ref),
            ).fetchone()
            if row is None:
                raise RecordNotFoundError("episode was not found")
            script = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='v5_scripts'"
            ).fetchone()
            if script is not None and connection.execute(
                "SELECT 1 FROM v5_scripts WHERE workspace_ref=? AND series_ref=? AND episode_ref=? LIMIT 1",
                (workspace_ref, series_ref, episode_ref),
            ).fetchone() is not None:
                raise DependentRecordError("dependent_script_exists")
            connection.execute(
                "DELETE FROM v5_episode_plan_bindings WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?",
                (workspace_ref, series_ref, episode_ref),
            )
            connection.execute(
                "DELETE FROM v5_episode_projects WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?",
                (workspace_ref, series_ref, episode_ref),
            )
        return self._episode(row)

    def delete_series(
        self,
        workspace_ref: str,
        series_ref: str,
    ) -> tuple[SeriesRecord, list[EpisodeRecord]]:
        with self._lock, self._write_session() as connection:
            series_row = connection.execute(
                "SELECT * FROM v5_series WHERE workspace_ref = ? AND series_ref = ?",
                (workspace_ref, series_ref),
            ).fetchone()
            if series_row is None:
                raise RecordNotFoundError("series was not found")
            project_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='v5_project_series_relationships'"
            ).fetchone()
            if project_table is not None and connection.execute(
                "SELECT 1 FROM v5_project_series_relationships WHERE workspace_ref=? AND series_ref=? LIMIT 1",
                (workspace_ref, series_ref),
            ).fetchone() is not None:
                raise DependentRecordError("dependent_project_exists")
            script_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='v5_scripts'"
            ).fetchone()
            if script_table is not None and connection.execute(
                "SELECT 1 FROM v5_scripts WHERE workspace_ref=? AND series_ref=? LIMIT 1",
                (workspace_ref, series_ref),
            ).fetchone() is not None:
                raise DependentRecordError("dependent_script_exists")
            episode_rows = connection.execute(
                "SELECT * FROM v5_episode_projects WHERE workspace_ref = ? AND series_ref = ? ORDER BY episode_number",
                (workspace_ref, series_ref),
            ).fetchall()
            connection.execute(
                "DELETE FROM v5_episode_plan_bindings WHERE workspace_ref = ? AND series_ref = ?",
                (workspace_ref, series_ref),
            )
            connection.execute(
                "DELETE FROM v5_episode_projects WHERE workspace_ref = ? AND series_ref = ?",
                (workspace_ref, series_ref),
            )
            connection.execute(
                "DELETE FROM v5_series WHERE workspace_ref = ? AND series_ref = ?",
                (workspace_ref, series_ref),
            )
        return self._series(series_row), [self._episode(row) for row in episode_rows]


class SeriesEpisodeService:
    """V5 owner for Series, Episode, and immutable confirmed-plan bindings."""

    def __init__(
        self,
        repository: SeriesEpisodeRepository,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _series_mapping(record: SeriesRecord) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "seriesRef": record.seriesRef,
            "contentProfileRef": record.contentProfileRef,
            "title": record.title,
            "description": record.description,
            "status": record.status,
            "plannedEpisodeCount": record.plannedEpisodeCount,
            "createdAt": record.createdAt,
            "updatedAt": record.updatedAt,
            "version": record.version,
        }

    @staticmethod
    def _episode_mapping(record: EpisodeRecord) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "seriesRef": record.seriesRef,
            "episodeRef": record.episodeRef,
            "episodeNumber": record.episodeNumber,
            "seasonNumber": record.seasonNumber,
            "volumeNumber": record.volumeNumber,
            "title": record.title,
            "status": record.status,
            "canonicalProjectRef": record.canonicalProjectRef,
            "creativePlanRef": record.creativePlanRef,
            "createdAt": record.createdAt,
            "updatedAt": record.updatedAt,
            "version": record.version,
        }

    @staticmethod
    def _plan_mapping(record: ConfirmedCreativePlanRecord) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "creativePlanRef": record.creativePlanRef,
            "sourcePlanRef": record.sourcePlanRef,
            "sourcePlanSchemaVersion": record.sourcePlanSchemaVersion,
            "sourcePlanVersion": record.sourcePlanVersion,
            "brief": json.loads(record.briefJson),
            "sourcePlan": json.loads(record.sourcePlanJson),
            "confirmationStatus": record.confirmationStatus,
            "confirmedAt": record.confirmedAt,
            "version": record.version,
        }

    @staticmethod
    def _binding_mapping(record: ConfirmedCreativePlanBinding) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "seriesRef": record.seriesRef,
            "episodeRef": record.episodeRef,
            "creativePlanRef": record.creativePlanRef,
            "sourcePlanRef": record.sourcePlanRef,
            "sourcePlanSchemaVersion": record.sourcePlanSchemaVersion,
            "sourcePlanVersion": record.sourcePlanVersion,
            "brief": json.loads(record.briefJson),
            "sourcePlan": json.loads(record.sourcePlanJson),
            "boundAt": record.boundAt,
            "version": record.version,
        }

    def create_series(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SeriesEpisodeError("series input must be an object")
        now = self._clock()
        record = SeriesRecord(
            SERIES_SCHEMA_VERSION,
            _required_ref(value.get("workspaceRef"), "workspaceRef"),
            self._ref_factory("series"),
            _required_ref(value.get("contentProfileRef"), "contentProfileRef"),
            _required_text(value.get("title"), "title"),
            str(value.get("description") or "").strip()[:2000],
            "active",
            _positive_int(value.get("plannedEpisodeCount", 1), "plannedEpisodeCount", maximum=10_000),
            now,
            now,
            1,
        )
        return self._series_mapping(self.repository.create_series(record))

    def get_series(self, workspace_ref: str, series_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        record = self.repository.get_series(workspace, _required_ref(series_ref, "seriesRef"))
        if record is None:
            raise RecordNotFoundError("series was not found")
        result = self._series_mapping(record)
        result["episodes"] = [
            self._episode_with_lineage(item)
            for item in self.repository.list_episodes(workspace, record.seriesRef)
        ]
        return result

    def list_series(self, workspace_ref: str) -> list[dict[str, Any]]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        return [self.get_series(workspace, item.seriesRef) for item in self.repository.list_series(workspace)]

    def confirm_creative_plan(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping) or value.get("humanConfirmed") is not True:
            raise UnconfirmedPlanError("explicit human confirmation is required")
        workspace = _required_ref(value.get("workspaceRef"), "workspaceRef")
        source_plan_ref = _required_ref(value.get("sourcePlanRef"), "sourcePlanRef")
        source_schema = _required_ref(value.get("sourcePlanSchemaVersion"), "sourcePlanSchemaVersion")
        plan = _validate_confirmed_source_plan(value.get("sourcePlan"), source_schema)
        brief_value = value.get("brief")
        if not isinstance(brief_value, Mapping):
            raise SeriesEpisodeError("brief must be an object")
        now = self._clock()
        record = ConfirmedCreativePlanRecord(
            CONFIRMED_PLAN_SCHEMA_VERSION,
            workspace,
            self._ref_factory("creative-plan"),
            source_plan_ref,
            source_schema,
            _positive_int(value.get("sourcePlanVersion"), "sourcePlanVersion"),
            _json_copy(brief_value, "brief"),
            _json_copy(plan, "sourcePlan"),
            "confirmed",
            now,
            1,
        )
        return self._plan_mapping(self.repository.store_confirmed_plan(record))

    def create_episode(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SeriesEpisodeError("episode input must be an object")
        workspace = _required_ref(value.get("workspaceRef"), "workspaceRef")
        series_ref = _required_ref(value.get("seriesRef"), "seriesRef")
        series = self.repository.get_series(workspace, series_ref)
        if series is None:
            raise RecordNotFoundError("series was not found")
        creative_plan_ref = _required_ref(value.get("creativePlanRef"), "creativePlanRef")
        plan = self.repository.get_confirmed_plan(workspace, creative_plan_ref)
        if plan is None or plan.confirmationStatus != "confirmed":
            raise UnconfirmedPlanError("confirmed creative plan was not found")
        now = self._clock()
        if value.get("canonicalProjectRef") not in (None, ""):
            raise SeriesEpisodeError("canonicalProjectRef binding is not available in M2")
        episode_ref = self._ref_factory("episode")
        episode = EpisodeRecord(
            EPISODE_SCHEMA_VERSION,
            workspace,
            episode_ref,
            series_ref,
            _positive_int(value.get("episodeNumber"), "episodeNumber"),
            _positive_int(value.get("seasonNumber", 1), "seasonNumber"),
            _positive_int(value.get("volumeNumber", 1), "volumeNumber"),
            _required_text(value.get("title"), "title"),
            "draft",
            None,
            creative_plan_ref,
            now,
            now,
            1,
        )
        binding = ConfirmedCreativePlanBinding(
            PLAN_BINDING_SCHEMA_VERSION,
            workspace,
            series_ref,
            episode_ref,
            creative_plan_ref,
            plan.sourcePlanRef,
            plan.sourcePlanSchemaVersion,
            plan.sourcePlanVersion,
            plan.briefJson,
            plan.sourcePlanJson,
            now,
            1,
        )
        stored, _ = self.repository.create_episode_with_binding(episode, binding)
        return self._episode_with_lineage(stored)

    def _episode_with_lineage(self, record: EpisodeRecord) -> dict[str, Any]:
        result = self._episode_mapping(record)
        binding = self.repository.get_plan_binding(
            record.workspaceRef,
            record.seriesRef,
            record.episodeRef,
        )
        if binding is None:
            raise UnconfirmedPlanError("confirmed creative plan binding was not found")
        result.update(
            {
                "sourcePlanRef": binding.sourcePlanRef,
                "sourcePlanSchemaVersion": binding.sourcePlanSchemaVersion,
                "sourcePlanVersion": binding.sourcePlanVersion,
            }
        )
        return result

    def get_episode(self, workspace_ref: str, series_ref: str, episode_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        record = self.repository.get_episode(
            workspace,
            series,
            _required_ref(episode_ref, "episodeRef"),
        )
        if record is None:
            raise RecordNotFoundError("episode was not found")
        result = self._episode_with_lineage(record)
        binding = self.repository.get_plan_binding(workspace, series, record.episodeRef)
        if binding is None:
            raise UnconfirmedPlanError("confirmed creative plan binding was not found")
        result["confirmedPlanBinding"] = self._binding_mapping(binding)
        return result

    def delete_episode(self, workspace_ref: str, series_ref: str, episode_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        episode = _required_ref(episode_ref, "episodeRef")
        deleted = self.repository.delete_episode(workspace, series, episode)
        return {
            "schemaVersion": "v5.series-episode.deletion.v1",
            "kind": "episode",
            "workspaceRef": workspace,
            "seriesRef": series,
            "episodeRef": deleted.episodeRef,
            "deletedEpisodeCount": 1,
        }

    def delete_series(self, workspace_ref: str, series_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        deleted, episodes = self.repository.delete_series(workspace, series)
        return {
            "schemaVersion": "v5.series-episode.deletion.v1",
            "kind": "series",
            "workspaceRef": workspace,
            "seriesRef": deleted.seriesRef,
            "deletedEpisodeRefs": [item.episodeRef for item in episodes],
            "deletedEpisodeCount": len(episodes),
        }

    def build_script_studio_bootstrap(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        episode = self.repository.get_episode(
            workspace,
            series,
            _required_ref(episode_ref, "episodeRef"),
        )
        if episode is None:
            raise RecordNotFoundError("episode was not found")
        binding = self.repository.get_plan_binding(workspace, series, episode.episodeRef)
        if binding is None:
            raise UnconfirmedPlanError("confirmed creative plan binding was not found")
        source = json.loads(binding.sourcePlanJson)
        return {
            "schemaVersion": SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "episodeRef": episode.episodeRef,
            "seriesRef": episode.seriesRef,
            "sourcePlanRef": binding.sourcePlanRef,
            "sourcePlanSchemaVersion": binding.sourcePlanSchemaVersion,
            "sourcePlanVersion": binding.sourcePlanVersion,
            "storyDirection": source["storyDirection"],
            "scriptDraft": source["scriptDraft"],
            "characters": source["productionPlan"]["characters"],
            "scenes": source["productionPlan"]["scenes"],
            "storyboardPlan": source["storyboardPlan"],
            "visualStyle": source["visualStyle"],
            "productionPlan": source["productionPlan"],
        }
