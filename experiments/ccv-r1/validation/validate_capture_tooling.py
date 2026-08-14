#!/usr/bin/env python3
"""No-GPU regression checks for CCV-R1 historical capture tooling.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "capture"))
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_common import (  # noqa: E402
    EvidenceError,
    FINAL_STATUS,
    PARTIAL_STATUS,
    validate_manifest_consistency,
)
from finalize_historical_capture import (  # noqa: E402
    build_capture_template,
    finalize_historical_capture,
)


def expect_failure(label: str, expected_text: str, operation) -> None:
    try:
        operation()
    except (EvidenceError, FileNotFoundError) as error:
        if expected_text not in str(error):
            raise AssertionError(f"{label}: unexpected error: {error}") from error
        print(f"PASS {label}: {error}")
        return
    raise AssertionError(f"{label}: operation unexpectedly passed")


def write_safetensors(path: Path, tensor_name: str, dimension: int) -> None:
    shape = [2, dimension]
    tensor_bytes = shape[0] * shape[1] * 2
    header = {
        tensor_name: {
            "dtype": "F16",
            "shape": shape,
            "data_offsets": [0, tensor_bytes],
        }
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(len(encoded).to_bytes(8, byteorder="little") + encoded + bytes(tensor_bytes))


def usage_ref(round_id: str, evidence_ref: str) -> str:
    if evidence_ref == "ccv-r1-log-round-1":
        return "ccv-r1-workflow-round-1"
    if evidence_ref == "ccv-r1-log-round-2":
        return "ccv-r1-workflow-round-2"
    if evidence_ref == "ccv-r1-log-round-3":
        return "ccv-r1-workflow-round-3"
    return {
        "round-1": "ccv-r1-log-round-1",
        "round-2": "ccv-r1-log-round-2",
        "round-3": "ccv-r1-log-round-3",
        "shared": "ccv-r1-log-round-1",
    }[round_id]


def complete_capture(template: dict, evidence_root: Path) -> dict:
    capture = copy.deepcopy(template)
    capture["status"] = "COLLECTION_INPUT_NOT_REVIEWED"
    capture["manifestCreatedAt"] = "2026-08-14T12:00:00+00:00"
    capture["snapshotState"] = "UNAVAILABLE"
    capture["sourceDiskSnapshotRef"] = None
    capture["claims"]["externalCollectionStarted"] = True

    model_tensors = {
        "base": ("model.diffusion_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight", 2048),
        "identity_adapter": ("ip_adapter.1.to_k_ip.weight", 2048),
        "image_encoder": ("text_model.encoder.layer.weight", 1024),
        "pose_control": ("control_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight", 2048),
    }
    for index, record in enumerate(capture["records"]):
        suffix = ".safetensors" if record["role"] in model_tensors else ".bin"
        relative = Path("records") / f"{index:02d}-{record['evidenceRef']}{suffix}"
        path = evidence_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if record["role"] in model_tensors:
            tensor_name, dimension = model_tensors[record["role"]]
            write_safetensors(path, tensor_name, dimension)
        else:
            path.write_bytes(f"fixture:{record['evidenceRef']}".encode("utf-8"))
        record.update(
            {
                "collectionState": "RECOVERED",
                "sourcePath": relative.as_posix(),
                "usageLinkState": "VERIFIED",
                "usageLinkEvidenceRefs": [usage_ref(record["roundId"], record["evidenceRef"])],
                "storageRef": f"restricted://ccv-r1/{record['evidenceRef']}",
                "source": "EXTERNAL_GPU_READ_ONLY_RECOVERY",
                "licenseStatus": "REVIEW_REQUIRED_NOT_FOR_PRODUCTION",
            }
        )
        if record["evidenceRef"] == "ccv-r1-reference-face-crop":
            record["lineage"] = {
                "parentEvidenceRef": "ccv-r1-reference-full-body",
                "operation": "FACE_CROP",
            }

    for index, run in enumerate(capture["runs"]):
        relative = Path("outputs") / f"{index:02d}.png"
        path = evidence_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"output:{run['runId']}".encode("utf-8"))
        run.update(
            {
                "seed": 100000 + index,
                "outputCollectionState": "RECOVERED",
                "outputSourcePath": relative.as_posix(),
                "usageLinkState": "VERIFIED",
                "usageLinkEvidenceRefs": [
                    "ccv-r1-log-round-1"
                    if "r1-" in run["runId"]
                    else "ccv-r1-log-round-2"
                    if "r2" in run["runId"]
                    else "ccv-r1-log-round-3"
                ],
            }
        )

    for event in capture["failureLedger"]:
        event["eventState"] = "RECOVERED"
        event["occurredAt"] = None
    first_run = capture["runs"][0]["runId"]
    second_run = capture["runs"][1]["runId"]
    capture["failureLedger"].extend(
        [
            {
                "eventId": "ccv-r1-event-retry-fixture",
                "roundId": "round-1",
                "eventType": "RETRY",
                "eventState": "RECOVERED",
                "runId": second_run,
                "relatedRunId": first_run,
                "sourceEvidenceRefs": ["ccv-r1-log-round-1"],
                "summary": "Synthetic fixture proving normalized retry linkage.",
                "occurredAt": None,
            },
            {
                "eventId": "ccv-r1-event-exclusion-fixture",
                "roundId": "round-1",
                "eventType": "EXCLUSION",
                "eventState": "RECOVERED",
                "runId": None,
                "relatedRunId": first_run,
                "sourceEvidenceRefs": ["ccv-r1-log-round-1"],
                "summary": "Synthetic fixture proving normalized exclusion evidence.",
                "occurredAt": None,
            },
        ]
    )
    return capture


def record_by_ref(capture: dict, evidence_ref: str) -> dict:
    return next(record for record in capture["records"] if record["evidenceRef"] == evidence_ref)


def main() -> int:
    plan = json.loads((ROOT / "capture" / "capture-plan.pending.json").read_text(encoding="utf-8"))
    register = json.loads((ROOT / "experiment-manifest.pending.json").read_text(encoding="utf-8"))
    template = build_capture_template(plan, register)
    if len(template["records"]) != 27 or len(template["runs"]) != 50:
        raise AssertionError("capture template lost the exact 27-record / 50-run boundary")
    if any(record["collectionState"] != "PENDING" for record in template["records"]):
        raise AssertionError("capture template guessed an external evidence state")
    print("PASS capture template: 27 records / 50 runs / no guessed paths")

    with tempfile.TemporaryDirectory(prefix="ccv-r1-capture-") as temp:
        evidence_root = Path(temp)
        capture = complete_capture(template, evidence_root)
        manifest = finalize_historical_capture(plan, register, capture, evidence_root)
        if manifest["status"] != FINAL_STATUS or not manifest["historicalScriptBytesRecovered"]:
            raise AssertionError("complete capture did not derive complete status and script recovery")
        if not manifest["claims"]["historicalUsageVerified"]:
            raise AssertionError("verified fixture usage links were not derived")
        if len(manifest["failureLedger"]) != 4:
            raise AssertionError("failure/retry/exclusion ledger was not preserved")
        print("PASS complete capture: script custody derived / 27 records / 50 outputs / normalized event ledger")

        partial = copy.deepcopy(capture)
        missing_script = record_by_ref(partial, "ccv-r1-script-round-3")
        missing_script.update(
            {
                "collectionState": "MISSING",
                "sourcePath": None,
                "usageLinkState": "UNVERIFIED",
                "usageLinkEvidenceRefs": [],
                "storageRef": None,
            }
        )
        partial_manifest = finalize_historical_capture(plan, register, partial, evidence_root)
        if partial_manifest["status"] != PARTIAL_STATUS or partial_manifest["historicalScriptBytesRecovered"]:
            raise AssertionError("partial script recovery was overstated")
        print("PASS partial recovery remains partial and historicalScriptBytesRecovered=false")

        partial_event = copy.deepcopy(capture)
        partial_event["failureLedger"][0]["eventState"] = "MISSING"
        partial_event_manifest = finalize_historical_capture(plan, register, partial_event, evidence_root)
        if partial_event_manifest["status"] != PARTIAL_STATUS or partial_event_manifest["claims"]["historicalUsageVerified"]:
            raise AssertionError("missing failure evidence was overstated as complete or usage-verified")
        print("PASS missing failure evidence keeps capture and historical usage partial")

        traversal = copy.deepcopy(capture)
        record_by_ref(traversal, "ccv-r1-script-round-1")["sourcePath"] = "../escape.py"
        expect_failure(
            "path traversal fails closed",
            "relative and confined",
            lambda: finalize_historical_capture(plan, register, traversal, evidence_root),
        )

        zero_byte = copy.deepcopy(capture)
        empty = evidence_root / "records" / "empty.bin"
        empty.touch()
        record_by_ref(zero_byte, "ccv-r1-script-round-1")["sourcePath"] = "records/empty.bin"
        expect_failure(
            "zero-byte recovered evidence fails closed",
            "zero-byte file rejected",
            lambda: finalize_historical_capture(plan, register, zero_byte, evidence_root),
        )

        no_lineage = copy.deepcopy(capture)
        record_by_ref(no_lineage, "ccv-r1-reference-face-crop")["lineage"] = None
        expect_failure(
            "face crop without lineage fails closed",
            "face crop requires explicit lineage",
            lambda: finalize_historical_capture(plan, register, no_lineage, evidence_root),
        )

        missing_parent = copy.deepcopy(capture)
        parent = record_by_ref(missing_parent, "ccv-r1-reference-full-body")
        parent.update(
            {
                "collectionState": "MISSING",
                "sourcePath": None,
                "usageLinkState": "UNVERIFIED",
                "usageLinkEvidenceRefs": [],
                "storageRef": None,
            }
        )
        expect_failure(
            "recovered face crop with missing parent fails closed",
            "face crop lineage parent must be recovered",
            lambda: finalize_historical_capture(plan, register, missing_parent, evidence_root),
        )

        pending_model_source = copy.deepcopy(capture)
        record_by_ref(pending_model_source, "ccv-r1-model-sdxl-base")["source"] = "PENDING_EXTERNAL_GPU"
        expect_failure(
            "recovered model without explicit source fails closed",
            "recovered source must be explicit",
            lambda: finalize_historical_capture(plan, register, pending_model_source, evidence_root),
        )

        duplicate_event = copy.deepcopy(capture)
        duplicate_event["failureLedger"].append(copy.deepcopy(duplicate_event["failureLedger"][0]))
        expect_failure(
            "duplicate failure event fails closed",
            "eventId values must be unique",
            lambda: finalize_historical_capture(plan, register, duplicate_event, evidence_root),
        )

        false_partial_digest = copy.deepcopy(partial_manifest)
        missing_run = false_partial_digest["runs"][0]
        missing_run["runState"] = "MISSING_EVIDENCE"
        missing_run["output"].update(
            {
                "collectionState": "MISSING",
                "filePath": None,
                "sizeBytes": 1,
                "sha256": "0" * 64,
            }
        )
        false_partial_digest["captureReceipt"]["captureComplete"] = False
        false_partial_digest["claims"]["captureComplete"] = False
        false_partial_digest["status"] = PARTIAL_STATUS
        expect_failure(
            "missing output cannot retain digest fields",
            "unavailable output digest fields must be null",
            lambda: validate_manifest_consistency(false_partial_digest, finalized=True),
        )

    print("CCV-R1 historical capture G1 no-GPU validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
