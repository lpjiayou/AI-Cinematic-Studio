"""Validate tracked local Markdown targets and heading anchors."""

from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
from urllib.parse import unquote, urlsplit


tracked_files = set(
    subprocess.check_output(["git", "ls-files"], text=True).splitlines()
)
tracked_targets = set(tracked_files)
for tracked_file in tracked_files:
    parent = PurePosixPath(tracked_file).parent
    while parent.as_posix() != ".":
        tracked_targets.add(parent.as_posix())
        parent = parent.parent

files = [Path(path) for path in sorted(tracked_files) if path.endswith(".md")]
inline_link = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
reference_link = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)")
fence = re.compile(r"^ {0,3}(`{3,}|~{3,})")
heading = re.compile(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$")
explicit_anchor = re.compile(r"<(?:a|span)\s+(?:[^>]*\s)?(?:id|name)=[\"']([^\"']+)[\"']", re.I)
errors: list[str] = []
checked = 0
checked_anchors = 0


def github_slug(value: str) -> str:
    value = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("`", "").replace("*", "").replace("_", "")
    value = value.lower().strip()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s", "-", value)


def anchors_for(path: Path) -> set[str]:
    anchors: set[str] = set()
    slug_counts: dict[str, int] = {}
    in_fence: tuple[str, int] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        fence_match = fence.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if in_fence is None:
                in_fence = (marker[0], len(marker))
            elif marker[0] == in_fence[0] and len(marker) >= in_fence[1]:
                in_fence = None
            continue
        if in_fence is not None:
            continue
        for anchor in explicit_anchor.findall(line):
            anchors.add(unquote(anchor))
        match = heading.match(line)
        if not match:
            continue
        base = github_slug(match.group(1))
        occurrence = slug_counts.get(base, 0)
        slug_counts[base] = occurrence + 1
        anchors.add(base if occurrence == 0 else f"{base}-{occurrence}")
    return anchors


anchor_index = {path.as_posix(): anchors_for(path) for path in files}

for source in files:
    in_fence: tuple[str, int] | None = None
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(), start=1
    ):
        fence_match = fence.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if in_fence is None:
                in_fence = (marker[0], len(marker))
            elif marker[0] == in_fence[0] and len(marker) >= in_fence[1]:
                in_fence = None
            continue
        if in_fence is not None:
            continue

        targets = inline_link.findall(line)
        reference_match = reference_link.match(line)
        if reference_match:
            targets.append(reference_match.group(1))

        for raw_target in targets:
            target = raw_target.strip()
            if target.startswith("<") and ">" in target:
                target = target[1 : target.index(">")]
            else:
                target = target.split(maxsplit=1)[0]

            parsed = urlsplit(target)
            if parsed.scheme:
                continue
            if not parsed.path and not parsed.fragment:
                continue

            decoded_path = unquote(parsed.path).replace("\\", "/")
            source_parent = PurePosixPath(source.as_posix()).parent.as_posix()
            if not decoded_path:
                destination = source.as_posix()
            elif decoded_path.startswith("/"):
                destination = posixpath.normpath(decoded_path.lstrip("/"))
            else:
                destination = posixpath.normpath(posixpath.join(source_parent, decoded_path))

            if destination == ".." or destination.startswith("../"):
                errors.append(
                    f"{source}:{line_number}: local target escapes the repository {target!r}"
                )
                continue

            checked += 1
            if destination not in tracked_targets:
                errors.append(
                    f"{source}:{line_number}: missing tracked local target {target!r}"
                )
                continue

            if parsed.fragment and destination.endswith(".md"):
                checked_anchors += 1
                fragment = unquote(parsed.fragment)
                if fragment not in anchor_index.get(destination, set()):
                    errors.append(
                        f"{source}:{line_number}: missing Markdown anchor "
                        f"{fragment!r} in {destination!r}"
                    )

if errors:
    print("Documentation link validation failed:")
    print("\n".join(f"- {error}" for error in errors))
    raise SystemExit(1)

print(
    f"Validated {checked} local documentation links and {checked_anchors} anchors "
    f"across {len(files)} files."
)
