# Required-Check Documentation Fast-Path Policy

Status: `ACTIVE / FAIL-CLOSED`

Owner: `Repository Governance Owner / CI Governance Owner`

Authorized by:
`ACS-DOCUMENTATION-GOVERNANCE-PR-D-AND-DOCS-ONLY-CI-FAST-PATH`

Bounded revision: Project Lead's 2026-09-13 instruction to proceed with measured
CI optimization; production behavior and the five required contexts are unchanged.

## 1. Purpose

This policy permits a path-proven documentation-only pull request to satisfy the
existing required checks without installing FFmpeg or executing the complete Unit,
Contract and Integration suites. It does not remove, rename, skip or neutral-pass a
required check and does not reduce test coverage for a protected or unknown change.

The only classifications are:

```text
CI_SCOPE=DOCS_ONLY
CI_SCOPE=AFFECTED_TESTS
CI_SCOPE=FULL_SUITE
```

`PARTIAL`, `SMART`, `AUTO_GUESS` and `BEST_EFFORT` are forbidden.

## 2. Required contexts and branch rule

The five required context names remain byte-for-byte unchanged:

```text
Markdown
Documentation Links
Unit Tests
Contract Tests
Integration Tests
```

Every required job runs for every pull request. A required job must not use a
job-level condition that can make its conclusion `skipped`. Step-level selection is
permitted only after successful classification. Classification failure makes every
required job fail.

The protected `main` branch requires a pull request, strict status checks, linear
history, zero approving reviews, squash-only merge and zero bypass actors. The
workflow therefore runs automatically for pull requests targeting `main` and through
manual `workflow_dispatch`, plus a daily full run at 19:19 UTC. It does not repeat
the same tested tree after squash merge through a `push` trigger. Scheduled checks
are additional regression evidence, not a replacement for a PR's required checks
or permission to release a known failing main.

## 3. Closed documentation-only allowlist

The following root documents are eligible:

- `AGENTS.md`
- `CURRENT_MILESTONE.md`
- `README.md`
- `README-*.md`
- `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`
- `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`

Files below `docs/`, `governance/` and `architecture/` are eligible only when their
exact suffix is one of:

```text
.md
.mdx
.rst
.txt
.json
.yaml
.yml
```

GitHub documentation templates are eligible only at:

- `.github/PULL_REQUEST_TEMPLATE.md`;
- `.github/pull_request_template.md`, the repository's existing equivalent;
- `.github/PULL_REQUEST_TEMPLATE/**` with an allowed documentation suffix; or
- direct `.md` children of `.github/ISSUE_TEMPLATE/`.

Both current normative documents and immutable historical evidence may use the
documentation-only path. `experiments/` never does, even when a file has a Markdown
suffix.

## 4. Unconditional full-suite paths

Any change touching these prefixes is `FULL_SUITE`, except the exact existing-test
modification exception in section 4.1:

```text
services/
apps/
tests/
experiments/
scripts/
.github/workflows/
.github/actions/
backend/
frontend/
migrations/
schemas/
runtime/
models/
```

Dependency, build, container and runtime lock files are also unconditional
`FULL_SUITE`, including `pyproject.toml`, `requirements*.txt`, `constraints*.txt`,
Node lockfiles, Python lockfiles, `Dockerfile*`, `docker-compose*` and `compose*.yml`
or `compose*.yaml`. This protection applies even if such a filename is placed below a
documentation directory.

### 4.1 Closed isolated-test exception

Only `M` changes with identical regular-file modes to these existing files may use
`AFFECTED_TESTS` (ordinary documentation modifications may accompany them):

- `tests/integration/test_ai_director_project_draft_flow.py`
- `tests/integration/test_creator_project_context.py`
- `tests/integration/test_creator_series_episode.py`
- `tests/integration/test_creator_script_studio.py`
- `tests/integration/test_creator_series_planning.py`

These modules have no other Python consumers in the checked baseline. Every job
rechecks that the touched module names are not referenced by any other Python file
under `apps/`, `services/` or `tests/`. A new consumer, unavailable file or read
failure forces full execution. No production behavior change is eligible in this
first revision. Shared support, other tests, CI/classifier edits, additions,
deletions, renames, copies and mode changes remain full. Extending the allowlist
requires an independently reviewed classifier change with full CI.

All Unit and Contract tests still run. Integration executes all five listed files
plus these critical regression files, once each through the existing shard runner:

- `tests/integration/test_creator_lifecycle_sqlite_p2.py`
- `tests/integration/test_creator_public_http_v1.py`
- `tests/integration/test_creator_narrative_currentness_m7.py`

The mode reports the exact selected paths and actual counts, and explicitly reports
`FULL_SUITE_EXECUTED=false`. An empty affected worker reports zero selected/executed
tests; the required aggregator validates exact selection coverage and every worker
must succeed. No failed, cancelled, skipped or missing worker can satisfy it.

## 5. Fail-closed conditions

The classifier reads exactly:

```text
git diff --name-status -M -C <base> <head>
```

and reads the raw modes for the same diff. It considers additions, modifications,
deletions, renames, copies and type changes, including both source and destination of
a rename or copy.

Each condition below forces `FULL_SUITE` or a failing classification:

- mixed documentation and protected changes outside section 4.1;
- an unknown path, status or document suffix;
- an empty diff;
- an unresolved or invalid base/head SHA;
- a Git diff failure;
- a submodule or symlink mode;
- any file-type change;
- a rename or copy crossing documentation, protected or unknown boundaries;
- classifier, workflow or non-allowlisted test changes;
- any dependency or runtime lock change; and
- every `workflow_dispatch` or `schedule` execution.

Changing a suffix cannot convert an unknown or protected path into an eligible path.

## 6. Machine-readable evidence

Every required job creates and verifies `CI_CHANGE_SCOPE.json`. It contains only:

```text
schemaVersion
eventName
baseSha
headSha
classification
changedFiles[]
protectedMatches[]
unknownMatches[]
classificationReason
selectedIntegrationFiles[]
payloadDigest
```

The closed payload uses schema version 2. Selection is empty outside
`AFFECTED_TESTS`; inside it, the exact eight-file list is mandatory even if the
digest is recomputed. The digest is SHA-256 over canonical JSON excluding
`payloadDigest`. The payload must
not contain a token, runner path or absolute working directory. A missing field,
invalid digest, inconsistent scope or failed classification produces
`CI_SCOPE_CONSISTENCY=FAIL` and fails the job.

## 7. Required-job behavior

Markdown always runs:

```text
python scripts/validate_markdown.py
python scripts/validate_document_registry.py
python scripts/validate_current_state.py
```

Documentation Links always runs:

```text
python scripts/validate_doc_links.py
python scripts/validate_document_supersession.py
```

For `DOCS_ONLY`, Unit Tests runs fixed classifier fixtures plus registry/current
authority checks; Contract Tests verifies the M1-M19 dimensions, M12/M13 gates, A100
gate and Frontend-pin semantics; Integration Tests verifies current milestone,
cross-repository baseline, complete index, supersession and history/current
isolation. These are real governance checks and must not report fabricated test
counts.

For `FULL_SUITE`, the existing complete discovery roots remain unchanged:

```text
tests/unit/test_*.py
tests/contract/test_*.py
tests/integration/test_*.py
```

Both code-test modes may enter the deterministic FFmpeg installation step. Existing
tests are not deleted, excluded, reclassified as slow or weakened.

## 8. Full-suite Integration sharding

For `FULL_SUITE`, all files matching `tests/integration/test_*.py` are distributed
across six independent, non-required worker jobs. The fixed assignment is rebalanced
from successful workflow run
[34758261278](https://github.com/lpjiayou/AI-Cinematic-Studio/actions/runs/34758261278):
77 files and 564 discovered tests. Its four worker test times were 1124.214,
650.846, 709.197 and 1064.285 seconds. Longest-first allocation uses each logged
file's elapsed time; files absent from the top-20 reports receive a conservative
three-second estimate. Estimated new weights are 594, 595, 594, 596, 595 and 594
seconds. These are planning estimates, not measured speed-up claims; retain CI's
actual timing reports for verification. Assertions and media specifications do not
change.

The assignment lives in `scripts/run_ci_fast_path.py`. Before execution, every
worker verifies that each currently discovered Integration test file occurs exactly
once and no assigned path is absent. Unit's coverage test and the final aggregator
verify that the sum of per-shard discovered tests equals complete discovery; workers
discover only their assigned suite, avoiding repeated full discovery. Each worker
then verifies its executed count, permits
only the pre-existing authenticated full-render acceptance skip and fails if its
execution wall time exceeds 1,200 seconds. No test assertion, fixture or discovery
root changes.

Each worker uses a separate GitHub-hosted runner and a shard-specific temporary
directory. A worker checks for both `ffmpeg` and `ffprobe`, installs FFmpeg only when
either command is absent, and records both versions plus setup duration. It also
reports final media-process and listener counts.

The only required Integration context is the final job named exactly
`Integration Tests`. It uses `if: always()`, depends on the entire worker matrix and
fails unless every worker succeeds. The six worker contexts are evidence only and
are not branch-rule requirements. No required context is added or renamed.

## 9. Observability

Every required job reports:

```text
CI_SCOPE=
JOB_START_UTC=
SETUP_SECONDS=
RUNTIME_INSTALL_SECONDS=
TEST_SECONDS=
JOB_TOTAL_SECONDS=
```

Full Integration additionally reports discovered count, the twenty slowest test
files, final FFmpeg process count and residual listener count. While it runs, a safe
heartbeat is emitted at least once every 120 seconds and is stopped and joined when
the test runner exits.

In `DOCS_ONLY`, every job must report:

```text
DOCS_ONLY_FAST_PATH=PASS
FULL_SUITE_EXECUTED=false
FFMPEG_INSTALL_EXECUTED=false
```

## 10. Authority boundary

This policy changes CI execution selection only. It changes no production source,
Public API, DTO, SQLite schema, dependency, Frontend behavior or Core/Frontend pin.
It authorizes no runtime, model, provider, GPU, A100, M12-C3/C4, M13 Extension G0,
asset admission, Master/Export or publication action.
