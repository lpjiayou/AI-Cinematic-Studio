#!/usr/bin/env python3
"""Independently validate a completed CCV-R2 G3-G2 result root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from execute_g3_gpu_experiment import (
    EXPECTED_INVENTORY_SHA256,
    EXPECTED_RECEIPT_SHA256,
    EXPECTED_RUN_COUNT,
    RESULT_STATE_COMPLETE,
    ExecutionError,
    confined_path,
    load_json,
    require,
    sha256_file,
    verify_authorization,
    verify_completed_row,
)


def validate(result_root: Path) -> tuple[str, str]:
    root = result_root.resolve()
    required_names = {
        "execution-authorization.json",
        "result-ledger.json",
        "failure-ledger.json",
        "execution-receipt.json",
        "result-inventory.json",
        "result-inventory.sha256",
        "review-package.json",
    }
    for name in required_names:
        require((root / name).is_file(), f"missing result control: {name}")
    authorization_path = root / "execution-authorization.json"
    authorization_preliminary = load_json(authorization_path)
    preparation_root = Path(authorization_preliminary["preparationRoot"]).resolve()
    authorization, authorization_sha = verify_authorization(
        authorization_path, preparation_root, root
    )
    receipt_path = preparation_root / "g3-readiness.json"
    preparation_inventory_path = preparation_root / "preparation-inventory.json"
    receipt_sha, _ = sha256_file(receipt_path)
    preparation_inventory_sha, _ = sha256_file(preparation_inventory_path)
    require(receipt_sha == EXPECTED_RECEIPT_SHA256, "source G3-G1 readiness receipt changed")
    require(preparation_inventory_sha == EXPECTED_INVENTORY_SHA256, "source preparation inventory changed")
    source_receipt = load_json(receipt_path)
    requests = source_receipt.get("requests")
    require(isinstance(requests, list) and len(requests) == EXPECTED_RUN_COUNT, "source receipt request count mismatch")
    expected_by_id = {row["runId"]: row for row in requests}
    require(len(expected_by_id) == EXPECTED_RUN_COUNT, "source receipt run IDs are not unique")

    ledger = load_json(root / "result-ledger.json")
    require(ledger.get("schemaVersion") == "ACS-CCV-R2-G3-G2-RESULT-LEDGER-1", "result ledger schema mismatch")
    require(ledger.get("state") == RESULT_STATE_COMPLETE, "result ledger is not complete")
    require(ledger.get("readinessSha256") == receipt_sha, "result ledger receipt mismatch")
    require(ledger.get("authorizationSha256") == authorization_sha, "result ledger authorization mismatch")
    require(
        ledger.get("counts")
        == {"expected": EXPECTED_RUN_COUNT, "queued": EXPECTED_RUN_COUNT, "succeeded": EXPECTED_RUN_COUNT, "failed": 0},
        "result ledger counts mismatch",
    )
    claims = ledger.get("claims", {})
    for field in ("gpuExecutionAuthorized", "gpuExecutionStarted", "comfyUiQueueTouched", "imageGenerated"):
        require(claims.get(field) is True, f"result ledger claim must be true: {field}")
    for field in ("validationAccepted", "productionReady"):
        require(claims.get(field) is False, f"result ledger claim must remain false: {field}")
    rows = ledger.get("runs")
    require(isinstance(rows, list) and len(rows) == EXPECTED_RUN_COUNT, "result ledger must contain 51 rows")
    rows_by_id = {row.get("runId"): row for row in rows}
    require(set(rows_by_id) == set(expected_by_id), "result ledger run set mismatch")
    prompt_ids = [row.get("promptId") for row in rows]
    require(None not in prompt_ids and len(prompt_ids) == len(set(prompt_ids)), "prompt IDs must be unique")
    for index, request in enumerate(requests, start=1):
        row = rows_by_id[request["runId"]]
        require(row.get("state") == "COMPLETE", f"run is not complete: {request['runId']}")
        require(row.get("failureEventId") is None, f"completed run retains failure: {request['runId']}")
        verify_completed_row(row, request, root, source_receipt["protocolVersion"])
        print(f"RESULT_VERIFY {index}/{EXPECTED_RUN_COUNT} {request['runId']}", flush=True)

    failures = load_json(root / "failure-ledger.json")
    require(failures.get("schemaVersion") == "ACS-CCV-R2-G3-G2-FAILURE-LEDGER-1", "failure ledger schema mismatch")
    require(failures.get("events") == [], "failure ledger is not empty")
    require(failures.get("automaticRetryAuthorized") is False, "automatic retry flag changed")

    actual_outputs = {
        path.relative_to(root).as_posix()
        for path in (root / "outputs").rglob("*")
        if path.is_file()
    }
    expected_outputs = {row["plannedOutputPath"] for row in requests}
    require(actual_outputs == expected_outputs, "output file set mismatch")

    inventory_path = root / "result-inventory.json"
    inventory_sha, _ = sha256_file(inventory_path)
    marker = (root / "result-inventory.sha256").read_text("utf-8").split()
    require(marker == [inventory_sha, "result-inventory.json"], "result inventory marker mismatch")
    inventory = load_json(inventory_path)
    require(inventory.get("schemaVersion") == "ACS-CCV-R2-G3-G2-RESULT-INVENTORY-1", "result inventory schema mismatch")
    entries = inventory.get("entries")
    require(isinstance(entries, list) and len(entries) == EXPECTED_RUN_COUNT, "result inventory count mismatch")
    indexed = {entry["path"]: entry for entry in entries}
    require(set(indexed) == expected_outputs, "result inventory paths mismatch")
    for relative, entry in indexed.items():
        path = confined_path(root, relative, prefix="outputs")
        digest, size = sha256_file(path)
        require(digest == entry.get("sha256") and size == entry.get("sizeBytes"), f"result inventory mismatch: {relative}")
        require(entry.get("runId") in expected_by_id, f"result inventory run ID unknown: {relative}")

    execution_receipt = load_json(root / "execution-receipt.json")
    require(execution_receipt.get("state") == RESULT_STATE_COMPLETE, "execution receipt state mismatch")
    require(execution_receipt.get("readinessSha256") == receipt_sha, "execution receipt preparation binding mismatch")
    require(execution_receipt.get("authorizationSha256") == authorization_sha, "execution receipt authorization binding mismatch")
    require(execution_receipt.get("resultInventorySha256") == inventory_sha, "execution receipt inventory binding mismatch")
    require(
        execution_receipt.get("counts")
        == {"expected": EXPECTED_RUN_COUNT, "queued": EXPECTED_RUN_COUNT, "succeeded": EXPECTED_RUN_COUNT, "failed": 0},
        "execution receipt counts mismatch",
    )
    for field in ("validationAccepted", "productionReady"):
        require(execution_receipt.get("claims", {}).get(field) is False, f"execution receipt claim must remain false: {field}")

    review = load_json(root / "review-package.json")
    require(review.get("state") == "AWAITING_INDEPENDENT_BLIND_VISUAL_REVIEW", "review package state mismatch")
    require(review.get("itemCount") == EXPECTED_RUN_COUNT, "review package count mismatch")
    items = review.get("items")
    require(isinstance(items, list) and len(items) == EXPECTED_RUN_COUNT, "review package item count mismatch")
    require(
        all(set(item) == {"blindLabel", "path", "sha256"} for item in items),
        "review package leaks unblinded fields or omits required fields",
    )
    require(len({item["blindLabel"] for item in items}) == EXPECTED_RUN_COUNT, "review blind labels are not unique")
    require({item["path"] for item in items} == expected_outputs, "review package output set mismatch")
    for field in ("validationAccepted", "productionReady"):
        require(review.get("claims", {}).get(field) is False, f"review claim must remain false: {field}")

    allowed_controls = required_names
    actual_controls = {
        path.name
        for path in root.iterdir()
        if path.is_file()
    }
    require(actual_controls == allowed_controls, "unexpected or missing top-level result control")
    require(authorization.get("automaticRetryAuthorized") is False, "authorization retry boundary changed")
    return inventory_sha, authorization_sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_root", type=Path)
    args = parser.parse_args()
    try:
        inventory_sha, authorization_sha = validate(args.result_root)
        print("CCV_R2_G3_G2_RESULT_VALIDATION=PASS")
        print("OUTPUT_COUNT=51")
        print(f"RESULT_INVENTORY_SHA256={inventory_sha}")
        print(f"AUTHORIZATION_SHA256={authorization_sha}")
        print("AWAITING_INDEPENDENT_BLIND_VISUAL_REVIEW=true")
        print("VALIDATION_ACCEPTED=false")
        print("PRODUCTION_READY=false")
        return 0
    except (OSError, ValueError, KeyError, ExecutionError, json.JSONDecodeError) as exc:
        print("CCV_R2_G3_G2_RESULT_VALIDATION=FAIL")
        print(f"ERROR={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

