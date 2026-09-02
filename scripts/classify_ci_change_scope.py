"""Classify a Git commit range as DOCS_ONLY or FULL_SUITE, fail closed."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fnmatch import fnmatchcase
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Callable, Sequence


SCHEMA_VERSION = 1
DOCS_ONLY = "DOCS_ONLY"
FULL_SUITE = "FULL_SUITE"
ALLOWED_EVENTS = {"pull_request", "workflow_dispatch"}
HEX_SHA = re.compile(r"[0-9a-f]{40}")

ROOT_DOCUMENTS = {
    "AGENTS.md",
    "CURRENT_MILESTONE.md",
    "README.md",
    "AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md",
    "AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md",
}
DOC_PREFIXES = ("docs/", "governance/", "architecture/")
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".json", ".yaml", ".yml"}
PROTECTED_PREFIXES = (
    "services/",
    "apps/",
    "tests/",
    "experiments/",
    "scripts/",
    ".github/workflows/",
    ".github/actions/",
    "backend/",
    "frontend/",
    "migrations/",
    "schemas/",
    "runtime/",
    "models/",
)
DEPENDENCY_EXACT_NAMES = {
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "pipfile",
    "pipfile.lock",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "go.mod",
    "go.sum",
}
VALID_STATUS_CODES = {"A", "M", "D", "R", "C", "T"}
REGULAR_MODES = {"000000", "100644", "100755"}


@dataclass(frozen=True)
class ChangedFile:
    """One name-status entry plus its Git modes."""

    status: str
    old_path: str | None
    new_path: str | None
    old_mode: str | None = None
    new_mode: str | None = None

    @property
    def status_code(self) -> str:
        return self.status[:1]

    @property
    def paths(self) -> tuple[str, ...]:
        values: list[str] = []
        for path in (self.old_path, self.new_path):
            if path is not None and path not in values:
                values.append(path)
        return tuple(values)

    def as_json(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "oldPath": self.old_path,
            "newPath": self.new_path,
            "oldMode": self.old_mode,
            "newMode": self.new_mode,
        }


@dataclass(frozen=True)
class ClassificationOutcome:
    payload: dict[str, object]
    failed: bool = False


DiffReader = Callable[[Path, str, str], list[ChangedFile]]


def _safe_relative_path(path: str) -> bool:
    if not path or "\\" in path or path.startswith("/"):
        return False
    parts = PurePosixPath(path).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _is_dependency_or_runtime_file(path: str) -> bool:
    name = PurePosixPath(path).name
    lowered = name.lower()
    if lowered in DEPENDENCY_EXACT_NAMES:
        return True
    if fnmatchcase(lowered, "requirements*.txt"):
        return True
    if fnmatchcase(lowered, "constraints*.txt"):
        return True
    if lowered.startswith("dockerfile"):
        return True
    if lowered.startswith("docker-compose"):
        return True
    if fnmatchcase(lowered, "compose*.yml") or fnmatchcase(lowered, "compose*.yaml"):
        return True
    if lowered.endswith(".lock") or lowered.endswith("-lock.json"):
        return True
    return False


def path_class(path: str) -> tuple[str, str]:
    """Return DOCS, PROTECTED or UNKNOWN plus a stable reason."""

    if not _safe_relative_path(path):
        return "UNKNOWN", "UNSAFE_OR_NON_RELATIVE_PATH"
    if _is_dependency_or_runtime_file(path):
        return "PROTECTED", "DEPENDENCY_OR_RUNTIME_FILE"
    for prefix in PROTECTED_PREFIXES:
        if path.startswith(prefix):
            return "PROTECTED", f"PROTECTED_PREFIX:{prefix}"

    if path in ROOT_DOCUMENTS:
        return "DOCS", "ROOT_DOCUMENT"
    if fnmatchcase(path, "README-*.md") and "/" not in path:
        return "DOCS", "ROOT_README_VARIANT"
    if path == ".github/PULL_REQUEST_TEMPLATE.md":
        return "DOCS", "GITHUB_DOCUMENT_TEMPLATE"
    if path == ".github/pull_request_template.md":
        return "DOCS", "GITHUB_DOCUMENT_TEMPLATE_EQUIVALENT"
    if path.startswith(".github/PULL_REQUEST_TEMPLATE/"):
        return (
            ("DOCS", "GITHUB_DOCUMENT_TEMPLATE_DIRECTORY")
            if PurePosixPath(path).suffix in DOC_SUFFIXES
            else ("UNKNOWN", "UNAPPROVED_DOCUMENT_SUFFIX")
        )
    if PurePosixPath(path).parent.as_posix() == ".github/ISSUE_TEMPLATE":
        return (
            ("DOCS", "GITHUB_ISSUE_TEMPLATE")
            if PurePosixPath(path).suffix == ".md"
            else ("UNKNOWN", "UNAPPROVED_DOCUMENT_SUFFIX")
        )
    if path.startswith(DOC_PREFIXES):
        return (
            ("DOCS", "DOCUMENT_DIRECTORY_AND_SUFFIX")
            if PurePosixPath(path).suffix in DOC_SUFFIXES
            else ("UNKNOWN", "UNAPPROVED_DOCUMENT_SUFFIX")
        )
    return "UNKNOWN", "PATH_OUTSIDE_CLOSED_ALLOWLIST"


def payload_digest(payload: dict[str, object]) -> str:
    content = dict(payload)
    content.pop("payloadDigest", None)
    encoded = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _payload(
    *,
    event_name: str,
    base_sha: str,
    head_sha: str,
    classification: str,
    changed_files: Sequence[ChangedFile],
    protected_matches: Sequence[str],
    unknown_matches: Sequence[str],
    reason: str,
) -> dict[str, object]:
    ordered_changes = sorted(
        (change.as_json() for change in changed_files),
        key=lambda item: (
            str(item["oldPath"] or ""),
            str(item["newPath"] or ""),
            str(item["status"]),
        ),
    )
    result: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "eventName": event_name,
        "baseSha": base_sha,
        "headSha": head_sha,
        "classification": classification,
        "changedFiles": ordered_changes,
        "protectedMatches": sorted(set(protected_matches)),
        "unknownMatches": sorted(set(unknown_matches)),
        "classificationReason": reason,
    }
    result["payloadDigest"] = payload_digest(result)
    return result


def classify_records(
    event_name: str,
    base_sha: str,
    head_sha: str,
    changed_files: Sequence[ChangedFile],
) -> ClassificationOutcome:
    """Classify already-parsed changes. Inputs must be commit SHAs."""

    if event_name == "workflow_dispatch":
        return ClassificationOutcome(
            _payload(
                event_name=event_name,
                base_sha=base_sha,
                head_sha=head_sha,
                classification=FULL_SUITE,
                changed_files=changed_files,
                protected_matches=["<event:workflow_dispatch>"],
                unknown_matches=[],
                reason="WORKFLOW_DISPATCH_ALWAYS_FULL_SUITE",
            )
        )
    if event_name != "pull_request":
        return ClassificationOutcome(
            _payload(
                event_name=event_name,
                base_sha=base_sha,
                head_sha=head_sha,
                classification=FULL_SUITE,
                changed_files=changed_files,
                protected_matches=[f"<event:{event_name}>"],
                unknown_matches=[],
                reason="UNSUPPORTED_EVENT_FAIL_CLOSED",
            ),
            failed=True,
        )
    if not changed_files:
        return ClassificationOutcome(
            _payload(
                event_name=event_name,
                base_sha=base_sha,
                head_sha=head_sha,
                classification=FULL_SUITE,
                changed_files=[],
                protected_matches=["<empty-diff>"],
                unknown_matches=[],
                reason="EMPTY_DIFF_FULL_SUITE",
            )
        )

    docs_paths: set[str] = set()
    protected_matches: set[str] = set()
    unknown_matches: set[str] = set()
    mode_or_type_change = False

    for change in changed_files:
        if change.status_code not in VALID_STATUS_CODES:
            unknown_matches.add(f"<status:{change.status}>")
        if change.status_code == "T":
            mode_or_type_change = True
            protected_matches.add(f"<type-change:{','.join(change.paths)}>")

        modes = tuple(mode for mode in (change.old_mode, change.new_mode) if mode)
        if any(mode not in REGULAR_MODES for mode in modes):
            mode_or_type_change = True
            protected_matches.add(f"<non-regular-mode:{','.join(change.paths)}>")
        if (
            change.old_mode not in {None, "000000"}
            and change.new_mode not in {None, "000000"}
            and change.old_mode != change.new_mode
        ):
            mode_or_type_change = True
            protected_matches.add(f"<mode-change:{','.join(change.paths)}>")

        for path in change.paths:
            classification, reason = path_class(path)
            if classification == "DOCS":
                docs_paths.add(path)
            elif classification == "PROTECTED":
                protected_matches.add(f"{path} [{reason}]")
            else:
                unknown_matches.add(f"{path} [{reason}]")

    if protected_matches or unknown_matches:
        if docs_paths:
            reason = "MIXED_CHANGE_FULL_SUITE"
        elif mode_or_type_change:
            reason = "TYPE_OR_MODE_CHANGE_FULL_SUITE"
        elif protected_matches:
            reason = "PROTECTED_CHANGE_FULL_SUITE"
        else:
            reason = "UNKNOWN_CHANGE_FULL_SUITE"
        return ClassificationOutcome(
            _payload(
                event_name=event_name,
                base_sha=base_sha,
                head_sha=head_sha,
                classification=FULL_SUITE,
                changed_files=changed_files,
                protected_matches=sorted(protected_matches),
                unknown_matches=sorted(unknown_matches),
                reason=reason,
            )
        )

    return ClassificationOutcome(
        _payload(
            event_name=event_name,
            base_sha=base_sha,
            head_sha=head_sha,
            classification=DOCS_ONLY,
            changed_files=changed_files,
            protected_matches=[],
            unknown_matches=[],
            reason="DOCS_ONLY_ALLOWLIST_PROVEN",
        )
    )


def _decode_path(value: bytes) -> str:
    path = value.decode("utf-8")
    if not _safe_relative_path(path):
        return path
    return path


def _nul_tokens(data: bytes) -> list[bytes]:
    tokens = data.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    return tokens


def _parse_name_status(data: bytes) -> list[tuple[str, str | None, str | None]]:
    tokens = _nul_tokens(data)
    records: list[tuple[str, str | None, str | None]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii")
        index += 1
        code = status[:1]
        if code in {"R", "C"}:
            if index + 1 >= len(tokens):
                raise ValueError("truncated rename/copy name-status record")
            old_path = _decode_path(tokens[index])
            new_path = _decode_path(tokens[index + 1])
            index += 2
        else:
            if index >= len(tokens):
                raise ValueError("truncated name-status record")
            path = _decode_path(tokens[index])
            index += 1
            old_path = path if code != "A" else None
            new_path = path if code != "D" else None
        records.append((status, old_path, new_path))
    return records


def _parse_raw_modes(
    data: bytes,
) -> dict[tuple[str, str | None, str | None], tuple[str, str]]:
    tokens = _nul_tokens(data)
    modes: dict[tuple[str, str | None, str | None], tuple[str, str]] = {}
    index = 0
    while index < len(tokens):
        header = tokens[index].decode("ascii")
        index += 1
        fields = header.split()
        if len(fields) != 5 or not fields[0].startswith(":"):
            raise ValueError(f"invalid raw diff header {header!r}")
        old_mode = fields[0][1:]
        new_mode = fields[1]
        status = fields[4]
        code = status[:1]
        if code in {"R", "C"}:
            if index + 1 >= len(tokens):
                raise ValueError("truncated rename/copy raw record")
            old_path = _decode_path(tokens[index])
            new_path = _decode_path(tokens[index + 1])
            index += 2
        else:
            if index >= len(tokens):
                raise ValueError("truncated raw record")
            path = _decode_path(tokens[index])
            index += 1
            old_path = path if code != "A" else None
            new_path = path if code != "D" else None
        modes[(status, old_path, new_path)] = (old_mode, new_mode)
    return modes


def read_git_diff(repo_root: Path, base_sha: str, head_sha: str) -> list[ChangedFile]:
    """Read name/status and modes without placing repository paths in the payload."""

    common = ["-M", "-C", base_sha, head_sha, "--"]
    name_status = subprocess.run(
        ["git", "diff", "--name-status", "-z", *common],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout
    raw = subprocess.run(
        ["git", "diff", "--raw", "-z", *common],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout
    names = _parse_name_status(name_status)
    raw_modes = _parse_raw_modes(raw)
    records: list[ChangedFile] = []
    for key in names:
        if key not in raw_modes:
            raise ValueError(f"raw diff has no matching mode record for {key!r}")
        old_mode, new_mode = raw_modes[key]
        records.append(
            ChangedFile(
                status=key[0],
                old_path=key[1],
                new_path=key[2],
                old_mode=old_mode,
                new_mode=new_mode,
            )
        )
    return records


def classify_repository_change(
    *,
    repo_root: Path,
    event_name: str,
    base_sha: str,
    head_sha: str,
    diff_reader: DiffReader = read_git_diff,
) -> ClassificationOutcome:
    if event_name not in ALLOWED_EVENTS:
        return classify_records(event_name, base_sha, head_sha, [])
    if not HEX_SHA.fullmatch(base_sha) or not HEX_SHA.fullmatch(head_sha):
        return ClassificationOutcome(
            _payload(
                event_name=event_name,
                base_sha=base_sha,
                head_sha=head_sha,
                classification=FULL_SUITE,
                changed_files=[],
                protected_matches=["<missing-or-invalid-base-head>"],
                unknown_matches=[],
                reason="MISSING_OR_INVALID_BASE_HEAD_FAIL_CLOSED",
            ),
            failed=True,
        )
    if event_name == "workflow_dispatch":
        return classify_records(event_name, base_sha, head_sha, [])
    try:
        changes = diff_reader(repo_root, base_sha, head_sha)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return ClassificationOutcome(
            _payload(
                event_name=event_name,
                base_sha=base_sha,
                head_sha=head_sha,
                classification=FULL_SUITE,
                changed_files=[],
                protected_matches=["<git-diff-failure>"],
                unknown_matches=[],
                reason="GIT_DIFF_FAILED_FAIL_CLOSED",
            ),
            failed=True,
        )
    return classify_records(event_name, base_sha, head_sha, changes)


def verify_payload(payload: dict[str, object]) -> None:
    required = {
        "schemaVersion",
        "eventName",
        "baseSha",
        "headSha",
        "classification",
        "changedFiles",
        "protectedMatches",
        "unknownMatches",
        "classificationReason",
        "payloadDigest",
    }
    if set(payload) != required:
        raise ValueError("classification payload fields are not the closed schema")
    if payload["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("unsupported classification schemaVersion")
    if payload["classification"] not in {DOCS_ONLY, FULL_SUITE}:
        raise ValueError("invalid CI scope classification")
    if payload["payloadDigest"] != payload_digest(payload):
        raise ValueError("classification payload digest mismatch")


def write_payload(path: Path, payload: dict[str, object]) -> None:
    verify_payload(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--output", type=Path, default=Path("CI_CHANGE_SCOPE.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcome = classify_repository_change(
        repo_root=Path.cwd(),
        event_name=args.event_name,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
    )
    write_payload(args.output, outcome.payload)
    print(f"CI_SCOPE={outcome.payload['classification']}")
    print(f"CI_SCOPE_REASON={outcome.payload['classificationReason']}")
    print(f"CI_SCOPE_PAYLOAD_DIGEST={outcome.payload['payloadDigest']}")
    if outcome.failed:
        print("CI_SCOPE_CONSISTENCY=FAIL")
        raise SystemExit(2)
    print("CI_SCOPE_CONSISTENCY=PASS")


if __name__ == "__main__":
    main()
