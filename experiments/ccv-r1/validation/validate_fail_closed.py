#!/usr/bin/env python3
"""Reproducible no-GPU checks for the CCV-R1 evidence harness.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_common import (  # noqa: E402
    EvidenceError,
    load_json,
    sha256_file,
    validate_config,
    validate_model_compatibility,
    verify_file_record,
)


def expect_failure(label: str, expected_text: str, operation) -> None:
    try:
        operation()
    except EvidenceError as error:
        if expected_text not in str(error):
            raise AssertionError(f"{label}: unexpected error: {error}") from error
        print(f"PASS {label}: {error}")
        return
    raise AssertionError(f"{label}: operation unexpectedly passed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CCV-R1 no-GPU validation and optionally write the combined pending manifest")
    parser.add_argument("--write-pending-manifest", type=Path)
    args = parser.parse_args()

    counts: list[int] = []
    configs: list[dict] = []
    all_runs: list[dict] = []
    for round_id in ("round-1", "round-2", "round-3"):
        config = load_json(ROOT / "configs" / f"{round_id}.json")
        runs = validate_config(config, round_id)
        validate_model_compatibility(config["models"])
        configs.append(config)
        all_runs.extend(runs)
        counts.append(len(runs))
    if counts != [10, 25, 15] or sum(counts) != 50:
        raise AssertionError(f"unexpected run matrix: {counts}")
    print("PASS run matrix: round-1=10, round-2=25, round-3=15, total=50")

    with tempfile.TemporaryDirectory(prefix="ccv-r1-") as temp:
        temp_root = Path(temp)
        empty = temp_root / "empty.safetensors"
        empty.touch()
        empty_record = {
            "filePath": str(empty),
            "sizeBytes": 1,
            "sha256": "0" * 64,
        }
        expect_failure(
            "zero-byte model fails closed",
            "zero-byte file rejected",
            lambda: verify_file_record(empty_record, "pose_control"),
        )

        nonempty = temp_root / "model.safetensors"
        nonempty.write_bytes(b"ccv-r1-validation-fixture")
        payload = nonempty.read_bytes()
        valid_record = {
            "filePath": str(nonempty),
            "sizeBytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        verify_file_record(valid_record, "fixture")
        print("PASS non-empty file size and SHA-256 verification")
        missing_sha_record = {
            "filePath": str(nonempty),
            "sizeBytes": len(payload),
            "sha256": None,
        }
        expect_failure(
            "missing checksum fails closed",
            "SHA-256 is required",
            lambda: verify_file_record(missing_sha_record, "fixture"),
        )

    mismatched = [
        {
            "role": "base",
            "modelFamily": "sdxl",
            "conditioningDimension": 2048,
        },
        {
            "role": "pose_control",
            "modelFamily": "sd15",
            "conditioningDimension": 768,
        },
    ]
    expect_failure(
        "SD1.5/SDXL mismatch fails closed",
        "does not match base",
        lambda: validate_model_compatibility(mismatched),
    )

    if args.write_pending_manifest:
        models = []
        artifacts = []
        for config in configs:
            for model in config["models"]:
                models.append({"roundId": config["roundId"], **model})
            for artifact in config.get("artifacts", []):
                artifacts.append({"roundId": config["roundId"], **artifact})
        manifest = {
            "$schema": "./experiment-manifest.schema.json",
            "manifestVersion": "1.0",
            "experimentId": "acs-ccv-r1",
            "roundId": "all-rounds",
            "status": "EXPERIMENT_REPORTED_INDEPENDENT_REPRODUCTION_NOT_POSSIBLE",
            "rightsLabels": ["SYNTHETIC_TEST_ONLY", "NOT_FOR_PRODUCTION"],
            "historicalExecutionDate": "2026-08-14",
            "manifestCreatedAt": None,
            "historicalScriptBytesRecovered": False,
            "hardenedSuccessorScripts": [
                {
                    "role": "hardened_successor_script",
                    "logicalName": script_name,
                    "sizeBytes": (ROOT / "scripts" / script_name).stat().st_size,
                    "sha256": sha256_file(ROOT / "scripts" / script_name),
                }
                for script_name in (
                    "character_consistency_test.py",
                    "ipadapter_face_test.py",
                    "ipadapter_pose_test.py",
                    "evidence_common.py",
                )
            ],
            "environment": {config["roundId"]: config["environment"] for config in configs},
            "models": models,
            "artifacts": artifacts,
            "expectedRunCount": len(all_runs),
            "runs": all_runs,
            "claims": {
                "validationAccepted": False,
                "independentReproductionPossible": False,
                "schemaChangeAuthorized": False,
            },
        }
        args.write_pending_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.write_pending_manifest.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"PASS wrote combined pending manifest with {len(all_runs)} run rows")

    print("CCV-R1 no-GPU fail-closed validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
