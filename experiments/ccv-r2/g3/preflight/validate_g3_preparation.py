#!/usr/bin/env python3
"""Fail-closed independent validation of a CCV-R2 G3 no-GPU preparation root."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


EXPECTED_SCHEMA = "ACS-CCV-R2-G3-READINESS-1"
EXPECTED_STATE = "G3_GPU_READY_PREPARATION_COMPLETE_NO_GPU_EXECUTION"
EXPECTED_GOVERNANCE = "ACS-CCV-R2-G3-G1-NO-GPU-PREPARATION"
EXPECTED_G0_COMMIT = "41faaadf4c959944da3afd8c1d52b3e2429da68c"
OPAQUE_RUN = re.compile(r"^G3R[0-9A-F]{16}$")
OPAQUE_LABEL = re.compile(r"^G3B\d{3}$")
FALSE_CLAIMS = {
    "gpuExecutionAuthorized": False,
    "gpuExecutionStarted": False,
    "comfyUiQueueTouched": False,
    "modelLoaded": False,
    "imageGenerated": False,
    "validationAccepted": False,
    "productionReady": False,
}


class ValidationError(RuntimeError):
    pass


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON {path}: {exc}") from exc


def confined(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValidationError(f"unconfined relative path: {relative}")
    path = (root / Path(*pure.parts)).resolve()
    if root.resolve() not in path.parents:
        raise ValidationError(f"path escapes preparation root: {relative}")
    return path


def verify_control(root: Path, record: dict[str, Any], label: str) -> Path:
    path = confined(root, record["path"])
    if not path.is_file():
        raise ValidationError(f"{label} missing: {record['path']}")
    digest, size = sha256_file(path)
    if digest != record["sha256"] or size != record["sizeBytes"]:
        raise ValidationError(f"{label} digest/size mismatch: {record['path']}")
    return path


def validate_request(root: Path, row: dict[str, Any]) -> None:
    allowed = {
        "path", "sizeBytes", "sha256", "runId", "blindLabel", "shotId",
        "seed", "phase", "plannedOutputPath",
    }
    if set(row) != allowed:
        raise ValidationError(f"request public keys mismatch: {sorted(set(row) ^ allowed)}")
    if not OPAQUE_RUN.fullmatch(row["runId"]):
        raise ValidationError(f"non-opaque runId: {row['runId']}")
    if not OPAQUE_LABEL.fullmatch(row["blindLabel"]):
        raise ValidationError(f"invalid blind label: {row['blindLabel']}")
    path = verify_control(root, row, "request")
    if path.name != f"{row['blindLabel']}__{row['runId']}.json":
        raise ValidationError(f"request filename mismatch: {path.name}")
    payload = load_json(path)
    metadata = payload.get("extra_data", {}).get("extra_pnginfo", {}).get("ccvR2G3")
    expected = {
        "runId": row["runId"],
        "blindLabel": row["blindLabel"],
        "shotId": row["shotId"],
        "seed": row["seed"],
        "protocolVersion": "g3-rcr-v1",
    }
    if metadata != expected:
        raise ValidationError(f"request metadata mismatch: {row['runId']}")
    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        raise ValidationError(f"request prompt missing: {row['runId']}")
    save_nodes = [
        node for node in prompt.values()
        if isinstance(node, dict) and node.get("class_type") == "SaveImage"
    ]
    if len(save_nodes) != 1:
        raise ValidationError(f"request SaveImage count mismatch: {row['runId']}")
    prefix = save_nodes[0].get("inputs", {}).get("filename_prefix")
    if prefix != f"ccv-r2-g3/{row['blindLabel']}__{row['runId']}":
        raise ValidationError(f"request output prefix mismatch: {row['runId']}")


def validate(root: Path) -> tuple[str, str]:
    root = root.resolve()
    receipt_path = root / "g3-readiness.json"
    receipt = load_json(receipt_path)
    if receipt.get("schemaVersion") != EXPECTED_SCHEMA:
        raise ValidationError("readiness schemaVersion mismatch")
    if receipt.get("state") != EXPECTED_STATE:
        raise ValidationError("readiness state mismatch")
    if receipt.get("governanceCheckpoint") != EXPECTED_GOVERNANCE:
        raise ValidationError("readiness governance checkpoint mismatch")
    if receipt.get("g0Commit") != EXPECTED_G0_COMMIT:
        raise ValidationError("readiness G0 commit mismatch")
    if receipt.get("claims") != FALSE_CLAIMS:
        raise ValidationError("readiness claims are not the exact frozen false set")
    if receipt.get("counts") != {"main": 45, "additionalSweep": 6, "uniqueRequests": 51}:
        raise ValidationError("readiness counts mismatch")
    requests = receipt.get("requests")
    if not isinstance(requests, list) or len(requests) != 51:
        raise ValidationError("readiness must contain 51 requests")

    run_ids, labels, paths, outputs = set(), set(), set(), set()
    phase_counts = {"MAIN": 0, "BACK_TURNING_SWEEP": 0}
    for row in requests:
        validate_request(root, row)
        for seen, value, name in (
            (run_ids, row["runId"], "runId"),
            (labels, row["blindLabel"], "blindLabel"),
            (paths, row["path"], "request path"),
            (outputs, row["plannedOutputPath"], "planned output"),
        ):
            if value in seen:
                raise ValidationError(f"duplicate {name}: {value}")
            seen.add(value)
        if row["phase"] not in phase_counts:
            raise ValidationError(f"unknown request phase: {row['phase']}")
        phase_counts[row["phase"]] += 1
    if phase_counts != {"MAIN": 45, "BACK_TURNING_SWEEP": 6}:
        raise ValidationError(f"request phase counts mismatch: {phase_counts}")
    if labels != {f"G3B{index:03d}" for index in range(1, 52)}:
        raise ValidationError("blind-label set is incomplete")

    for key, schema, state in (
        ("technicalMapLock", "ACS-CCV-R2-G3-TECHNICAL-MAP-1", "SEALED_BEFORE_GPU_DO_NOT_SEND_TO_REVIEWERS"),
        ("reviewTemplateLock", "ACS-CCV-R2-G3-REVIEW-TEMPLATE-1", "LOCKED_EMPTY_BEFORE_GPU"),
    ):
        record = receipt.get(key)
        if not isinstance(record, dict):
            raise ValidationError(f"missing {key}")
        path = confined(root, record["path"])
        digest, _ = sha256_file(path)
        if digest != record["sha256"]:
            raise ValidationError(f"{key} digest mismatch")
        value = load_json(path)
        if value.get("schemaVersion") != schema or value.get("state") != state:
            raise ValidationError(f"{key} schema/state mismatch")
        sidecar = path.with_name(path.name + ".sha256")
        expected_line = f"{digest}  {path.name}\n"
        if sidecar.read_text("utf-8") != expected_line:
            raise ValidationError(f"{key} sidecar mismatch")

    technical = load_json(confined(root, receipt["technicalMapLock"]["path"]))
    if technical.get("itemCount") != 51 or len(technical.get("items", [])) != 51:
        raise ValidationError("technical map item count mismatch")
    tech_pairs = {(item.get("runId"), item.get("blindLabel")) for item in technical["items"]}
    if tech_pairs != {(row["runId"], row["blindLabel"]) for row in requests}:
        raise ValidationError("technical map/request binding mismatch")
    if sum(item.get("phase") == "MAIN" for item in technical["items"]) != 45:
        raise ValidationError("technical map main count mismatch")
    if sum(item.get("phase") == "BACK_TURNING_SWEEP" for item in technical["items"]) != 6:
        raise ValidationError("technical map sweep count mismatch")

    inventory = load_json(root / "preparation-inventory.json")
    entries = inventory.get("entries")
    if not isinstance(entries, list):
        raise ValidationError("preparation inventory entries missing")
    entry_paths = [entry.get("path") for entry in entries]
    if len(entry_paths) != len(set(entry_paths)):
        raise ValidationError("preparation inventory contains duplicate paths")
    expected_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_file()
        and path.name not in {"preparation-inventory.json", "preparation-inventory.sha256"}
    }
    if set(entry_paths) != expected_paths:
        raise ValidationError("preparation inventory path set mismatch")
    for entry in entries:
        verify_control(root, entry, "inventory entry")
    inventory_sha, _ = sha256_file(root / "preparation-inventory.json")
    if (root / "preparation-inventory.sha256").read_text("utf-8") != (
        f"{inventory_sha}  preparation-inventory.json\n"
    ):
        raise ValidationError("preparation inventory sidecar mismatch")
    readiness_sha, _ = sha256_file(receipt_path)
    return readiness_sha, inventory_sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preparation_root", type=Path)
    args = parser.parse_args()
    try:
        readiness_sha, inventory_sha = validate(args.preparation_root)
        print("CCV_R2_G3_G1_VALIDATION=PASS")
        print("REQUEST_COUNT=51")
        print(f"READINESS_SHA256={readiness_sha}")
        print(f"PREPARATION_INVENTORY_SHA256={inventory_sha}")
        print("GPU_EXECUTION_STARTED=false")
        print("COMFYUI_QUEUE_TOUCHED=false")
        return 0
    except (OSError, KeyError, TypeError, ValueError, ValidationError) as exc:
        print("CCV_R2_G3_G1_VALIDATION=FAIL")
        print(f"ERROR={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
