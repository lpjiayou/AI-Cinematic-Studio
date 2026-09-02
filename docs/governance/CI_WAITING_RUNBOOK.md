# CI Waiting Runbook

Status: `ACTIVE / FAIL-CLOSED`

Owner: `Repository Governance Owner / CI Governance Owner`

Authorized by:
`ACS-UPSTREAM-CLOSEOUT-AGENTS-CI-WAITING-AND-INTEGRATION-SHARDING`

## 1. Purpose

This runbook defines the single-call waiter for the five protected Core checks. It
does not start or rerun a workflow. It observes one exact PR head commit and emits
nothing until a terminal result is known.

The only terminal results are:

```text
PASS
FAIL
TIMEOUT
API_ERROR
```

## 2. Preconditions

Resolve and freeze before starting the waiter:

- repository in `owner/name` form;
- the exact PR head commit SHA and tree;
- `CI_SCOPE=DOCS_ONLY|FULL_SUITE`;
- an already configured GitHub token with read access to checks;
- confirmation that no waiter has already been started for this head tree.

Do not install `gh`, open a cloud browser, trigger `workflow_dispatch`, rerun a
workflow or move the PR branch while the waiter is active.

## 3. Required contexts

Only these exact names count:

```text
Markdown
Documentation Links
Unit Tests
Contract Tests
Integration Tests
```

Unrelated workflows, jobs, statuses and empty check suites are ignored. When the
current commit contains duplicate check runs with the same required name, select the
run with the greatest numeric check-run `id`.

## 4. Standard-library REST waiter

The following reference uses only the Python standard library. Run it once inside one
blocking tool call. Pass `DOCS_ONLY` for a 10-minute deadline or `FULL_SUITE` for a
60-minute deadline. It prints exactly one JSON result at termination and never prints
polling progress.

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REQUIRED = (
    "Markdown",
    "Documentation Links",
    "Unit Tests",
    "Contract Tests",
    "Integration Tests",
)
DEADLINE_SECONDS = {"DOCS_ONLY": 600, "FULL_SUITE": 3600}
POLL_SECONDS = 15
API_VERSION = "2022-11-28"


def terminal(result: str, *, sha: str, checks: dict[str, dict] | None = None,
             detail: str | None = None) -> int:
    payload: dict[str, object] = {"result": result, "headSha": sha}
    if checks is not None:
        payload["requiredChecks"] = {
            name: {
                "id": checks[name]["id"],
                "status": checks[name]["status"],
                "conclusion": checks[name].get("conclusion"),
            }
            for name in REQUIRED
            if name in checks
        }
    if detail is not None:
        payload["detail"] = detail
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return {"PASS": 0, "FAIL": 1, "TIMEOUT": 2, "API_ERROR": 3}[result]


def api_page(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "acs-ci-waiter",
        },
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status}")
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("check_runs"), list):
        raise ValueError("malformed check-runs response")
    return payload


def current_check_runs(repository: str, sha: str, token: str) -> list[dict]:
    owner, name = repository.split("/", 1)
    base = (
        "https://api.github.com/repos/"
        f"{quote(owner, safe='')}/{quote(name, safe='')}/commits/"
        f"{quote(sha, safe='')}/check-runs"
    )
    runs: list[dict] = []
    page = 1
    while True:
        payload = api_page(f"{base}?filter=all&per_page=100&page={page}", token)
        batch = payload["check_runs"]
        runs.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return runs
        page += 1


def newest_required(runs: list[dict]) -> dict[str, dict]:
    selected: dict[str, dict] = {}
    for run in runs:
        name = run.get("name")
        run_id = run.get("id")
        if name not in REQUIRED or not isinstance(run_id, int):
            continue
        previous = selected.get(name)
        if previous is None or run_id > previous["id"]:
            selected[name] = run
    return selected


def main() -> int:
    if len(sys.argv) != 4:
        return terminal(
            "API_ERROR",
            sha="UNKNOWN",
            detail="usage: waiter.py OWNER/REPO HEAD_SHA DOCS_ONLY|FULL_SUITE",
        )
    repository, sha, scope = sys.argv[1:]
    token = os.environ.get("GITHUB_TOKEN", "")
    if (
        repository.count("/") != 1
        or len(sha) != 40
        or any(ch not in "0123456789abcdef" for ch in sha)
        or scope not in DEADLINE_SECONDS
        or not token
    ):
        return terminal("API_ERROR", sha=sha, detail="invalid or missing input")

    deadline = time.monotonic() + DEADLINE_SECONDS[scope]
    while True:
        try:
            selected = newest_required(current_check_runs(repository, sha, token))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
            return terminal(
                "API_ERROR",
                sha=sha,
                detail=f"{type(error).__name__}: {error}",
            )

        failed = {
            name: run
            for name, run in selected.items()
            if run.get("status") == "completed"
            and run.get("conclusion") != "success"
        }
        if failed:
            return terminal(
                "FAIL",
                sha=sha,
                checks=selected,
                detail="required check reached a non-success terminal conclusion",
            )

        if len(selected) == len(REQUIRED) and all(
            selected[name].get("status") == "completed"
            and selected[name].get("conclusion") == "success"
            for name in REQUIRED
        ):
            return terminal("PASS", sha=sha, checks=selected)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return terminal(
                "TIMEOUT",
                sha=sha,
                checks=selected,
                detail="required checks did not all succeed before the deadline",
            )
        time.sleep(min(POLL_SECONDS, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
```

Example invocation, using credentials already provided to the blocking environment:

```bash
python waiter.py lpjiayou/AI-Cinematic-Studio "$PR_HEAD_SHA" DOCS_ONLY
```

The invocation itself must be the single blocking wait. A caller must not wrap it in
an Agent-level query/sleep loop.

## 5. Result handling

| Result | Meaning | Required action |
| --- | --- | --- |
| `PASS` | The newest run for every required name completed successfully. | If already authorized, squash merge in the same Agent turn. |
| `FAIL` | A required check reached a terminal non-success conclusion. | Do not rerun this tree; diagnose, correct and create a new tree. |
| `TIMEOUT` | The scope deadline expired before all required checks succeeded. | Do not silently extend or rerun; report the blocker. |
| `API_ERROR` | Authentication, transport, HTTP or response validation failed. | Report the API failure; do not substitute browser polling. |

After `PASS` with merge authorization, continue without another handoff:

```text
wait
→ squash merge
→ safe task-branch cleanup
→ git fetch --prune
→ main commit/tree verification
→ clean-worktree verification
→ one final report
```

## 6. Boundaries

This runbook changes no workflow, required context, test scope or retry policy. It
authorizes no GPU, Provider, A100, runtime installation, asset admission, canonical
mutation, Master/Export or publication action.
