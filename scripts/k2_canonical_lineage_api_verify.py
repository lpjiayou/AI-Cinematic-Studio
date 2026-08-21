#!/usr/bin/env python3
"""Verify one canonical K2 root through the authenticated Creator Public API.

The verifier is read-only with respect to Creator Core. It loads the secret-free
bootstrap receipt, performs authenticated GET requests against the loopback Public
API, compares every foundational lineage reference/version/digest, and writes one
secret-free verification receipt only after all checks pass.

The raw bearer credential is accepted only through ``K2_CREATOR_API_BEARER_TOKEN``.
It is never accepted on the command line, serialized, hashed into evidence, or
printed. Redirects are not followed, so an Authorization header cannot be forwarded
away from the explicitly validated loopback origin.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote, urlencode, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import k2_canonical_lineage_bootstrap as bootstrap  # noqa: E402


VERIFICATION_SCHEMA_VERSION = "k2.canonical-lineage-public-api-verification.v1"
TOKEN_ENVIRONMENT_VARIABLE = "K2_CREATOR_API_BEARER_TOKEN"
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 10.0
RESOURCE_COUNT = 7
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SPECIFICATION_PATH = (
    REPOSITORY_ROOT
    / "experiments"
    / "k2-001-canonical-bootstrap"
    / "k2-001-canonical-bootstrap.v1.json"
)


class ApiVerificationError(RuntimeError):
    """Stable error that contains no response body or credential material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ApiOrigin:
    scheme: str
    hostname: str
    port: int


JsonGetter = Callable[[str, Mapping[str, str] | None], Mapping[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ApiVerificationError("non_canonical_json_value") from None


def _digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path, code: str = "file_digest_failed") -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise ApiVerificationError(code) from None
    return digest.hexdigest()


def _fields(value: Any, expected: set[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ApiVerificationError(code)
    return value


def _required_mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ApiVerificationError(code)
    return value


def _required_list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise ApiVerificationError(code)
    return value


def _safe_ref(value: Any, code: str) -> str:
    if not isinstance(value, str) or bootstrap.REF_PATTERN.fullmatch(value) is None:
        raise ApiVerificationError(code)
    return value


def _safe_sha256(value: Any, code: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ApiVerificationError(code)
    return value


def _existing_canonical_root(path: Path | str) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute():
        raise ApiVerificationError("canonical_root_must_be_absolute")
    lexical = Path(os.path.abspath(os.fspath(supplied)))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ApiVerificationError("canonical_root_symlink_rejected")
    try:
        resolved = lexical.resolve(strict=True)
        metadata = resolved.stat()
    except OSError:
        raise ApiVerificationError("canonical_root_unavailable") from None
    if not stat.S_ISDIR(metadata.st_mode):
        raise ApiVerificationError("canonical_root_not_directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ApiVerificationError("canonical_root_permissions_invalid")
    return resolved


def _load_bootstrap_receipt(root: Path) -> tuple[Mapping[str, Any], Path, str]:
    path = root / bootstrap.RECEIPT_FILENAME
    try:
        receipt_metadata = path.lstat()
    except OSError:
        raise ApiVerificationError("bootstrap_receipt_invalid") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(receipt_metadata.st_mode)
        or stat.S_IMODE(receipt_metadata.st_mode) != 0o600
    ):
        raise ApiVerificationError("bootstrap_receipt_file_invalid")
    try:
        value = bootstrap._load_json_object(path)
    except bootstrap.BootstrapError as error:
        raise ApiVerificationError("bootstrap_receipt_invalid") from error
    receipt = _fields(
        value,
        {
            "schemaVersion",
            "packageId",
            "specification",
            "databaseFiles",
            "lineage",
            "verification",
            "exitState",
        },
        "bootstrap_receipt_fields_invalid",
    )
    if (
        receipt.get("schemaVersion") != bootstrap.RECEIPT_SCHEMA_VERSION
        or receipt.get("packageId") != bootstrap.PACKAGE_ID
    ):
        raise ApiVerificationError("bootstrap_receipt_identity_invalid")
    specification = _fields(
        receipt.get("specification"),
        {"schemaVersion", "sha256", "payloadSha256", "repositoryCommit"},
        "bootstrap_specification_receipt_invalid",
    )
    if specification.get("schemaVersion") != bootstrap.SPECIFICATION_SCHEMA_VERSION:
        raise ApiVerificationError("bootstrap_specification_schema_invalid")
    specification_digest = _safe_sha256(
        specification.get("sha256"), "specification_digest_invalid"
    )
    payload_digest = _safe_sha256(
        specification.get("payloadSha256"), "payload_digest_invalid"
    )
    try:
        exact_specification = bootstrap.validate_specification(SPECIFICATION_PATH)
    except bootstrap.BootstrapError as error:
        raise ApiVerificationError("checked_in_specification_invalid") from error
    if (
        specification_digest != exact_specification.specification_sha256
        or payload_digest != exact_specification.payload_sha256
    ):
        raise ApiVerificationError("bootstrap_specification_digest_mismatch")
    repository_commit = specification.get("repositoryCommit")
    if (
        not isinstance(repository_commit, str)
        or bootstrap.COMMIT_PATTERN.fullmatch(repository_commit) is None
    ):
        raise ApiVerificationError("repository_commit_invalid")
    exit_state = receipt.get("exitState")
    expected_exit_state = {
        "canonicalRootStatus": "ROOTS_READY",
        "m6AuthorityStatus": "NOT_CREATED",
        "identityLockStatus": "NOT_CREATED",
        "rightsAuthorityStatus": "NOT_CONNECTED",
        "providerAuthorityStatus": "NOT_CONNECTED",
        "budgetAuthorityStatus": "NOT_CONNECTED",
        "p1Gate": "NOT_PASSED",
        "publicationAllowed": False,
    }
    if exit_state != expected_exit_state:
        raise ApiVerificationError("bootstrap_exit_state_invalid")
    verification = _fields(
        receipt.get("verification"),
        {
            "restartVerified",
            "scannerMode",
            "databaseCount",
            "productionDatabaseCount",
            "productionRunCount",
            "currentLineageStatus",
            "downstreamFactTablesEmpty",
        },
        "bootstrap_verification_fields_invalid",
    )
    if (
        verification.get("restartVerified") is not True
        or verification.get("scannerMode") != "SQLITE_READ_ONLY_QUERY_ONLY"
        or not isinstance(verification.get("databaseCount"), int)
        or verification.get("databaseCount") < 2
        or verification.get("productionDatabaseCount") != 1
        or verification.get("productionRunCount") != 1
        or verification.get("currentLineageStatus") != "FOUND_READ_ONLY"
        or verification.get("downstreamFactTablesEmpty") is not True
    ):
        raise ApiVerificationError("bootstrap_verification_state_invalid")

    database_entries = _required_list(
        receipt.get("databaseFiles"), "bootstrap_database_inventory_invalid"
    )
    expected_names = sorted(bootstrap.DATABASE_FILENAMES.values())
    observed_names: list[str] = []
    verified_entries: list[dict[str, str]] = []
    for item in database_entries:
        entry = _fields(
            item,
            {"path", "sha256"},
            "bootstrap_database_inventory_entry_invalid",
        )
        filename = entry.get("path")
        if not isinstance(filename, str):
            raise ApiVerificationError("bootstrap_database_filename_invalid")
        digest = _safe_sha256(
            entry.get("sha256"), "bootstrap_database_digest_invalid"
        )
        observed_names.append(filename)
        database_path = root / filename
        try:
            metadata = database_path.lstat()
        except OSError:
            raise ApiVerificationError("bootstrap_database_file_missing") from None
        if (
            database_path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size == 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ApiVerificationError("bootstrap_database_file_invalid")
        if _file_sha256(database_path, "bootstrap_database_digest_failed") != digest:
            raise ApiVerificationError("bootstrap_database_digest_mismatch")
        verified_entries.append({"path": filename, "sha256": digest})
    if sorted(observed_names) != expected_names or len(set(observed_names)) != len(
        expected_names
    ):
        raise ApiVerificationError("bootstrap_database_inventory_names_invalid")

    expected_root_entries = {
        *expected_names,
        bootstrap.RECEIPT_FILENAME,
        bootstrap.INVENTORY_FILENAME,
    }
    try:
        actual_root_entries = {entry.name for entry in root.iterdir()}
    except OSError:
        raise ApiVerificationError("canonical_root_inventory_failed") from None
    if actual_root_entries != expected_root_entries:
        raise ApiVerificationError("canonical_root_unexpected_entry")

    receipt_sha256 = _file_sha256(path, "bootstrap_receipt_digest_failed")
    inventory_path = root / bootstrap.INVENTORY_FILENAME
    try:
        inventory_metadata = inventory_path.lstat()
        inventory_content = inventory_path.read_bytes()
    except OSError:
        raise ApiVerificationError("bootstrap_inventory_unavailable") from None
    if (
        inventory_path.is_symlink()
        or not stat.S_ISREG(inventory_metadata.st_mode)
        or stat.S_IMODE(inventory_metadata.st_mode) != 0o600
    ):
        raise ApiVerificationError("bootstrap_inventory_file_invalid")
    expected_inventory = "".join(
        f"{item['sha256']}  {item['path']}\n"
        for item in sorted(
            [
                *verified_entries,
                {"path": bootstrap.RECEIPT_FILENAME, "sha256": receipt_sha256},
            ],
            key=lambda item: item["path"],
        )
    ).encode("utf-8")
    if inventory_content != expected_inventory:
        raise ApiVerificationError("bootstrap_inventory_content_mismatch")
    return receipt, path, receipt_sha256


def _reject_json_constant(value: str) -> None:
    del value
    raise ValueError


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _validate_origin(value: str) -> ApiOrigin:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ApiVerificationError("base_url_invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ApiVerificationError("base_url_invalid")
    hostname = parsed.hostname.strip("[]").casefold()
    try:
        loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if not loopback:
        raise ApiVerificationError("base_url_must_be_loopback")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise ApiVerificationError("base_url_invalid") from None
    return ApiOrigin(parsed.scheme, hostname, port)


def _load_bearer_token(environment: Mapping[str, str]) -> str:
    token = environment.get(TOKEN_ENVIRONMENT_VARIABLE, "")
    if (
        not isinstance(token, str)
        or not token
        or token != token.strip()
        or len(token.encode("utf-8")) > 4096
        or any(ord(character) < 33 for character in token)
    ):
        raise ApiVerificationError("bearer_token_environment_invalid")
    return token


def _http_getter(origin: ApiOrigin, token: str, timeout: float) -> JsonGetter:
    def get_json(path: str, query: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        if not path.startswith("/creator/api/v1/"):
            raise ApiVerificationError("public_api_path_invalid")
        suffix = "?" + urlencode(query) if query else ""
        connection_class = (
            http.client.HTTPSConnection
            if origin.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_class(origin.hostname, origin.port, timeout=timeout)
        try:
            connection.request(
                "GET",
                path + suffix,
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            if response.status != 200:
                raise ApiVerificationError("public_api_response_status_invalid")
            content_type = response.getheader("Content-Type", "").split(";", 1)[0]
            if content_type.strip().casefold() != "application/json":
                raise ApiVerificationError("public_api_content_type_invalid")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if not body or len(body) > MAX_RESPONSE_BYTES:
                raise ApiVerificationError("public_api_response_size_invalid")
            try:
                value = json.loads(
                    body.decode("utf-8"),
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeError, json.JSONDecodeError, ValueError):
                raise ApiVerificationError("public_api_json_invalid") from None
            if not isinstance(value, Mapping) or value.get("ok") is not True:
                raise ApiVerificationError("public_api_envelope_invalid")
            return value
        except ApiVerificationError:
            raise
        except (OSError, http.client.HTTPException):
            raise ApiVerificationError("public_api_request_failed") from None
        finally:
            connection.close()

    return get_json


def _equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        raise ApiVerificationError(code)


def _creative_plan_digest(binding: Mapping[str, Any]) -> str:
    return _digest(
        {
            "creativePlanRef": binding.get("creativePlanRef"),
            "sourcePlanRef": binding.get("sourcePlanRef"),
            "sourcePlanSchemaVersion": binding.get("sourcePlanSchemaVersion"),
            "sourcePlanVersion": binding.get("sourcePlanVersion"),
            "brief": binding.get("brief"),
            "sourcePlan": binding.get("sourcePlan"),
            "confirmationStatus": "confirmed",
        }
    )


def verify_public_api(
    receipt: Mapping[str, Any],
    get_json: JsonGetter,
) -> tuple[list[dict[str, str]], Mapping[str, Any]]:
    lineage = _required_mapping(receipt.get("lineage"), "lineage_receipt_invalid")
    workspace_ref = _safe_ref(lineage.get("workspaceRef"), "workspace_ref_invalid")
    content_profile_ref = _safe_ref(
        lineage.get("contentProfileRef"), "content_profile_ref_invalid"
    )
    series_receipt = _required_mapping(lineage.get("series"), "series_receipt_invalid")
    creative_receipt = _required_mapping(
        lineage.get("creativePlan"), "creative_plan_receipt_invalid"
    )
    project_receipt = _required_mapping(lineage.get("project"), "project_receipt_invalid")
    episode_receipt = _required_mapping(lineage.get("episode"), "episode_receipt_invalid")
    planning_receipt = _required_mapping(
        lineage.get("seriesPlan"), "series_plan_receipt_invalid"
    )
    script_receipt = _required_mapping(lineage.get("script"), "script_receipt_invalid")
    run_receipt = _required_mapping(
        lineage.get("episodeProductionRun"), "production_run_receipt_invalid"
    )

    series_ref = _safe_ref(series_receipt.get("seriesRef"), "series_ref_invalid")
    project_ref = _safe_ref(project_receipt.get("projectRef"), "project_ref_invalid")
    episode_ref = _safe_ref(episode_receipt.get("episodeRef"), "episode_ref_invalid")
    run_ref = _safe_ref(run_receipt.get("productionRunRef"), "production_run_ref_invalid")

    queries = {
        "series": get_json(f"/creator/api/v1/series/{quote(series_ref, safe='')}", None),
        "project": get_json(f"/creator/api/v1/projects/{quote(project_ref, safe='')}", None),
        "episode": get_json(
            f"/creator/api/v1/episodes/{quote(episode_ref, safe='')}",
            {"seriesRef": series_ref},
        ),
        "seriesPlan": get_json(
            "/creator/api/v1/series-planning-workspaces",
            {"projectRef": project_ref, "seriesRef": series_ref},
        ),
        "script": get_json(
            "/creator/api/v1/script-workspaces",
            {"seriesRef": series_ref, "episodeRef": episode_ref},
        ),
        "productionRun": get_json(
            f"/creator/api/v1/episode-production-runs/{quote(run_ref, safe='')}",
            None,
        ),
        "productionRunList": get_json(
            "/creator/api/v1/episode-production-runs",
            None,
        ),
    }

    series = _required_mapping(queries["series"].get("series"), "api_series_invalid")
    _equal(series.get("workspaceRef"), workspace_ref, "api_series_workspace_mismatch")
    _equal(series.get("contentProfileRef"), content_profile_ref, "api_series_profile_mismatch")
    _equal(series.get("seriesRef"), series_ref, "api_series_ref_mismatch")
    _equal(series.get("version"), series_receipt.get("version"), "api_series_version_mismatch")
    episodes = _required_list(series.get("episodes"), "api_series_episodes_invalid")
    _equal(
        [item.get("episodeRef") for item in episodes if isinstance(item, Mapping)],
        [episode_ref],
        "api_series_episode_membership_mismatch",
    )

    project = _required_mapping(queries["project"].get("project"), "api_project_invalid")
    for field, expected in (
        ("workspaceRef", workspace_ref),
        ("contentProfileRef", content_profile_ref),
        ("projectRef", project_ref),
        ("version", project_receipt.get("version")),
        ("seriesRefs", [series_ref]),
    ):
        _equal(project.get(field), expected, f"api_project_{field}_mismatch")

    episode = _required_mapping(queries["episode"].get("episode"), "api_episode_invalid")
    for field, expected in (
        ("workspaceRef", workspace_ref),
        ("seriesRef", series_ref),
        ("episodeRef", episode_ref),
        ("creativePlanRef", creative_receipt.get("creativePlanRef")),
        ("version", episode_receipt.get("version")),
    ):
        _equal(episode.get(field), expected, f"api_episode_{field}_mismatch")
    binding = _required_mapping(
        episode.get("confirmedPlanBinding"), "api_creative_plan_binding_invalid"
    )
    for field in (
        "creativePlanRef",
        "sourcePlanRef",
        "sourcePlanSchemaVersion",
        "sourcePlanVersion",
    ):
        _equal(
            binding.get(field),
            creative_receipt.get(field),
            f"api_creative_plan_{field}_mismatch",
        )
    _equal(
        _creative_plan_digest(binding),
        creative_receipt.get("lineageDigest"),
        "api_creative_plan_digest_mismatch",
    )

    planning = _required_mapping(
        queries["seriesPlan"].get("workspace"), "api_series_plan_invalid"
    )
    plan = _required_mapping(planning.get("plan"), "api_series_plan_record_invalid")
    for field, expected in (
        ("workspaceRef", workspace_ref),
        ("contentProfileRef", content_profile_ref),
        ("projectRef", project_ref),
        ("seriesRef", series_ref),
        ("seriesPlanRef", planning_receipt.get("seriesPlanRef")),
        ("currentSeriesPlanVersionRef", planning_receipt.get("seriesPlanVersionRef")),
        ("confirmedSeriesPlanVersionRef", planning_receipt.get("seriesPlanVersionRef")),
        ("version", planning_receipt.get("planVersion")),
    ):
        _equal(plan.get(field), expected, f"api_series_plan_{field}_mismatch")
    plan_versions = _required_list(planning.get("versions"), "api_series_plan_versions_invalid")
    selected_plans = [
        item
        for item in plan_versions
        if isinstance(item, Mapping)
        and item.get("seriesPlanVersionRef") == planning_receipt.get("seriesPlanVersionRef")
    ]
    _equal(len(selected_plans), 1, "api_series_plan_selected_version_mismatch")
    _equal(
        selected_plans[0].get("versionNumber"),
        planning_receipt.get("versionNumber"),
        "api_series_plan_version_number_mismatch",
    )
    episode_plan_items = _required_list(
        selected_plans[0].get("episodePlanItems"),
        "api_episode_plan_items_invalid",
    )
    _equal(
        [item.get("episodePlanItemRef") for item in episode_plan_items if isinstance(item, Mapping)],
        [planning_receipt.get("episodePlanItemRef")],
        "api_episode_plan_item_ref_mismatch",
    )

    script_workspace = _required_mapping(
        queries["script"].get("workspace"), "api_script_workspace_invalid"
    )
    script = _required_mapping(script_workspace.get("script"), "api_script_invalid")
    for field, expected in (
        ("workspaceRef", workspace_ref),
        ("seriesRef", series_ref),
        ("episodeRef", episode_ref),
        ("scriptRef", script_receipt.get("scriptRef")),
        ("currentScriptVersionRef", script_receipt.get("scriptVersionRef")),
        ("confirmedScriptVersionRef", script_receipt.get("scriptVersionRef")),
        ("version", script_receipt.get("scriptVersion")),
    ):
        _equal(script.get(field), expected, f"api_script_{field}_mismatch")
    script_versions = _required_list(
        script_workspace.get("versions"), "api_script_versions_invalid"
    )
    selected_scripts = [
        item
        for item in script_versions
        if isinstance(item, Mapping)
        and item.get("scriptVersionRef") == script_receipt.get("scriptVersionRef")
    ]
    _equal(len(selected_scripts), 1, "api_script_selected_version_mismatch")
    _equal(
        selected_scripts[0].get("versionNumber"),
        script_receipt.get("versionNumber"),
        "api_script_version_number_mismatch",
    )

    run = _required_mapping(
        queries["productionRun"].get("run"), "api_production_run_invalid"
    )
    expected_run = {
        "workspaceRef": workspace_ref,
        "productionRunRef": run_ref,
        "contentProfileRef": content_profile_ref,
        "projectRef": project_ref,
        "seriesRef": series_ref,
        "episodeRef": episode_ref,
        "seriesPlanRef": planning_receipt.get("seriesPlanRef"),
        "seriesPlanVersionRef": planning_receipt.get("seriesPlanVersionRef"),
        "episodePlanItemRef": planning_receipt.get("episodePlanItemRef"),
        "scriptRef": script_receipt.get("scriptRef"),
        "scriptVersionRef": script_receipt.get("scriptVersionRef"),
        "upstreamDigest": run_receipt.get("upstreamDigest"),
        "payloadDigest": run_receipt.get("payloadDigest"),
        "state": "ROOTS_READY",
        "version": run_receipt.get("version"),
        "idempotentReplay": False,
    }
    for field, expected in expected_run.items():
        _equal(run.get(field), expected, f"api_production_run_{field}_mismatch")
    manifest = _required_mapping(run.get("manifest"), "api_production_run_manifest_invalid")
    for field, expected in (
        ("publicationAllowed", False),
        ("expectedSceneCount", 2),
        ("expectedShotCount", 4),
    ):
        _equal(manifest.get(field), expected, f"api_production_manifest_{field}_mismatch")
    upstream = _required_mapping(
        run.get("upstreamSnapshot"), "api_production_upstream_snapshot_invalid"
    )
    _equal(
        _digest(upstream),
        run_receipt.get("upstreamDigest"),
        "api_production_upstream_digest_recalculation_mismatch",
    )
    _equal(
        _digest(
            {
                "workspaceRef": workspace_ref,
                "projectRef": project_ref,
                "seriesRef": series_ref,
                "episodeRef": episode_ref,
                "manifest": manifest,
                "upstreamDigest": run_receipt.get("upstreamDigest"),
            }
        ),
        run_receipt.get("payloadDigest"),
        "api_production_payload_digest_recalculation_mismatch",
    )
    scene_budgets = _required_list(
        manifest.get("sceneBudgets"), "api_production_scene_budgets_invalid"
    )
    _equal(
        [item.get("shotCount") for item in scene_budgets if isinstance(item, Mapping)],
        [2, 2],
        "api_production_scene_budgets_mismatch",
    )
    _equal(
        _required_mapping(upstream.get("seriesPlan"), "api_series_plan_snapshot_invalid").get("versionDigest"),
        planning_receipt.get("versionDigest"),
        "api_series_plan_version_digest_mismatch",
    )
    _equal(
        _required_mapping(upstream.get("script"), "api_script_snapshot_invalid").get("versionDigest"),
        script_receipt.get("versionDigest"),
        "api_script_version_digest_mismatch",
    )

    listed = _required_list(
        queries["productionRunList"].get("runs"), "api_production_run_list_invalid"
    )
    _equal(len(listed), 1, "api_production_run_count_mismatch")
    _equal(
        listed[0].get("productionRunRef") if isinstance(listed[0], Mapping) else None,
        run_ref,
        "api_production_run_list_ref_mismatch",
    )
    _equal(
        listed[0].get("payloadDigest") if isinstance(listed[0], Mapping) else None,
        run_receipt.get("payloadDigest"),
        "api_production_run_list_digest_mismatch",
    )

    resources = [
        {"resource": name, "responseSha256": _digest(value)}
        for name, value in sorted(queries.items())
    ]
    safe_lineage = {
        "workspaceRef": workspace_ref,
        "contentProfileRef": content_profile_ref,
        "projectRef": project_ref,
        "seriesRef": series_ref,
        "episodeRef": episode_ref,
        "productionRunRef": run_ref,
        "upstreamDigest": run_receipt.get("upstreamDigest"),
        "payloadDigest": run_receipt.get("payloadDigest"),
        "state": "ROOTS_READY",
    }
    return resources, safe_lineage


def build_verification_receipt(
    bootstrap_receipt: Mapping[str, Any],
    bootstrap_receipt_sha256: str,
    resources: Sequence[Mapping[str, str]],
    lineage: Mapping[str, Any],
    *,
    verified_at: str | None = None,
) -> Mapping[str, Any]:
    if len(resources) != RESOURCE_COUNT:
        raise ApiVerificationError("verified_resource_count_invalid")
    specification = _required_mapping(
        bootstrap_receipt.get("specification"), "bootstrap_specification_receipt_invalid"
    )
    timestamp = verified_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = {
        "schemaVersion": VERIFICATION_SCHEMA_VERSION,
        "packageId": bootstrap.PACKAGE_ID,
        "verifiedAt": timestamp,
        "canonicalBootstrapReceipt": {
            "sha256": bootstrap_receipt_sha256,
            "specificationSha256": specification.get("sha256"),
            "payloadSha256": specification.get("payloadSha256"),
            "repositoryCommit": specification.get("repositoryCommit"),
        },
        "api": {
            "originClass": "local-loopback",
            "authentication": "SERVER_TO_SERVER_BEARER_VERIFIED_NOT_RECORDED",
            "method": "AUTHENTICATED_GET_ONLY",
            "resourceCount": len(resources),
            "resources": list(resources),
        },
        "lineage": dict(lineage),
        "exitState": dict(bootstrap_receipt["exitState"]),
    }
    bootstrap._reject_secret_fields(result)
    return result


def _validate_output_path(path: Path | str) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute():
        raise ApiVerificationError("output_must_be_absolute")
    lexical = Path(os.path.abspath(os.fspath(supplied)))
    current = Path(lexical.anchor)
    for part in lexical.parent.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ApiVerificationError("output_symlink_component_rejected")
    try:
        parent = lexical.parent.resolve(strict=True)
    except OSError:
        raise ApiVerificationError("output_parent_unavailable") from None
    output = parent / lexical.name
    if output.exists() or output.is_symlink():
        raise ApiVerificationError("output_already_exists")
    if not stat.S_ISDIR(parent.stat().st_mode) or not os.access(parent, os.W_OK | os.X_OK):
        raise ApiVerificationError("output_parent_not_writable")
    return output


def _write_private(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        raise ApiVerificationError("verification_receipt_write_failed") from None


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a canonical K2 root through authenticated loopback Creator Public API reads."
        )
    )
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _arguments(argv)
        if not 0.1 <= args.timeout_seconds <= 60.0:
            raise ApiVerificationError("timeout_invalid")
        root = _existing_canonical_root(args.canonical_root)
        receipt, _, receipt_sha256 = _load_bootstrap_receipt(root)
        try:
            repository_commit = bootstrap._resolve_repository_commit(None)
        except bootstrap.BootstrapError as error:
            raise ApiVerificationError("repository_checkout_invalid") from error
        if repository_commit != receipt["specification"]["repositoryCommit"]:
            raise ApiVerificationError("repository_commit_receipt_mismatch")
        origin = _validate_origin(args.base_url)
        token = _load_bearer_token(os.environ)
        output = _validate_output_path(args.output)
        resources, lineage = verify_public_api(
            receipt,
            _http_getter(origin, token, args.timeout_seconds),
        )
        verification = build_verification_receipt(
            receipt,
            receipt_sha256,
            resources,
            lineage,
        )
        content = _canonical_bytes(verification) + b"\n"
        _write_private(output, content)
        print("K2_CANONICAL_PUBLIC_API_VERIFICATION=PASS")
        print("CANONICAL_BOOTSTRAP_RECEIPT_SHA256=" + receipt_sha256)
        print("VERIFIED_RESOURCE_COUNT=" + str(len(resources)))
        print("PRODUCTION_RUN_REF=" + str(lineage["productionRunRef"]))
        print("PRODUCTION_RUN_PAYLOAD_DIGEST=" + str(lineage["payloadDigest"]))
        print("CANONICAL_ROOT_STATUS=ROOTS_READY")
        print("P1_GATE=NOT_PASSED")
        print("PUBLICATION_ALLOWED=false")
        print("VERIFICATION_OUTPUT=" + str(output))
        print("VERIFICATION_OUTPUT_SHA256=" + sha256(content).hexdigest())
        return 0
    except ApiVerificationError as error:
        print("K2_CANONICAL_PUBLIC_API_VERIFICATION=FAIL")
        print("K2_API_VERIFICATION_ERROR=" + error.code)
        return 2
    except Exception as error:
        print("K2_CANONICAL_PUBLIC_API_VERIFICATION=FAIL")
        print("K2_API_VERIFICATION_ERROR=unexpected_" + type(error).__name__.lower())
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
