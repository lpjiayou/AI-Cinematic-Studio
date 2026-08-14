#!/usr/bin/env python3
"""Round 2 hardened evidence entrypoint.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION
"""

from pathlib import Path

from evidence_common import run_cli


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            "round-2",
            Path(__file__).resolve().parents[1] / "configs" / "round-2.json",
        )
    )
