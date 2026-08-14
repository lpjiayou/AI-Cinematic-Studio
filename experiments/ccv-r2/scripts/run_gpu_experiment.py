#!/usr/bin/env python3
"""Receipt-bound CCV-R2 runner. Default mode validates and exits without GPU work."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


class RunnerError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preparation_root", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.preparation_root.resolve()
    try:
        validator = Path(__file__).resolve().parents[1] / "preflight/validate_preparation.py"
        result = subprocess.run([sys.executable, str(validator), str(root)], check=False)
        if result.returncode != 0:
            raise RunnerError("preparation validation failed")
        receipt_path = root / "execution-readiness.json"
        receipt_sha = sha256_file(receipt_path)
        if not args.execute:
            print("CCV_R2_RUNNER=VALIDATE_ONLY_PASS")
            print("GPU_EXECUTION_STARTED=false")
            print(f"PREPARATION_RECEIPT_SHA256={receipt_sha}")
            return 0
        if args.authorization is None or not args.authorization.is_file():
            raise RunnerError("--execute requires an explicit authorization JSON file")
        authorization = json.loads(args.authorization.read_text("utf-8"))
        required = {
            "gpuExecutionAuthorized": True,
            "governanceCheckpoint": "ACS-CCV-R2-G2-GPU-EXECUTION",
            "preparationReceiptSha256": receipt_sha,
            "maximumQueueCount": 45,
        }
        for key, value in required.items():
            if authorization.get(key) != value:
                raise RunnerError(f"authorization mismatch for {key}")
        raise RunnerError(
            "G2 execution transport is intentionally not enabled by the G1 checkpoint; "
            "implement and review the G2 result ledger before queue submission"
        )
    except (OSError, ValueError, RunnerError) as exc:
        print("CCV_R2_RUNNER=FAIL_CLOSED")
        print(f"ERROR={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
