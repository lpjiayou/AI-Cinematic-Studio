"""Authoritative SQLite V2 schema for the bounded lifecycle relationships."""

SQLITE_LIFECYCLE_SCHEMA_VERSION = 2

MARKERS = {
    "v5_series_episode_schema": "series_episode",
    "v5_project_schema": "project_context",
    "v5_script_studio_schema": "script_studio",
    "v5_series_planning_schema": "series_planning",
}

TABLE_COLUMNS = {
    "v5_series": "workspace_ref,series_ref,schema_version,content_profile_ref,title,description,status,planned_episode_count,created_at,updated_at,version",
    "v5_confirmed_creative_plans": "workspace_ref,creative_plan_ref,schema_version,source_plan_ref,source_plan_schema_version,source_plan_version,brief_json,source_plan_json,confirmation_status,confirmed_at,version",
    "v5_projects": "workspace_ref,project_ref,schema_version,content_profile_ref,project_type,title,description,target_platform,aspect_ratio,default_duration_sec,planned_episode_count,status,created_at,updated_at,version",
    "v5_project_series_relationships": "workspace_ref,project_ref,series_ref,schema_version,linked_at,version",
    "v5_episode_projects": "workspace_ref,episode_ref,schema_version,series_ref,episode_number,season_number,volume_number,title,status,canonical_project_ref,creative_plan_ref,created_at,updated_at,version",
    "v5_episode_plan_bindings": "workspace_ref,series_ref,episode_ref,schema_version,creative_plan_ref,source_plan_ref,source_plan_schema_version,source_plan_version,brief_json,source_plan_json,bound_at,version",
    "v5_scripts": "workspace_ref,series_ref,episode_ref,script_ref,schema_version,title,current_script_version_ref,confirmed_script_version_ref,created_at,updated_at,version",
    "v5_script_versions": "workspace_ref,script_ref,script_version_ref,schema_version,series_ref,episode_ref,source_plan_ref,source_plan_schema_version,source_plan_version,version_number,content_json,change_kind,parent_script_version_ref,created_at",
    "v5_series_plans": "workspace_ref,series_plan_ref,schema_version,content_profile_ref,project_ref,series_ref,current_version_ref,confirmed_version_ref,status,created_at,updated_at,version",
    "v5_series_plan_versions": "workspace_ref,series_plan_ref,series_plan_version_ref,schema_version,content_profile_ref,project_ref,series_ref,version_number,content_json,change_kind,parent_version_ref,created_at",
}

TABLE_ORDER = tuple(TABLE_COLUMNS)
DROP_ORDER = tuple(reversed(TABLE_ORDER))


def table_statements(names: dict[str, str] | None = None) -> tuple[str, ...]:
    n = {name: name for name in TABLE_ORDER}
    n.update(names or {})
    return (
        f"""CREATE TABLE {n['v5_series']} (workspace_ref TEXT NOT NULL, series_ref TEXT NOT NULL, schema_version TEXT NOT NULL, content_profile_ref TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, planned_episode_count INTEGER NOT NULL CHECK(planned_episode_count > 0), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, series_ref))""",
        f"""CREATE TABLE {n['v5_confirmed_creative_plans']} (workspace_ref TEXT NOT NULL, creative_plan_ref TEXT NOT NULL, schema_version TEXT NOT NULL, source_plan_ref TEXT NOT NULL, source_plan_schema_version TEXT NOT NULL, source_plan_version INTEGER NOT NULL, brief_json TEXT NOT NULL, source_plan_json TEXT NOT NULL, confirmation_status TEXT NOT NULL CHECK(confirmation_status = 'confirmed'), confirmed_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, creative_plan_ref))""",
        f"""CREATE TABLE {n['v5_projects']} (workspace_ref TEXT NOT NULL, project_ref TEXT NOT NULL, schema_version TEXT NOT NULL, content_profile_ref TEXT NOT NULL, project_type TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, target_platform TEXT NOT NULL, aspect_ratio TEXT NOT NULL, default_duration_sec INTEGER NOT NULL CHECK(default_duration_sec > 0), planned_episode_count INTEGER NOT NULL CHECK(planned_episode_count > 0), status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, project_ref))""",
        f"""CREATE TABLE {n['v5_project_series_relationships']} (workspace_ref TEXT NOT NULL, project_ref TEXT NOT NULL, series_ref TEXT NOT NULL, schema_version TEXT NOT NULL, linked_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, project_ref, series_ref), UNIQUE(workspace_ref, series_ref), FOREIGN KEY(workspace_ref, project_ref) REFERENCES {n['v5_projects']}(workspace_ref, project_ref) ON DELETE RESTRICT, FOREIGN KEY(workspace_ref, series_ref) REFERENCES {n['v5_series']}(workspace_ref, series_ref) ON DELETE RESTRICT)""",
        f"""CREATE TABLE {n['v5_episode_projects']} (workspace_ref TEXT NOT NULL, episode_ref TEXT NOT NULL, schema_version TEXT NOT NULL, series_ref TEXT NOT NULL, episode_number INTEGER NOT NULL CHECK(episode_number > 0), season_number INTEGER NOT NULL CHECK(season_number > 0), volume_number INTEGER NOT NULL CHECK(volume_number > 0), title TEXT NOT NULL, status TEXT NOT NULL, canonical_project_ref TEXT, creative_plan_ref TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, series_ref, episode_ref), UNIQUE(workspace_ref, series_ref, episode_number), FOREIGN KEY(workspace_ref, series_ref) REFERENCES {n['v5_series']}(workspace_ref, series_ref) ON DELETE RESTRICT, FOREIGN KEY(workspace_ref, creative_plan_ref) REFERENCES {n['v5_confirmed_creative_plans']}(workspace_ref, creative_plan_ref) ON DELETE RESTRICT)""",
        f"""CREATE TABLE {n['v5_episode_plan_bindings']} (workspace_ref TEXT NOT NULL, series_ref TEXT NOT NULL, episode_ref TEXT NOT NULL, schema_version TEXT NOT NULL, creative_plan_ref TEXT NOT NULL, source_plan_ref TEXT NOT NULL, source_plan_schema_version TEXT NOT NULL, source_plan_version INTEGER NOT NULL, brief_json TEXT NOT NULL, source_plan_json TEXT NOT NULL, bound_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, series_ref, episode_ref), FOREIGN KEY(workspace_ref, series_ref, episode_ref) REFERENCES {n['v5_episode_projects']}(workspace_ref, series_ref, episode_ref) ON DELETE RESTRICT, FOREIGN KEY(workspace_ref, creative_plan_ref) REFERENCES {n['v5_confirmed_creative_plans']}(workspace_ref, creative_plan_ref) ON DELETE RESTRICT)""",
        f"""CREATE TABLE {n['v5_scripts']} (workspace_ref TEXT NOT NULL, series_ref TEXT NOT NULL, episode_ref TEXT NOT NULL, script_ref TEXT NOT NULL, schema_version TEXT NOT NULL, title TEXT NOT NULL, current_script_version_ref TEXT NOT NULL, confirmed_script_version_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, script_ref), UNIQUE(workspace_ref, series_ref, episode_ref), UNIQUE(workspace_ref, script_ref, series_ref, episode_ref), FOREIGN KEY(workspace_ref, series_ref, episode_ref) REFERENCES {n['v5_episode_projects']}(workspace_ref, series_ref, episode_ref) ON DELETE RESTRICT)""",
        f"""CREATE TABLE {n['v5_script_versions']} (workspace_ref TEXT NOT NULL, script_ref TEXT NOT NULL, script_version_ref TEXT NOT NULL, schema_version TEXT NOT NULL, series_ref TEXT NOT NULL, episode_ref TEXT NOT NULL, source_plan_ref TEXT NOT NULL, source_plan_schema_version TEXT NOT NULL, source_plan_version INTEGER NOT NULL, version_number INTEGER NOT NULL, content_json TEXT NOT NULL, change_kind TEXT NOT NULL, parent_script_version_ref TEXT, created_at TEXT NOT NULL, PRIMARY KEY(workspace_ref, script_ref, script_version_ref), UNIQUE(workspace_ref, script_ref, version_number), FOREIGN KEY(workspace_ref, script_ref, series_ref, episode_ref) REFERENCES {n['v5_scripts']}(workspace_ref, script_ref, series_ref, episode_ref) ON DELETE RESTRICT, FOREIGN KEY(workspace_ref, series_ref, episode_ref) REFERENCES {n['v5_episode_projects']}(workspace_ref, series_ref, episode_ref) ON DELETE RESTRICT)""",
        f"""CREATE TABLE {n['v5_series_plans']} (workspace_ref TEXT NOT NULL, series_plan_ref TEXT NOT NULL, schema_version TEXT NOT NULL, content_profile_ref TEXT NOT NULL, project_ref TEXT NOT NULL, series_ref TEXT NOT NULL, current_version_ref TEXT NOT NULL, confirmed_version_ref TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(workspace_ref, series_plan_ref), UNIQUE(workspace_ref, project_ref, series_ref), FOREIGN KEY(workspace_ref, project_ref, series_ref) REFERENCES {n['v5_project_series_relationships']}(workspace_ref, project_ref, series_ref) ON DELETE RESTRICT)""",
        f"""CREATE TABLE {n['v5_series_plan_versions']} (workspace_ref TEXT NOT NULL, series_plan_ref TEXT NOT NULL, series_plan_version_ref TEXT NOT NULL, schema_version TEXT NOT NULL, content_profile_ref TEXT NOT NULL, project_ref TEXT NOT NULL, series_ref TEXT NOT NULL, version_number INTEGER NOT NULL, content_json TEXT NOT NULL, change_kind TEXT NOT NULL, parent_version_ref TEXT, created_at TEXT NOT NULL, PRIMARY KEY(workspace_ref, series_plan_ref, series_plan_version_ref), UNIQUE(workspace_ref, series_plan_ref, version_number), FOREIGN KEY(workspace_ref, series_plan_ref) REFERENCES {n['v5_series_plans']}(workspace_ref, series_plan_ref) ON DELETE RESTRICT)""",
    )


def index_statements() -> tuple[str, ...]:
    return (
        "CREATE INDEX IF NOT EXISTS ix_project_series_parent ON v5_project_series_relationships(workspace_ref, series_ref)",
        "CREATE INDEX IF NOT EXISTS ix_episode_series_parent ON v5_episode_projects(workspace_ref, series_ref)",
        "CREATE INDEX IF NOT EXISTS ix_script_episode_parent ON v5_scripts(workspace_ref, series_ref, episode_ref)",
        "CREATE INDEX IF NOT EXISTS ix_script_version_episode_parent ON v5_script_versions(workspace_ref, series_ref, episode_ref)",
    )
