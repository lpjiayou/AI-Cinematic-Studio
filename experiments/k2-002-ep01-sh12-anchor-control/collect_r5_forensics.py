#!/usr/bin/env python3
"""Freeze R5 control-plane forensics without modifying original R5 evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


EVIDENCE = Path("/data/k2-technical-evidence/k2-002-ep01-i2v-v2-sh12-r5-anchor-only")
RUNNER = Path("/data/coding/AI-Cinematic-Studio-main-2701/experiments/k2-002-ep01-sh12-anchor-control/run_controlled_experiment.py")
WORKFLOW = EVIDENCE / "materialized/EP01_SH12_R5.workflow.json"
LOG = EVIDENCE / "logs/comfyui.log"
SOURCE_VIDEO = Path("/data/coding/apps/ComfyUI/output/k2-002-ep01-i2v-v2/EP01_SH12-v2-technical-evidence_00005_.mp4")
RECOVERED_VIDEO = EVIDENCE / "recovered_media/EP01_SH12_R5_RECOVERED.mp4"
FORENSICS = EVIDENCE / "forensics"
CLIENT_ID = "k2-002-ep01-sh12-r5-anchor-only"


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path: Path, value: object) -> None:
    write_exclusive(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n")


def run_json(*command: str) -> object:
    return json.loads(subprocess.check_output(command, text=True))


def main() -> None:
    for frozen in (
        EVIDENCE / "receipts/DRY_RUN.json",
        EVIDENCE / "RUN_ATTEMPT_1.json",
        EVIDENCE / "FAILED_AFTER_RESERVATION.json",
        WORKFLOW,
        LOG,
        SOURCE_VIDEO,
    ):
        if not frozen.is_file():
            raise SystemExit(f"required R5 evidence missing: {frozen}")
    if FORENSICS.exists() or RECOVERED_VIDEO.exists():
        raise SystemExit("forensics/recovered media already exists; refusing overwrite")

    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    submitted_payload = {"prompt": workflow, "client_id": CLIENT_ID}
    workflow_sha = hashlib.sha256(canonical_bytes(workflow)).hexdigest()
    request_sha = hashlib.sha256(canonical_bytes(submitted_payload)).hexdigest()
    attempt = json.loads((EVIDENCE / "RUN_ATTEMPT_1.json").read_text(encoding="utf-8"))
    failure = json.loads((EVIDENCE / "FAILED_AFTER_RESERVATION.json").read_text(encoding="utf-8"))
    source_stat = SOURCE_VIDEO.stat()
    ffprobe = run_json(
        "ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=index,codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames,duration:format=duration,size",
        "-of", "json", str(SOURCE_VIDEO),
    )
    video_sha = digest(SOURCE_VIDEO)

    FORENSICS.mkdir(parents=True, exist_ok=False)
    write_json(FORENSICS / "R5_REQUEST.json", {
        "schemaVersion": 1,
        "experimentId": "K2-002-EP01-SH12-R5-ANCHOR-ONLY",
        "endpoint": "http://127.0.0.1:8188/prompt",
        "method": "POST",
        "requestTimeExact": None,
        "requestTimeBoundsUtc": {"after": attempt["reservedAt"], "before": failure["failedAt"]},
        "recoveryStatus": "RECONSTRUCTED_EXACTLY_FROM_FROZEN_RUNNER_AND_WORKFLOW",
        "body": submitted_payload,
        "promptId": None,
        "promptIdPolicy": "SERVER_GENERATED_BECAUSE_R5_REQUEST_OMITTED_PROMPT_ID",
        "clientId": CLIENT_ID,
        "extraData": None,
        "apiPromptCanonicalSha256": workflow_sha,
        "requestCanonicalSha256": request_sha,
    })
    write_json(FORENSICS / "R5_RESPONSE.json", {
        "schemaVersion": 1,
        "httpStatus": None,
        "body": None,
        "promptId": None,
        "number": None,
        "nodeErrors": None,
        "rawResponsePersistedByR5Runner": False,
        "factsProvenByControlFlow": {
            "responseWasSuccessfulJsonObject": True,
            "responsePromptIdWasNonemptyString": True,
            "reason": "R5 passed ComfyTransport.json and prompt_id validation before entering history polling",
        },
    })
    write_json(FORENSICS / "R5_HISTORY_RESPONSE.json", {
        "schemaVersion": 1,
        "rawHistoryResponse": None,
        "rawHistoryPersistedByR5Runner": False,
        "observedControlFlow": "history[prompt_id] existed and was a mapping; old tuple validation then raised",
        "actualComfyUi028TupleSchema": {"1": "prompt_id", "2": "api_prompt", "3": "extra_data", "source": "server.py queue put tuple and main.py execution path"},
        "oldRunnerParser": {"1": "incorrectly_compared_to_api_prompt", "2": "incorrectly_treated_as_extra_data"},
        "fieldDifferences": [
            {"pointer": "/history/<prompt_id>/prompt/1", "actualType": "string prompt_id", "oldExpectedType": "object api_prompt"},
            {"pointer": "/history/<prompt_id>/prompt/2", "actualType": "object api_prompt", "oldExpectedType": "object extra_data containing client_id"},
            {"pointer": "/history/<prompt_id>/prompt/3", "actualType": "object extra_data", "oldRunnerAction": "ignored"},
        ],
        "primaryFailureClassification": "HISTORY_SCHEMA_PARSE_ERROR",
    })
    write_json(FORENSICS / "R5_QUEUE_SNAPSHOT.json", {
        "schemaVersion": 1,
        "preSubmitChecks": [
            {"phase": "initialQueue", "running": 0, "pending": 0, "provenBy": "execution reached POST after _verify_queue_empty"},
            {"phase": "preSubmitQueue", "running": 0, "pending": 0, "provenBy": "execution reached POST after second _verify_queue_empty"},
        ],
        "postSubmitRawSnapshotsPersisted": False,
    })
    write_exclusive(FORENSICS / "R5_WEBSOCKET_EVENTS.jsonl", canonical_bytes({
        "available": False,
        "reason": "R5 runner implemented no WebSocket connection or event capture",
    }) + b"\n")
    write_exclusive(FORENSICS / "R5_COMFYUI_LOG_EXCERPT.txt", LOG.read_bytes())
    write_json(FORENSICS / "R5_OUTPUT_RECOVERY_AUDIT.json", {
        "schemaVersion": 1,
        "windowLocal": {"start": "2026-08-28T17:24:30+08:00", "end": "2026-08-28T17:28:00+08:00"},
        "sourcePath": str(SOURCE_VIDEO),
        "sourceBytes": source_stat.st_size,
        "sourceMtimeNs": source_stat.st_mtime_ns,
        "sourceSha256": video_sha,
        "ffprobe": ffprobe,
        "logFacts": ["got prompt", "Prompt executed in 53.30 seconds"],
        "matchingMediaCount": 1,
        "r5CompleteOutputRecovered": True,
        "causalBindingStatus": "OUTPUT_TIME_AND_PREFIX_MATCH; ORIGINAL_PROMPT_ID_AND_HISTORY_RAW_VALUE_NOT_PERSISTED",
    })

    RECOVERED_VIDEO.parent.mkdir(parents=True, exist_ok=False)
    shutil.copy2(SOURCE_VIDEO, RECOVERED_VIDEO)
    if digest(RECOVERED_VIDEO) != video_sha:
        raise SystemExit("recovered media digest mismatch")
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(RECOVERED_VIDEO), "-f", "framemd5", str(FORENSICS / "R5_RECOVERED.framemd5")], check=True)
    write_json(FORENSICS / "R5_RECOVERY_RECEIPT.json", {
        "schemaVersion": 1,
        "r5AttemptState": "FAILED_AFTER_PROMPT_ACCEPTED",
        "r5ExperimentValidity": "INVALID_CONTROL_PLANE_HISTORY_BINDING",
        "r5CompleteOutputRecovered": True,
        "sourcePath": str(SOURCE_VIDEO),
        "recoveredPath": str(RECOVERED_VIDEO),
        "sha256": video_sha,
        "ffprobe": ffprobe,
        "r5AttemptLockPreserved": True,
        "r5RunBudgetConsumed": True,
        "r6Allowed": False,
        "r6BlockReason": "R5_COMPLETE_OUTPUT_RECOVERED",
    })

    hashes = []
    for path in sorted(FORENSICS.iterdir()):
        if path.name == "SHA256SUMS.txt" or not path.is_file():
            continue
        hashes.append(f"{digest(path)}  {path.name}")
    write_exclusive(FORENSICS / "SHA256SUMS.txt", ("\n".join(hashes) + "\n").encode("utf-8"))
    print("R5_FORENSICS=PASS")
    print("R5_COMPLETE_OUTPUT_RECOVERED=true")
    print(f"R5_RECOVERED_VIDEO_SHA256={video_sha}")
    print("R6_ALLOWED=false")


if __name__ == "__main__":
    main()
