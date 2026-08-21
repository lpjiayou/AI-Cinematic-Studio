#!/usr/bin/env python3
"""Validate or atomically create the one authorized K2 canonical root lineage.

The default mode is write-free. Formal apply requires an exact acknowledgement,
creates every database in a private same-filesystem staging directory, restarts the
accepted V5 boundaries, verifies the result through the existing read-only scanner,
and only then publishes the canonical directory with a no-replace atomic rename.

This utility stops at ``ROOTS_READY``. It does not create M6 authority, Identity Lock,
Rights/Provider/budget authority, provider work, admitted assets or publication
eligibility.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import ctypes
from dataclasses import dataclass
import errno
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from apps.creator_workspace_mvp.ai_director import (  # noqa: E402
    AI_DIRECTOR_SCHEMA_VERSION,
    CreativeBrief,
    validate_plan,
)
from apps.creator_workspace_mvp.script_studio import (  # noqa: E402
    SCRIPT_CANDIDATE_SCHEMA_VERSION,
    validate_script_candidate,
)
from apps.creator_workspace_mvp.series_director import (  # noqa: E402
    SERIES_PLAN_CANDIDATE_SCHEMA_VERSION,
    validate_series_plan_candidate,
)
from scripts import k2_readonly_lineage_scan  # noqa: E402
from services.v5_core_os.episode_production import (  # noqa: E402
    create_local_development_boundary as create_episode_production_boundary,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly  # noqa: E402


SPECIFICATION_SCHEMA_VERSION = "k2.canonical-lineage-bootstrap.v1"
PACKAGE_ID = "k2-001-canonical-root-v1"
RECEIPT_SCHEMA_VERSION = "k2.canonical-lineage-bootstrap-receipt.v1"
ACKNOWLEDGEMENT = "NEW_CANONICAL_K2_LINEAGE_NOT_RECOVERY"
LOCATION_AUDIT_SHA256 = (
    "7aaa36333f08be3bdfd09c6b4632804f3b7bf14a0bd1bc35f359df0391fa167b"
)
CANONICAL_ROOT_STATUS = "ROOTS_READY"
RECEIPT_FILENAME = "k2-canonical-bootstrap-receipt.v1.json"
INVENTORY_FILENAME = "k2-canonical-bootstrap-inventory.sha256"
DATABASE_FILENAMES = {
    "lifecycle": "creator-workspace.sqlite3",
    "episodeProduction": "episode-production.sqlite3",
    "episodeEvidence": "episode-production.sqlite3.evidence.sqlite3",
    "productionPolicy": "episode-production.sqlite3.production-policy.sqlite3",
    "providerExperiments": "episode-production.sqlite3.provider-experiments.sqlite3",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,199}$")
SECRET_FIELD_PATTERN = re.compile(
    r"(?:api[_-]?key|access[_-]?key|secret|token|password|credential(?:value|source)?)",
    re.IGNORECASE,
)


class BootstrapError(RuntimeError):
    """Stable, non-payload-bearing bootstrap failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class BootstrapValidationError(BootstrapError):
    """The checked-in specification is not eligible for apply."""


class BootstrapApplyError(BootstrapError):
    """The canonical directory was not safely published."""


@dataclass(frozen=True)
class ValidatedSpecification:
    path: Path
    value: Mapping[str, Any]
    payload: Mapping[str, Any]
    specification_sha256: str
    payload_sha256: str
    source_plan: Mapping[str, Any]
    series_plan_candidate: Mapping[str, Any]
    script_candidate: Mapping[str, Any]


@dataclass(frozen=True)
class BootstrapPaths:
    root: Path
    lifecycle: Path
    episode_production: Path
    episode_evidence: Path
    production_policy: Path
    provider_experiments: Path


@dataclass(frozen=True)
class BootstrapResult:
    target: Path
    receipt: Mapping[str, Any]
    receipt_sha256: str
    inventory_sha256: str


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
        raise BootstrapValidationError("non_canonical_json_value") from None


def _canonical_digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _reject_json_constant(value: str) -> None:
    del value
    raise BootstrapValidationError("non_finite_json_number")


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapValidationError("duplicate_json_field")
        result[key] = value
    return result


def _load_json_object(path: Path) -> Mapping[str, Any]:
    try:
        metadata = path.lstat()
    except OSError:
        raise BootstrapValidationError("specification_unavailable") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise BootstrapValidationError("specification_must_be_regular_file")
    if metadata.st_size < 2 or metadata.st_size > 1_048_576:
        raise BootstrapValidationError("specification_size_invalid")
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except BootstrapError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BootstrapValidationError("specification_json_invalid") from None
    if not isinstance(value, Mapping):
        raise BootstrapValidationError("specification_must_be_object")
    return value


def _fields(value: Any, expected: set[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise BootstrapValidationError(code)
    return value


def _text(value: Any, code: str, *, maximum: int = 10_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise BootstrapValidationError(code)
    return value


def _ref(value: Any, code: str) -> str:
    text = _text(value, code, maximum=200)
    if REF_PATTERN.fullmatch(text) is None:
        raise BootstrapValidationError(code)
    return text


def _integer(value: Any, code: str, *, minimum: int = 1, maximum: int = 10_000) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise BootstrapValidationError(code)
    return value


def _false(value: Any, code: str) -> None:
    if value is not False:
        raise BootstrapValidationError(code)


def _true(value: Any, code: str) -> None:
    if value is not True:
        raise BootstrapValidationError(code)


def _reject_secret_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or SECRET_FIELD_PATTERN.search(key):
                raise BootstrapValidationError("secret_shaped_field_rejected")
            _reject_secret_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_fields(nested)


def _validate_authorization(value: Any) -> Mapping[str, Any]:
    authorization = _fields(
        value,
        {
            "decision",
            "decisionDate",
            "priorLineageStatus",
            "locationAuditSha256",
            "recoveryClaimed",
            "historicalEvidenceAttached",
        },
        "authorization_fields_invalid",
    )
    expected = {
        "decision": "NEW_CANONICAL_K2_LINEAGE_AUTHORIZED",
        "decisionDate": "2026-08-21",
        "priorLineageStatus": "NOT_FOUND",
        "locationAuditSha256": LOCATION_AUDIT_SHA256,
        "recoveryClaimed": False,
        "historicalEvidenceAttached": False,
    }
    if dict(authorization) != expected:
        raise BootstrapValidationError("authorization_state_invalid")
    return authorization


def _validate_exit_state(value: Any) -> Mapping[str, Any]:
    exit_state = _fields(
        value,
        {
            "canonicalRootStatus",
            "m6AuthorityStatus",
            "identityLockStatus",
            "rightsAuthorityStatus",
            "providerAuthorityStatus",
            "budgetAuthorityStatus",
            "p1Gate",
            "publicationAllowed",
        },
        "exit_state_fields_invalid",
    )
    expected = {
        "canonicalRootStatus": "ROOTS_READY",
        "m6AuthorityStatus": "NOT_CREATED",
        "identityLockStatus": "NOT_CREATED",
        "rightsAuthorityStatus": "NOT_CONNECTED",
        "providerAuthorityStatus": "NOT_CONNECTED",
        "budgetAuthorityStatus": "NOT_CONNECTED",
        "p1Gate": "NOT_PASSED",
        "publicationAllowed": False,
    }
    if dict(exit_state) != expected:
        raise BootstrapValidationError("exit_state_invalid")
    return exit_state


def validate_specification(path: Path | str) -> ValidatedSpecification:
    specification_path = Path(path)
    value = _fields(
        _load_json_object(specification_path),
        {"schemaVersion", "packageId", "payload", "payloadSha256"},
        "specification_fields_invalid",
    )
    if value.get("schemaVersion") != SPECIFICATION_SCHEMA_VERSION:
        raise BootstrapValidationError("specification_schema_invalid")
    if value.get("packageId") != PACKAGE_ID:
        raise BootstrapValidationError("package_id_invalid")
    _reject_secret_fields(value)

    payload = _fields(
        value.get("payload"),
        {
            "authorization",
            "scope",
            "series",
            "creativePlan",
            "project",
            "episode",
            "seriesPlan",
            "script",
            "productionRun",
            "exitState",
        },
        "payload_fields_invalid",
    )
    payload_digest = _canonical_digest(payload)
    declared_digest = value.get("payloadSha256")
    if (
        not isinstance(declared_digest, str)
        or SHA256_PATTERN.fullmatch(declared_digest) is None
        or declared_digest != payload_digest
    ):
        raise BootstrapValidationError("payload_digest_mismatch")

    _validate_authorization(payload.get("authorization"))
    scope = _fields(
        payload.get("scope"),
        {"workspaceRef", "contentProfileRef"},
        "scope_fields_invalid",
    )
    _ref(scope.get("workspaceRef"), "workspace_ref_invalid")
    _ref(scope.get("contentProfileRef"), "content_profile_ref_invalid")
    if scope["workspaceRef"] == scope["contentProfileRef"]:
        raise BootstrapValidationError("scope_refs_must_be_distinct")

    series = _fields(
        payload.get("series"),
        {"title", "description", "plannedEpisodeCount"},
        "series_fields_invalid",
    )
    _text(series.get("title"), "series_title_invalid", maximum=300)
    _text(series.get("description"), "series_description_invalid", maximum=2_000)
    if _integer(series.get("plannedEpisodeCount"), "series_count_invalid") != 1:
        raise BootstrapValidationError("series_count_must_equal_one")

    creative = _fields(
        payload.get("creativePlan"),
        {
            "humanConfirmed",
            "sourcePlanRef",
            "sourcePlanSchemaVersion",
            "sourcePlanVersion",
            "brief",
            "sourcePlan",
        },
        "creative_plan_fields_invalid",
    )
    _true(creative.get("humanConfirmed"), "creative_plan_confirmation_required")
    _ref(creative.get("sourcePlanRef"), "source_plan_ref_invalid")
    if creative.get("sourcePlanSchemaVersion") != AI_DIRECTOR_SCHEMA_VERSION:
        raise BootstrapValidationError("source_plan_schema_invalid")
    if _integer(creative.get("sourcePlanVersion"), "source_plan_version_invalid") != 1:
        raise BootstrapValidationError("source_plan_version_must_equal_one")
    brief = _fields(
        creative.get("brief"),
        {"topic", "theme", "audience", "duration", "platform", "style", "character"},
        "creative_brief_fields_invalid",
    )
    try:
        brief_record = CreativeBrief.from_mapping(brief)
        source_plan = validate_plan(creative.get("sourcePlan"), brief_record)
    except Exception as error:
        if error.__class__.__module__.startswith("apps.creator_workspace_mvp"):
            raise BootstrapValidationError("creative_plan_validation_failed") from None
        raise
    if brief_record.duration_seconds != 30:
        raise BootstrapValidationError("creative_duration_must_equal_30")
    if source_plan.get("schemaVersion") != creative.get("sourcePlanSchemaVersion"):
        raise BootstrapValidationError("source_plan_lineage_mismatch")
    if source_plan["productionPlan"]["shotCount"] != 4:
        raise BootstrapValidationError("source_plan_shot_count_must_equal_four")
    if source_plan["productionPlan"]["characters"] != ["林澈", "顾言"]:
        raise BootstrapValidationError("source_plan_characters_invalid")

    project = _fields(
        payload.get("project"),
        {
            "projectType",
            "title",
            "description",
            "targetPlatform",
            "aspectRatio",
            "defaultDurationSec",
            "plannedEpisodeCount",
        },
        "project_fields_invalid",
    )
    if project.get("projectType") != "series":
        raise BootstrapValidationError("project_type_invalid")
    for field in ("title", "description", "targetPlatform"):
        _text(project.get(field), f"project_{field}_invalid", maximum=2_000)
    if project.get("aspectRatio") != "16:9":
        raise BootstrapValidationError("project_aspect_ratio_invalid")
    if _integer(project.get("defaultDurationSec"), "project_duration_invalid") != 30:
        raise BootstrapValidationError("project_duration_must_equal_30")
    if _integer(project.get("plannedEpisodeCount"), "project_count_invalid") != 1:
        raise BootstrapValidationError("project_count_must_equal_one")

    episode = _fields(
        payload.get("episode"),
        {"episodeNumber", "seasonNumber", "volumeNumber", "title"},
        "episode_fields_invalid",
    )
    for field in ("episodeNumber", "seasonNumber", "volumeNumber"):
        if _integer(episode.get(field), f"episode_{field}_invalid") != 1:
            raise BootstrapValidationError("episode_numbering_must_equal_one")
    _text(episode.get("title"), "episode_title_invalid", maximum=300)
    if episode["title"] != source_plan["storyDirection"]["title"]:
        raise BootstrapValidationError("episode_title_lineage_mismatch")

    series_plan = _fields(
        payload.get("seriesPlan"),
        {"humanConfirmed", "candidate"},
        "series_plan_fields_invalid",
    )
    _true(series_plan.get("humanConfirmed"), "series_plan_confirmation_required")
    try:
        series_candidate = validate_series_plan_candidate(
            series_plan.get("candidate"),
            {"plannedEpisodeCount": 1},
        )
    except Exception as error:
        if error.__class__.__module__.startswith("apps.creator_workspace_mvp"):
            raise BootstrapValidationError("series_plan_validation_failed") from None
        raise
    if series_candidate.get("schemaVersion") != SERIES_PLAN_CANDIDATE_SCHEMA_VERSION:
        raise BootstrapValidationError("series_plan_schema_invalid")
    plan_items = series_candidate["episodePlanItems"]
    if (
        len(plan_items) != 1
        or plan_items[0]["episodeNumber"] != 1
        or plan_items[0]["title"] != episode["title"]
    ):
        raise BootstrapValidationError("series_plan_episode_mismatch")

    script = _fields(
        payload.get("script"),
        {"humanConfirmed", "candidate"},
        "script_fields_invalid",
    )
    _true(script.get("humanConfirmed"), "script_confirmation_required")
    candidate_value = script.get("candidate")
    if not isinstance(candidate_value, Mapping):
        raise BootstrapValidationError("script_candidate_invalid")
    if candidate_value.get("schemaVersion") != SCRIPT_CANDIDATE_SCHEMA_VERSION:
        raise BootstrapValidationError("script_schema_invalid")
    try:
        script_candidate = validate_script_candidate(
            candidate_value,
            {"storyboardPlan": source_plan["storyboardPlan"]},
        )
    except Exception as error:
        if error.__class__.__module__.startswith("apps.creator_workspace_mvp"):
            raise BootstrapValidationError("script_validation_failed") from None
        raise
    scenes = script_candidate["scenes"]
    if len(scenes) != 2 or script_candidate["targetDurationSec"] != 30:
        raise BootstrapValidationError("script_structure_invalid")
    if sum(scene["estimatedDurationSec"] for scene in scenes) != 30:
        raise BootstrapValidationError("script_scene_duration_invalid")
    character_names = sorted(
        {character for scene in scenes for character in scene["characters"]}
    )
    if character_names != ["林澈", "顾言"]:
        raise BootstrapValidationError("script_characters_invalid")
    if script_candidate["title"] != episode["title"]:
        raise BootstrapValidationError("script_title_lineage_mismatch")

    production_run = _fields(
        payload.get("productionRun"),
        {"idempotencyKey", "shotsPerScene"},
        "production_run_fields_invalid",
    )
    _ref(production_run.get("idempotencyKey"), "idempotency_key_invalid")
    shots = production_run.get("shotsPerScene")
    if shots != [2, 2] or any(isinstance(item, bool) for item in shots):
        raise BootstrapValidationError("shots_per_scene_invalid")
    _validate_exit_state(payload.get("exitState"))

    return ValidatedSpecification(
        specification_path.resolve(),
        value,
        payload,
        _canonical_digest(value),
        payload_digest,
        source_plan,
        series_candidate,
        script_candidate,
    )


def _symlink_component_present(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def validate_target_directory(path: Path | str) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute():
        raise BootstrapValidationError("target_must_be_absolute")
    lexical = Path(os.path.abspath(os.fspath(supplied)))
    if _symlink_component_present(lexical.parent):
        raise BootstrapValidationError("target_symlink_component_rejected")
    try:
        parent = lexical.parent.resolve(strict=True)
    except OSError:
        raise BootstrapValidationError("target_parent_unavailable") from None
    target = parent / lexical.name
    forbidden = {Path("/"), Path("/tmp"), Path.home().resolve()}
    if target in forbidden or target.name in {"", ".", ".."}:
        raise BootstrapValidationError("target_path_forbidden")
    if target.exists() or target.is_symlink():
        raise BootstrapValidationError("target_already_exists")
    try:
        metadata = parent.stat()
    except OSError:
        raise BootstrapValidationError("target_parent_unavailable") from None
    if not stat.S_ISDIR(metadata.st_mode) or not os.access(parent, os.W_OK | os.X_OK):
        raise BootstrapValidationError("target_parent_not_writable")
    return target


def _resolve_repository_commit(explicit: str | None) -> str:
    if explicit is not None:
        value = explicit.strip().lower()
        if COMMIT_PATTERN.fullmatch(value) is None:
            raise BootstrapValidationError("repository_commit_invalid")
        return value
    try:
        status = subprocess.run(
            [
                "git",
                "-C",
                str(REPOSITORY_ROOT),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if status.stdout.strip():
            raise BootstrapValidationError("repository_not_clean")
        resolved = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.strip().lower()
    except BootstrapError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise BootstrapValidationError("repository_commit_unavailable") from None
    if COMMIT_PATTERN.fullmatch(resolved) is None:
        raise BootstrapValidationError("repository_commit_invalid")
    return resolved


def _paths(root: Path) -> BootstrapPaths:
    return BootstrapPaths(
        root=root,
        lifecycle=root / DATABASE_FILENAMES["lifecycle"],
        episode_production=root / DATABASE_FILENAMES["episodeProduction"],
        episode_evidence=root / DATABASE_FILENAMES["episodeEvidence"],
        production_policy=root / DATABASE_FILENAMES["productionPolicy"],
        provider_experiments=root / DATABASE_FILENAMES["providerExperiments"],
    )


def _episode_boundary(
    assembly: LifecycleAssembly,
    paths: BootstrapPaths,
    *,
    initialize_if_missing: bool,
):
    return create_episode_production_boundary(
        paths.episode_production,
        project_boundary=assembly.project_context,
        series_episode_boundary=assembly.series_episode,
        series_planning_boundary=assembly.series_planning,
        script_studio_boundary=assembly.script_studio,
        evidence_database_path=paths.episode_evidence,
        production_policy_database_path=paths.production_policy,
        provider_experiment_database_path=paths.provider_experiments,
        initialize_if_missing=initialize_if_missing,
    )


def _creative_plan_lineage_digest(
    *,
    creative_plan: Mapping[str, Any] | None = None,
    episode_binding: Mapping[str, Any] | None = None,
) -> str:
    source = creative_plan if creative_plan is not None else episode_binding
    if not isinstance(source, Mapping):
        raise BootstrapApplyError("creative_plan_verification_failed")
    projection = {
        "creativePlanRef": source.get("creativePlanRef"),
        "sourcePlanRef": source.get("sourcePlanRef"),
        "sourcePlanSchemaVersion": source.get("sourcePlanSchemaVersion"),
        "sourcePlanVersion": source.get("sourcePlanVersion"),
        "brief": source.get("brief"),
        "sourcePlan": source.get("sourcePlan"),
        "confirmationStatus": "confirmed",
    }
    return _canonical_digest(projection)


def _create_roots(
    specification: ValidatedSpecification,
    paths: BootstrapPaths,
) -> dict[str, Any]:
    payload = specification.payload
    scope = payload["scope"]
    workspace_ref = scope["workspaceRef"]
    content_profile_ref = scope["contentProfileRef"]
    assembly = LifecycleAssembly.sqlite(paths.lifecycle, initialize_or_upgrade=True)

    series = assembly.series_episode.create_series(
        {
            "workspaceRef": workspace_ref,
            "contentProfileRef": content_profile_ref,
            **payload["series"],
        }
    )
    creative_input = payload["creativePlan"]
    creative_plan = assembly.series_episode.confirm_creative_plan(
        {
            "workspaceRef": workspace_ref,
            "humanConfirmed": creative_input["humanConfirmed"],
            "sourcePlanRef": creative_input["sourcePlanRef"],
            "sourcePlanSchemaVersion": creative_input["sourcePlanSchemaVersion"],
            "sourcePlanVersion": creative_input["sourcePlanVersion"],
            "brief": creative_input["brief"],
            "sourcePlan": specification.source_plan,
        }
    )
    project = assembly.project_context.create_project(
        {
            "workspaceRef": workspace_ref,
            "contentProfileRef": content_profile_ref,
            "seriesRef": series["seriesRef"],
            **payload["project"],
        }
    )
    episode = assembly.series_episode.create_episode(
        {
            "workspaceRef": workspace_ref,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": creative_plan["creativePlanRef"],
            **payload["episode"],
        }
    )
    initial_plan = assembly.series_planning.confirm_candidate(
        {
            "workspaceRef": workspace_ref,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": payload["seriesPlan"]["humanConfirmed"],
            "candidate": specification.series_plan_candidate,
        }
    )
    plan_item = initial_plan["version"]["episodePlanItems"][0]
    bound_plan = assembly.series_planning.create_episode_plan_item_binding_version(
        {
            "workspaceRef": workspace_ref,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial_plan["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial_plan["plan"]["version"],
            "episodePlanItemBindings": [
                {
                    "episodeRef": episode["episodeRef"],
                    "episodePlanItemRef": plan_item["episodePlanItemRef"],
                }
            ],
        }
    )
    confirmed_plan = assembly.series_planning.confirm_version(
        {
            "workspaceRef": workspace_ref,
            "seriesPlanRef": bound_plan["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": bound_plan["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": bound_plan["plan"]["version"],
            "humanConfirmed": payload["seriesPlan"]["humanConfirmed"],
        }
    )
    generated_script = assembly.script_studio.create_version(
        {
            "workspaceRef": workspace_ref,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "changeKind": "ai-generation",
            "content": specification.script_candidate,
        }
    )
    confirmed_script = assembly.script_studio.confirm_version(
        {
            "workspaceRef": workspace_ref,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": generated_script["script"]["scriptRef"],
            "scriptVersionRef": generated_script["scriptVersion"]["scriptVersionRef"],
            "humanConfirmed": payload["script"]["humanConfirmed"],
        }
    )
    production = _episode_boundary(assembly, paths, initialize_if_missing=True)
    run_command = {
        "workspaceRef": workspace_ref,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "episodeRef": episode["episodeRef"],
        **payload["productionRun"],
    }
    production_run = production.create_run(run_command)
    if (
        production_run.get("state") != CANONICAL_ROOT_STATUS
        or production_run.get("manifest", {}).get("publicationAllowed") is not False
        or production_run.get("manifest", {}).get("expectedSceneCount") != 2
        or production_run.get("manifest", {}).get("expectedShotCount") != 4
    ):
        raise BootstrapApplyError("production_root_exit_state_invalid")
    return {
        "assembly": assembly,
        "series": series,
        "creativePlan": creative_plan,
        "project": project,
        "episode": episode,
        "confirmedPlan": confirmed_plan,
        "confirmedScript": confirmed_script,
        "runCommand": run_command,
        "productionRun": production_run,
    }


def _restart_and_verify(
    specification: ValidatedSpecification,
    paths: BootstrapPaths,
    created: Mapping[str, Any],
) -> dict[str, Any]:
    workspace_ref = specification.payload["scope"]["workspaceRef"]
    assembly = LifecycleAssembly.sqlite(paths.lifecycle, initialize_or_upgrade=False)
    production = _episode_boundary(assembly, paths, initialize_if_missing=False)
    run_ref = created["productionRun"]["productionRunRef"]
    run = production.get_run(workspace_ref, run_ref)
    replay = production.create_run(created["runCommand"])
    runs = production.list_runs(workspace_ref)
    if (
        len(runs) != 1
        or run.get("productionRunRef") != run_ref
        or run.get("payloadDigest") != created["productionRun"]["payloadDigest"]
        or run.get("upstreamDigest") != created["productionRun"]["upstreamDigest"]
        or run.get("state") != CANONICAL_ROOT_STATUS
        or replay.get("productionRunRef") != run_ref
        or replay.get("idempotentReplay") is not True
    ):
        raise BootstrapApplyError("production_run_restart_verification_failed")

    series = assembly.series_episode.get_series(
        workspace_ref, created["series"]["seriesRef"]
    )
    project = assembly.project_context.get_project(
        workspace_ref, created["project"]["projectRef"]
    )
    episode = assembly.series_episode.get_episode(
        workspace_ref,
        created["series"]["seriesRef"],
        created["episode"]["episodeRef"],
    )
    planning = assembly.series_planning.get_workspace(
        workspace_ref,
        created["project"]["projectRef"],
        created["series"]["seriesRef"],
    )
    script = assembly.script_studio.get_workspace(
        workspace_ref,
        created["series"]["seriesRef"],
        created["episode"]["episodeRef"],
    )
    confirmed_plan_ref = planning["plan"]["confirmedSeriesPlanVersionRef"]
    selected_plan = next(
        item
        for item in planning["versions"]
        if item["seriesPlanVersionRef"] == confirmed_plan_ref
    )
    confirmed_script_ref = script["script"]["confirmedScriptVersionRef"]
    selected_script = next(
        item
        for item in script["versions"]
        if item["scriptVersionRef"] == confirmed_script_ref
    )
    if (
        series["version"] != created["series"]["version"]
        or project["version"] != created["project"]["version"]
        or episode["version"] != created["episode"]["version"]
        or confirmed_plan_ref
        != created["confirmedPlan"]["confirmedSeriesPlanVersionRef"]
        or confirmed_script_ref
        != created["confirmedScript"]["script"]["confirmedScriptVersionRef"]
        or _creative_plan_lineage_digest(
            creative_plan=created["creativePlan"]
        )
        != _creative_plan_lineage_digest(
            episode_binding=episode["confirmedPlanBinding"]
        )
    ):
        raise BootstrapApplyError("lifecycle_restart_verification_failed")
    return {
        "assembly": assembly,
        "series": series,
        "project": project,
        "episode": episode,
        "planning": planning,
        "selectedPlan": selected_plan,
        "script": script,
        "selectedScript": selected_script,
        "productionRun": run,
    }


def _parse_scan_value(lines: Sequence[str], prefix: str) -> str:
    values = [line[len(prefix) :] for line in lines if line.startswith(prefix)]
    if len(values) != 1:
        raise BootstrapApplyError("readonly_scan_summary_invalid")
    return values[0]


def _readonly_scan_verify(paths: BootstrapPaths, expected_run: Mapping[str, Any]) -> dict[str, Any]:
    captured = StringIO()
    with redirect_stdout(captured):
        exit_code = k2_readonly_lineage_scan.scan(
            paths.root,
            max_depth=1,
            max_rows=20,
        )
    lines = captured.getvalue().splitlines()
    if exit_code != 0:
        raise BootstrapApplyError("readonly_scan_failed")
    mode = _parse_scan_value(lines, "K2_SCAN_MODE=")
    database_count = int(_parse_scan_value(lines, "K2_DATABASES_FOUND="))
    production_database_count = int(
        _parse_scan_value(lines, "K2_PRODUCTION_DATABASES_FOUND=")
    )
    production_run_count = int(
        _parse_scan_value(lines, "K2_PRODUCTION_RUNS_FOUND=")
    )
    status_value = _parse_scan_value(lines, "K2_CURRENT_LINEAGE_STATUS=")
    run_values = [
        json.loads(line[len("K2_RUN=") :])
        for line in lines
        if line.startswith("K2_RUN=")
    ]
    if (
        mode != "SQLITE_READ_ONLY_QUERY_ONLY"
        or database_count < 2
        or production_database_count != 1
        or production_run_count != 1
        or status_value != "FOUND_READ_ONLY"
        or len(run_values) != 1
    ):
        raise BootstrapApplyError("readonly_scan_lineage_count_invalid")
    projected = run_values[0]
    expected_projection = {
        "workspace_ref": expected_run["workspaceRef"],
        "production_run_ref": expected_run["productionRunRef"],
        "content_profile_ref": expected_run["contentProfileRef"],
        "project_ref": expected_run["projectRef"],
        "series_ref": expected_run["seriesRef"],
        "episode_ref": expected_run["episodeRef"],
        "series_plan_ref": expected_run["seriesPlanRef"],
        "series_plan_version_ref": expected_run["seriesPlanVersionRef"],
        "episode_plan_item_ref": expected_run["episodePlanItemRef"],
        "script_ref": expected_run["scriptRef"],
        "script_version_ref": expected_run["scriptVersionRef"],
        "upstream_digest": expected_run["upstreamDigest"],
        "payload_digest": expected_run["payloadDigest"],
        "state": expected_run["state"],
        "created_at": expected_run["createdAt"],
        "updated_at": expected_run["updatedAt"],
        "version": expected_run["version"],
    }
    if projected != expected_projection:
        raise BootstrapApplyError("readonly_scan_projection_mismatch")
    zero_row_tables = {
        "v5_episode_production_facts",
        "v5_episode_production_gates",
        "v5_production_policy_bundles",
        "v5_provider_experiments",
    }
    table_rows: dict[str, int] = {}
    for line in lines:
        if not line.startswith("K2_TABLE="):
            continue
        value = json.loads(line[len("K2_TABLE=") :])
        table_rows[value["table"]] = int(value["rows"])
    if any(table_rows.get(table) != 0 for table in zero_row_tables):
        raise BootstrapApplyError("downstream_authority_or_provider_fact_present")
    return {
        "mode": mode,
        "databaseCount": database_count,
        "productionDatabaseCount": production_database_count,
        "productionRunCount": production_run_count,
        "currentLineageStatus": status_value,
        "downstreamFactTablesEmpty": True,
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        raise BootstrapApplyError("file_digest_failed") from None
    return digest.hexdigest()


def _database_inventory(paths: BootstrapPaths) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for filename in sorted(DATABASE_FILENAMES.values()):
        path = paths.root / filename
        try:
            metadata = path.lstat()
        except OSError:
            raise BootstrapApplyError("database_file_missing") from None
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size == 0:
            raise BootstrapApplyError("database_file_invalid")
        result.append({"path": filename, "sha256": _sha256_file(path)})
    return result


def _build_receipt(
    specification: ValidatedSpecification,
    repository_commit: str,
    created: Mapping[str, Any],
    restarted: Mapping[str, Any],
    scan: Mapping[str, Any],
    databases: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    run = restarted["productionRun"]
    selected_plan = restarted["selectedPlan"]
    selected_script = restarted["selectedScript"]
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA_VERSION,
        "packageId": PACKAGE_ID,
        "specification": {
            "schemaVersion": SPECIFICATION_SCHEMA_VERSION,
            "sha256": specification.specification_sha256,
            "payloadSha256": specification.payload_sha256,
            "repositoryCommit": repository_commit,
        },
        "databaseFiles": list(databases),
        "lineage": {
            "workspaceRef": run["workspaceRef"],
            "contentProfileRef": run["contentProfileRef"],
            "series": {
                "seriesRef": run["seriesRef"],
                "version": restarted["series"]["version"],
            },
            "creativePlan": {
                "creativePlanRef": created["creativePlan"]["creativePlanRef"],
                "version": created["creativePlan"]["version"],
                "sourcePlanRef": created["creativePlan"]["sourcePlanRef"],
                "sourcePlanSchemaVersion": created["creativePlan"][
                    "sourcePlanSchemaVersion"
                ],
                "sourcePlanVersion": created["creativePlan"]["sourcePlanVersion"],
                "lineageDigest": _creative_plan_lineage_digest(
                    creative_plan=created["creativePlan"]
                ),
            },
            "project": {
                "projectRef": run["projectRef"],
                "version": restarted["project"]["version"],
            },
            "episode": {
                "episodeRef": run["episodeRef"],
                "version": restarted["episode"]["version"],
            },
            "seriesPlan": {
                "seriesPlanRef": run["seriesPlanRef"],
                "planVersion": restarted["planning"]["plan"]["version"],
                "seriesPlanVersionRef": run["seriesPlanVersionRef"],
                "versionNumber": selected_plan["versionNumber"],
                "versionDigest": run["upstreamSnapshot"]["seriesPlan"][
                    "versionDigest"
                ],
                "episodePlanItemRef": run["episodePlanItemRef"],
            },
            "script": {
                "scriptRef": run["scriptRef"],
                "scriptVersion": restarted["script"]["script"]["version"],
                "scriptVersionRef": run["scriptVersionRef"],
                "versionNumber": selected_script["versionNumber"],
                "versionDigest": run["upstreamSnapshot"]["script"]["versionDigest"],
            },
            "episodeProductionRun": {
                "productionRunRef": run["productionRunRef"],
                "version": run["version"],
                "state": run["state"],
                "upstreamDigest": run["upstreamDigest"],
                "payloadDigest": run["payloadDigest"],
            },
        },
        "verification": {
            "restartVerified": True,
            "scannerMode": scan["mode"],
            "databaseCount": scan["databaseCount"],
            "productionDatabaseCount": scan["productionDatabaseCount"],
            "productionRunCount": scan["productionRunCount"],
            "currentLineageStatus": scan["currentLineageStatus"],
            "downstreamFactTablesEmpty": scan["downstreamFactTablesEmpty"],
        },
        "exitState": dict(specification.payload["exitState"]),
    }
    _reject_secret_fields(receipt)
    return receipt


def _write_private(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        raise BootstrapApplyError("evidence_write_failed") from None


def _set_private_permissions(root: Path) -> None:
    try:
        for directory, child_directories, filenames in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            if directory_path.is_symlink():
                raise BootstrapApplyError("staging_symlink_rejected")
            os.chmod(directory_path, 0o700)
            for name in child_directories:
                child = directory_path / name
                if child.is_symlink():
                    raise BootstrapApplyError("staging_symlink_rejected")
            for name in filenames:
                child = directory_path / name
                if child.is_symlink() or not child.is_file():
                    raise BootstrapApplyError("staging_file_invalid")
                os.chmod(child, 0o600)
    except BootstrapError:
        raise
    except OSError:
        raise BootstrapApplyError("private_permissions_failed") from None


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        raise BootstrapApplyError("directory_fsync_failed") from None


def _fsync_tree(root: Path) -> None:
    try:
        for directory, _, filenames in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            for name in filenames:
                descriptor = os.open(directory_path / name, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            _fsync_directory(directory_path)
    except BootstrapError:
        raise
    except OSError:
        raise BootstrapApplyError("tree_fsync_failed") from None


def _rename_noreplace(source: Path, target: Path) -> None:
    try:
        library = ctypes.CDLL(None, use_errno=True)
        operation = library.renameat2
    except (OSError, AttributeError):
        raise BootstrapApplyError("atomic_noreplace_unavailable") from None
    operation.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    result = operation(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(target),
        1,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise BootstrapApplyError("target_already_exists")
    if error_number in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
        raise BootstrapApplyError("atomic_noreplace_unavailable")
    raise BootstrapApplyError("atomic_publish_failed")


def _cleanup_staging(staging: Path, parent: Path, prefix: str) -> None:
    try:
        if staging.parent.resolve() != parent.resolve() or not staging.name.startswith(prefix):
            raise BootstrapApplyError("staging_cleanup_scope_invalid")
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)
    except BootstrapError:
        raise
    except OSError:
        raise BootstrapApplyError("staging_cleanup_failed") from None


def apply_bootstrap(
    specification: ValidatedSpecification,
    target_directory: Path | str,
    *,
    acknowledgement: str,
    repository_commit: str,
) -> BootstrapResult:
    if acknowledgement != ACKNOWLEDGEMENT:
        raise BootstrapValidationError("exact_acknowledgement_required")
    if COMMIT_PATTERN.fullmatch(repository_commit) is None:
        raise BootstrapValidationError("repository_commit_invalid")
    target = validate_target_directory(target_directory)
    parent = target.parent
    prefix = f".{target.name}.staging-"
    try:
        staging = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
        os.chmod(staging, 0o700)
    except OSError:
        raise BootstrapApplyError("staging_creation_failed") from None
    published = False
    try:
        paths = _paths(staging)
        created = _create_roots(specification, paths)
        restarted = _restart_and_verify(specification, paths, created)
        scan = _readonly_scan_verify(paths, restarted["productionRun"])
        _set_private_permissions(staging)
        databases = _database_inventory(paths)
        receipt = _build_receipt(
            specification,
            repository_commit,
            created,
            restarted,
            scan,
            databases,
        )
        receipt_bytes = _canonical_bytes(receipt) + b"\n"
        receipt_path = staging / RECEIPT_FILENAME
        _write_private(receipt_path, receipt_bytes)
        inventory_entries = [
            *databases,
            {"path": RECEIPT_FILENAME, "sha256": sha256(receipt_bytes).hexdigest()},
        ]
        inventory_content = "".join(
            f"{item['sha256']}  {item['path']}\n"
            for item in sorted(inventory_entries, key=lambda item: item["path"])
        ).encode("utf-8")
        inventory_path = staging / INVENTORY_FILENAME
        _write_private(inventory_path, inventory_content)
        _set_private_permissions(staging)
        _fsync_tree(staging)
        _fsync_directory(parent)
        _rename_noreplace(staging, target)
        published = True
        _fsync_directory(parent)
        return BootstrapResult(
            target=target,
            receipt=receipt,
            receipt_sha256=sha256(receipt_bytes).hexdigest(),
            inventory_sha256=sha256(inventory_content).hexdigest(),
        )
    except BootstrapError:
        raise
    except Exception as error:
        raise BootstrapApplyError(
            "unexpected_" + type(error).__name__.lower()
        ) from None
    finally:
        if not published and staging.exists():
            _cleanup_staging(staging, parent, prefix)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or atomically create the one authorized K2 canonical root "
            "lineage; default mode performs no write."
        )
    )
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--acknowledge-new-lineage")
    parser.add_argument("--repository-commit")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _arguments(argv)
        specification = validate_specification(args.spec)
        target = validate_target_directory(args.target_dir)
        print("K2_CANONICAL_BOOTSTRAP_VALIDATION=PASS")
        print("SPECIFICATION_SCHEMA_VERSION=" + SPECIFICATION_SCHEMA_VERSION)
        print("PACKAGE_ID=" + PACKAGE_ID)
        print("SPECIFICATION_SHA256=" + specification.specification_sha256)
        print("PAYLOAD_SHA256=" + specification.payload_sha256)
        if not args.apply:
            print("K2_CANONICAL_BOOTSTRAP_MODE=DRY_RUN_NO_WRITE")
            print("K2_CANONICAL_ROOT_STATUS=NOT_CREATED")
            print("M6_AUTHORITY_STATUS=NOT_CREATED")
            print("IDENTITY_LOCK_STATUS=NOT_CREATED")
            print("P1_GATE=NOT_PASSED")
            print("PUBLICATION_ALLOWED=false")
            return 0
        repository_commit = _resolve_repository_commit(args.repository_commit)
        result = apply_bootstrap(
            specification,
            target,
            acknowledgement=args.acknowledge_new_lineage or "",
            repository_commit=repository_commit,
        )
        run = result.receipt["lineage"]["episodeProductionRun"]
        print("K2_CANONICAL_BOOTSTRAP=PASS")
        print("CANONICAL_TARGET=" + str(result.target))
        print("REPOSITORY_COMMIT=" + repository_commit)
        print("RECEIPT_SHA256=" + result.receipt_sha256)
        print("INVENTORY_SHA256=" + result.inventory_sha256)
        print("WORKSPACE_REF=" + result.receipt["lineage"]["workspaceRef"])
        print("PROJECT_REF=" + result.receipt["lineage"]["project"]["projectRef"])
        print("SERIES_REF=" + result.receipt["lineage"]["series"]["seriesRef"])
        print("EPISODE_REF=" + result.receipt["lineage"]["episode"]["episodeRef"])
        print("EPISODE_PRODUCTION_RUN_REF=" + run["productionRunRef"])
        print("EPISODE_PRODUCTION_RUN_PAYLOAD_DIGEST=" + run["payloadDigest"])
        print("K2_CANONICAL_ROOT_STATUS=" + run["state"])
        print("M6_AUTHORITY_STATUS=NOT_CREATED")
        print("IDENTITY_LOCK_STATUS=NOT_CREATED")
        print("P1_GATE=NOT_PASSED")
        print("PUBLICATION_ALLOWED=false")
        return 0
    except BootstrapError as error:
        print("K2_CANONICAL_BOOTSTRAP=FAIL")
        print("K2_BOOTSTRAP_ERROR=" + error.code)
        return 2
    except Exception as error:
        print("K2_CANONICAL_BOOTSTRAP=FAIL")
        print("K2_BOOTSTRAP_ERROR=unexpected_" + type(error).__name__.lower())
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
