"""Additive SQLite schema for the bounded M6 durable local-development slice."""

from __future__ import annotations


SQLITE_SERIES_INTELLIGENCE_SCHEMA_VERSION = 1
MARKER_TABLE = "v5_series_intelligence_schema"
MARKER_COMPONENT = "series_intelligence"

SCOPE_COLUMNS = (
    "business_domain",
    "tenant_id",
    "workspace_ref",
    "project_ref",
    "series_ref",
)
SCOPE_SQL = ", ".join(
    f"{column} TEXT NOT NULL CHECK(length(trim({column})) > 0)"
    for column in SCOPE_COLUMNS
)
SCOPE_KEY_SQL = ", ".join(SCOPE_COLUMNS)

M6_TABLE_COLUMNS = {
    "v5_m6_series_bibles": (
        *SCOPE_COLUMNS, "schema_version", "series_bible_ref",
        "current_series_bible_version_ref", "confirmed_series_bible_version_ref",
        "revision", "created_at", "updated_at", "record_json",
    ),
    "v5_m6_series_bible_versions": (
        *SCOPE_COLUMNS, "schema_version", "series_bible_ref",
        "series_bible_version_ref", "version_number",
        "parent_series_bible_version_ref", "series_plan_ref",
        "series_plan_version_ref", "series_plan_version_digest",
        "canonical_schema_version", "content_digest", "canonical_digest",
        "status", "content_json", "record_json",
    ),
    "v5_m6_character_continuities": (
        *SCOPE_COLUMNS, "schema_version", "character_continuity_ref",
        "current_character_continuity_version_ref",
        "confirmed_character_continuity_version_ref", "revision", "created_at",
        "updated_at", "record_json",
    ),
    "v5_m6_character_continuity_versions": (
        *SCOPE_COLUMNS, "schema_version", "character_continuity_ref",
        "character_continuity_version_ref", "version_number",
        "parent_character_continuity_version_ref", "series_plan_ref",
        "series_plan_version_ref", "series_plan_version_digest",
        "series_bible_ref", "series_bible_version_ref",
        "series_bible_version_digest", "canonical_schema_version",
        "content_digest", "canonical_digest", "status", "content_json",
        "record_json",
    ),
    "v5_m6_baseline_snapshots": (
        *SCOPE_COLUMNS, "schema_version", "m6_baseline_snapshot_ref",
        "activation_revision", "series_plan_ref", "series_plan_version_ref",
        "series_plan_version_digest", "series_bible_ref",
        "series_bible_version_ref", "series_bible_version_digest",
        "character_continuity_ref", "character_continuity_version_ref",
        "character_continuity_version_digest", "canonical_schema_version",
        "content_digest", "canonical_digest", "status", "approval_ref",
        "confirmed_by_actor_ref", "confirmed_at", "superseded_at", "record_json",
    ),
    "v5_m6_operations": (
        *SCOPE_COLUMNS, "idempotency_key", "operation_ref", "operation_type",
        "input_digest", "result_json",
    ),
    "v5_m6_outbox": (
        "position", *SCOPE_COLUMNS, "event_id", "event_type", "event_version",
        "aggregate_type", "aggregate_ref", "operation_ref", "correlation_id",
        "causation_id", "occurred_at", "event_json",
    ),
}
M6_TABLES = tuple(M6_TABLE_COLUMNS)


def table_statements() -> tuple[str, ...]:
    scope = SCOPE_SQL
    scope_key = SCOPE_KEY_SQL
    m5_parent = (
        "workspace_ref, project_ref, series_ref, series_plan_ref, "
        "series_plan_version_ref"
    )
    return (
        f"""CREATE TABLE v5_m6_series_bibles (
            {scope},
            schema_version TEXT NOT NULL,
            series_bible_ref TEXT NOT NULL,
            current_series_bible_version_ref TEXT NOT NULL,
            confirmed_series_bible_version_ref TEXT,
            revision INTEGER NOT NULL CHECK(revision > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY({scope_key}),
            UNIQUE({scope_key}, series_bible_ref),
            FOREIGN KEY({scope_key}, series_bible_ref, current_series_bible_version_ref)
                REFERENCES v5_m6_series_bible_versions(
                    {scope_key}, series_bible_ref, series_bible_version_ref
                ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY({scope_key}, series_bible_ref, confirmed_series_bible_version_ref)
                REFERENCES v5_m6_series_bible_versions(
                    {scope_key}, series_bible_ref, series_bible_version_ref
                ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
        )""",
        f"""CREATE TABLE v5_m6_series_bible_versions (
            {scope},
            schema_version TEXT NOT NULL,
            series_bible_ref TEXT NOT NULL,
            series_bible_version_ref TEXT NOT NULL,
            version_number INTEGER NOT NULL CHECK(version_number > 0),
            parent_series_bible_version_ref TEXT,
            series_plan_ref TEXT NOT NULL,
            series_plan_version_ref TEXT NOT NULL,
            series_plan_version_digest TEXT NOT NULL,
            canonical_schema_version TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            canonical_digest TEXT NOT NULL CHECK(canonical_digest = content_digest),
            status TEXT NOT NULL CHECK(status IN ('DRAFT','CANDIDATE','CONFIRMED')),
            content_json TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY({scope_key}, series_bible_ref, series_bible_version_ref),
            UNIQUE({scope_key}, series_bible_ref, version_number),
            UNIQUE({scope_key}, series_bible_ref, series_bible_version_ref, content_digest),
            FOREIGN KEY({scope_key}, series_bible_ref)
                REFERENCES v5_m6_series_bibles({scope_key}, series_bible_ref)
                ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY({scope_key}, series_bible_ref, parent_series_bible_version_ref)
                REFERENCES v5_m6_series_bible_versions(
                    {scope_key}, series_bible_ref, series_bible_version_ref
                ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY({m5_parent})
                REFERENCES v5_series_plan_versions({m5_parent}) ON DELETE RESTRICT
        )""",
        f"""CREATE TABLE v5_m6_character_continuities (
            {scope},
            schema_version TEXT NOT NULL,
            character_continuity_ref TEXT NOT NULL,
            current_character_continuity_version_ref TEXT NOT NULL,
            confirmed_character_continuity_version_ref TEXT,
            revision INTEGER NOT NULL CHECK(revision > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY({scope_key}),
            UNIQUE({scope_key}, character_continuity_ref),
            FOREIGN KEY({scope_key}, character_continuity_ref, current_character_continuity_version_ref)
                REFERENCES v5_m6_character_continuity_versions(
                    {scope_key}, character_continuity_ref, character_continuity_version_ref
                ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY({scope_key}, character_continuity_ref, confirmed_character_continuity_version_ref)
                REFERENCES v5_m6_character_continuity_versions(
                    {scope_key}, character_continuity_ref, character_continuity_version_ref
                ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
        )""",
        f"""CREATE TABLE v5_m6_character_continuity_versions (
            {scope},
            schema_version TEXT NOT NULL,
            character_continuity_ref TEXT NOT NULL,
            character_continuity_version_ref TEXT NOT NULL,
            version_number INTEGER NOT NULL CHECK(version_number > 0),
            parent_character_continuity_version_ref TEXT,
            series_plan_ref TEXT NOT NULL,
            series_plan_version_ref TEXT NOT NULL,
            series_plan_version_digest TEXT NOT NULL,
            series_bible_ref TEXT NOT NULL,
            series_bible_version_ref TEXT NOT NULL,
            series_bible_version_digest TEXT NOT NULL,
            canonical_schema_version TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            canonical_digest TEXT NOT NULL CHECK(canonical_digest = content_digest),
            status TEXT NOT NULL CHECK(status IN ('DRAFT','CANDIDATE','CONFIRMED')),
            content_json TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY({scope_key}, character_continuity_ref, character_continuity_version_ref),
            UNIQUE({scope_key}, character_continuity_ref, version_number),
            UNIQUE({scope_key}, character_continuity_ref, character_continuity_version_ref, content_digest),
            FOREIGN KEY({scope_key}, character_continuity_ref)
                REFERENCES v5_m6_character_continuities({scope_key}, character_continuity_ref)
                ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY({scope_key}, character_continuity_ref, parent_character_continuity_version_ref)
                REFERENCES v5_m6_character_continuity_versions(
                    {scope_key}, character_continuity_ref, character_continuity_version_ref
                ) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY(
                {scope_key}, series_bible_ref, series_bible_version_ref,
                series_bible_version_digest
            ) REFERENCES v5_m6_series_bible_versions(
                {scope_key}, series_bible_ref, series_bible_version_ref, content_digest
            ) ON DELETE RESTRICT,
            FOREIGN KEY({m5_parent})
                REFERENCES v5_series_plan_versions({m5_parent}) ON DELETE RESTRICT
        )""",
        f"""CREATE TABLE v5_m6_baseline_snapshots (
            {scope},
            schema_version TEXT NOT NULL,
            m6_baseline_snapshot_ref TEXT NOT NULL,
            activation_revision INTEGER NOT NULL CHECK(activation_revision > 0),
            series_plan_ref TEXT NOT NULL,
            series_plan_version_ref TEXT NOT NULL,
            series_plan_version_digest TEXT NOT NULL,
            series_bible_ref TEXT NOT NULL,
            series_bible_version_ref TEXT NOT NULL,
            series_bible_version_digest TEXT NOT NULL,
            character_continuity_ref TEXT NOT NULL,
            character_continuity_version_ref TEXT NOT NULL,
            character_continuity_version_digest TEXT NOT NULL,
            canonical_schema_version TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            canonical_digest TEXT NOT NULL CHECK(canonical_digest = content_digest),
            status TEXT NOT NULL CHECK(status IN ('ACTIVE','SUPERSEDED')),
            approval_ref TEXT NOT NULL,
            confirmed_by_actor_ref TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            superseded_at TEXT,
            record_json TEXT NOT NULL,
            PRIMARY KEY({scope_key}, m6_baseline_snapshot_ref),
            UNIQUE({scope_key}, activation_revision),
            FOREIGN KEY(
                {scope_key}, series_bible_ref, series_bible_version_ref,
                series_bible_version_digest
            ) REFERENCES v5_m6_series_bible_versions(
                {scope_key}, series_bible_ref, series_bible_version_ref, content_digest
            ) ON DELETE RESTRICT,
            FOREIGN KEY(
                {scope_key}, character_continuity_ref,
                character_continuity_version_ref, character_continuity_version_digest
            ) REFERENCES v5_m6_character_continuity_versions(
                {scope_key}, character_continuity_ref,
                character_continuity_version_ref, content_digest
            ) ON DELETE RESTRICT,
            FOREIGN KEY({m5_parent})
                REFERENCES v5_series_plan_versions({m5_parent}) ON DELETE RESTRICT
        )""",
        f"""CREATE TABLE v5_m6_operations (
            {scope},
            idempotency_key TEXT NOT NULL,
            operation_ref TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            input_digest TEXT NOT NULL,
            result_json TEXT NOT NULL,
            PRIMARY KEY({scope_key}, idempotency_key)
        )""",
        f"""CREATE TABLE v5_m6_outbox (
            position INTEGER PRIMARY KEY AUTOINCREMENT,
            {scope},
            event_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_version INTEGER NOT NULL CHECK(event_version > 0),
            aggregate_type TEXT NOT NULL,
            aggregate_ref TEXT NOT NULL,
            operation_ref TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            causation_id TEXT,
            occurred_at TEXT NOT NULL,
            event_json TEXT NOT NULL,
            UNIQUE({scope_key}, event_id)
        )""",
    )


def index_statements() -> tuple[str, ...]:
    return (
        "CREATE UNIQUE INDEX ux_m5_plan_version_full_identity "
        "ON v5_series_plan_versions("
        "workspace_ref, project_ref, series_ref, series_plan_ref, series_plan_version_ref)",
        "CREATE UNIQUE INDEX ux_m6_one_active_baseline "
        "ON v5_m6_baseline_snapshots(" + SCOPE_KEY_SQL + ") WHERE status = 'ACTIVE'",
        "CREATE INDEX ix_m6_outbox_scope_position ON v5_m6_outbox("
        + SCOPE_KEY_SQL + ", position)",
    )
