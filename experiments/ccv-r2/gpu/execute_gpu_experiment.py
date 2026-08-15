#!/usr/bin/env python3
"""Execute the frozen CCV-R2 matrix through local ComfyUI.

The runner is bound to the G1 preparation receipt and a G2 authorization document.
It submits at most one prompt at a time, records every terminal event atomically, and
never retries automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GOVERNANCE_CHECKPOINT = "ACS-CCV-R2-G2-GPU-EXECUTION"
EXPECTED_RECEIPT_SHA256 = "995035ee1169b7335d7c0707ea6adc31e36cd342c2a281f475fd66b7f4952c05"
EXPECTED_INVENTORY_SHA256 = "95e1257003b28aced87719d31b4caba2eabc5a18995d2d9b98dbfb20157db40a"
EXPECTED_RUN_COUNT = 45
RESULT_STATE_ACTIVE = "GPU_EXECUTION_ACTIVE"
RESULT_STATE_COMPLETE = "GPU_GENERATION_COMPLETE_AWAITING_INDEPENDENT_REVIEW"
TERMINAL_FAILURE_STATES = {"error", "failed", "cancelled", "canceled"}


class ExecutionError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExecutionError(message)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_bytes(value))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def confined_path(root: Path, relative: str, *, prefix: str | None = None) -> Path:
    rel = Path(relative)
    require(not rel.is_absolute(), f"absolute path rejected: {relative}")
    require(".." not in rel.parts, f"path traversal rejected: {relative}")
    candidate = (root / rel).resolve()
    boundary = root.resolve()
    require(candidate == boundary or boundary in candidate.parents, f"path escaped boundary: {relative}")
    if prefix is not None:
        required = (boundary / prefix).resolve()
        require(candidate == required or required in candidate.parents, f"path outside {prefix}: {relative}")
    return candidate


def validate_preparation(preparation_root: Path) -> None:
    validator = Path(__file__).resolve().parents[1] / "preflight" / "validate_preparation.py"
    require(validator.is_file(), f"G1 validator missing: {validator}")
    result = subprocess.run(
        [sys.executable, str(validator), str(preparation_root)],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    require(result.returncode == 0, "G1 preparation validation failed")


def verify_authorization(
    authorization_path: Path,
    preparation_root: Path,
    result_root: Path,
) -> tuple[dict[str, Any], str]:
    raw = authorization_path.read_bytes()
    authorization = json.loads(raw)
    required = {
        "schemaVersion": "ACS-CCV-R2-G2-EXECUTION-AUTHORIZATION-1",
        "gpuExecutionAuthorized": True,
        "governanceCheckpoint": GOVERNANCE_CHECKPOINT,
        "preparationReceiptSha256": EXPECTED_RECEIPT_SHA256,
        "preparationInventorySha256": EXPECTED_INVENTORY_SHA256,
        "expectedRunCount": EXPECTED_RUN_COUNT,
        "maximumQueueCount": EXPECTED_RUN_COUNT,
        "maximumInFlight": 1,
        "automaticRetryAuthorized": False,
    }
    for key, expected in required.items():
        require(authorization.get(key) == expected, f"authorization mismatch for {key}")
    require(
        Path(authorization.get("preparationRoot", "")).resolve() == preparation_root.resolve(),
        "authorization preparationRoot mismatch",
    )
    require(
        Path(authorization.get("resultRoot", "")).resolve() == result_root.resolve(),
        "authorization resultRoot mismatch",
    )
    server = str(authorization.get("comfyUiServer", ""))
    parsed = urllib.parse.urlparse(server)
    require(parsed.scheme == "http", "ComfyUI server must use http")
    require(parsed.hostname in {"127.0.0.1", "localhost", "::1"}, "ComfyUI server must be local")
    require(parsed.path in {"", "/"}, "ComfyUI server URL must not include a path")
    output_root = Path(str(authorization.get("comfyUiOutputRoot", "")))
    require(output_root.is_absolute(), "comfyUiOutputRoot must be absolute")
    claims = authorization.get("claims", {})
    require(claims.get("validationAccepted") is False, "validationAccepted must remain false")
    require(claims.get("productionReady") is False, "productionReady must remain false")
    return authorization, sha256_bytes(raw)


def request_path(preparation_root: Path, request: dict[str, Any]) -> Path:
    registered = Path(str(request["path"]))
    path = (
        preparation_root / "requests" / registered.name
        if registered.is_absolute()
        else preparation_root / registered
    )
    if not path.is_file():
        path = preparation_root / "requests" / f"{request['blindLabel']}__{request['runId']}.json"
    require(path.is_file(), f"request file missing: {request['runId']}")
    digest, size = sha256_file(path)
    require(digest == request["sha256"], f"request digest mismatch: {request['runId']}")
    require(size == request["sizeBytes"], f"request size mismatch: {request['runId']}")
    return path


def expected_metadata(request: dict[str, Any], protocol_version: str) -> dict[str, Any]:
    return {
        "runId": request["runId"],
        "blindLabel": request["blindLabel"],
        "armId": request["armId"],
        "shotId": request["shotId"],
        "seed": request["seed"],
        "protocolVersion": protocol_version,
    }


def png_text_chunks(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with path.open("rb") as handle:
        require(handle.read(8) == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}")
        while True:
            raw_length = handle.read(4)
            require(len(raw_length) == 4, f"truncated PNG: {path}")
            length = struct.unpack(">I", raw_length)[0]
            chunk_type = handle.read(4)
            data = handle.read(length)
            crc = handle.read(4)
            require(len(chunk_type) == 4 and len(data) == length and len(crc) == 4, f"truncated PNG chunk: {path}")
            if chunk_type == b"tEXt":
                key, separator, value = data.partition(b"\x00")
                if separator:
                    values[key.decode("latin-1")] = value.decode("latin-1")
            elif chunk_type == b"zTXt":
                key, separator, remainder = data.partition(b"\x00")
                if separator and len(remainder) >= 2 and remainder[0] == 0:
                    values[key.decode("latin-1")] = zlib.decompress(remainder[1:]).decode("utf-8")
            elif chunk_type == b"iTXt":
                key, separator, remainder = data.partition(b"\x00")
                if separator and len(remainder) >= 2:
                    compressed = remainder[0] == 1
                    remainder = remainder[2:]
                    _, _, remainder = remainder.partition(b"\x00")
                    _, _, value = remainder.partition(b"\x00")
                    if compressed:
                        value = zlib.decompress(value)
                    values[key.decode("latin-1")] = value.decode("utf-8")
            if chunk_type == b"IEND":
                break
    return values


def verify_png_metadata(path: Path, expected: dict[str, Any]) -> str:
    text = png_text_chunks(path)
    require("ccvR2" in text, f"PNG ccvR2 metadata missing: {path}")
    actual = json.loads(text["ccvR2"])
    require(actual == expected, f"PNG ccvR2 metadata mismatch: {path}")
    return sha256_bytes(canonical_bytes(actual))


class ComfyClient:
    def __init__(self, server: str, timeout_seconds: int, poll_seconds: float):
        self.server = server.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self.client_id = str(uuid.uuid4())

    def _json(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None
        method = "GET"
        headers: dict[str, str] = {}
        if payload is not None:
            data = canonical_bytes(payload)
            method = "POST"
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.server + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ExecutionError(f"ComfyUI request failed for {path}: {exc}") from exc

    def probe(self) -> None:
        data = self._json("/system_stats")
        require(isinstance(data, dict), "unexpected ComfyUI system_stats response")

    def queue(self, payload: dict[str, Any]) -> str:
        body = dict(payload)
        body["client_id"] = self.client_id
        result = self._json("/prompt", body)
        prompt_id = result.get("prompt_id") if isinstance(result, dict) else None
        require(isinstance(prompt_id, str) and prompt_id, "ComfyUI did not return prompt_id")
        return prompt_id

    def wait(self, prompt_id: str) -> dict[str, str]:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            response = self._json(f"/history/{urllib.parse.quote(prompt_id, safe='')}")
            entry = response.get(prompt_id) if isinstance(response, dict) else None
            if not entry:
                time.sleep(self.poll_seconds)
                continue
            status = entry.get("status", {}) if isinstance(entry, dict) else {}
            status_string = str(status.get("status_str", "")).lower()
            messages = status.get("messages", [])
            failed_message = next(
                (
                    item
                    for item in messages
                    if isinstance(item, list)
                    and item
                    and str(item[0]).lower() in {"execution_error", "execution_interrupted"}
                ),
                None,
            )
            if status_string in TERMINAL_FAILURE_STATES or failed_message is not None:
                raise ExecutionError(f"ComfyUI terminal failure for {prompt_id}: {failed_message or status_string}")
            if status.get("completed") is True:
                images = []
                for node in entry.get("outputs", {}).values():
                    if isinstance(node, dict):
                        images.extend(item for item in node.get("images", []) if isinstance(item, dict))
                require(len(images) == 1, f"expected exactly one image for {prompt_id}, found {len(images)}")
                image = images[0]
                require(image.get("type") == "output", f"non-output image rejected for {prompt_id}")
                filename = image.get("filename")
                subfolder = image.get("subfolder", "")
                require(isinstance(filename, str) and filename, f"missing output filename for {prompt_id}")
                require(isinstance(subfolder, str), f"invalid output subfolder for {prompt_id}")
                return {"filename": filename, "subfolder": subfolder}
            time.sleep(self.poll_seconds)
        raise ExecutionError(f"ComfyUI history timeout for {prompt_id}")


def initial_ledger(
    preparation_root: Path,
    result_root: Path,
    receipt_sha: str,
    authorization_sha: str,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "schemaVersion": "ACS-CCV-R2-G2-RESULT-LEDGER-1",
        "experimentId": "acs-ccv-r2",
        "state": RESULT_STATE_ACTIVE,
        "governanceCheckpoint": GOVERNANCE_CHECKPOINT,
        "preparationRoot": str(preparation_root),
        "preparationReceiptSha256": receipt_sha,
        "authorizationSha256": authorization_sha,
        "resultRoot": str(result_root),
        "createdAt": now,
        "updatedAt": now,
        "counts": {"expected": EXPECTED_RUN_COUNT, "queued": 0, "succeeded": 0, "failed": 0},
        "claims": {
            "gpuExecutionAuthorized": True,
            "gpuExecutionStarted": False,
            "comfyUiQueueTouched": False,
            "imageGenerated": False,
            "validationAccepted": False,
            "productionReady": False,
        },
        "runs": [],
    }


def initial_failure_ledger(receipt_sha: str, authorization_sha: str) -> dict[str, Any]:
    return {
        "schemaVersion": "ACS-CCV-R2-G2-FAILURE-LEDGER-1",
        "experimentId": "acs-ccv-r2",
        "state": "EMPTY",
        "preparationReceiptSha256": receipt_sha,
        "authorizationSha256": authorization_sha,
        "automaticRetryAuthorized": False,
        "events": [],
    }


def load_or_create_state(
    result_root: Path,
    authorization_path: Path,
    authorization_sha: str,
    preparation_root: Path,
    receipt_sha: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger_path = result_root / "result-ledger.json"
    failure_path = result_root / "failure-ledger.json"
    stored_authorization = result_root / "execution-authorization.json"
    if not result_root.exists():
        result_root.mkdir(parents=True)
        (result_root / "outputs").mkdir()
        atomic_write_bytes(stored_authorization, authorization_path.read_bytes())
        ledger = initial_ledger(preparation_root, result_root, receipt_sha, authorization_sha)
        failures = initial_failure_ledger(receipt_sha, authorization_sha)
        atomic_write_json(ledger_path, ledger)
        atomic_write_json(failure_path, failures)
        return ledger, failures
    require(result_root.is_dir(), f"result root is not a directory: {result_root}")
    for path in (stored_authorization, ledger_path, failure_path):
        require(path.is_file(), f"existing result root is not resumable; missing {path.name}")
    stored_sha, _ = sha256_file(stored_authorization)
    require(stored_sha == authorization_sha, "stored authorization digest mismatch")
    ledger = load_json(ledger_path)
    failures = load_json(failure_path)
    require(ledger.get("schemaVersion") == "ACS-CCV-R2-G2-RESULT-LEDGER-1", "result ledger schema mismatch")
    require(ledger.get("preparationReceiptSha256") == receipt_sha, "result ledger receipt mismatch")
    require(ledger.get("authorizationSha256") == authorization_sha, "result ledger authorization mismatch")
    require(Path(ledger.get("resultRoot", "")).resolve() == result_root.resolve(), "result ledger root mismatch")
    require(failures.get("events") == [], "failed execution cannot resume without separate retry authorization")
    run_ids = [row.get("runId") for row in ledger.get("runs", [])]
    require(len(run_ids) == len(set(run_ids)), "duplicate result-ledger run ID")
    require(all(row.get("state") == "COMPLETE" for row in ledger.get("runs", [])), "non-terminal run blocks safe resume")
    return ledger, failures


def verify_completed_row(
    row: dict[str, Any],
    request: dict[str, Any],
    result_root: Path,
    protocol_version: str,
) -> None:
    require(row.get("runId") == request["runId"], "resume run binding mismatch")
    require(row.get("blindLabel") == request["blindLabel"], "resume blind label mismatch")
    require(row.get("plannedOutputPath") == request["plannedOutputPath"], "resume output path mismatch")
    destination = confined_path(result_root, request["plannedOutputPath"], prefix="outputs")
    require(destination.is_file(), f"completed output missing: {request['runId']}")
    digest, size = sha256_file(destination)
    require(digest == row.get("output", {}).get("sha256"), f"completed output digest mismatch: {request['runId']}")
    require(size == row.get("output", {}).get("sizeBytes"), f"completed output size mismatch: {request['runId']}")
    meta_sha = verify_png_metadata(destination, expected_metadata(request, protocol_version))
    require(meta_sha == row.get("output", {}).get("promptMetadataSha256"), f"metadata digest mismatch: {request['runId']}")


def record_failure(
    ledger: dict[str, Any],
    failures: dict[str, Any],
    result_root: Path,
    request: dict[str, Any],
    prompt_id: str | None,
    error: Exception,
) -> None:
    event_id = f"G2-F{len(failures['events']) + 1:04d}"
    event = {
        "eventId": event_id,
        "runId": request["runId"],
        "blindLabel": request["blindLabel"],
        "stage": "GPU_EXECUTION",
        "failureCode": type(error).__name__,
        "message": str(error),
        "occurredAt": utc_now(),
        "promptId": prompt_id,
        "retryAuthorized": False,
        "disposition": "TERMINAL_FAILED",
    }
    failures["events"].append(event)
    failures["state"] = "TERMINAL_FAILURE_RECORDED"
    existing = next((row for row in ledger["runs"] if row["runId"] == request["runId"]), None)
    if existing is None:
        ledger["runs"].append(
            {
                "runId": request["runId"],
                "blindLabel": request["blindLabel"],
                "armId": request["armId"],
                "shotId": request["shotId"],
                "seed": request["seed"],
                "plannedOutputPath": request["plannedOutputPath"],
                "state": "FAILED",
                "promptId": prompt_id,
                "failureEventId": event_id,
            }
        )
    else:
        existing.update({"state": "FAILED", "failureEventId": event_id})
    ledger["state"] = "FAIL_CLOSED"
    ledger["counts"]["failed"] = len(failures["events"])
    ledger["updatedAt"] = utc_now()
    atomic_write_json(result_root / "failure-ledger.json", failures)
    atomic_write_json(result_root / "result-ledger.json", ledger)


def finalize(
    ledger: dict[str, Any],
    result_root: Path,
    receipt: dict[str, Any],
    authorization_sha: str,
) -> None:
    completed = ledger["runs"]
    require(len(completed) == EXPECTED_RUN_COUNT, "cannot finalize before 45 completed runs")
    output_rows = []
    for row in sorted(completed, key=lambda value: value["plannedOutputPath"]):
        path = confined_path(result_root, row["plannedOutputPath"], prefix="outputs")
        digest, size = sha256_file(path)
        require(digest == row["output"]["sha256"] and size == row["output"]["sizeBytes"], f"final output mismatch: {row['runId']}")
        output_rows.append(
            {
                "path": path.relative_to(result_root).as_posix(),
                "sizeBytes": size,
                "sha256": digest,
                "runId": row["runId"],
                "blindLabel": row["blindLabel"],
            }
        )
    inventory = {"schemaVersion": "ACS-CCV-R2-G2-RESULT-INVENTORY-1", "entries": output_rows}
    atomic_write_json(result_root / "result-inventory.json", inventory)
    inventory_sha, _ = sha256_file(result_root / "result-inventory.json")
    atomic_write_bytes(
        result_root / "result-inventory.sha256",
        f"{inventory_sha}  result-inventory.json\n".encode("utf-8"),
    )
    review = {
        "schemaVersion": "ACS-CCV-R2-G2-BLIND-REVIEW-PACKAGE-1",
        "state": "AWAITING_INDEPENDENT_BLIND_VISUAL_REVIEW",
        "experimentId": "acs-ccv-r2",
        "itemCount": EXPECTED_RUN_COUNT,
        "criteria": [
            {"id": "identity-continuity", "weight": 0.4},
            {"id": "shot-pose-adherence", "weight": 0.3},
            {"id": "anatomy-artifact-freedom", "weight": 0.2},
            {"id": "reference-contamination-control", "weight": 0.1},
        ],
        "items": [
            {
                "blindLabel": row["blindLabel"],
                "path": row["plannedOutputPath"],
                "sha256": row["output"]["sha256"],
            }
            for row in sorted(completed, key=lambda value: value["blindLabel"])
        ],
        "claims": {"validationAccepted": False, "productionReady": False},
    }
    atomic_write_json(result_root / "review-package.json", review)
    execution_receipt = {
        "schemaVersion": "ACS-CCV-R2-G2-EXECUTION-RECEIPT-1",
        "state": RESULT_STATE_COMPLETE,
        "completedAt": utc_now(),
        "host": socket.gethostname(),
        "preparationReceiptSha256": EXPECTED_RECEIPT_SHA256,
        "authorizationSha256": authorization_sha,
        "resultInventorySha256": inventory_sha,
        "counts": {"expected": EXPECTED_RUN_COUNT, "queued": EXPECTED_RUN_COUNT, "succeeded": EXPECTED_RUN_COUNT, "failed": 0},
        "sourceSoftware": receipt.get("software"),
        "sourceHostGpu": receipt.get("host", {}).get("gpu"),
        "claims": {
            "gpuExecutionAuthorized": True,
            "gpuExecutionStarted": True,
            "comfyUiQueueTouched": True,
            "imageGenerated": True,
            "validationAccepted": False,
            "productionReady": False,
        },
    }
    atomic_write_json(result_root / "execution-receipt.json", execution_receipt)
    ledger["state"] = RESULT_STATE_COMPLETE
    ledger["counts"] = {"expected": EXPECTED_RUN_COUNT, "queued": EXPECTED_RUN_COUNT, "succeeded": EXPECTED_RUN_COUNT, "failed": 0}
    ledger["claims"].update(
        {
            "gpuExecutionStarted": True,
            "comfyUiQueueTouched": True,
            "imageGenerated": True,
            "validationAccepted": False,
            "productionReady": False,
        }
    )
    ledger["updatedAt"] = utc_now()
    atomic_write_json(result_root / "result-ledger.json", ledger)


def execute(
    preparation_root: Path,
    authorization_path: Path,
    *,
    client: ComfyClient | Any | None = None,
    validate_first: bool = True,
) -> Path:
    preparation_root = preparation_root.resolve()
    require(preparation_root.is_dir(), f"preparation root missing: {preparation_root}")
    receipt_path = preparation_root / "execution-readiness.json"
    inventory_path = preparation_root / "preparation-inventory.json"
    require(receipt_path.is_file() and inventory_path.is_file(), "G1 preparation controls missing")
    receipt_sha, _ = sha256_file(receipt_path)
    inventory_sha, _ = sha256_file(inventory_path)
    require(receipt_sha == EXPECTED_RECEIPT_SHA256, "G1 receipt digest is not authorized")
    require(inventory_sha == EXPECTED_INVENTORY_SHA256, "G1 inventory digest is not authorized")
    if validate_first:
        validate_preparation(preparation_root)
    receipt = load_json(receipt_path)
    requests = receipt.get("requests")
    require(isinstance(requests, list) and len(requests) == EXPECTED_RUN_COUNT, "receipt must contain 45 requests")
    for field in ("runId", "blindLabel", "plannedOutputPath"):
        values = [row.get(field) for row in requests]
        require(None not in values and len(values) == len(set(values)), f"request field must be unique: {field}")
    preliminary = json.loads(authorization_path.read_text("utf-8"))
    result_root = Path(str(preliminary.get("resultRoot", ""))).resolve()
    authorization, authorization_sha = verify_authorization(
        authorization_path.resolve(), preparation_root, result_root
    )
    ledger, failures = load_or_create_state(
        result_root,
        authorization_path.resolve(),
        authorization_sha,
        preparation_root,
        receipt_sha,
    )
    completed_by_id = {row["runId"]: row for row in ledger["runs"]}
    for request in requests:
        if request["runId"] in completed_by_id:
            verify_completed_row(completed_by_id[request["runId"]], request, result_root, receipt["protocolVersion"])
    if len(completed_by_id) == EXPECTED_RUN_COUNT:
        finalize(ledger, result_root, receipt, authorization_sha)
        return result_root
    if client is None:
        client = ComfyClient(
            authorization["comfyUiServer"],
            int(authorization.get("historyTimeoutSeconds", 1800)),
            float(authorization.get("pollIntervalSeconds", 2)),
        )
    client.probe()
    comfy_output_root = Path(authorization["comfyUiOutputRoot"]).resolve()
    require(comfy_output_root.is_dir(), f"ComfyUI output root missing: {comfy_output_root}")
    queue_submissions = int(ledger["counts"]["queued"])
    for index, request in enumerate(requests, start=1):
        if request["runId"] in completed_by_id:
            print(f"RESUME_VERIFIED {index}/{EXPECTED_RUN_COUNT} {request['runId']}", flush=True)
            continue
        require(queue_submissions < authorization["maximumQueueCount"], "maximum queue count reached")
        payload_path = request_path(preparation_root, request)
        payload = load_json(payload_path)
        prompt_id: str | None = None
        started = time.monotonic()
        queued_at = utc_now()
        try:
            prompt_id = client.queue(payload)
            queue_submissions += 1
            row = {
                "runId": request["runId"],
                "blindLabel": request["blindLabel"],
                "armId": request["armId"],
                "shotId": request["shotId"],
                "seed": request["seed"],
                "plannedOutputPath": request["plannedOutputPath"],
                "requestPath": request["path"],
                "requestSha256": request["sha256"],
                "state": "QUEUED",
                "promptId": prompt_id,
                "queuedAt": queued_at,
                "completedAt": None,
                "durationSeconds": None,
                "output": None,
                "failureEventId": None,
            }
            ledger["runs"].append(row)
            ledger["counts"]["queued"] = queue_submissions
            ledger["claims"]["gpuExecutionStarted"] = True
            ledger["claims"]["comfyUiQueueTouched"] = True
            ledger["updatedAt"] = utc_now()
            atomic_write_json(result_root / "result-ledger.json", ledger)
            image = client.wait(prompt_id)
            source = confined_path(
                comfy_output_root,
                str(Path(image["subfolder"]) / image["filename"]),
            )
            require(source.is_file(), f"ComfyUI output missing: {source}")
            source_sha, source_size = sha256_file(source)
            require(source_size > 0, f"zero-byte output rejected: {source}")
            destination = confined_path(result_root, request["plannedOutputPath"], prefix="outputs")
            require(not destination.exists(), f"destination already exists: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".copying")
            require(not temporary.exists(), f"temporary destination already exists: {temporary}")
            shutil.copyfile(source, temporary)
            copied_sha, copied_size = sha256_file(temporary)
            require((copied_sha, copied_size) == (source_sha, source_size), "output copy digest mismatch")
            metadata_sha = verify_png_metadata(
                temporary,
                expected_metadata(request, receipt["protocolVersion"]),
            )
            os.replace(temporary, destination)
            row.update(
                {
                    "state": "COMPLETE",
                    "completedAt": utc_now(),
                    "durationSeconds": round(time.monotonic() - started, 3),
                    "output": {
                        "path": request["plannedOutputPath"],
                        "sizeBytes": copied_size,
                        "sha256": copied_sha,
                        "promptMetadataSha256": metadata_sha,
                    },
                }
            )
            ledger["counts"]["succeeded"] = sum(item["state"] == "COMPLETE" for item in ledger["runs"])
            ledger["claims"]["imageGenerated"] = True
            ledger["updatedAt"] = utc_now()
            atomic_write_json(result_root / "result-ledger.json", ledger)
            completed_by_id[request["runId"]] = row
            print(f"GPU_RUN_PASS {index}/{EXPECTED_RUN_COUNT} {request['runId']} {prompt_id}", flush=True)
        except Exception as exc:
            record_failure(ledger, failures, result_root, request, prompt_id, exc)
            raise ExecutionError(f"execution stopped after {request['runId']}: {exc}") from exc
    finalize(ledger, result_root, receipt, authorization_sha)
    return result_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preparation_root", type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    args = parser.parse_args()
    try:
        result_root = execute(args.preparation_root, args.authorization)
        print("CCV_R2_G2_GPU_EXECUTION=PASS")
        print("RUN_COUNT=45")
        print(f"RESULT_ROOT={result_root}")
        print("VALIDATION_ACCEPTED=false")
        print("PRODUCTION_READY=false")
        return 0
    except (OSError, ValueError, KeyError, ExecutionError) as exc:
        print("CCV_R2_G2_GPU_EXECUTION=FAIL_CLOSED")
        print(f"ERROR={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
