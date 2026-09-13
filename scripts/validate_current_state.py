"""Validate concise current state, immutable history and M1-M19 truth fields."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import subprocess


CURRENT = Path("CURRENT_MILESTONE.md")
HISTORY = Path("CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md")
MATRIX = Path("docs/status/M1-M19-CAPABILITY-STATUS.md")
BASELINE = Path("docs/status/CROSS_REPOSITORY_BASELINE.md")
EXPECTED_HISTORY_SHA256 = "5e05b68e83ed55f90b342aee627001a7bbf66cf59f92e5106270175b07f61f6a"

REQUIRED_BASELINE_VALUES = {
    "M13_FROZEN_CORE_MAIN": "a455c8e76427d53d75bb7f15259b9875d9768914",
    "M13_FROZEN_CORE_TREE": "d92159d5c3c5d3896d1fe9e56b896413277fe4e8",
    "M13_BASE_TAG": "m13-base-backend-v1",
    "M13_BASE_TAG_OBJECT": "b2d086b622bdb5456f6af325e458aa3771e43e80",
    "M13_BASE_TAG_TARGET": "a455c8e76427d53d75bb7f15259b9875d9768914",
    "PRE_PIN_FRONTEND_MAIN": "a0be9edc91437bf0e7c5dd14883e656e750b3aee",
    "PRE_PIN_FRONTEND_TREE": "c25b9e3744d561c93fed26d0a07e59a1915a6071",
}
REQUIRED_CURRENT = {
    "M12_RUNTIME_INSTALLED": "false",
    "M12_RUNTIME_G0": "NOT_COMPLETE",
    "M12_G0_3_STATE": "DEDICATED_CPU_VM_SELECTION_HOLD",
    "M12_C3_READY_TO_START": "false",
    "M13_BASE_BACKEND": "COMPLETE",
    "M13_BASE_CLOSEOUT": "ACCEPTED",
    "M13_PRODUCT_CAPABILITY_COMPLETE": "false",
    "M13_EXTENSION_G0_AUTHORIZED": "false",
    "M13_EXTENSION_IMPLEMENTATION_AUTHORIZED": "false",
    "A100_START_AUTHORIZED": "false",
    "PUBLICATION_ALLOWED": "false",
}
REQUIRED_CI_GOVERNANCE = {
    "DOCUMENT_GOVERNANCE_VALIDATION": "IMPLEMENTED",
    "DOCS_ONLY_CI_FAST_PATH": "IMPLEMENTED",
    "REQUIRED_CHECK_CONTEXTS": "5_UNCHANGED",
    "PROTECTED_CHANGE_FULL_SUITE": "ENFORCED",
    "POST_MERGE_DUPLICATE_FULL_CI": "REMOVED",
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
    values = [line[len(key) + 1 :] for line in text.splitlines() if line.startswith(f"{key}=")]
    if values != [value]:
        errors.append(f"{path}: expected exactly one complete {key}={value} record; found {values!r}")


STATE_BEGIN = "<!-- CURRENT_STATE:BEGIN -->"
STATE_END = "<!-- CURRENT_STATE:END -->"


def validate_current_projection(text: str, errors: list[str]) -> str:
    """Only the explicit active block can satisfy current execution predicates."""
    if text.count(STATE_BEGIN) != 1 or text.count(STATE_END) != 1:
        errors.append(f"{CURRENT}: expected exactly one current-state block")
        return ""
    start, end = text.index(STATE_BEGIN), text.index(STATE_END)
    if start >= end:
        errors.append(f"{CURRENT}: current-state markers are reversed")
        return ""
    block = text[start + len(STATE_BEGIN) : end].strip()
    if not block.startswith("```text\n") or not block.endswith("\n```"):
        errors.append(f"{CURRENT}: current-state block must contain one text fence")
        return ""
    block = block[len("```text\n") : -len("\n```")]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if not line:
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=([^\s;`]+)", line)
        if not match:
            errors.append(f"{CURRENT}: invalid current-state record {line!r}")
            continue
        key, value = match.groups()
        if key in fields:
            errors.append(f"{CURRENT}: duplicate current-state key {key}")
        fields[key] = value
        if key.startswith("SUPERSEDED_VALIDATOR_"):
            errors.append(f"{CURRENT}: historical validator alias is not a current field")
    for key, value in {**REQUIRED_CURRENT, **REQUIRED_CI_GOVERNANCE}.items():
        require_pair(block, key, value, CURRENT, errors)
    # Next actions change with accepted progress; do not hard-code an obsolete host task.
    for key in ("CURRENT_TASK", "NEXT_TASK"):
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]*", fields.get(key, "")):
            errors.append(f"{CURRENT}: missing or invalid {key}")
    return block


def history_section(data: bytes) -> bytes:
    start = data.find(b"\n## 0A.")
    if start < 0:
        raise ValueError("historical section marker is missing")
    return data[start + 1 :]


def validate_history(path: Path, errors: list[str]) -> None:
    """Preserve Git evidence bytes without rewriting an autocrlf checkout."""
    try:
        section = history_section(path.read_bytes())
        if sha256(section).hexdigest() == EXPECTED_HISTORY_SHA256:
            return
        # Only accept the checkout conversion actually declared by this repository.
        # Arbitrary CRLF normalization would hide an unapproved evidence edit.
        ref = f"HEAD:{path.as_posix()}"
        committed = history_section(subprocess.check_output(["git", "cat-file", "blob", ref]))
        checkout = history_section(subprocess.check_output(["git", "cat-file", "--filters", ref]))
        if sha256(committed).hexdigest() == EXPECTED_HISTORY_SHA256 and section == checkout:
            return
        errors.append(f"{path}: historical content differs from the immutable Git evidence")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        errors.append(f"{path}: cannot verify historical evidence: {error}")


def main() -> None:
    errors: list[str] = []
    current_text = CURRENT.read_text(encoding="utf-8")
    matrix_text = MATRIX.read_text(encoding="utf-8")
    baseline_text = BASELINE.read_text(encoding="utf-8")

    if len(current_text.splitlines()) > 200:
        errors.append(f"{CURRENT}: must remain concise (maximum 200 lines)")
    if any(len(line) > 800 for line in current_text.splitlines()):
        errors.append(f"{CURRENT}: oversized execution-history paragraph (maximum 800 characters per line)")
    if re.search(r"(?m)^## 0A\.", current_text):
        errors.append(f"{CURRENT}: unarchived historical section 0A found")

    validate_history(HISTORY, errors)

    for key, value in REQUIRED_BASELINE_VALUES.items():
        require_pair(baseline_text, key, value, BASELINE, errors)
    current_block = validate_current_projection(current_text, errors)

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
        if any(forbidden in text.splitlines() for text in (current_block, baseline_text, matrix_text)):
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
