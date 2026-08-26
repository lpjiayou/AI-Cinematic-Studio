from pathlib import Path
import re
import subprocess

files = [
    Path(path)
    for path in subprocess.check_output(
        ["git", "ls-files", "--", "*.md"],
        text=True,
    ).splitlines()
]
errors: list[str] = []

if not files:
    errors.append("No tracked Markdown files were found.")

for path in files:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        errors.append(f"{path}: invalid UTF-8 ({error})")
        continue

    if not text.strip():
        errors.append(f"{path}: file is empty")
    if "\ufffd" in text:
        errors.append(f"{path}: contains the Unicode replacement character")
    if not re.search(r"(?m)^#\s+\S", text):
        errors.append(f"{path}: missing a level-one heading")

    open_fence: tuple[str, int, int] | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if not match:
            continue
        marker = match.group(1)
        if open_fence is None:
            open_fence = (marker[0], len(marker), line_number)
        elif marker[0] == open_fence[0] and len(marker) >= open_fence[1]:
            open_fence = None

    if open_fence is not None:
        errors.append(
            f"{path}:{open_fence[2]}: unclosed {open_fence[0] * open_fence[1]} fence"
        )

if errors:
    print("Markdown validation failed:")
    print("\n".join(f"- {error}" for error in errors))
    raise SystemExit(1)

print(f"Validated {len(files)} tracked Markdown files.")
