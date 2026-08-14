#!/usr/bin/env python3
"""Validate a CCV-R2 G1 preparation directory without contacting ComfyUI."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_STATE = "GPU_READY_PREPARATION_COMPLETE_NO_GPU_EXECUTION"


class ValidationError(RuntimeError):
    pass


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(16 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def classify(prompt: dict[str, Any]) -> tuple[bool, bool]:
    names = [str(node.get("class_type", "")).lower() for node in prompt.values() if isinstance(node, dict)]
    return (
        any("ipadapter" in name and "loader" not in name for name in names),
        any("controlnetapply" in name for name in names),
    )


def inspect_payload(path: Path, request: dict[str, Any]) -> None:
    payload = json.loads(path.read_text("utf-8"))
    require(set(payload) == {"prompt", "extra_data"}, f"{path.name}: unexpected envelope")
    prompt = payload["prompt"]
    meta = payload["extra_data"]["extra_pnginfo"]["ccvR2"]
    for field in ("runId", "blindLabel", "armId", "shotId", "seed"):
        require(meta[field] == request[field], f"{path.name}: metadata mismatch for {field}")
    expected = {
        "A0_TEXT_BASELINE": (False, False),
        "A1_FACE_IDENTITY": (True, False),
        "A2_FACE_OPENPOSE": (True, True),
    }[request["armId"]]
    require(classify(prompt) == expected, f"{path.name}: arm graph semantics mismatch")
    samplers = [node for node in prompt.values() if isinstance(node, dict) and node.get("class_type") == "KSampler"]
    require(len(samplers) == 1, f"{path.name}: expected one KSampler")
    inputs = samplers[0].get("inputs", {})
    require(inputs.get("seed") == request["seed"], f"{path.name}: seed mismatch")
    require(inputs.get("steps") == 25, f"{path.name}: steps mismatch")
    require(inputs.get("cfg") == 7, f"{path.name}: cfg mismatch")
    require(inputs.get("sampler_name") == "dpmpp_2m", f"{path.name}: sampler mismatch")
    require(inputs.get("scheduler") == "karras", f"{path.name}: scheduler mismatch")
    saves = [node for node in prompt.values() if isinstance(node, dict) and node.get("class_type") == "SaveImage"]
    require(len(saves) == 1, f"{path.name}: expected one SaveImage")
    prefix = saves[0].get("inputs", {}).get("filename_prefix")
    require(prefix == f"ccv-r2/{request['blindLabel']}__{request['runId']}", f"{path.name}: output prefix mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preparation_root", type=Path)
    args = parser.parse_args()
    root = args.preparation_root.resolve()
    try:
        receipt_path = root / "execution-readiness.json"
        inventory_path = root / "preparation-inventory.json"
        marker_path = root / "preparation-inventory.sha256"
        for path in (receipt_path, inventory_path, marker_path):
            require(path.is_file(), f"missing required file: {path}")
        receipt = json.loads(receipt_path.read_text("utf-8"))
        require(receipt.get("state") == EXPECTED_STATE, "readiness state mismatch")
        claims = receipt.get("claims", {})
        for field in (
            "gpuExecutionAuthorized",
            "gpuExecutionStarted",
            "comfyUiQueueTouched",
            "modelLoaded",
            "imageGenerated",
            "validationAccepted",
            "productionReady",
        ):
            require(claims.get(field) is False, f"claim must remain false: {field}")
        requests = receipt.get("requests")
        require(isinstance(requests, list) and len(requests) == 45, "receipt must contain 45 requests")
        require(receipt.get("counts") == {"arms": 3, "shots": 5, "seeds": 3, "runs": 45}, "count block mismatch")
        for field in ("runId", "blindLabel", "plannedOutputPath"):
            values = [row[field] for row in requests]
            require(len(values) == len(set(values)), f"duplicate request field: {field}")
        inventory = json.loads(inventory_path.read_text("utf-8"))["entries"]
        marker_sha = marker_path.read_text("utf-8").split()[0]
        actual_inventory_sha, _ = sha256_file(inventory_path)
        require(marker_sha == actual_inventory_sha, "inventory marker digest mismatch")
        indexed = {row["path"]: row for row in inventory}
        for relative, row in indexed.items():
            path = root / relative
            require(path.is_file(), f"inventory path missing: {relative}")
            digest, size = sha256_file(path)
            require(digest == row["sha256"] and size == row["sizeBytes"], f"inventory mismatch: {relative}")
        for index, request in enumerate(requests, start=1):
            path = Path(request["path"])
            if path.is_absolute():
                path = root / "requests" / path.name
            else:
                path = root / path
            if not path.is_file():
                path = root / "requests" / f"{request['blindLabel']}__{request['runId']}.json"
            digest, size = sha256_file(path)
            require(digest == request["sha256"] and size == request["sizeBytes"], f"request digest mismatch: {path.name}")
            inspect_payload(path, request)
            print(f"VALIDATE {index}/45 {request['runId']}")
        actual_files = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name not in {"preparation-inventory.json", "preparation-inventory.sha256"}
        }
        require(actual_files == set(indexed), "unindexed or missing preparation files")
        print("CCV_R2_G1_PREPARATION_VALIDATION=PASS")
        print("REQUEST_COUNT=45")
        print(f"PREPARATION_ROOT={root}")
        return 0
    except (OSError, KeyError, ValueError, ValidationError) as exc:
        print("CCV_R2_G1_PREPARATION_VALIDATION=FAIL")
        print(f"ERROR={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
