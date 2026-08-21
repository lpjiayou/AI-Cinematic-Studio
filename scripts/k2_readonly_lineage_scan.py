#!/usr/bin/env python3
"""Locate current K2 SQLite lineage without creating or mutating a database.

The scanner opens existing SQLite files with ``mode=ro`` and ``query_only``. It
prints only table counts plus stable references, versions, states and digests from
known Creator/K2 tables. Payload JSON, creative text, idempotency keys and credential
fields are never selected.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Iterator, Mapping, Sequence


DATABASE_SUFFIXES = (".sqlite3", ".sqlite", ".db")
DEFAULT_SKIP_DIRECTORIES = frozenset(
    {
        ".cache",
        ".conda",
        ".git",
        ".rootcache",
        "downloads",
        "miniconda",
        "models",
        "node_modules",
        "pip-cache",
        "venvs",
        "wheels",
    }
)


class Projection:
    def __init__(
        self,
        label: str,
        columns: Sequence[str],
        order_by: Sequence[str],
    ) -> None:
        self.label = label
        self.columns = tuple(columns)
        self.order_by = tuple(order_by)


PROJECTIONS: Mapping[str, Projection] = {
    "v5_episode_production_runs": Projection(
        "K2_RUN",
        (
            "workspace_ref",
            "production_run_ref",
            "content_profile_ref",
            "project_ref",
            "series_ref",
            "episode_ref",
            "series_plan_ref",
            "series_plan_version_ref",
            "episode_plan_item_ref",
            "script_ref",
            "script_version_ref",
            "upstream_digest",
            "payload_digest",
            "state",
            "created_at",
            "updated_at",
            "version",
        ),
        ("created_at", "production_run_ref"),
    ),
    "v5_episode_production_gates": Projection(
        "K2_GATE",
        (
            "workspace_ref",
            "production_run_ref",
            "gate_name",
            "root_payload_digest",
            "request_digest",
            "from_state",
            "to_state",
            "created_at",
        ),
        ("production_run_ref", "created_at", "gate_name"),
    ),
    "v5_episode_production_facts": Projection(
        "K2_FACT",
        (
            "workspace_ref",
            "production_run_ref",
            "gate_name",
            "fact_kind",
            "fact_ref",
            "fact_version",
            "payload_digest",
        ),
        ("production_run_ref", "gate_name", "fact_kind", "fact_ref"),
    ),
    "v5_production_policy_bundles": Projection(
        "K2_POLICY",
        (
            "workspace_ref",
            "production_run_ref",
            "request_digest",
            "payload_digest",
            "created_at",
        ),
        ("created_at", "production_run_ref"),
    ),
    "v5_provider_experiments": Projection(
        "K2_EXPERIMENT",
        (
            "workspace_ref",
            "production_run_ref",
            "experiment_ref",
            "request_digest",
            "payload_digest",
            "created_at",
        ),
        ("created_at", "experiment_ref"),
    ),
    "v5_projects": Projection(
        "K2_PROJECT",
        (
            "workspace_ref",
            "project_ref",
            "content_profile_ref",
            "project_type",
            "status",
            "created_at",
            "updated_at",
            "version",
        ),
        ("created_at", "project_ref"),
    ),
    "v5_project_series_relationships": Projection(
        "K2_PROJECT_SERIES",
        (
            "workspace_ref",
            "project_ref",
            "series_ref",
            "linked_at",
            "version",
        ),
        ("linked_at", "project_ref", "series_ref"),
    ),
    "v5_series": Projection(
        "K2_SERIES",
        (
            "workspace_ref",
            "series_ref",
            "content_profile_ref",
            "status",
            "created_at",
            "updated_at",
            "version",
        ),
        ("created_at", "series_ref"),
    ),
    "v5_episode_projects": Projection(
        "K2_EPISODE",
        (
            "workspace_ref",
            "episode_ref",
            "series_ref",
            "canonical_project_ref",
            "creative_plan_ref",
            "episode_number",
            "status",
            "created_at",
            "updated_at",
            "version",
        ),
        ("created_at", "series_ref", "episode_number"),
    ),
    "v5_scripts": Projection(
        "K2_SCRIPT",
        (
            "workspace_ref",
            "series_ref",
            "episode_ref",
            "script_ref",
            "current_script_version_ref",
            "confirmed_script_version_ref",
            "created_at",
            "updated_at",
            "version",
        ),
        ("created_at", "script_ref"),
    ),
}


def _json(value: Mapping[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _database_candidates(
    root: Path,
    *,
    max_depth: int,
    skip_directories: frozenset[str],
) -> Iterator[Path]:
    root_depth = len(root.parts)
    for directory, child_directories, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        depth = len(current.parts) - root_depth
        child_directories[:] = sorted(
            name
            for name in child_directories
            if name not in skip_directories and not (current / name).is_symlink()
        )
        if depth >= max_depth:
            child_directories[:] = []
        for filename in sorted(filenames):
            if not filename.casefold().endswith(DATABASE_SUFFIXES):
                continue
            path = current / filename
            try:
                metadata = path.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISREG(metadata.st_mode) and metadata.st_size > 0:
                yield path.resolve()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        path.as_uri() + "?mode=ro",
        uri=True,
        timeout=5,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")'))


def _rows(
    connection: sqlite3.Connection,
    table: str,
    projection: Projection,
    max_rows: int,
) -> tuple[int, list[dict[str, object]]]:
    available = set(_columns(connection, table))
    if not set(projection.columns).issubset(available):
        raise sqlite3.DatabaseError("known table columns are incomplete")
    selected = ",".join(f'"{column}"' for column in projection.columns)
    ordering = ",".join(f'"{column}"' for column in projection.order_by)
    total = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    cursor = connection.execute(
        f'SELECT {selected} FROM "{table}" ORDER BY {ordering} LIMIT ?',
        (max_rows,),
    )
    values = [dict(row) for row in cursor.fetchall()]
    return total, values


def scan(root: Path, *, max_depth: int, max_rows: int) -> int:
    root = root.resolve()
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("scan root must be an existing absolute directory")
    if max_depth < 0 or max_depth > 12:
        raise ValueError("max depth must be between 0 and 12")
    if max_rows < 1 or max_rows > 1000:
        raise ValueError("max rows must be between 1 and 1000")

    print("K2_SCAN_MODE=SQLITE_READ_ONLY_QUERY_ONLY")
    print("K2_SCAN_ROOT=" + str(root))
    matched_databases = 0
    production_databases = 0
    production_runs = 0

    for path in _database_candidates(
        root,
        max_depth=max_depth,
        skip_directories=DEFAULT_SKIP_DIRECTORIES,
    ):
        try:
            connection = _connect_read_only(path)
            known_tables = sorted(_tables(connection) & set(PROJECTIONS))
        except sqlite3.Error as error:
            print(
                "K2_DATABASE_SKIPPED="
                + _json({"errorType": type(error).__name__, "path": str(path)})
            )
            continue
        if not known_tables:
            connection.close()
            continue

        matched_databases += 1
        if "v5_episode_production_runs" in known_tables:
            production_databases += 1
        print(
            "K2_DATABASE="
            + _json(
                {
                    "path": str(path),
                    "sizeBytes": path.stat().st_size,
                    "tables": known_tables,
                    "walPresent": Path(str(path) + "-wal").is_file(),
                }
            )
        )
        try:
            quick_check = str(connection.execute("PRAGMA quick_check(1)").fetchone()[0])
            print(
                "K2_DATABASE_INTEGRITY="
                + _json({"path": str(path), "quickCheck": quick_check})
            )
            for table in known_tables:
                projection = PROJECTIONS[table]
                try:
                    total, values = _rows(connection, table, projection, max_rows)
                except sqlite3.Error as error:
                    print(
                        "K2_TABLE_READ_ERROR="
                        + _json(
                            {
                                "errorType": type(error).__name__,
                                "path": str(path),
                                "table": table,
                            }
                        )
                    )
                    continue
                print(
                    "K2_TABLE="
                    + _json({"path": str(path), "rows": total, "table": table})
                )
                if table == "v5_episode_production_runs":
                    production_runs += total
                for value in values:
                    print(projection.label + "=" + _json(value))
                if total > len(values):
                    print(
                        "K2_ROWS_TRUNCATED="
                        + _json(
                            {
                                "path": str(path),
                                "reported": len(values),
                                "table": table,
                                "total": total,
                            }
                        )
                    )
        finally:
            connection.close()

    print("K2_DATABASES_FOUND=" + str(matched_databases))
    print("K2_PRODUCTION_DATABASES_FOUND=" + str(production_databases))
    print("K2_PRODUCTION_RUNS_FOUND=" + str(production_runs))
    if production_runs < 1:
        print("K2_CURRENT_LINEAGE_STATUS=NOT_FOUND")
        return 3
    print("K2_CURRENT_LINEAGE_STATUS=FOUND_READ_ONLY")
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Locate existing K2 SQLite lineage in read-only/query-only mode without "
            "printing payload JSON or credential-shaped fields."
        )
    )
    parser.add_argument("--root", type=Path, default=Path("/data"))
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--max-rows", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        return scan(args.root, max_depth=args.max_depth, max_rows=args.max_rows)
    except (OSError, ValueError) as error:
        print("K2_LINEAGE_SCAN_ERROR=" + type(error).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
