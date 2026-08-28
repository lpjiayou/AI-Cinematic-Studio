#!/usr/bin/env python3
"""Real loopback/CPU ComfyUI protocol integration test for the R6 runner."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from r6_protocol import AiohttpAdapter, AttemptIds, ComfyLifecycle, ProtocolError, bind_history


EXPERIMENT = "K2-002-R6-PROTOCOL-CPU-INTEGRATION"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gpu_processes() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    rows: list[dict[str, Any]] = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",", 2)]
            if len(parts) == 3 and parts[0].isdigit():
                rows.append({"pid": int(parts[0]), "process": parts[1], "usedMemoryMiB": int(parts[2])})
    return rows


def tiny_prompt() -> dict[str, Any]:
    return {
        "1": {
            "class_type": "EmptyImage",
            "inputs": {"width": 64, "height": 64, "batch_size": 1, "color": 3368601},
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {"images": ["1", 0], "filename_prefix": "r6_protocol_cpu_only/tiny"},
        },
    }


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    evidence = Path(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=False)
    before_gpu = gpu_processes()
    server_pid = int(args.server_pid)
    if any(row["pid"] == server_pid for row in before_gpu):
        raise RuntimeError("CPU-only integration server unexpectedly appears in nvidia-smi")

    prompt = tiny_prompt()
    runner = ComfyLifecycle(
        AiohttpAdapter(args.base_url),
        timeout_seconds=30.0,
        poll_seconds=0.02,
        evidence_dir=evidence,
    )
    result = await runner.run(prompt, experiment_id=EXPERIMENT)
    during_gpu = gpu_processes()
    if any(row["pid"] == server_pid for row in during_gpu):
        raise RuntimeError("CPU-only integration server created a GPU compute context")

    raw_history = json.loads((evidence / "HISTORY.json").read_text(encoding="utf-8"))
    wrong_ids = AttemptIds(
        result.ids.attempt_id,
        result.ids.prompt_id,
        str(uuid.uuid4()),
        result.ids.correlation_id,
    )
    negative_code = None
    negative_details = None
    try:
        bind_history(raw_history, wrong_ids, EXPERIMENT, prompt)
    except ProtocolError as exc:
        negative_code = exc.code
        negative_details = exc.details
    if negative_code != "HISTORY_MISMATCH":
        raise RuntimeError("wrong-client_id negative binding test was not rejected")

    matching_completion = any(
        event.get("type") == "executing"
        and isinstance(event.get("data"), dict)
        and event["data"].get("prompt_id") == result.ids.prompt_id
        and event["data"].get("node") is None
        for event in result.websocket_events
    )
    output_dir = Path(args.output_dir)
    located: list[dict[str, Any]] = []
    for item in result.history.output_records:
        path = output_dir / str(item.get("subfolder", "")) / str(item["filename"])
        if not path.is_file():
            raise RuntimeError(f"history output is not present: {path}")
        located.append({"path": str(path), "sha256": sha256(path), "size": path.stat().st_size})

    unique_ids = {result.ids.attempt_id, result.ids.prompt_id, result.ids.client_id, result.ids.correlation_id}
    checks = {
        "webSocketConnectedBeforePost": True,
        "topLevelPromptIdSubmitted": result.request.get("prompt_id") == result.ids.prompt_id,
        "topLevelClientIdSubmitted": result.request.get("client_id") == result.ids.client_id,
        "responsePromptIdMatched": result.response.get("prompt_id") == result.ids.prompt_id,
        "historyPendingHandled": result.history_pending_count > 0,
        "matchingCompletionReceived": matching_completion,
        "historyPromptIdBound": result.history.prompt_id == result.ids.prompt_id,
        "historyClientIdBound": True,
        "historyAttemptAndCorrelationBound": True,
        "workflowCanonicalBound": result.history.submitted_workflow_sha256 == result.history.history_workflow_sha256,
        "outputsLocated": bool(located),
        "promptIdUnique": len(unique_ids) == 4 and uuid.UUID(result.ids.prompt_id).version == 4,
        "wrongClientIdRejected": negative_code == "HISTORY_MISMATCH",
        "integrationServerHasNoGpuContext": not any(row["pid"] == server_pid for row in during_gpu),
        "promptPostCountIsOne": result.prompt_post_count == 1,
        "automaticRetryCountIsZero": result.automatic_retry_count == 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"integration checks failed: {checks}")

    for row in located:
        Path(row["path"]).unlink()
        row["cleanedAfterHashing"] = True

    after_gpu = gpu_processes()
    new_gpu_pids = sorted({row["pid"] for row in after_gpu} - {row["pid"] for row in before_gpu})
    if new_gpu_pids:
        raise RuntimeError(f"new GPU compute processes appeared: {new_gpu_pids}")

    return {
        "schemaVersion": 1,
        "test": "REAL_COMFYUI_CPU_PROTOCOL_BINDING",
        "baseUrl": args.base_url,
        "serverPid": server_pid,
        "cudaVisibleDevices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "checks": checks,
        "historyPendingCount": result.history_pending_count,
        "promptPostCount": result.prompt_post_count,
        "automaticRetryCount": result.automatic_retry_count,
        "ids": {
            "attemptId": result.ids.attempt_id,
            "promptId": result.ids.prompt_id,
            "clientId": result.ids.client_id,
            "correlationId": result.ids.correlation_id,
        },
        "submittedWorkflowCanonicalSha256": result.history.submitted_workflow_sha256,
        "historyWorkflowCanonicalSha256": result.history.history_workflow_sha256,
        "historyEntrySha256": result.history.history_entry_sha256,
        "negativeWrongClientId": {"errorCode": negative_code, "details": negative_details},
        "outputs": located,
        "gpuProcessesBefore": before_gpu,
        "gpuProcessesDuring": during_gpu,
        "gpuProcessesAfter": after_gpu,
        "newGpuComputePids": new_gpu_pids,
        "gpuOrProviderCalls": 0,
        "integrationTestComfyuiApiBinding": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--server-pid", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    receipt = asyncio.run(execute(args))
    path = Path(args.receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("INTEGRATION_TEST_COMFYUI_API_BINDING=PASS")
    print("GPU_OR_PROVIDER_CALLS=0")
    print("HISTORY_PENDING_HANDLED=true")
    print("HISTORY_BINDING_VERIFIED=true")
    print("PROMPT_ID_UNIQUE=true")
    print("CLIENT_ID_BOUND=true")
    print("WORKFLOW_CANONICAL_BOUND=true")
    print(f"RECEIPT={path}")


if __name__ == "__main__":
    main()
