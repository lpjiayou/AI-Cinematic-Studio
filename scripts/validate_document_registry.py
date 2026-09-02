"""Validate complete, single-class documentation registry coverage."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


REGISTRY_PATH = Path("docs/governance/DOCUMENT_REGISTRY.json")
ALLOWED_CLASSES = {
    "ACCEPTED_DECISION",
    "NORMATIVE_ARCHITECTURE",
    "NORMATIVE_CONTRACT",
    "CURRENT_STATUS",
    "CAPABILITY_MATRIX",
    "OPERATIONAL_RUNBOOK",
    "IMPLEMENTATION_EVIDENCE",
    "HISTORICAL_EVIDENCE",
    "SUPERSEDED",
    "DRAFT",
    "DEPRECATED",
    "GENERATED_REFERENCE",
}
REQUIRED_FIELDS = {
    "path",
    "repository",
    "documentClass",
    "status",
    "owner",
    "authoritativeFor",
    "supersedes",
    "supersededBy",
    "currentStateClaimsAllowed",
    "historicalMutationPolicy",
    "lastReviewedBaseline",
    "lastReviewedAt",
    "linkedFromIndex",
    "notes",
}
HISTORICAL_CLASSES = {
    "IMPLEMENTATION_EVIDENCE",
    "HISTORICAL_EVIDENCE",
    "SUPERSEDED",
}
BANNED_CURRENT_PATHS = {
    "sandbox:/workspace",
    "/workspace/scratch",
    "/mnt/c",
    "C:\\Users\\",
}


def tracked_paths() -> set[str]:
    return set(
        subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    )


def governed_paths(tracked: set[str]) -> set[str]:
    governed: set[str] = set()
    for path in tracked:
        name = Path(path).name.lower()
        if path.endswith((".md", ".mdx", ".rst")):
            governed.add(path)
        elif path == "tests/fixtures/v5_fonts/OFL.txt":
            governed.add(path)
        elif path == REGISTRY_PATH.as_posix():
            governed.add(path)
        elif path.endswith((".json", ".yaml", ".yml")) and "manifest" in name:
            governed.add(path)
    return governed


def load_registry() -> dict[str, object]:
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot load {REGISTRY_PATH}: {error}") from error


def main() -> None:
    errors: list[str] = []
    tracked = tracked_paths()
    expected = governed_paths(tracked)
    registry = load_registry()
    records = registry.get("documents")
    if not isinstance(records, list):
        raise SystemExit("DOCUMENT_REGISTRY.json: documents must be an array")

    seen: set[str] = set()
    registered: set[str] = set()
    for index, record in enumerate(records):
        label = f"documents[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label}: record must be an object")
            continue
        missing = sorted(REQUIRED_FIELDS - set(record))
        if missing:
            errors.append(f"{label}: missing fields {missing}")
            continue

        path = record["path"]
        if not isinstance(path, str) or not path:
            errors.append(f"{label}: path must be a non-empty string")
            continue
        registered.add(path)
        if path in seen:
            errors.append(f"{path}: duplicate registry record")
        seen.add(path)
        if path not in tracked:
            errors.append(f"{path}: registry target is not tracked")

        document_class = record["documentClass"]
        if not isinstance(document_class, str) or document_class not in ALLOWED_CLASSES:
            errors.append(f"{path}: invalid documentClass {document_class!r}")
        if document_class == "UNKNOWN":
            errors.append(f"{path}: DOCUMENT_CLASS=UNKNOWN is forbidden")
        if record["repository"] != "Core":
            errors.append(f"{path}: repository must be 'Core'")
        for field in ("status", "owner", "historicalMutationPolicy", "notes"):
            if not isinstance(record[field], str) or not record[field].strip():
                errors.append(f"{path}: {field} must be a non-empty string")
        for field in ("authoritativeFor", "supersedes", "supersededBy"):
            value = record[field]
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                errors.append(f"{path}: {field} must be an array of strings")
        for field in ("currentStateClaimsAllowed", "linkedFromIndex"):
            if not isinstance(record[field], bool):
                errors.append(f"{path}: {field} must be boolean")
        if record["linkedFromIndex"] is not True:
            errors.append(f"{path}: linkedFromIndex must be true")
        if not re.fullmatch(r"[0-9a-f]{40}", str(record["lastReviewedBaseline"])):
            errors.append(f"{path}: lastReviewedBaseline must be a 40-hex commit")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(record["lastReviewedAt"])):
            errors.append(f"{path}: lastReviewedAt must be YYYY-MM-DD")

        if document_class in HISTORICAL_CLASSES:
            if "HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true" not in str(record["notes"]):
                errors.append(f"{path}: historical/evidence note lacks path-authority guard")
            if record["currentStateClaimsAllowed"] is not False:
                errors.append(f"{path}: historical/evidence document cannot make current claims")
        if document_class in {"CURRENT_STATUS", "CAPABILITY_MATRIX"}:
            if record["currentStateClaimsAllowed"] is not True:
                errors.append(f"{path}: current projection must allow evidence-backed current claims")
            try:
                text = Path(path).read_text(encoding="utf-8")
            except OSError as error:
                errors.append(f"{path}: cannot read current document ({error})")
            else:
                for banned in BANNED_CURRENT_PATHS:
                    if banned in text:
                        errors.append(f"{path}: current document contains banned path {banned!r}")
        elif record["currentStateClaimsAllowed"] is not False:
            errors.append(f"{path}: only CURRENT_STATUS/CAPABILITY_MATRIX may allow current claims")
        if document_class == "SUPERSEDED" and not record["supersededBy"]:
            errors.append(f"{path}: SUPERSEDED document must name supersededBy")

    missing_records = sorted(expected - registered)
    extra_records = sorted(registered - expected)
    if missing_records:
        errors.append(f"unregistered governed documents: {missing_records}")
    if extra_records:
        errors.append(f"registered paths outside governed inventory: {extra_records}")

    if errors:
        print("Document registry validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)

    print(f"Validated registry coverage for {len(expected)} governed documents; UNKNOWN=0.")


if __name__ == "__main__":
    main()
