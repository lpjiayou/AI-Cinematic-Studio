#!/usr/bin/env python3
"""Validate the pending CCV-R1 historical-evidence capture plan without GPU access.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "capture" / "capture-plan.pending.json"
CAPTURE_SCHEMA_PATH = ROOT / "capture" / "historical-capture.schema.json"
MANIFEST_SCHEMA_PATH = ROOT / "experiment-manifest.schema.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: top-level JSON value must be an object")
    return value


def logical_names(plan: dict, group: str) -> set[str]:
    return {record["logicalName"] for record in plan["groups"][group]}


def main() -> int:
    plan = load_json(PLAN_PATH)
    require(plan["planVersion"] == "1.0", "planVersion must be 1.0")
    require(plan["captureId"] == "acs-ccv-r1-historical-evidence", "unexpected captureId")
    require(plan["status"] == "PENDING_EXTERNAL_GPU_CAPTURE", "capture plan must remain pending")
    require(plan["captureMode"] == "READ_ONLY_NO_RERUN", "capture mode must remain read-only")
    require(plan["sourceHostState"] == "POWERED_OFF", "source host must remain powered off in G0")
    require(plan["sourceDiskSnapshotRef"] is None, "G0 must not claim an external snapshot")
    require(plan["rightsLabels"] == ["SYNTHETIC_TEST_ONLY", "NOT_FOR_PRODUCTION"], "rights labels changed")

    register_path = (PLAN_PATH.parent / plan["runRegister"]).resolve()
    register = load_json(register_path)
    runs = register["runs"]
    counts = Counter(run["roundId"] for run in runs)
    expected_counts = {"round-1": 10, "round-2": 25, "round-3": 15}
    require(dict(counts) == expected_counts, f"run register count mismatch: {dict(counts)}")
    require(plan["expectedRunCounts"] == {**expected_counts, "total": 50}, "plan run counts changed")
    require(len(runs) == 50, "run register must contain 50 rows")
    run_ids = [run["runId"] for run in runs]
    output_paths = [run["output"]["logicalPath"] for run in runs]
    require(len(set(run_ids)) == 50, "run IDs must be unique")
    require(len(set(output_paths)) == 50, "output logical paths must be unique")

    expected_groups = {
        "historicalScripts": {
            "character_consistency_test.py",
            "ipadapter_face_test.py",
            "ipadapter_pose_test.py",
        },
        "workflows": {"round-1.api.json", "round-2.api.json", "round-3.api.json"},
        "models": {
            "sd_xl_base_1.0.safetensors",
            "ip-adapter-plus-face_sdxl_vit-h.safetensors",
            "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
            "controlnet-openpose-sdxl.safetensors",
        },
        "references": {
            "consistency_fixed_01_medium_front.png",
            "consistency_fixed_01_medium_front_face_crop.png",
        },
        "poseSkeletons": {
            "01_medium_front_coco18.png",
            "02_closeup_side_coco18.png",
            "03_full_walking_coco18.png",
            "04_back_turning_coco18.png",
            "05_sitting_high_coco18.png",
        },
        "runLogs": {"round-1.log", "round-2.log", "round-3.log"},
        "environmentRecords": {
            "nvidia-smi.txt",
            "python-version.txt",
            "pytorch-version.txt",
            "comfyui-commit.txt",
            "custom-node-commits.json",
        },
        "failureRecords": {
            "zero-byte-controlnet-download.txt",
            "sd15-sdxl-dimension-mismatch.txt",
        },
    }
    require(set(plan["groups"]) == set(expected_groups), "capture groups changed")
    for group, expected_names in expected_groups.items():
        require(logical_names(plan, group) == expected_names, f"{group}: evidence list mismatch")

    records = [record for group in plan["groups"].values() for record in group]
    evidence_refs = [record["evidenceRef"] for record in records]
    require(len(evidence_refs) == len(set(evidence_refs)), "evidenceRef values must be unique")
    for record in records:
        require(record["sourcePath"] is None, f"{record['evidenceRef']}: sourcePath must remain pending")
        require(record["collectionState"] == "PENDING", f"{record['evidenceRef']}: collectionState changed")
        require(record["sizeBytes"] is None, f"{record['evidenceRef']}: size must remain pending")
        require(record["sha256"] is None, f"{record['evidenceRef']}: digest must remain pending")
        require(record["usageLinkState"] == "PENDING", f"{record['evidenceRef']}: usage link was guessed")
        require(record["storageRef"] is None, f"{record['evidenceRef']}: storageRef must remain pending")

    blockers = {blocker["code"] for blocker in plan["toolingBlockers"]}
    require(blockers == {"CCV-CAPTURE-001", "CCV-CAPTURE-002", "CCV-CAPTURE-003"}, "tooling blockers changed")
    require(all(blocker["status"] == "OPEN" for blocker in plan["toolingBlockers"]), "G0 must not close G1 blockers")

    capture_schema = load_json(CAPTURE_SCHEMA_PATH)
    manifest_schema = load_json(MANIFEST_SCHEMA_PATH)
    capture_properties = capture_schema["properties"]
    require(capture_properties["records"]["minItems"] == 27, "G1 capture schema must require 27 records")
    require(capture_properties["runs"]["minItems"] == 50, "G1 capture schema must require 50 runs")
    require("failureLedger" in capture_properties, "G1 capture schema must define failureLedger")
    statuses = manifest_schema["properties"]["status"]["enum"]
    require(
        "EVIDENCE_CAPTURE_PARTIAL_NOT_VALIDATION_ACCEPTED" in statuses,
        "manifest schema must distinguish partial recovery",
    )
    require("historicalScripts" in manifest_schema["properties"], "manifest schema must normalize historical scripts")
    require("captureReceipt" in manifest_schema["properties"], "manifest schema must define captureReceipt")
    require(plan["claims"] == {
        "externalCollectionStarted": False,
        "historicalUsageVerified": False,
        "independentReproductionPossible": False,
        "validationAccepted": False,
        "schemaChangeAuthorized": False,
        "ccvR2Authorized": False,
    }, "G0 claims changed")

    print("CCV-R1 capture plan PASS")
    print("run register: round-1=10, round-2=25, round-3=15, total=50")
    print(f"pending non-output evidence records: {len(records)}")
    print("external GPU access: NOT STARTED")
    print("G0 plan blockers: 3 OPEN as immutable historical plan state")
    print("G1 schema surfaces: historical scripts / 27 records / 50 runs / failure ledger PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
