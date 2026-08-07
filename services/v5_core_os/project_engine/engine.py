"""Dependency-free in-memory foundation for the V5 Project Engine MVP."""

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Optional, Sequence

from .errors import (
    DuplicateProjectError,
    InvalidProjectLifecycleTransitionError,
    ProjectNotFoundError,
    ValidationError,
)
from .models import Project, ProjectLifecycleState

Clock = Callable[[], datetime]


class ProjectEngine:
    """Create, query, list, and archive process-local projects.

    Workspace and owner references are stored as opaque identifiers. This
    engine does not resolve them, make access decisions, or expose transport
    and persistence behavior.
    """

    def __init__(self, *, clock: Optional[Clock] = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._projects: Dict[str, Project] = {}
        self._lock = RLock()

    def create_project(
        self,
        *,
        project_id: str,
        workspace_id: str,
        owner_identity_id: str,
    ) -> Project:
        """Create an active project with opaque workspace and owner references."""

        normalized_project_id = self._identifier(project_id, "project_id")
        normalized_workspace_id = self._identifier(workspace_id, "workspace_id")
        normalized_owner_identity_id = self._identifier(
            owner_identity_id,
            "owner_identity_id",
        )

        with self._lock:
            if normalized_project_id in self._projects:
                raise DuplicateProjectError(
                    "Project already exists: {}".format(normalized_project_id)
                )

            timestamp = self._timestamp()
            project = Project(
                project_id=normalized_project_id,
                workspace_id=normalized_workspace_id,
                owner_identity_id=normalized_owner_identity_id,
                lifecycle_state=ProjectLifecycleState.ACTIVE,
                created_at=timestamp,
                updated_at=timestamp,
            )
            self._projects[normalized_project_id] = project
            return project

    def get_project(self, project_id: str) -> Project:
        """Return a project by its opaque identifier."""

        normalized_project_id = self._identifier(project_id, "project_id")
        with self._lock:
            try:
                return self._projects[normalized_project_id]
            except KeyError as error:
                raise ProjectNotFoundError(
                    "Project not found: {}".format(normalized_project_id)
                ) from error

    def list_projects(self) -> Sequence[Project]:
        """Return an immutable snapshot of all projects without ordering promises."""

        with self._lock:
            return tuple(self._projects.values())

    def archive_project(self, project_id: str) -> Project:
        """Move an active project to the archived lifecycle state."""

        normalized_project_id = self._identifier(project_id, "project_id")
        with self._lock:
            try:
                project = self._projects[normalized_project_id]
            except KeyError as error:
                raise ProjectNotFoundError(
                    "Project not found: {}".format(normalized_project_id)
                ) from error

            if project.lifecycle_state is not ProjectLifecycleState.ACTIVE:
                raise InvalidProjectLifecycleTransitionError(
                    "Only active projects can be archived"
                )

            archived_project = replace(
                project,
                lifecycle_state=ProjectLifecycleState.ARCHIVED,
                updated_at=self._timestamp(),
            )
            self._projects[normalized_project_id] = archived_project
            return archived_project

    def _timestamp(self) -> datetime:
        timestamp = self._clock()
        if not isinstance(timestamp, datetime):
            raise ValidationError("clock must return a datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValidationError("clock must return a timezone-aware datetime")
        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _identifier(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError("{} must be a string".format(field_name))
        if not value or value != value.strip():
            raise ValidationError(
                "{} must be non-empty and contain no surrounding whitespace".format(
                    field_name
                )
            )
        if not value.isprintable() or any(character.isspace() for character in value):
            raise ValidationError(
                "{} must contain printable, non-whitespace characters only".format(
                    field_name
                )
            )
        return value
