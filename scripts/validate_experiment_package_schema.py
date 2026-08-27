#!/usr/bin/env python3
"""Validate camera-field alignment for one explicitly selected new package.

This is a pre-package gate, not a repository migration.  It reads only the
``shots.json`` and ``camera_contract.json`` below ``--new-package-root``.  It
never discovers or scans existing experiment packages, so frozen legacy
packages remain outside the gate unless an operator explicitly selects them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.v5_core_os.episode_production.shot_graph import (  # noqa: E402
    ValidationFailedError,
    _camera,
    _validate_camera,
)


CAMERA_FIELD_ALIASES = {
    "framing": "shotSize",
    "primaryMove": "movement",
    "lensMmEquivalent": "lensMm",
}


class ExperimentSchemaGateError(ValueError):
    """A newly created experiment package is not schema-aligned."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ExperimentSchemaGateError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExperimentSchemaGateError(f"{label} could not be read") from exc
    except UnicodeDecodeError as exc:
        raise ExperimentSchemaGateError(f"{label} is not valid UTF-8 JSON") from exc
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ExperimentSchemaGateError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ExperimentSchemaGateError(f"{label} must be a JSON object")
    return value


def _domain_camera_fields() -> tuple[str, ...]:
    """Derive the field contract from every branch of the domain camera factory."""

    samples = (
        _camera(global_order=1, scene_order=1, scene_shot_count=3),
        _camera(global_order=2, scene_order=2, scene_shot_count=3),
        _camera(global_order=3, scene_order=3, scene_shot_count=3),
    )
    fields = tuple(samples[0])
    field_set = set(fields)
    if not fields or any(set(sample) != field_set for sample in samples[1:]):
        raise ExperimentSchemaGateError(
            "domain _camera() branches do not expose one stable field schema"
        )
    return fields


def _reject_camera_aliases(value: Any, field: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            replacement = CAMERA_FIELD_ALIASES.get(key)
            if replacement is not None:
                raise ExperimentSchemaGateError(
                    f"{field}.{key} is prohibited; use {replacement}"
                )
            _reject_camera_aliases(item, f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_camera_aliases(item, f"{field}[{index}]")


def _shots(value: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    shots = value.get("shots")
    if (
        not isinstance(shots, list)
        or not shots
        or not all(isinstance(shot, Mapping) for shot in shots)
    ):
        raise ExperimentSchemaGateError(f"{label}.shots must be a non-empty array")
    return shots


def _validate_camera_payload(
    value: Mapping[str, Any],
    field: str,
    domain_fields: Sequence[str],
) -> None:
    missing = [name for name in domain_fields if name not in value]
    if missing:
        raise ExperimentSchemaGateError(
            f"{field} is missing domain camera fields: {', '.join(missing)}"
        )
    projection = {name: value[name] for name in domain_fields}
    try:
        _validate_camera(projection, field)
    except ValidationFailedError as exc:
        raise ExperimentSchemaGateError(str(exc)) from exc


def _validate_camera_contract(
    value: Mapping[str, Any], domain_fields: Sequence[str]
) -> int:
    shots = _shots(value, "camera_contract.json")
    for index, shot in enumerate(shots):
        camera = shot.get("camera")
        if not isinstance(camera, Mapping):
            raise ExperimentSchemaGateError(
                f"camera_contract.json.shots[{index}].camera must be an object"
            )
        _validate_camera_payload(
            camera,
            f"camera_contract.json.shots[{index}].camera",
            domain_fields,
        )
    return len(shots)


def _validate_shots_document(
    value: Mapping[str, Any], domain_fields: Sequence[str]
) -> int:
    """Validate camera data when shots.json carries it; references may omit it."""

    shots = _shots(value, "shots.json")
    count = 0
    domain_field_set = set(domain_fields)
    for index, shot in enumerate(shots):
        camera = shot.get("camera")
        if camera is not None:
            if not isinstance(camera, Mapping):
                raise ExperimentSchemaGateError(
                    f"shots.json.shots[{index}].camera must be an object"
                )
            _validate_camera_payload(
                camera,
                f"shots.json.shots[{index}].camera",
                domain_fields,
            )
            count += 1
            continue

        direct_fields = domain_field_set.intersection(shot)
        if direct_fields:
            _validate_camera_payload(
                shot,
                f"shots.json.shots[{index}]",
                domain_fields,
            )
            count += 1
    return count


def validate_new_package(package_root: Path) -> dict[str, Any]:
    """Validate exactly one caller-selected package directory without discovery."""

    root = package_root.resolve()
    if not root.is_dir():
        raise ExperimentSchemaGateError("--new-package-root must be a directory")

    shots = _load_object(root / "shots.json", "shots.json")
    camera_contract = _load_object(
        root / "camera_contract.json", "camera_contract.json"
    )
    domain_fields = _domain_camera_fields()

    _reject_camera_aliases(shots, "shots.json")
    _reject_camera_aliases(camera_contract, "camera_contract.json")

    shots_camera_count = _validate_shots_document(shots, domain_fields)
    contract_camera_count = _validate_camera_contract(
        camera_contract, domain_fields
    )
    return {
        "packageRoot": str(root),
        "domainCameraFields": list(domain_fields),
        "shotsCameraCount": shots_camera_count,
        "cameraContractCameraCount": contract_camera_count,
        "discoveredPackageCount": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed camera schema gate for one newly created experiment package. "
            "No existing packages are discovered or scanned."
        )
    )
    parser.add_argument(
        "--new-package-root",
        required=True,
        type=Path,
        help="new package directory containing shots.json and camera_contract.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = validate_new_package(args.new_package_root)
    except ExperimentSchemaGateError as exc:
        print(f"EXPERIMENT_PACKAGE_SCHEMA_GATE=FAIL: {exc}", file=sys.stderr)
        return 2

    print("EXPERIMENT_PACKAGE_SCHEMA_GATE=PASS")
    print("SCOPE=EXPLICIT_NEW_PACKAGE_ONLY")
    print(f"PACKAGE_ROOT={result['packageRoot']}")
    print(f"DOMAIN_CAMERA_FIELDS={','.join(result['domainCameraFields'])}")
    print(f"SHOTS_JSON_CAMERA_COUNT={result['shotsCameraCount']}")
    print(
        "CAMERA_CONTRACT_CAMERA_COUNT="
        f"{result['cameraContractCameraCount']}"
    )
    print(f"DISCOVERED_PACKAGE_COUNT={result['discoveredPackageCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
