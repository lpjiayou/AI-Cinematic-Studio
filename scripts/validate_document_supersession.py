"""Validate supersession edges, historical isolation and index reachability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


REGISTRY = Path("docs/governance/DOCUMENT_REGISTRY.json")
INDEX = Path("docs/README.md")
AUTHORITY_MAP = Path("docs/governance/DOCUMENT_AUTHORITY_MAP.md")
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


def render_projections(records: list[dict]) -> tuple[str, str]:
    """Derive navigation only; the existing registry remains the single source."""
    paths = [record["path"] for record in records]
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate registry path")
    if any(record["documentClass"] not in CLASSES for record in records):
        raise ValueError("unknown registry class")
    groups = {
        cls: sorted((r for r in records if r["documentClass"] == cls), key=lambda r: r["path"])
        for cls in CLASSES
    }
    index: list[str] = []
    authority = [
        "## Classification totals", "",
        "| Class | Count | Current-state claims allowed |",
        "| --- | ---: | --- |",
    ]
    for cls, group in groups.items():
        allowed = "yes" if cls in {"CURRENT_STATUS", "CAPABILITY_MATRIX"} else "no"
        authority.append(f"| `{cls}` | {len(group)} | {allowed} |")
    authority.append("")
    for cls, group in groups.items():
        index.extend([f"## {cls}", ""])
        authority.extend([f"## {cls}", ""])
        if not group:
            index.extend(["No documents registered in this class.", ""])
            authority.extend(["No documents registered in this class.", ""])
            continue
        authority.extend(["| Document | Status | Owner |", "| --- | --- | --- |"])
        for record in group:
            path, status, owner = record["path"], record["status"], record["owner"]
            # relpath is computed structurally; generated Markdown stays portable on Windows.
            relative = path[5:] if path.startswith("docs/") else f"../{path}"
            index.append(f"- [`{path}`]({relative}) — `{status}`")
            authority.append(f"| [`{path}`](../../{path}) | `{status}` | {owner} |")
        index.append("")
        authority.append("")
    return "\n".join(index), "\n".join(authority)


def replace_projection(text: str, heading: str, generated: str) -> str:
    matches = list(re.finditer(rf"(?m)^{re.escape(heading)}$", text))
    if len(matches) != 1:
        raise ValueError(f"expected one projection heading: {heading}")
    return text[: matches[0].start()] + generated


def check_projection(text: str, heading: str, generated: str, path: Path) -> str | None:
    if text != replace_projection(text, heading, generated):
        return f"{path}: registry projection drift; regenerate with --write"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the two existing navigation projections only")
    args = parser.parse_args()
    errors: list[str] = []
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    records = payload["documents"]
    by_path = {record["path"]: record for record in records}
    index_text = INDEX.read_text(encoding="utf-8")
    authority_text = AUTHORITY_MAP.read_text(encoding="utf-8")
    try:
        generated_index, generated_map = render_projections(records)
        projected_index = replace_projection(index_text, "## ACCEPTED_DECISION", generated_index)
        projected_map = replace_projection(authority_text, "## Classification totals", generated_map)
    except (KeyError, ValueError) as error:
        raise SystemExit(f"Invalid registry projection: {error}") from error
    if not args.write:
        for text, heading, generated, path in (
            (index_text, "## ACCEPTED_DECISION", generated_index, INDEX),
            (authority_text, "## Classification totals", generated_map, AUTHORITY_MAP),
        ):
            error = check_projection(text, heading, generated, path)
            if error:
                errors.append(error)
    else:
        # Validate graph/reachability before either controlled output is written.
        index_text = projected_index
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

    if args.write:
        INDEX.write_text(projected_index, encoding="utf-8", newline="\n")
        AUTHORITY_MAP.write_text(projected_map, encoding="utf-8", newline="\n")

    print(
        f"Validated {len(records)} indexed documents, {len(graph)} superseded records, "
        "zero orphans, zero unclassified supersession relationships and exact registry projections."
    )


if __name__ == "__main__":
    main()
