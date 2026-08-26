"""Additive SQLite schema for durable canonical registration receipts."""

MARKER_TABLE = "v5_canonical_registration_schema"
MARKER_COMPONENT = "canonical_registration"
TABLE = "v5_canonical_registrations"
SCHEMA_VERSION = 1
INDEX = "ix_canonical_registration_episode_parent"


def table_statement() -> str:
    return f"""CREATE TABLE {TABLE} (
        workspace_ref TEXT NOT NULL,
        registration_ref TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        canonical_target_ref TEXT NOT NULL,
        canonical_target_digest TEXT NOT NULL,
        registration_key TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        package_digest TEXT NOT NULL,
        request_json TEXT NOT NULL,
        request_digest TEXT NOT NULL,
        project_ref TEXT NOT NULL,
        series_ref TEXT NOT NULL,
        episode_ref TEXT NOT NULL,
        creative_plan_ref TEXT NOT NULL,
        script_ref TEXT NOT NULL,
        script_version_ref TEXT NOT NULL,
        acceptance_ref TEXT NOT NULL,
        result_json TEXT NOT NULL,
        result_digest TEXT NOT NULL,
        receipt_digest TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        publication_allowed INTEGER NOT NULL CHECK(publication_allowed = 0),
        PRIMARY KEY(workspace_ref, registration_ref),
        UNIQUE(workspace_ref, registration_key),
        UNIQUE(workspace_ref, idempotency_key),
        FOREIGN KEY(workspace_ref, project_ref, series_ref)
            REFERENCES v5_project_series_relationships(
                workspace_ref, project_ref, series_ref
            ) ON DELETE RESTRICT,
        FOREIGN KEY(workspace_ref, series_ref, episode_ref)
            REFERENCES v5_episode_projects(
                workspace_ref, series_ref, episode_ref
            ) ON DELETE RESTRICT,
        FOREIGN KEY(workspace_ref, creative_plan_ref)
            REFERENCES v5_confirmed_creative_plans(
                workspace_ref, creative_plan_ref
            ) ON DELETE RESTRICT,
        FOREIGN KEY(workspace_ref, script_ref, script_version_ref)
            REFERENCES v5_script_acceptances(
                workspace_ref, script_ref, script_version_ref
            ) ON DELETE RESTRICT
    )"""


def index_statement() -> str:
    return (
        f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE}"
        "(workspace_ref, series_ref, episode_ref)"
    )


def marker_statement() -> str:
    return (
        f"CREATE TABLE {MARKER_TABLE} ("
        "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
    )


__all__ = [
    "INDEX",
    "MARKER_COMPONENT",
    "MARKER_TABLE",
    "SCHEMA_VERSION",
    "TABLE",
    "index_statement",
    "marker_statement",
    "table_statement",
]
