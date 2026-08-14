#!/usr/bin/env python3
"""Normalize and hash a read-only CCV-R1 historical evidence recovery.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION

This command never starts a GPU process or regenerates an image. It reads an explicit
collection input beneath a caller-supplied root and writes only a normalized manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_common import (  # noqa: E402
    EvidenceError,
    FINAL_STATUS,
    PARTIAL_STATUS,
    RIGHTS_LABELS,
    historical_script_bytes_recovered,
    load_json,
    sha256_file,
    validate_manifest_consistency,
    verify_model_record,
)


PLAN_PATH = ROOT / "capture" / "capture-plan.pending.json"
RUN_REGISTER_PATH = ROOT / "experiment-manifest.pending.json"
RECORD_STATES = {"RECOVERED", "MISSING", "AMBIGUOUS"}
USAGE_STATES = {"VERIFIED", "UNVERIFIED", "NOT_APPLICABLE"}
KNOWN_FAILURE_EVENTS = (
    {
        "eventId": "ccv-r1-event-zero-byte-controlnet",
        "roundId": "round-3",
        "eventType": "FAILURE",
        "eventState": "PENDING",
        "runId": None,
        "relatedRunId": None,
        "sourceEvidenceRefs": ["ccv-r1-failure-zero-byte-controlnet"],
        "summary": "Known zero-byte ControlNet download incident; historical evidence pending.",
        "occurredAt": None,
    },
    {
        "eventId": "ccv-r1-event-sd15-sdxl-mismatch",
        "roundId": "round-3",
        "eventType": "FAILURE",
        "eventState": "PENDING",
        "runId": None,
        "relatedRunId": None,
        "sourceEvidenceRefs": ["ccv-r1-failure-sd15-sdxl"],
        "summary": "Known SD1.5/SDXL dimension mismatch incident; historical evidence pending.",
        "occurredAt": None,
    },
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _plan_records(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for records in plan["groups"].values() for record in records]


def build_capture_template(plan: dict[str, Any], run_register: dict[str, Any]) -> dict[str, Any]:
    records = []
    for plan_record in _plan_records(plan):
        records.append(
            {
                "evidenceRef": plan_record["evidenceRef"],
                "roundId": plan_record["roundId"],
                "role": plan_record["role"],
                "logicalName": plan_record["logicalName"],
                "collectionState": "PENDING",
                "sourcePath": None,
                "usageLinkState": "PENDING",
                "usageLinkEvidenceRefs": [],
                "storageRef": None,
                "source": plan_record["source"],
                "licenseStatus": plan_record["licenseStatus"],
                "lineage": None,
            }
        )
    runs = []
    for run in run_register["runs"]:
        seed = run["parameters"].get("seed")
        runs.append(
            {
                "runId": run["runId"],
                "seed": seed if type(seed) is int else None,
                "outputCollectionState": "PENDING",
                "outputSourcePath": None,
                "usageLinkState": "PENDING",
                "usageLinkEvidenceRefs": [],
                "retryOfRunId": None,
                "excluded": False,
                "exclusionReason": None,
            }
        )
    return {
        "$schema": "./historical-capture.schema.json",
        "captureVersion": "1.0",
        "captureId": "acs-ccv-r1-historical-evidence",
        "status": "CAPTURE_TEMPLATE",
        "rightsLabels": list(RIGHTS_LABELS),
        "snapshotState": "PENDING",
        "sourceDiskSnapshotRef": None,
        "records": records,
        "runs": runs,
        "failureLedger": deepcopy(list(KNOWN_FAILURE_EVENTS)),
        "claims": {
            "externalCollectionStarted": False,
            "validationAccepted": False,
            "independentReproductionPossible": False,
            "schemaChangeAuthorized": False,
            "ccvR2Authorized": False,
        },
    }


def _resolve_file(evidence_root: Path, source_path: Any, label: str) -> Path:
    require(isinstance(source_path, str) and source_path, f"{label}: recovered sourcePath is required")
    relative = Path(source_path)
    require(not relative.is_absolute() and ".." not in relative.parts, f"{label}: sourcePath must be relative and confined")
    root = evidence_root.resolve(strict=True)
    require(root.is_dir(), "evidence root must be a directory")
    candidate = (root / relative).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise EvidenceError(f"{label}: sourcePath escapes evidence root") from error
    require(candidate.is_file(), f"{label}: sourcePath is not a file")
    require(candidate.stat().st_size > 0, f"{label}: zero-byte file rejected")
    return candidate


def _model_declarations() -> dict[str, dict[str, Any]]:
    declarations: dict[str, dict[str, Any]] = {}
    for round_id in ("round-1", "round-2", "round-3"):
        config = load_json(ROOT / "configs" / f"{round_id}.json")
        for model in config["models"]:
            current = declarations.get(model["logicalName"])
            declaration = {
                "modelFamily": model["modelFamily"],
                "conditioningDimension": model["conditioningDimension"],
            }
            require(current is None or current == declaration, f"conflicting model declaration for {model['logicalName']}")
            declarations[model["logicalName"]] = declaration
    return declarations


def _validate_capture_input(
    plan: dict[str, Any],
    run_register: dict[str, Any],
    capture: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    require(capture.get("captureVersion") == "1.0", "captureVersion must be 1.0")
    require(capture.get("captureId") == plan["captureId"], "captureId mismatch")
    require(capture.get("status") == "COLLECTION_INPUT_NOT_REVIEWED", "capture input status is invalid")
    require(tuple(capture.get("rightsLabels", ())) == RIGHTS_LABELS, "rights labels changed")
    require(capture.get("snapshotState") in {"CAPTURED", "UNAVAILABLE"}, "snapshotState must be CAPTURED or UNAVAILABLE")
    snapshot_ref = capture.get("sourceDiskSnapshotRef")
    if capture["snapshotState"] == "CAPTURED":
        require(isinstance(snapshot_ref, str) and snapshot_ref, "captured snapshot requires sourceDiskSnapshotRef")
    else:
        require(snapshot_ref is None, "unavailable snapshot must have null sourceDiskSnapshotRef")

    claims = capture.get("claims")
    require(isinstance(claims, dict), "capture claims are required")
    require(claims.get("externalCollectionStarted") is True, "collection input must record externalCollectionStarted=true")
    for claim in ("validationAccepted", "independentReproductionPossible", "schemaChangeAuthorized", "ccvR2Authorized"):
        require(claims.get(claim) is False, f"capture input cannot set {claim}")

    planned = {record["evidenceRef"]: record for record in _plan_records(plan)}
    records = capture.get("records")
    require(isinstance(records, list), "capture records must be a list")
    captured = {record.get("evidenceRef"): record for record in records if isinstance(record, dict)}
    require(len(records) == 27 and set(captured) == set(planned), "capture records must exactly match the 27-record plan")
    require(len(captured) == len(records), "duplicate capture evidenceRef")
    for evidence_ref, record in captured.items():
        plan_record = planned[evidence_ref]
        for field in ("roundId", "role", "logicalName"):
            require(record.get(field) == plan_record[field], f"{evidence_ref}: {field} differs from plan")
        state = record.get("collectionState")
        require(state in RECORD_STATES, f"{evidence_ref}: collectionState must be resolved")
        usage_state = record.get("usageLinkState")
        require(usage_state in USAGE_STATES, f"{evidence_ref}: usageLinkState must be resolved")
        usage_refs = record.get("usageLinkEvidenceRefs")
        require(isinstance(usage_refs, list) and len(usage_refs) == len(set(usage_refs)), f"{evidence_ref}: invalid usage links")
        require(all(ref in planned and ref != evidence_ref for ref in usage_refs), f"{evidence_ref}: usage links must reference other planned evidence")
        if usage_state == "VERIFIED":
            require(usage_refs, f"{evidence_ref}: VERIFIED usage requires evidence references")
        if state == "RECOVERED":
            require(isinstance(record.get("storageRef"), str) and record["storageRef"], f"{evidence_ref}: storageRef is required")
            require(
                isinstance(record.get("source"), str) and record["source"] and not record["source"].startswith("PENDING"),
                f"{evidence_ref}: recovered source must be explicit",
            )
            require(
                isinstance(record.get("licenseStatus"), str)
                and record["licenseStatus"]
                and not record["licenseStatus"].startswith("PENDING"),
                f"{evidence_ref}: recovered licenseStatus must be explicit",
            )
        else:
            require(record.get("sourcePath") is None, f"{evidence_ref}: unavailable sourcePath must be null")
            require(record.get("storageRef") is None, f"{evidence_ref}: unavailable storageRef must be null")
        if evidence_ref == "ccv-r1-reference-face-crop" and state == "RECOVERED":
            lineage = record.get("lineage")
            require(isinstance(lineage, dict), "face crop requires explicit lineage")
            require(
                lineage.get("parentEvidenceRef") == "ccv-r1-reference-full-body"
                and lineage.get("operation") == "FACE_CROP",
                "face crop lineage must reference the full-body source",
            )
            require(
                captured["ccv-r1-reference-full-body"].get("collectionState") == "RECOVERED",
                "face crop lineage parent must be recovered",
            )

    for evidence_ref, record in captured.items():
        if record.get("usageLinkState") == "VERIFIED":
            require(
                all(captured[ref].get("collectionState") == "RECOVERED" for ref in record["usageLinkEvidenceRefs"]),
                f"{evidence_ref}: VERIFIED usage cannot reference unavailable evidence",
            )

    registered_runs = {run["runId"]: run for run in run_register["runs"]}
    runs = capture.get("runs")
    require(isinstance(runs, list), "capture runs must be a list")
    captured_runs = {run.get("runId"): run for run in runs if isinstance(run, dict)}
    require(len(runs) == 50 and set(captured_runs) == set(registered_runs), "capture runs must exactly match the 50-run register")
    require(len(captured_runs) == len(runs), "duplicate capture runId")
    for run_id, run in captured_runs.items():
        state = run.get("outputCollectionState")
        require(state in RECORD_STATES, f"{run_id}: outputCollectionState must be resolved")
        seed = run.get("seed")
        require(seed is None or (type(seed) is int and seed >= 0), f"{run_id}: seed must be null or an exact non-negative integer")
        usage_state = run.get("usageLinkState")
        require(usage_state in USAGE_STATES, f"{run_id}: usageLinkState must be resolved")
        usage_refs = run.get("usageLinkEvidenceRefs")
        require(isinstance(usage_refs, list) and len(usage_refs) == len(set(usage_refs)), f"{run_id}: invalid usage links")
        require(all(ref in planned for ref in usage_refs), f"{run_id}: unknown usage evidence reference")
        if usage_state == "VERIFIED":
            require(usage_refs, f"{run_id}: VERIFIED usage requires evidence references")
            require(
                all(captured[ref].get("collectionState") == "RECOVERED" for ref in usage_refs),
                f"{run_id}: VERIFIED usage cannot reference unavailable evidence",
            )
        if state == "RECOVERED":
            require(type(seed) is int, f"{run_id}: recovered output requires an exact seed")
        else:
            require(run.get("outputSourcePath") is None, f"{run_id}: unavailable outputSourcePath must be null")
        retry_of = run.get("retryOfRunId")
        require(retry_of is None or retry_of in registered_runs, f"{run_id}: retryOfRunId is unknown")
        excluded = run.get("excluded")
        require(type(excluded) is bool, f"{run_id}: excluded must be boolean")
        if excluded:
            require(isinstance(run.get("exclusionReason"), str) and run["exclusionReason"], f"{run_id}: exclusionReason is required")
        else:
            require(run.get("exclusionReason") is None, f"{run_id}: exclusionReason must be null")
    return captured, captured_runs


def _normalize_record(
    record: dict[str, Any],
    evidence_root: Path,
    model_declarations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    normalized = deepcopy(record)
    source_path = record.get("sourcePath")
    state = record["collectionState"]
    if state != "RECOVERED":
        normalized.update({"filePath": None, "sizeBytes": None, "sha256": None})
        return normalized

    path = _resolve_file(evidence_root, source_path, record["evidenceRef"])
    normalized["filePath"] = source_path
    normalized["sizeBytes"] = path.stat().st_size
    normalized["sha256"] = sha256_file(path)
    if record["role"] in {"base", "identity_adapter", "image_encoder", "pose_control"}:
        declaration = model_declarations.get(record["logicalName"])
        require(declaration is not None, f"{record['evidenceRef']}: missing model declaration")
        verification = {
            **normalized,
            **declaration,
            "filePath": str(path),
        }
        _, _, architecture = verify_model_record(verification, record["evidenceRef"])
        normalized.update(declaration)
        if architecture is not None:
            normalized["architectureEvidence"] = architecture
    return normalized


def finalize_historical_capture(
    plan: dict[str, Any],
    run_register: dict[str, Any],
    capture: dict[str, Any],
    evidence_root: Path,
) -> dict[str, Any]:
    captured_records, captured_runs = _validate_capture_input(plan, run_register, capture)
    declarations = _model_declarations()
    normalized_by_ref = {
        evidence_ref: _normalize_record(record, evidence_root, declarations)
        for evidence_ref, record in captured_records.items()
    }
    evidence_refs = set(normalized_by_ref)
    run_ids = {run["runId"] for run in run_register["runs"]}

    normalized_runs = []
    for registered in run_register["runs"]:
        capture_run = captured_runs[registered["runId"]]
        state = capture_run["outputCollectionState"]
        output = {
            "logicalPath": registered["output"]["logicalPath"],
            "filePath": None,
            "sizeBytes": None,
            "sha256": None,
            "collectionState": state,
            "usageLinkState": capture_run["usageLinkState"],
            "usageLinkEvidenceRefs": list(capture_run["usageLinkEvidenceRefs"]),
        }
        if state == "RECOVERED":
            path = _resolve_file(evidence_root, capture_run.get("outputSourcePath"), registered["runId"])
            output.update(
                {
                    "filePath": capture_run["outputSourcePath"],
                    "sizeBytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        parameters = deepcopy(registered["parameters"])
        parameters["seed"] = capture_run["seed"]
        run_state = {
            "RECOVERED": "CAPTURED",
            "MISSING": "MISSING_EVIDENCE",
            "AMBIGUOUS": "AMBIGUOUS_EVIDENCE",
        }[state]
        normalized_runs.append(
            {
                **{key: deepcopy(registered[key]) for key in ("runId", "roundId", "batchId", "shotId")},
                "parameters": parameters,
                "output": output,
                "runState": run_state,
                "failure": None,
                "retryOfRunId": capture_run["retryOfRunId"],
                "excluded": capture_run["excluded"],
                "exclusionReason": capture_run["exclusionReason"],
            }
        )

    failure_ledger = deepcopy(capture.get("failureLedger"))
    require(isinstance(failure_ledger, list), "failureLedger must be a list")
    event_ids = [event.get("eventId") for event in failure_ledger if isinstance(event, dict)]
    require(len(event_ids) == len(failure_ledger) == len(set(event_ids)), "failureLedger eventId values must be unique")
    for event in failure_ledger:
        require(event.get("eventType") in {"FAILURE", "RETRY", "EXCLUSION"}, f"{event.get('eventId')}: invalid eventType")
        require(event.get("eventState") in RECORD_STATES, f"{event.get('eventId')}: eventState must be resolved")
        require(event.get("runId") is None or event["runId"] in run_ids, f"{event.get('eventId')}: unknown runId")
        require(event.get("relatedRunId") is None or event["relatedRunId"] in run_ids, f"{event.get('eventId')}: unknown relatedRunId")
        refs = event.get("sourceEvidenceRefs")
        require(isinstance(refs, list) and refs and all(ref in evidence_refs for ref in refs), f"{event.get('eventId')}: invalid sourceEvidenceRefs")
        if event.get("eventState") == "RECOVERED":
            require(
                all(normalized_by_ref[ref].get("collectionState") == "RECOVERED" for ref in refs),
                f"{event.get('eventId')}: recovered event cannot reference unavailable evidence",
            )
        require(isinstance(event.get("summary"), str) and event["summary"], f"{event.get('eventId')}: summary is required")

    scripts = [normalized_by_ref[record["evidenceRef"]] for record in plan["groups"]["historicalScripts"]]
    models = [normalized_by_ref[record["evidenceRef"]] for record in plan["groups"]["models"]]
    artifact_groups = ("workflows", "references", "poseSkeletons", "runLogs", "environmentRecords", "failureRecords")
    artifacts = [
        normalized_by_ref[record["evidenceRef"]]
        for group in artifact_groups
        for record in plan["groups"][group]
    ]
    all_records = scripts + models + artifacts
    complete = (
        all(record["collectionState"] == "RECOVERED" for record in all_records)
        and all(run["runState"] == "CAPTURED" and type(run["parameters"]["seed"]) is int for run in normalized_runs)
        and all(run["excluded"] is False for run in normalized_runs)
        and all(event["eventState"] == "RECOVERED" for event in failure_ledger)
    )
    historical_usage_verified = all(
        record["collectionState"] == "RECOVERED"
        and record["usageLinkState"] in {"VERIFIED", "NOT_APPLICABLE"}
        for record in all_records
    ) and all(
        run["runState"] == "CAPTURED"
        and run["output"]["usageLinkState"] in {"VERIFIED", "NOT_APPLICABLE"}
        for run in normalized_runs
    ) and all(event["eventState"] == "RECOVERED" for event in failure_ledger)
    successor_names = (
        "character_consistency_test.py",
        "ipadapter_face_test.py",
        "ipadapter_pose_test.py",
        "evidence_common.py",
    )
    manifest = {
        "$schema": "./experiment-manifest.schema.json",
        "manifestVersion": "1.0",
        "experimentId": "acs-ccv-r1",
        "roundId": "all-rounds",
        "status": FINAL_STATUS if complete else PARTIAL_STATUS,
        "rightsLabels": list(RIGHTS_LABELS),
        "historicalExecutionDate": "2026-08-14",
        "manifestCreatedAt": capture.get("manifestCreatedAt"),
        "historicalScriptBytesRecovered": historical_script_bytes_recovered(scripts),
        "historicalScripts": scripts,
        "hardenedSuccessorScripts": [
            {
                "role": "hardened_successor_script",
                "logicalName": name,
                "sizeBytes": (ROOT / "scripts" / name).stat().st_size,
                "sha256": sha256_file(ROOT / "scripts" / name),
            }
            for name in successor_names
        ],
        "environment": {
            "evidenceRefs": [record["evidenceRef"] for record in normalized_by_ref.values() if record["role"] in {"environment_capture", "repository_commit"}],
            "historicalStateRequiresVerifiedUsageLink": True,
        },
        "models": models,
        "artifacts": artifacts,
        "expectedRunCount": 50,
        "runs": normalized_runs,
        "failureLedger": failure_ledger,
        "captureReceipt": {
            "captureId": capture["captureId"],
            "snapshotState": capture["snapshotState"],
            "sourceDiskSnapshotRef": capture["sourceDiskSnapshotRef"],
            "recordCount": len(all_records),
            "recoveredRecordCount": sum(record["collectionState"] == "RECOVERED" for record in all_records),
            "captureComplete": complete,
        },
        "claims": {
            "validationAccepted": False,
            "independentReproductionPossible": False,
            "schemaChangeAuthorized": False,
            "externalCollectionStarted": True,
            "captureComplete": complete,
            "historicalUsageVerified": historical_usage_verified,
            "ccvR2Authorized": False,
        },
    }
    validate_manifest_consistency(manifest, finalized=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare or finalize CCV-R1 historical evidence without GPU execution."
    )
    parser.add_argument("--plan", type=Path, default=PLAN_PATH, help="frozen G0 pending capture plan")
    parser.add_argument("--run-register", type=Path, default=RUN_REGISTER_PATH, help="frozen 50-run register")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-template", type=Path, help="write a normalized collection-input template")
    action.add_argument("--capture-input", type=Path, help="completed collection input to finalize")
    parser.add_argument("--evidence-root", type=Path, help="read-only root containing recovered bytes")
    parser.add_argument("--manifest-out", type=Path, help="normalized manifest destination")
    args = parser.parse_args()

    plan = load_json(args.plan)
    run_register = load_json(args.run_register)
    if args.write_template:
        template = build_capture_template(plan, run_register)
        args.write_template.parent.mkdir(parents=True, exist_ok=True)
        args.write_template.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote capture template: records={len(template['records'])}, runs={len(template['runs'])}")
        return 0

    require(args.evidence_root is not None, "--evidence-root is required with --capture-input")
    require(args.manifest_out is not None, "--manifest-out is required with --capture-input")
    capture = load_json(args.capture_input)
    manifest = finalize_historical_capture(plan, run_register, capture, args.evidence_root)
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote historical manifest: status={manifest['status']}, "
        f"records={manifest['captureReceipt']['recordCount']}, runs={len(manifest['runs'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
