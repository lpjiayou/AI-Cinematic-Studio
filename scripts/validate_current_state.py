"""Validate concise current state, immutable history and M1-M19 truth fields."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re


CURRENT = Path("CURRENT_MILESTONE.md")
HISTORY = Path("CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md")
MATRIX = Path("docs/status/M1-M19-CAPABILITY-STATUS.md")
BASELINE = Path("docs/status/CROSS_REPOSITORY_BASELINE.md")
EXPECTED_HISTORY_SHA256 = "5e05b68e83ed55f90b342aee627001a7bbf66cf59f92e5106270175b07f61f6a"

REQUIRED_BASELINE_VALUES = {
    "CORE_MAIN": "a455c8e76427d53d75bb7f15259b9875d9768914",
    "CORE_TREE": "d92159d5c3c5d3896d1fe9e56b896413277fe4e8",
    "M13_BASE_TAG": "m13-base-backend-v1",
    "M13_BASE_TAG_OBJECT": "b2d086b622bdb5456f6af325e458aa3771e43e80",
    "M13_BASE_TAG_TARGET": "a455c8e76427d53d75bb7f15259b9875d9768914",
    "FRONTEND_MAIN": "a0be9edc91437bf0e7c5dd14883e656e750b3aee",
    "FRONTEND_TREE": "c25b9e3744d561c93fed26d0a07e59a1915a6071",
}
REQUIRED_CURRENT = {
    "M12_RUNTIME_INSTALLED": "false",
    "M12_RUNTIME_G0": "NOT_COMPLETE",
    "M12_G0_3_STATE": "ENVIRONMENT_HOLD",
    "M12_C3_READY_TO_START": "false",
    "M13_BASE_BACKEND": "COMPLETE",
    "M13_BASE_CLOSEOUT": "ACCEPTED",
    "M13_PRODUCT_CAPABILITY_COMPLETE": "false",
    "M13_EXTENSION_G0_AUTHORIZED": "false",
    "M13_EXTENSION_IMPLEMENTATION_AUTHORIZED": "false",
    "A100_START_AUTHORIZED": "false",
    "PUBLICATION_ALLOWED": "false",
    "NEXT_TASK": "LOCAL_WSL2_HANDOFF_AND_M12_C3_PREFLIGHT",
}
MATRIX_DIMENSIONS = {
    "ARCHITECTURE_STATUS",
    "BACKEND_STATUS",
    "RUNTIME_STATUS",
    "FRONTEND_STATUS",
    "PRODUCT_STATUS",
    "PRODUCTION_STATUS",
}


def require_pair(text: str, key: str, value: str, path: Path, errors: list[str]) -> None:
    if f"{key}={value}" not in text:
        errors.append(f"{path}: missing {key}={value}")


def main() -> None:
    errors: list[str] = []
    current_text = CURRENT.read_text(encoding="utf-8")
    matrix_text = MATRIX.read_text(encoding="utf-8")
    baseline_text = BASELINE.read_text(encoding="utf-8")
    history_bytes = HISTORY.read_bytes()

    if len(current_text.splitlines()) > 200:
        errors.append(f"{CURRENT}: must remain concise (maximum 200 lines)")
    if re.search(r"(?m)^## 0A\.", current_text):
        errors.append(f"{CURRENT}: unarchived historical section 0A found")

    marker = b"\n## 0A."
    start = history_bytes.find(marker)
    if start < 0:
        errors.append(f"{HISTORY}: historical section marker is missing")
    else:
        digest = sha256(history_bytes[start + 1 :]).hexdigest()
        if digest != EXPECTED_HISTORY_SHA256:
            errors.append(f"{HISTORY}: historical bytes digest {digest} != {EXPECTED_HISTORY_SHA256}")

    for key, value in REQUIRED_BASELINE_VALUES.items():
        require_pair(baseline_text, key, value, BASELINE, errors)
    for key, value in REQUIRED_CURRENT.items():
        require_pair(current_text, key, value, CURRENT, errors)

    for forbidden in (
        "M13_BASE_CLOSEOUT_ACCEPTED=false",
        "M13_EXTENSION_G0_AUTHORIZED=true",
        "M13_EXTENSION_IMPLEMENTATION_AUTHORIZED=true",
        "M12_RUNTIME_G0=PASS",
        "M12_RUNTIME_G0=COMPLETE",
        "M12_C3_READY_TO_START=true",
        "A100_START_AUTHORIZED=true",
        "PUBLICATION_ALLOWED=true",
    ):
        if forbidden in current_text or forbidden in baseline_text or forbidden in matrix_text:
            errors.append(f"current projection contains forbidden state {forbidden}")

    matrix_current = matrix_text.split("## 3.", maxsplit=1)[0]
    for dimension in MATRIX_DIMENSIONS:
        if dimension not in matrix_current:
            errors.append(f"{MATRIX}: missing dimension {dimension}")
    for milestone in range(1, 20):
        rows = re.findall(rf"(?m)^\| M{milestone} \|", matrix_current)
        if len(rows) != 1:
            errors.append(f"{MATRIX}: expected one six-dimensional M{milestone} row, found {len(rows)}")

    for key, value in {
        "M12_RUNTIME_INSTALLED": "false",
        "M12_RUNTIME_G0": "NOT_COMPLETE",
        "M12_C3_READY_TO_START": "false",
        "M13_BASE_BACKEND": "COMPLETE",
        "M13_BASE_CLOSEOUT": "ACCEPTED",
        "M13_FRONTEND_PRODUCT_SURFACE": "INCOMPLETE",
        "M13_EXTENSION_CATALOG": "NOT_AUTHORIZED",
        "M13_PUBLICATION": "NOT_AUTHORIZED",
        "M13_PRODUCT_CAPABILITY_COMPLETE": "false",
        "A100_START_AUTHORIZED": "false",
    }.items():
        require_pair(matrix_text, key, value, MATRIX, errors)

    tag_match = re.search(r"(?m)^M13_BASE_TAG=(.+)$", baseline_text)
    object_match = re.search(r"(?m)^M13_BASE_TAG_OBJECT=([0-9a-f]{40})$", baseline_text)
    target_match = re.search(r"(?m)^M13_BASE_TAG_TARGET=([0-9a-f]{40})$", baseline_text)
    if not tag_match or not re.fullmatch(r"m13-base-backend-v1", tag_match.group(1)):
        errors.append(f"{BASELINE}: behavior tag name is invalid")
    if not object_match or not target_match:
        errors.append(f"{BASELINE}: tag object/target must be 40-hex values")

    if errors:
        print("Current-state validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)

    print(
        "Validated concise current state, immutable history SHA-256, "
        "M1-M19 dimensions, M12/M13 gates and frozen behavior tag fields."
    )


if __name__ == "__main__":
    main()
