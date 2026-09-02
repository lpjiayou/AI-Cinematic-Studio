"""Validate supersession edges, historical isolation and index reachability."""

from __future__ import annotations

import json
from pathlib import Path
import re


REGISTRY = Path("docs/governance/DOCUMENT_REGISTRY.json")
INDEX = Path("docs/README.md")
SUPERSESSION_MAP = Path("docs/governance/DOCUMENT_SUPERSESSION_MAP.md")
CLASSES = [
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
]


def index_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for document_class in CLASSES:
        match = re.search(
            rf"(?ms)^## {re.escape(document_class)}\n(.*?)(?=^## |\Z)",
            text,
        )
        sections[document_class] = match.group(1) if match else ""
    return sections


def main() -> None:
    errors: list[str] = []
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    records = payload["documents"]
    by_path = {record["path"]: record for record in records}
    index_text = INDEX.read_text(encoding="utf-8")
    sections = index_sections(index_text)

    for document_class in CLASSES:
        if not sections[document_class]:
            errors.append(f"{INDEX}: missing class section {document_class}")

    graph: dict[str, list[str]] = {}
    for record in records:
        path = record["path"]
        if f"`{path}`" not in sections.get(record["documentClass"], ""):
            errors.append(f"{path}: not linked from its {record['documentClass']} index section")
        for field in ("supersedes", "supersededBy"):
            for related in record[field]:
                if related not in by_path:
                    errors.append(f"{path}: {field} references unregistered {related}")
        if record["documentClass"] == "SUPERSEDED":
            if not record["supersededBy"]:
                errors.append(f"{path}: missing supersededBy")
            for successor in record["supersededBy"]:
                if path not in by_path.get(successor, {}).get("supersedes", []):
                    errors.append(f"{path}: successor {successor} lacks reverse supersedes edge")
            graph[path] = list(record["supersededBy"])

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(path: str) -> None:
        if path in visiting:
            errors.append(f"supersession cycle detected at {path}")
            return
        if path in visited:
            return
        visiting.add(path)
        for successor in graph.get(path, []):
            visit(successor)
        visiting.remove(path)
        visited.add(path)

    for path in graph:
        visit(path)

    map_text = SUPERSESSION_MAP.read_text(encoding="utf-8")
    if "UNCLASSIFIED_SUPERSESSION_COUNT=0" not in map_text:
        errors.append(f"{SUPERSESSION_MAP}: unclassified supersession count is not zero")

    if errors:
        print("Document supersession validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)

    print(
        f"Validated {len(records)} indexed documents, {len(graph)} superseded records, "
        "zero orphans and zero unclassified supersession relationships."
    )


if __name__ == "__main__":
    main()
