#!/usr/bin/env python3
"""Round 1 hardened evidence entrypoint.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION
"""

from pathlib import Path

from evidence_common import run_cli


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            "round-1",
            Path(__file__).resolve().parents[1] / "configs" / "round-1.json",
        )
    )
