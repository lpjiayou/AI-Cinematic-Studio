"""V5-owned Script Studio facts, repository port, and local adapters."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4


SCRIPT_SCHEMA_VERSION = "v5.script.v1"
SCRIPT_VERSION_SCHEMA_VERSION = "creator.script-studio.script-version.v1"
STORYBOARD_BOOTSTRAP_SCHEMA_VERSION = "creator.storyboard.bootstrap-input.v1"
SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION = "creator.script-studio.bootstrap-input.v1"
SQLITE_SCHEMA_VERSION = 1


class ScriptStudioError(ValueError):
    code = "invalid_request"


class RecordNotFoundError(ScriptStudioError):
    code = "not_found"


class DuplicateRecordError(ScriptStudioError):
    code = "duplicate_record"


class ScopeMismatchError(ScriptStudioError):
    code = "scope_mismatch"


class VersionConflictError(ScriptStudioError):
    code = "version_conflict"


class ScriptNotConfirmedError(ScriptStudioError):
    code = "script_not_confirmed"


class RepositoryWriteError(ScriptStudioError):
    code = "application_error"


class UpstreamReader(Protocol):
    def build_script_studio_bootstrap(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_text(value: Any, field: str, *, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if not text:
        raise ScriptStudioError(f"{field} is required")
    if len(text) > limit:
        raise ScriptStudioError(f"{field} is too long")
    return text


def _required_ref(value: Any, field: str) -> str:
    text = _required_text(value, field, limit=200)
    if not text.isprintable() or any(character.isspace() for character in text):
        raise ScriptStudioError(f"{field} is invalid")
    return text


def _positive_int(value: Any, field: str, *, maximum: int = 100_000) -> int:
    if isinstance(value, bool):
        raise ScriptStudioError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ScriptStudioError(f"{field} must be an integer") from exc
    if result < 1 or result > maximum:
        raise ScriptStudioError(f"{field} is out of range")
    return result


def _positive_number(value: Any, field: str, *, maximum: float = 3600) -> float:
    if isinstance(value, bool):
        raise ScriptStudioError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ScriptStudioError(f"{field} must be a number") from exc
    if result <= 0 or result > maximum:
        raise ScriptStudioError(f"{field} is out of range")
    return round(result, 3)


def _text_list(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise ScriptStudioError(f"{field} must be an array")
    result = [_required_text(item, field, limit=1000) for item in value]
    if not allow_empty and not result:
        raise ScriptStudioError(f"{field} must not be empty")
    return result


def _dialogue(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ScriptStudioError(f"{field} must be an array")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ScriptStudioError(f"{field}[{index}] must be an object")
        if set(item) != {"speaker", "text", "emotion"}:
            raise ScriptStudioError(f"{field}[{index}] fields are invalid")
        result.append(
            {
                "speaker": _required_text(item.get("speaker"), f"{field}.speaker", limit=120),
                "text": _required_text(item.get("text"), f"{field}.text", limit=2000),
                "emotion": _required_text(item.get("emotion"), f"{field}.emotion", limit=200),
            }
        )
    return result


def _bootstrap_target_duration(bootstrap: Mapping[str, Any]) -> float:
    storyboard = bootstrap.get("storyboardPlan")
    if not isinstance(storyboard, list) or not storyboard:
        raise ScriptStudioError("bootstrap storyboardPlan is invalid")
    return round(
        sum(_positive_number(item.get("durationSec"), "storyboardPlan.durationSec") for item in storyboard if isinstance(item, Mapping)),
        3,
    )


def _validate_bootstrap(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScriptStudioError("bootstrap is invalid")
    if value.get("schemaVersion") != SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION:
        raise ScriptStudioError("bootstrap schemaVersion is invalid")
    for field in (
        "workspaceRef",
        "seriesRef",
        "episodeRef",
        "sourcePlanRef",
        "sourcePlanSchemaVersion",
    ):
        _required_ref(value.get(field), field)
    _positive_int(value.get("sourcePlanVersion"), "sourcePlanVersion")
    for field in ("storyDirection", "scriptDraft", "visualStyle", "productionPlan"):
        if not isinstance(value.get(field), Mapping):
            raise ScriptStudioError(f"bootstrap {field} is invalid")
    _bootstrap_target_duration(value)
    return value


def _normalize_content(
    value: Any,
    *,
    bootstrap: Mapping[str, Any],
    ref_factory: Callable[[str], str],
    existing_scene_refs: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScriptStudioError("script content must be an object")
    expected = {"title", "logline", "synopsis", "targetDurationSec", "scenes"}
    if set(value) != expected:
        raise ScriptStudioError("script content fields do not match the accepted contract")
    target_duration = _positive_number(value.get("targetDurationSec"), "targetDurationSec")
    bootstrap_duration = _bootstrap_target_duration(bootstrap)
    if abs(target_duration - bootstrap_duration) > 0.001:
        raise ScriptStudioError("targetDurationSec does not match Episode context")
    scenes_value = value.get("scenes")
    if not isinstance(scenes_value, list) or not scenes_value:
        raise ScriptStudioError("scenes must be a non-empty array")
    scenes: list[dict[str, Any]] = []
    scene_refs: set[str] = set()
    expected_number = 1
    for index, raw in enumerate(scenes_value):
        if not isinstance(raw, Mapping):
            raise ScriptStudioError(f"scenes[{index}] must be an object")
        allowed = {
            "scriptSceneRef",
            "sceneNumber",
            "heading",
            "location",
            "timeOfDay",
            "characters",
            "action",
            "dialogue",
            "narration",
            "subtitleText",
            "estimatedDurationSec",
            "scenePurpose",
            "continuityNotes",
            "productionNotes",
        }
        if set(raw) - allowed:
            raise ScriptStudioError(f"scenes[{index}] contains unsupported fields")
        number = _positive_int(raw.get("sceneNumber"), f"scenes[{index}].sceneNumber", maximum=10_000)
        if number != expected_number:
            raise ScriptStudioError("scene numbers must be continuous")
        expected_number += 1
        supplied_ref = raw.get("scriptSceneRef")
        if supplied_ref:
            scene_ref = _required_ref(supplied_ref, "scriptSceneRef")
            if existing_scene_refs is not None and scene_ref not in existing_scene_refs:
                raise ScopeMismatchError("scriptSceneRef does not belong to the source ScriptVersion")
        else:
            if existing_scene_refs is not None:
                raise ScriptStudioError("scriptSceneRef is required for a derived version")
            scene_ref = ref_factory("script-scene")
        if scene_ref in scene_refs:
            raise ScriptStudioError("scriptSceneRef values must be unique")
        scene_refs.add(scene_ref)
        scenes.append(
            {
                "scriptSceneRef": scene_ref,
                "sceneNumber": number,
                "heading": _required_text(raw.get("heading"), "heading", limit=300),
                "location": _required_text(raw.get("location"), "location", limit=300),
                "timeOfDay": _required_text(raw.get("timeOfDay"), "timeOfDay", limit=120),
                "characters": _text_list(raw.get("characters"), "characters"),
                "action": _required_text(raw.get("action"), "action", limit=6000),
                "dialogue": _dialogue(raw.get("dialogue"), "dialogue"),
                "narration": _text_list(raw.get("narration"), "narration"),
                "subtitleText": _text_list(raw.get("subtitleText"), "subtitleText"),
                "estimatedDurationSec": _positive_number(raw.get("estimatedDurationSec"), "estimatedDurationSec"),
                "scenePurpose": _required_text(raw.get("scenePurpose"), "scenePurpose", limit=1000),
                "continuityNotes": _text_list(raw.get("continuityNotes"), "continuityNotes"),
                "productionNotes": _text_list(raw.get("productionNotes"), "productionNotes"),
            }
        )
    total_duration = round(sum(scene["estimatedDurationSec"] for scene in scenes), 3)
    minimum = target_duration * 0.8
    maximum = target_duration * 1.2
    if not minimum <= total_duration <= maximum:
        raise ScriptStudioError("scene duration total is inconsistent with the Episode target")
    return {
        "title": _required_text(value.get("title"), "title", limit=300),
        "logline": _required_text(value.get("logline"), "logline", limit=1000),
        "synopsis": _required_text(value.get("synopsis"), "synopsis", limit=6000),
        "targetDurationSec": target_duration,
        "scenes": scenes,
    }


@dataclass(frozen=True)
class ScriptRecord:
    schemaVersion: str
    workspaceRef: str
    seriesRef: str
    episodeRef: str
    scriptRef: str
    title: str
    currentScriptVersionRef: str
    confirmedScriptVersionRef: str | None
    createdAt: str
    updatedAt: str
    version: int


@dataclass(frozen=True)
class ScriptVersionRecord:
    schemaVersion: str
    workspaceRef: str
    seriesRef: str
    episodeRef: str
    scriptRef: str
    scriptVersionRef: str
    sourcePlanRef: str
    sourcePlanSchemaVersion: str
    sourcePlanVersion: int
    versionNumber: int
    contentJson: str
    changeKind: str
    parentScriptVersionRef: str | None
    createdAt: str


class ScriptStudioRepository(Protocol):
    def create_script_with_version(
        self,
        script: ScriptRecord,
        version: ScriptVersionRecord,
    ) -> tuple[ScriptRecord, ScriptVersionRecord]: ...

    def append_version(
        self,
        updated_script: ScriptRecord,
        version: ScriptVersionRecord,
        expected_script_version: int,
    ) -> tuple[ScriptRecord, ScriptVersionRecord]: ...

    def confirm_version(
        self,
        updated_script: ScriptRecord,
        expected_script_version: int,
    ) -> ScriptRecord: ...

    def get_script(self, workspace_ref: str, series_ref: str, episode_ref: str) -> ScriptRecord | None: ...
    def get_script_by_ref(self, workspace_ref: str, script_ref: str) -> ScriptRecord | None: ...
    def get_version(self, workspace_ref: str, script_ref: str, version_ref: str) -> ScriptVersionRecord | None: ...
    def list_versions(self, workspace_ref: str, script_ref: str) -> list[ScriptVersionRecord]: ...


class InMemoryScriptStudioAdapter:
    """Deterministic repository adapter for tests only."""

    def __init__(self) -> None:
        self._scripts: dict[tuple[str, str], ScriptRecord] = {}
        self._episode_index: dict[tuple[str, str, str], str] = {}
        self._versions: dict[tuple[str, str, str], ScriptVersionRecord] = {}
        self._lock = RLock()

    def create_script_with_version(self, script, version):
        script_key = (script.workspaceRef, script.scriptRef)
        episode_key = (script.workspaceRef, script.seriesRef, script.episodeRef)
        version_key = (version.workspaceRef, version.scriptRef, version.scriptVersionRef)
        with self._lock:
            if script_key in self._scripts or episode_key in self._episode_index or version_key in self._versions:
                raise DuplicateRecordError("Script already exists for Episode")
            self._scripts[script_key] = script
            self._episode_index[episode_key] = script.scriptRef
            self._versions[version_key] = version
        return script, version

    def append_version(self, updated_script, version, expected_script_version):
        key = (updated_script.workspaceRef, updated_script.scriptRef)
        version_key = (version.workspaceRef, version.scriptRef, version.scriptVersionRef)
        with self._lock:
            current = self._scripts.get(key)
            if current is None:
                raise RecordNotFoundError("Script was not found")
            if current.version != expected_script_version:
                raise VersionConflictError("Script version changed")
            if version_key in self._versions:
                raise DuplicateRecordError("ScriptVersion already exists")
            self._versions[version_key] = version
            self._scripts[key] = updated_script
        return updated_script, version

    def confirm_version(self, updated_script, expected_script_version):
        key = (updated_script.workspaceRef, updated_script.scriptRef)
        with self._lock:
            current = self._scripts.get(key)
            if current is None:
                raise RecordNotFoundError("Script was not found")
            if current.version != expected_script_version:
                raise VersionConflictError("Script version changed")
            version_key = (
                updated_script.workspaceRef,
                updated_script.scriptRef,
                updated_script.confirmedScriptVersionRef,
            )
            if version_key not in self._versions:
                raise RecordNotFoundError("ScriptVersion was not found")
            self._scripts[key] = updated_script
        return updated_script

    def get_script(self, workspace_ref, series_ref, episode_ref):
        script_ref = self._episode_index.get((workspace_ref, series_ref, episode_ref))
        return self._scripts.get((workspace_ref, script_ref)) if script_ref else None

    def get_script_by_ref(self, workspace_ref, script_ref):
        return self._scripts.get((workspace_ref, script_ref))

    def get_version(self, workspace_ref, script_ref, version_ref):
        return self._versions.get((workspace_ref, script_ref, version_ref))

    def list_versions(self, workspace_ref, script_ref):
        records = [
            item
            for (workspace, script, _), item in self._versions.items()
            if workspace == workspace_ref and script == script_ref
        ]
        return sorted(records, key=lambda item: item.versionNumber)

    def lifecycle_has_episode_dependency(self, workspace_ref, series_ref, episode_ref):
        if (workspace_ref, series_ref, episode_ref) in self._episode_index:
            return True
        return any(
            record.workspaceRef == workspace_ref
            and record.seriesRef == series_ref
            and record.episodeRef == episode_ref
            for record in self._versions.values()
        )

    def lifecycle_has_series_dependency(self, workspace_ref, series_ref):
        if any(
            key[0] == workspace_ref and key[1] == series_ref
            for key in self._episode_index
        ):
            return True
        return any(
            record.workspaceRef == workspace_ref and record.seriesRef == series_ref
            for record in self._versions.values()
        )


class SqliteScriptStudioAdapter:
    """SQLite local-development durable adapter; not a production database."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS v5_script_studio_schema (
                    component TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v5_scripts (
                    workspace_ref TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    episode_ref TEXT NOT NULL,
                    script_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    current_script_version_ref TEXT NOT NULL,
                    confirmed_script_version_ref TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, script_ref),
                    UNIQUE(workspace_ref, series_ref, episode_ref)
                );
                CREATE TABLE IF NOT EXISTS v5_script_versions (
                    workspace_ref TEXT NOT NULL,
                    script_ref TEXT NOT NULL,
                    script_version_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    episode_ref TEXT NOT NULL,
                    source_plan_ref TEXT NOT NULL,
                    source_plan_schema_version TEXT NOT NULL,
                    source_plan_version INTEGER NOT NULL,
                    version_number INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    change_kind TEXT NOT NULL,
                    parent_script_version_ref TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_ref, script_ref, script_version_ref),
                    UNIQUE(workspace_ref, script_ref, version_number),
                    FOREIGN KEY(workspace_ref, script_ref)
                        REFERENCES v5_scripts(workspace_ref, script_ref) ON DELETE RESTRICT
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO v5_script_studio_schema VALUES (?, ?)",
                ("script_studio", SQLITE_SCHEMA_VERSION),
            )
            row = connection.execute(
                "SELECT schema_version FROM v5_script_studio_schema WHERE component = ?",
                ("script_studio",),
            ).fetchone()
            if row is None or row["schema_version"] != SQLITE_SCHEMA_VERSION:
                raise RuntimeError("unsupported Script Studio local-development schema version")

    @staticmethod
    def _script(row: sqlite3.Row) -> ScriptRecord:
        return ScriptRecord(
            row["schema_version"], row["workspace_ref"], row["series_ref"],
            row["episode_ref"], row["script_ref"], row["title"],
            row["current_script_version_ref"], row["confirmed_script_version_ref"],
            row["created_at"], row["updated_at"], row["version"],
        )

    @staticmethod
    def _version(row: sqlite3.Row) -> ScriptVersionRecord:
        return ScriptVersionRecord(
            row["schema_version"], row["workspace_ref"], row["series_ref"],
            row["episode_ref"], row["script_ref"], row["script_version_ref"],
            row["source_plan_ref"], row["source_plan_schema_version"],
            row["source_plan_version"], row["version_number"], row["content_json"],
            row["change_kind"], row["parent_script_version_ref"], row["created_at"],
        )

    @staticmethod
    def _script_values(record: ScriptRecord) -> tuple[Any, ...]:
        return (
            record.workspaceRef, record.seriesRef, record.episodeRef, record.scriptRef,
            record.schemaVersion, record.title, record.currentScriptVersionRef,
            record.confirmedScriptVersionRef, record.createdAt, record.updatedAt,
            record.version,
        )

    @staticmethod
    def _version_values(record: ScriptVersionRecord) -> tuple[Any, ...]:
        return (
            record.workspaceRef, record.scriptRef, record.scriptVersionRef,
            record.schemaVersion, record.seriesRef, record.episodeRef,
            record.sourcePlanRef, record.sourcePlanSchemaVersion, record.sourcePlanVersion,
            record.versionNumber, record.contentJson, record.changeKind,
            record.parentScriptVersionRef, record.createdAt,
        )

    def create_script_with_version(self, script, version):
        try:
            with self._lock, self._session() as connection:
                connection.execute(
                    "INSERT INTO v5_scripts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._script_values(script),
                )
                connection.execute(
                    "INSERT INTO v5_script_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._version_values(version),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecordError("Script or ScriptVersion already exists") from exc
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("Script write failed") from exc
        return script, version

    def append_version(self, updated_script, version, expected_script_version):
        try:
            with self._lock, self._session() as connection:
                row = connection.execute(
                    "SELECT version FROM v5_scripts WHERE workspace_ref = ? AND script_ref = ?",
                    (updated_script.workspaceRef, updated_script.scriptRef),
                ).fetchone()
                if row is None:
                    raise RecordNotFoundError("Script was not found")
                if row["version"] != expected_script_version:
                    raise VersionConflictError("Script version changed")
                connection.execute(
                    "INSERT INTO v5_script_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._version_values(version),
                )
                updated = connection.execute(
                    """
                    UPDATE v5_scripts
                    SET title = ?, current_script_version_ref = ?, updated_at = ?, version = ?
                    WHERE workspace_ref = ? AND script_ref = ? AND version = ?
                    """,
                    (
                        updated_script.title, updated_script.currentScriptVersionRef,
                        updated_script.updatedAt, updated_script.version,
                        updated_script.workspaceRef, updated_script.scriptRef,
                        expected_script_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise VersionConflictError("Script version changed")
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecordError("ScriptVersion already exists") from exc
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("ScriptVersion write failed") from exc
        return updated_script, version

    def confirm_version(self, updated_script, expected_script_version):
        try:
            with self._lock, self._session() as connection:
                version = connection.execute(
                    """
                    SELECT 1 FROM v5_script_versions
                    WHERE workspace_ref = ? AND script_ref = ? AND script_version_ref = ?
                    """,
                    (
                        updated_script.workspaceRef,
                        updated_script.scriptRef,
                        updated_script.confirmedScriptVersionRef,
                    ),
                ).fetchone()
                if version is None:
                    raise RecordNotFoundError("ScriptVersion was not found")
                updated = connection.execute(
                    """
                    UPDATE v5_scripts
                    SET confirmed_script_version_ref = ?, updated_at = ?, version = ?
                    WHERE workspace_ref = ? AND script_ref = ? AND version = ?
                    """,
                    (
                        updated_script.confirmedScriptVersionRef,
                        updated_script.updatedAt,
                        updated_script.version,
                        updated_script.workspaceRef,
                        updated_script.scriptRef,
                        expected_script_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise VersionConflictError("Script version changed")
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("Script confirmation failed") from exc
        return updated_script

    def get_script(self, workspace_ref, series_ref, episode_ref):
        with self._session() as connection:
            row = connection.execute(
                """
                SELECT * FROM v5_scripts
                WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?
                """,
                (workspace_ref, series_ref, episode_ref),
            ).fetchone()
        return self._script(row) if row else None

    def get_script_by_ref(self, workspace_ref, script_ref):
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_scripts WHERE workspace_ref = ? AND script_ref = ?",
                (workspace_ref, script_ref),
            ).fetchone()
        return self._script(row) if row else None

    def get_version(self, workspace_ref, script_ref, version_ref):
        with self._session() as connection:
            row = connection.execute(
                """
                SELECT * FROM v5_script_versions
                WHERE workspace_ref = ? AND script_ref = ? AND script_version_ref = ?
                """,
                (workspace_ref, script_ref, version_ref),
            ).fetchone()
        return self._version(row) if row else None

    def list_versions(self, workspace_ref, script_ref):
        with self._session() as connection:
            rows = connection.execute(
                """
                SELECT * FROM v5_script_versions
                WHERE workspace_ref = ? AND script_ref = ? ORDER BY version_number
                """,
                (workspace_ref, script_ref),
            ).fetchall()
        return [self._version(row) for row in rows]


class ScriptStudioService:
    """V5 owner for Script identity, immutable versions, and confirmation refs."""

    def __init__(
        self,
        repository: ScriptStudioRepository,
        upstream: UpstreamReader,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.upstream = upstream
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _script_mapping(record: ScriptRecord) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "seriesRef": record.seriesRef,
            "episodeRef": record.episodeRef,
            "scriptRef": record.scriptRef,
            "title": record.title,
            "currentScriptVersionRef": record.currentScriptVersionRef,
            "confirmedScriptVersionRef": record.confirmedScriptVersionRef,
            "createdAt": record.createdAt,
            "updatedAt": record.updatedAt,
            "version": record.version,
        }

    @staticmethod
    def _version_mapping(record: ScriptVersionRecord) -> dict[str, Any]:
        content = json.loads(record.contentJson)
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "seriesRef": record.seriesRef,
            "episodeRef": record.episodeRef,
            "scriptRef": record.scriptRef,
            "scriptVersionRef": record.scriptVersionRef,
            "sourcePlanRef": record.sourcePlanRef,
            "sourcePlanSchemaVersion": record.sourcePlanSchemaVersion,
            "sourcePlanVersion": record.sourcePlanVersion,
            "versionNumber": record.versionNumber,
            **content,
            "changeKind": record.changeKind,
            "parentScriptVersionRef": record.parentScriptVersionRef,
            "createdAt": record.createdAt,
        }

    def _bootstrap(self, workspace: str, series: str, episode: str) -> Mapping[str, Any]:
        bootstrap = _validate_bootstrap(
            self.upstream.build_script_studio_bootstrap(workspace, series, episode)
        )
        if (
            bootstrap["workspaceRef"] != workspace
            or bootstrap["seriesRef"] != series
            or bootstrap["episodeRef"] != episode
        ):
            raise ScopeMismatchError("Script Studio bootstrap scope does not match")
        return bootstrap

    def get_workspace(self, workspace_ref: str, series_ref: str, episode_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        episode = _required_ref(episode_ref, "episodeRef")
        bootstrap = dict(self._bootstrap(workspace, series, episode))
        script = self.repository.get_script(workspace, series, episode)
        if script is None:
            return {"bootstrap": bootstrap, "script": None, "versions": []}
        return {
            "bootstrap": bootstrap,
            "script": self._script_mapping(script),
            "versions": [
                self._version_mapping(item)
                for item in self.repository.list_versions(workspace, script.scriptRef)
            ],
        }

    def create_version(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ScriptStudioError("version input must be an object")
        workspace = _required_ref(value.get("workspaceRef"), "workspaceRef")
        series = _required_ref(value.get("seriesRef"), "seriesRef")
        episode = _required_ref(value.get("episodeRef"), "episodeRef")
        change_kind = _required_text(value.get("changeKind"), "changeKind", limit=40)
        if change_kind not in {"ai-generation", "manual-edit", "ai-scene-rewrite"}:
            raise ScriptStudioError("changeKind is invalid")
        bootstrap = self._bootstrap(workspace, series, episode)
        existing = self.repository.get_script(workspace, series, episode)
        now = self._clock()
        if existing is None:
            if change_kind != "ai-generation":
                raise RecordNotFoundError("Script must be generated before editing")
            script_ref = self._ref_factory("script")
            version_ref = self._ref_factory("script-version")
            content = _normalize_content(
                value.get("content"),
                bootstrap=bootstrap,
                ref_factory=self._ref_factory,
            )
            script = ScriptRecord(
                SCRIPT_SCHEMA_VERSION,
                workspace,
                series,
                episode,
                script_ref,
                content["title"],
                version_ref,
                None,
                now,
                now,
                1,
            )
            version = ScriptVersionRecord(
                SCRIPT_VERSION_SCHEMA_VERSION,
                workspace,
                series,
                episode,
                script_ref,
                version_ref,
                bootstrap["sourcePlanRef"],
                bootstrap["sourcePlanSchemaVersion"],
                bootstrap["sourcePlanVersion"],
                1,
                json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                change_kind,
                None,
                now,
            )
            stored_script, stored_version = self.repository.create_script_with_version(script, version)
        else:
            supplied_script = _required_ref(value.get("scriptRef"), "scriptRef")
            if supplied_script != existing.scriptRef:
                raise ScopeMismatchError("scriptRef does not belong to Episode")
            parent_ref = _required_ref(value.get("baseScriptVersionRef"), "baseScriptVersionRef")
            parent = self.repository.get_version(workspace, existing.scriptRef, parent_ref)
            if parent is None:
                raise RecordNotFoundError("base ScriptVersion was not found")
            refs = {scene["scriptSceneRef"] for scene in json.loads(parent.contentJson)["scenes"]}
            content = _normalize_content(
                value.get("content"),
                bootstrap=bootstrap,
                ref_factory=self._ref_factory,
                existing_scene_refs=refs,
            )
            next_number = max(
                item.versionNumber
                for item in self.repository.list_versions(workspace, existing.scriptRef)
            ) + 1
            version_ref = self._ref_factory("script-version")
            version = ScriptVersionRecord(
                SCRIPT_VERSION_SCHEMA_VERSION,
                workspace,
                series,
                episode,
                existing.scriptRef,
                version_ref,
                bootstrap["sourcePlanRef"],
                bootstrap["sourcePlanSchemaVersion"],
                bootstrap["sourcePlanVersion"],
                next_number,
                json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                change_kind,
                parent_ref,
                now,
            )
            updated = replace(
                existing,
                title=content["title"],
                currentScriptVersionRef=version_ref,
                updatedAt=now,
                version=existing.version + 1,
            )
            stored_script, stored_version = self.repository.append_version(
                updated,
                version,
                existing.version,
            )
        return {
            "script": self._script_mapping(stored_script),
            "scriptVersion": self._version_mapping(stored_version),
        }

    def confirm_version(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping) or value.get("humanConfirmed") is not True:
            raise ScriptStudioError("explicit human confirmation is required")
        workspace = _required_ref(value.get("workspaceRef"), "workspaceRef")
        series = _required_ref(value.get("seriesRef"), "seriesRef")
        episode = _required_ref(value.get("episodeRef"), "episodeRef")
        script_ref = _required_ref(value.get("scriptRef"), "scriptRef")
        version_ref = _required_ref(value.get("scriptVersionRef"), "scriptVersionRef")
        script = self.repository.get_script(workspace, series, episode)
        if script is None or script.scriptRef != script_ref:
            raise RecordNotFoundError("Script was not found")
        version = self.repository.get_version(workspace, script_ref, version_ref)
        if version is None or version.seriesRef != series or version.episodeRef != episode:
            raise RecordNotFoundError("ScriptVersion was not found")
        updated = replace(
            script,
            confirmedScriptVersionRef=version_ref,
            updatedAt=self._clock(),
            version=script.version + 1,
        )
        stored = self.repository.confirm_version(updated, script.version)
        return {
            "script": self._script_mapping(stored),
            "confirmedVersion": self._version_mapping(version),
        }

    def build_storyboard_bootstrap(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        episode = _required_ref(episode_ref, "episodeRef")
        script = self.repository.get_script(workspace, series, episode)
        if script is None:
            raise RecordNotFoundError("Script was not found")
        if script.confirmedScriptVersionRef is None:
            raise ScriptNotConfirmedError("confirmed ScriptVersion is required")
        version = self.repository.get_version(
            workspace,
            script.scriptRef,
            script.confirmedScriptVersionRef,
        )
        if version is None:
            raise RecordNotFoundError("confirmed ScriptVersion was not found")
        content = json.loads(version.contentJson)
        return {
            "schemaVersion": STORYBOARD_BOOTSTRAP_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "seriesRef": series,
            "episodeRef": episode,
            "scriptRef": script.scriptRef,
            "scriptVersionRef": version.scriptVersionRef,
            "sourcePlanRef": version.sourcePlanRef,
            "sourcePlanSchemaVersion": version.sourcePlanSchemaVersion,
            "sourcePlanVersion": version.sourcePlanVersion,
            "title": content["title"],
            "logline": content["logline"],
            "synopsis": content["synopsis"],
            "targetDurationSec": content["targetDurationSec"],
            "scenes": content["scenes"],
            "nextGate": "m4-ip-character-binding-required",
            "storyboardProductionAuthorized": False,
        }
