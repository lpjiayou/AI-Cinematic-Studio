from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
from urllib.parse import unquote, urlsplit

tracked_files = set(
    subprocess.check_output(
        ["git", "ls-files"],
        text=True,
    ).splitlines()
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
errors: list[str] = []
checked = 0

for source in files:
    in_fence: tuple[str, int] | None = None
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
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
            if not parsed.path or parsed.scheme:
                continue

            decoded_path = unquote(parsed.path).replace("\\", "/")
            source_parent = PurePosixPath(source.as_posix()).parent.as_posix()
            if decoded_path.startswith("/"):
                destination = posixpath.normpath(decoded_path.lstrip("/"))
            else:
                destination = posixpath.normpath(
                    posixpath.join(source_parent, decoded_path)
                )

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

if errors:
    print("Documentation link validation failed:")
    print("\n".join(f"- {error}" for error in errors))
    raise SystemExit(1)

print(f"Validated {checked} local documentation links across {len(files)} files.")
