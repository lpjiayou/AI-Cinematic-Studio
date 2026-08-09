"""V5-owned Project context service, repository port, and local adapters."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4


PROJECT_SCHEMA_VERSION = "v5.project.v1"
PROJECT_SERIES_RELATIONSHIP_SCHEMA_VERSION = "v5.project-series-relationship.v1"
PROJECT_CONTEXT_SCHEMA_VERSION = "creator.project-context.v1"
SQLITE_SCHEMA_VERSION = 1
PROJECT_TYPES = frozenset({"series", "standalone", "product-video", "brand-film", "other"})


class ProjectContextError(ValueError):
    code = "invalid_request"


class ProjectRecordNotFoundError(ProjectContextError):
    code = "not_found"


class ProjectDuplicateError(ProjectContextError):
    code = "duplicate_record"


class ProjectScopeMismatchError(ProjectContextError):
    code = "scope_mismatch"


class ProjectLifecycleError(ProjectContextError):
    code = "lifecycle_conflict"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_text(value: Any, field: str, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProjectContextError(f"{field} is required")
    if len(text) > limit:
        raise ProjectContextError(f"{field} is too long")
    return text


def _required_ref(value: Any, field: str) -> str:
    text = _required_text(value, field, limit=200)
    if not text.isprintable() or any(character.isspace() for character in text):
        raise ProjectContextError(f"{field} is invalid")
    return text


def _optional_ref(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    return _required_ref(value, field)


def _positive_int(value: Any, field: str, *, maximum: int = 10_000) -> int:
    if isinstance(value, bool):
        raise ProjectContextError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectContextError(f"{field} must be an integer") from exc
    if result < 1 or result > maximum:
        raise ProjectContextError(f"{field} is out of range")
    return result


@dataclass(frozen=True)
class ProjectRecord:
    schemaVersion: str
    workspaceRef: str
    projectRef: str
    contentProfileRef: str
    projectType: str
    title: str
    description: str
    targetPlatform: str
    aspectRatio: str
    defaultDurationSec: int
    plannedEpisodeCount: int
    status: str
    createdAt: str
    updatedAt: str
    version: int


@dataclass(frozen=True)
class ProjectSeriesRelationship:
    schemaVersion: str
    workspaceRef: str
    projectRef: str
    seriesRef: str
    linkedAt: str
    version: int


class ProjectRepository(Protocol):
    def create_project(
        self,
        project: ProjectRecord,
        relationship: ProjectSeriesRelationship | None,
    ) -> tuple[ProjectRecord, ProjectSeriesRelationship | None]: ...

    def get_project(self, workspace_ref: str, project_ref: str) -> ProjectRecord | None: ...
    def list_projects(self, workspace_ref: str | None = None) -> list[ProjectRecord]: ...
    def list_series_relationships(
        self,
        workspace_ref: str,
        project_ref: str,
    ) -> list[ProjectSeriesRelationship]: ...
    def get_project_for_series(
        self,
        workspace_ref: str,
        series_ref: str,
    ) -> tuple[ProjectRecord, ProjectSeriesRelationship] | None: ...
    def archive_project(self, workspace_ref: str, project_ref: str, updated_at: str) -> ProjectRecord: ...


class InMemoryProjectAdapter:
    """Deterministic V5 Project repository adapter for tests only."""

    def __init__(self) -> None:
        self._projects: dict[tuple[str, str], ProjectRecord] = {}
        self._relationships: dict[tuple[str, str], ProjectSeriesRelationship] = {}
        self._lock = RLock()

    def create_project(
        self,
        project: ProjectRecord,
        relationship: ProjectSeriesRelationship | None,
    ) -> tuple[ProjectRecord, ProjectSeriesRelationship | None]:
        key = (project.workspaceRef, project.projectRef)
        with self._lock:
            if key in self._projects:
                raise ProjectDuplicateError("projectRef already exists in workspace")
            if relationship is not None:
                series_key = (relationship.workspaceRef, relationship.seriesRef)
                if series_key in self._relationships:
                    raise ProjectDuplicateError("seriesRef is already associated with a project")
                if relationship.workspaceRef != project.workspaceRef or relationship.projectRef != project.projectRef:
                    raise ProjectScopeMismatchError("project and series relationship do not match")
            self._projects[key] = project
            if relationship is not None:
                self._relationships[(relationship.workspaceRef, relationship.seriesRef)] = relationship
            return project, relationship

    def get_project(self, workspace_ref: str, project_ref: str) -> ProjectRecord | None:
        return self._projects.get((workspace_ref, project_ref))

    def list_projects(self, workspace_ref: str | None = None) -> list[ProjectRecord]:
        records = self._projects.values()
        if workspace_ref is not None:
            records = [record for record in records if record.workspaceRef == workspace_ref]
        return sorted(records, key=lambda item: (item.workspaceRef, item.createdAt, item.projectRef))

    def list_series_relationships(
        self,
        workspace_ref: str,
        project_ref: str,
    ) -> list[ProjectSeriesRelationship]:
        return sorted(
            (
                item
                for item in self._relationships.values()
                if item.workspaceRef == workspace_ref and item.projectRef == project_ref
            ),
            key=lambda item: (item.linkedAt, item.seriesRef),
        )

    def get_project_for_series(
        self,
        workspace_ref: str,
        series_ref: str,
    ) -> tuple[ProjectRecord, ProjectSeriesRelationship] | None:
        relationship = self._relationships.get((workspace_ref, series_ref))
        if relationship is None:
            return None
        project = self._projects.get((workspace_ref, relationship.projectRef))
        return (project, relationship) if project is not None else None

    def archive_project(self, workspace_ref: str, project_ref: str, updated_at: str) -> ProjectRecord:
        key = (workspace_ref, project_ref)
        with self._lock:
            project = self._projects.get(key)
            if project is None:
                raise ProjectRecordNotFoundError("project was not found")
            if project.status != "active":
                raise ProjectLifecycleError("only active projects can be archived")
            archived = replace(project, status="archived", updatedAt=updated_at, version=project.version + 1)
            self._projects[key] = archived
            return archived


class SqliteProjectAdapter:
    """SQLite local-development durable adapter; it is not production storage."""

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
                CREATE TABLE IF NOT EXISTS v5_project_schema (
                    component TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v5_projects (
                    workspace_ref TEXT NOT NULL,
                    project_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    content_profile_ref TEXT NOT NULL,
                    project_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_platform TEXT NOT NULL,
                    aspect_ratio TEXT NOT NULL,
                    default_duration_sec INTEGER NOT NULL CHECK(default_duration_sec > 0),
                    planned_episode_count INTEGER NOT NULL CHECK(planned_episode_count > 0),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, project_ref)
                );
                CREATE TABLE IF NOT EXISTS v5_project_series_relationships (
                    workspace_ref TEXT NOT NULL,
                    project_ref TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, project_ref, series_ref),
                    UNIQUE(workspace_ref, series_ref),
                    FOREIGN KEY(workspace_ref, project_ref)
                        REFERENCES v5_projects(workspace_ref, project_ref) ON DELETE RESTRICT
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO v5_project_schema VALUES (?, ?)",
                ("project_context", SQLITE_SCHEMA_VERSION),
            )
            row = connection.execute(
                "SELECT schema_version FROM v5_project_schema WHERE component = ?",
                ("project_context",),
            ).fetchone()
            if row is None or row["schema_version"] != SQLITE_SCHEMA_VERSION:
                raise RuntimeError("unsupported Project local-development schema version")

    @staticmethod
    def _project(row: sqlite3.Row) -> ProjectRecord:
        return ProjectRecord(
            row["schema_version"], row["workspace_ref"], row["project_ref"],
            row["content_profile_ref"], row["project_type"], row["title"],
            row["description"], row["target_platform"], row["aspect_ratio"],
            row["default_duration_sec"], row["planned_episode_count"], row["status"],
            row["created_at"], row["updated_at"], row["version"],
        )

    @staticmethod
    def _relationship(row: sqlite3.Row) -> ProjectSeriesRelationship:
        return ProjectSeriesRelationship(
            row["schema_version"], row["workspace_ref"], row["project_ref"],
            row["series_ref"], row["linked_at"], row["version"],
        )

    def create_project(
        self,
        project: ProjectRecord,
        relationship: ProjectSeriesRelationship | None,
    ) -> tuple[ProjectRecord, ProjectSeriesRelationship | None]:
        try:
            with self._lock, self._session() as connection:
                connection.execute(
                    "INSERT INTO v5_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        project.workspaceRef, project.projectRef, project.schemaVersion,
                        project.contentProfileRef, project.projectType, project.title,
                        project.description, project.targetPlatform, project.aspectRatio,
                        project.defaultDurationSec, project.plannedEpisodeCount, project.status,
                        project.createdAt, project.updatedAt, project.version,
                    ),
                )
                if relationship is not None:
                    connection.execute(
                        "INSERT INTO v5_project_series_relationships VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            relationship.workspaceRef, relationship.projectRef,
                            relationship.seriesRef, relationship.schemaVersion,
                            relationship.linkedAt, relationship.version,
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            raise ProjectDuplicateError("project or series relationship already exists") from exc
        return project, relationship

    def get_project(self, workspace_ref: str, project_ref: str) -> ProjectRecord | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_projects WHERE workspace_ref = ? AND project_ref = ?",
                (workspace_ref, project_ref),
            ).fetchone()
        return self._project(row) if row else None

    def list_projects(self, workspace_ref: str | None = None) -> list[ProjectRecord]:
        with self._session() as connection:
            if workspace_ref is None:
                rows = connection.execute(
                    "SELECT * FROM v5_projects ORDER BY workspace_ref, created_at, project_ref"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM v5_projects WHERE workspace_ref = ? ORDER BY created_at, project_ref",
                    (workspace_ref,),
                ).fetchall()
        return [self._project(row) for row in rows]

    def list_series_relationships(
        self,
        workspace_ref: str,
        project_ref: str,
    ) -> list[ProjectSeriesRelationship]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM v5_project_series_relationships WHERE workspace_ref = ? AND project_ref = ? ORDER BY linked_at, series_ref",
                (workspace_ref, project_ref),
            ).fetchall()
        return [self._relationship(row) for row in rows]

    def get_project_for_series(
        self,
        workspace_ref: str,
        series_ref: str,
    ) -> tuple[ProjectRecord, ProjectSeriesRelationship] | None:
        with self._session() as connection:
            row = connection.execute(
                """
                SELECT p.*, r.schema_version AS relationship_schema_version,
                       r.series_ref, r.linked_at, r.version AS relationship_version
                FROM v5_project_series_relationships r
                JOIN v5_projects p
                  ON p.workspace_ref = r.workspace_ref AND p.project_ref = r.project_ref
                WHERE r.workspace_ref = ? AND r.series_ref = ?
                """,
                (workspace_ref, series_ref),
            ).fetchone()
        if row is None:
            return None
        project = self._project(row)
        relationship = ProjectSeriesRelationship(
            row["relationship_schema_version"], row["workspace_ref"], row["project_ref"],
            row["series_ref"], row["linked_at"], row["relationship_version"],
        )
        return project, relationship

    def archive_project(self, workspace_ref: str, project_ref: str, updated_at: str) -> ProjectRecord:
        with self._lock, self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_projects WHERE workspace_ref = ? AND project_ref = ?",
                (workspace_ref, project_ref),
            ).fetchone()
            if row is None:
                raise ProjectRecordNotFoundError("project was not found")
            project = self._project(row)
            if project.status != "active":
                raise ProjectLifecycleError("only active projects can be archived")
            connection.execute(
                "UPDATE v5_projects SET status = 'archived', updated_at = ?, version = version + 1 WHERE workspace_ref = ? AND project_ref = ?",
                (updated_at, workspace_ref, project_ref),
            )
            updated = connection.execute(
                "SELECT * FROM v5_projects WHERE workspace_ref = ? AND project_ref = ?",
                (workspace_ref, project_ref),
            ).fetchone()
        return self._project(updated)


class ProjectContextService:
    """V5 owner for Project facts and Project-to-Series relationships."""

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        get_series: Callable[[str, str], Mapping[str, Any]],
        get_episode: Callable[[str, str, str], Mapping[str, Any]],
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self._get_series = get_series
        self._get_episode = get_episode
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _project_mapping(record: ProjectRecord, series_refs: list[str]) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "projectRef": record.projectRef,
            "contentProfileRef": record.contentProfileRef,
            "projectType": record.projectType,
            "title": record.title,
            "description": record.description,
            "targetPlatform": record.targetPlatform,
            "aspectRatio": record.aspectRatio,
            "defaultDurationSec": record.defaultDurationSec,
            "plannedEpisodeCount": record.plannedEpisodeCount,
            "status": record.status,
            "seriesRefs": series_refs,
            "createdAt": record.createdAt,
            "updatedAt": record.updatedAt,
            "version": record.version,
        }

    def _mapping(self, record: ProjectRecord) -> dict[str, Any]:
        relationships = self.repository.list_series_relationships(record.workspaceRef, record.projectRef)
        return self._project_mapping(record, [item.seriesRef for item in relationships])

    def _resolve_series(self, workspace_ref: str, series_ref: str) -> Mapping[str, Any]:
        try:
            return self._get_series(workspace_ref, series_ref)
        except Exception as exc:
            if getattr(exc, "code", "") == "not_found":
                raise ProjectRecordNotFoundError("series was not found") from None
            raise

    def create_project(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ProjectContextError("project input must be an object")
        workspace_ref = _required_ref(value.get("workspaceRef"), "workspaceRef")
        content_profile_ref = _required_ref(value.get("contentProfileRef"), "contentProfileRef")
        project_type = _required_ref(value.get("projectType"), "projectType")
        if project_type not in PROJECT_TYPES:
            raise ProjectContextError("projectType is invalid")
        series_ref = _optional_ref(value.get("seriesRef"), "seriesRef")
        if project_type == "series" and series_ref is None:
            raise ProjectContextError("seriesRef is required for a series project")
        if series_ref is not None:
            series = self._resolve_series(workspace_ref, series_ref)
            if series.get("contentProfileRef") != content_profile_ref:
                raise ProjectScopeMismatchError("Project and Series content profiles do not match")
        now = self._clock()
        project_ref = self._ref_factory("project")
        project = ProjectRecord(
            PROJECT_SCHEMA_VERSION,
            workspace_ref,
            project_ref,
            content_profile_ref,
            project_type,
            _required_text(value.get("title"), "title"),
            str(value.get("description") or "").strip()[:2000],
            str(value.get("targetPlatform") or "").strip()[:200],
            _required_text(value.get("aspectRatio", "9:16"), "aspectRatio", limit=20),
            _positive_int(value.get("defaultDurationSec", 60), "defaultDurationSec", maximum=86_400),
            _positive_int(value.get("plannedEpisodeCount", 1), "plannedEpisodeCount"),
            "active",
            now,
            now,
            1,
        )
        relationship = (
            ProjectSeriesRelationship(
                PROJECT_SERIES_RELATIONSHIP_SCHEMA_VERSION,
                workspace_ref,
                project_ref,
                series_ref,
                now,
                1,
            )
            if series_ref is not None
            else None
        )
        stored, _ = self.repository.create_project(project, relationship)
        return self._mapping(stored)

    def get_project(self, workspace_ref: str, project_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        record = self.repository.get_project(workspace, _required_ref(project_ref, "projectRef"))
        if record is None:
            raise ProjectRecordNotFoundError("project was not found")
        return self._mapping(record)

    def list_projects(self, workspace_ref: str) -> list[dict[str, Any]]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        return [self._mapping(item) for item in self.repository.list_projects(workspace)]

    def get_project_for_series(self, workspace_ref: str, series_ref: str) -> dict[str, Any] | None:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        result = self.repository.get_project_for_series(workspace, series)
        return self._mapping(result[0]) if result is not None else None

    def build_context(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str | None = None,
        episode_ref: str | None = None,
    ) -> dict[str, Any]:
        project = self.get_project(workspace_ref, project_ref)
        selected_series_ref = _optional_ref(series_ref, "seriesRef")
        relationships = project["seriesRefs"]
        if selected_series_ref is None:
            selected_series_ref = relationships[0] if len(relationships) == 1 else None
        if selected_series_ref is not None and selected_series_ref not in relationships:
            raise ProjectScopeMismatchError("series is not associated with project")
        series = self._resolve_series(project["workspaceRef"], selected_series_ref) if selected_series_ref else None
        selected_episode_ref = _optional_ref(episode_ref, "episodeRef")
        episode = None
        if selected_episode_ref is not None:
            if selected_series_ref is None:
                raise ProjectScopeMismatchError("episode requires an associated series")
            try:
                episode = self._get_episode(project["workspaceRef"], selected_series_ref, selected_episode_ref)
            except Exception as exc:
                if getattr(exc, "code", "") == "not_found":
                    raise ProjectRecordNotFoundError("episode was not found") from None
                raise
        return {
            "schemaVersion": PROJECT_CONTEXT_SCHEMA_VERSION,
            "workspaceRef": project["workspaceRef"],
            "contentProfileRef": project["contentProfileRef"],
            "projectRef": project["projectRef"],
            "seriesRef": selected_series_ref,
            "episodeRef": selected_episode_ref,
            "project": project,
            "series": series,
            "episode": episode,
        }

    def archive_project(self, workspace_ref: str, project_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        project = _required_ref(project_ref, "projectRef")
        return self._mapping(self.repository.archive_project(workspace, project, self._clock()))
