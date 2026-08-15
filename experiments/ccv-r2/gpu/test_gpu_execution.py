#!/usr/bin/env python3
"""Standard-library tests for the fail-closed G2 executor."""

from __future__ import annotations

import importlib
import json
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import execute_gpu_experiment as runner


ARMS = ["A0_TEXT_BASELINE", "A1_FACE_IDENTITY", "A2_FACE_OPENPOSE"]
SHOTS = [
    "01_medium_front",
    "02_closeup_side",
    "03_full_walking",
    "04_back_turning",
    "05_sitting_high",
]
SEEDS = [123456, 223456, 323456]


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_with_metadata(metadata: dict[str, object]) -> bytes:
    raw_pixel = b"\x00\x33\x66\x99"
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)),
            chunk(b"tEXt", b"ccvR2\x00" + json.dumps(metadata, sort_keys=True).encode("latin-1")),
            chunk(b"IDAT", zlib.compress(raw_pixel)),
            chunk(b"IEND", b""),
        ]
    )


class FakeComfyClient:
    def __init__(self, output_root: Path, fail_at: int | None = None):
        self.output_root = output_root
        self.fail_at = fail_at
        self.submissions = 0
        self.active = 0
        self.max_active = 0
        self.payloads: dict[str, dict[str, object]] = {}

    def probe(self) -> None:
        return None

    def queue(self, payload: dict[str, object]) -> str:
        if self.active != 0:
            raise AssertionError("runner queued more than one prompt")
        self.submissions += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        prompt_id = f"mock-{self.submissions:03d}"
        self.payloads[prompt_id] = payload
        return prompt_id

    def wait(self, prompt_id: str) -> dict[str, str]:
        if self.fail_at == self.submissions:
            self.active -= 1
            raise runner.ExecutionError("synthetic terminal GPU failure")
        payload = self.payloads[prompt_id]
        metadata = payload["extra_data"]["extra_pnginfo"]["ccvR2"]
        filename = prompt_id + ".png"
        (self.output_root / filename).write_bytes(png_with_metadata(metadata))
        self.active -= 1
        return {"filename": filename, "subfolder": ""}


class G2ExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="ccv-r2-g2-test-"))
        self.preparation = self.temp / "preparation"
        self.preparation.mkdir()
        (self.preparation / "requests").mkdir()
        self.comfy_output = self.temp / "comfy-output"
        self.comfy_output.mkdir()
        requests = []
        counter = 0
        for arm in ARMS:
            for seed in SEEDS:
                for shot in SHOTS:
                    counter += 1
                    run_id = f"{arm.lower()}__seed-{seed}__shot-{shot}"
                    blind_label = f"B{counter:03d}"
                    planned = f"outputs/{arm.lower()}/seed-{seed}/{shot}.png"
                    metadata = {
                        "runId": run_id,
                        "blindLabel": blind_label,
                        "armId": arm,
                        "shotId": shot,
                        "seed": seed,
                        "protocolVersion": "g0-v1",
                    }
                    payload = {
                        "prompt": {"1": {"class_type": "SaveImage", "inputs": {}}},
                        "extra_data": {"extra_pnginfo": {"ccvR2": metadata}},
                    }
                    relative = f"requests/{blind_label}__{run_id}.json"
                    payload_path = self.preparation / relative
                    payload_path.write_bytes(runner.canonical_bytes(payload))
                    digest, size = runner.sha256_file(payload_path)
                    requests.append(
                        {
                            "path": relative,
                            "sizeBytes": size,
                            "sha256": digest,
                            "runId": run_id,
                            "blindLabel": blind_label,
                            "armId": arm,
                            "shotId": shot,
                            "seed": seed,
                            "plannedOutputPath": planned,
                        }
                    )
        receipt = {
            "schemaVersion": "ACS-CCV-R2-EXECUTION-READINESS-1",
            "experimentId": "acs-ccv-r2",
            "protocolVersion": "g0-v1",
            "state": "GPU_READY_PREPARATION_COMPLETE_NO_GPU_EXECUTION",
            "requests": requests,
            "software": {"comfyUiCommit": "mock", "ipAdapterNodeCommit": "mock"},
            "host": {"gpu": {"name": "mock"}},
        }
        self.receipt_path = self.preparation / "execution-readiness.json"
        self.receipt_path.write_bytes(runner.canonical_bytes(receipt))
        self.inventory_path = self.preparation / "preparation-inventory.json"
        self.inventory_path.write_bytes(runner.canonical_bytes({"entries": []}))
        self.old_receipt = runner.EXPECTED_RECEIPT_SHA256
        self.old_inventory = runner.EXPECTED_INVENTORY_SHA256
        runner.EXPECTED_RECEIPT_SHA256 = runner.sha256_file(self.receipt_path)[0]
        runner.EXPECTED_INVENTORY_SHA256 = runner.sha256_file(self.inventory_path)[0]

    def tearDown(self) -> None:
        runner.EXPECTED_RECEIPT_SHA256 = self.old_receipt
        runner.EXPECTED_INVENTORY_SHA256 = self.old_inventory
        shutil.rmtree(self.temp)

    def authorization(self, result_root: Path, **changes: object) -> Path:
        value = {
            "schemaVersion": "ACS-CCV-R2-G2-EXECUTION-AUTHORIZATION-1",
            "governanceCheckpoint": runner.GOVERNANCE_CHECKPOINT,
            "authorizedBy": "PROJECT_LEAD",
            "authorizedAt": "2026-08-15",
            "gpuExecutionAuthorized": True,
            "preparationRoot": str(self.preparation),
            "preparationReceiptSha256": runner.EXPECTED_RECEIPT_SHA256,
            "preparationInventorySha256": runner.EXPECTED_INVENTORY_SHA256,
            "expectedRunCount": 45,
            "maximumQueueCount": 45,
            "maximumInFlight": 1,
            "automaticRetryAuthorized": False,
            "resultRoot": str(result_root),
            "comfyUiServer": "http://127.0.0.1:8188",
            "comfyUiOutputRoot": str(self.comfy_output),
            "historyTimeoutSeconds": 60,
            "pollIntervalSeconds": 0.25,
            "rightsLabels": ["SYNTHETIC_TEST_ONLY"],
            "claims": {"validationAccepted": False, "productionReady": False},
        }
        value.update(changes)
        path = self.temp / (result_root.name + "-authorization.json")
        path.write_bytes(runner.canonical_bytes(value))
        return path

    def test_45_runs_are_strictly_sequential_and_validate(self) -> None:
        result_root = self.temp / "result-success"
        authorization = self.authorization(result_root)
        client = FakeComfyClient(self.comfy_output)
        actual = runner.execute(
            self.preparation,
            authorization,
            client=client,
            validate_first=False,
        )
        self.assertEqual(actual, result_root)
        self.assertEqual(client.submissions, 45)
        self.assertEqual(client.max_active, 1)
        ledger = json.loads((result_root / "result-ledger.json").read_text())
        self.assertEqual(ledger["state"], runner.RESULT_STATE_COMPLETE)
        self.assertEqual(ledger["counts"]["succeeded"], 45)
        validator = importlib.import_module("validate_gpu_results")
        validator.EXPECTED_RECEIPT_SHA256 = runner.EXPECTED_RECEIPT_SHA256
        validator.EXPECTED_INVENTORY_SHA256 = runner.EXPECTED_INVENTORY_SHA256
        inventory_sha, _ = validator.validate(result_root)
        self.assertEqual(len(inventory_sha), 64)

    def test_terminal_failure_is_ledgered_once_and_stops(self) -> None:
        result_root = self.temp / "result-failure"
        authorization = self.authorization(result_root)
        client = FakeComfyClient(self.comfy_output, fail_at=3)
        with self.assertRaises(runner.ExecutionError):
            runner.execute(
                self.preparation,
                authorization,
                client=client,
                validate_first=False,
            )
        self.assertEqual(client.submissions, 3)
        failures = json.loads((result_root / "failure-ledger.json").read_text())
        self.assertEqual(len(failures["events"]), 1)
        self.assertFalse(failures["events"][0]["retryAuthorized"])
        ledger = json.loads((result_root / "result-ledger.json").read_text())
        self.assertEqual(ledger["state"], "FAIL_CLOSED")
        self.assertEqual(ledger["counts"], {"expected": 45, "queued": 3, "succeeded": 2, "failed": 1})

    def test_completed_resume_never_requeues(self) -> None:
        result_root = self.temp / "result-resume"
        authorization = self.authorization(result_root)
        first = FakeComfyClient(self.comfy_output)
        runner.execute(self.preparation, authorization, client=first, validate_first=False)
        second = FakeComfyClient(self.comfy_output)
        runner.execute(self.preparation, authorization, client=second, validate_first=False)
        self.assertEqual(first.submissions, 45)
        self.assertEqual(second.submissions, 0)

    def test_retry_authorization_mismatch_fails_before_queue(self) -> None:
        result_root = self.temp / "result-bad-auth"
        authorization = self.authorization(result_root, automaticRetryAuthorized=True)
        client = FakeComfyClient(self.comfy_output)
        with self.assertRaises(runner.ExecutionError):
            runner.execute(
                self.preparation,
                authorization,
                client=client,
                validate_first=False,
            )
        self.assertEqual(client.submissions, 0)
        self.assertFalse(result_root.exists())


if __name__ == "__main__":
    unittest.main()
