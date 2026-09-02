# Required-Check Documentation Fast-Path Policy

Status: `ACTIVE / FAIL-CLOSED`

Owner: `Repository Governance Owner / CI Governance Owner`

Authorized by:
`ACS-DOCUMENTATION-GOVERNANCE-PR-D-AND-DOCS-ONLY-CI-FAST-PATH`

## 1. Purpose

This policy permits a path-proven documentation-only pull request to satisfy the
existing required checks without installing FFmpeg or executing the complete Unit,
Contract and Integration suites. It does not remove, rename, skip or neutral-pass a
required check and does not reduce test coverage for a protected or unknown change.

The only classifications are:

```text
CI_SCOPE=DOCS_ONLY
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
manual `workflow_dispatch`; it does not repeat the same tested tree after squash
merge through a `push` trigger.

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

Any change touching these prefixes is `FULL_SUITE`:

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

## 5. Fail-closed conditions

The classifier reads exactly:

```text
git diff --name-status -M -C <base> <head>
```

and reads the raw modes for the same diff. It considers additions, modifications,
deletions, renames, copies and type changes, including both source and destination of
a rename or copy.

Each condition below forces `FULL_SUITE` or a failing classification:

- mixed documentation and protected changes;
- an unknown path, status or document suffix;
- an empty diff;
- an unresolved or invalid base/head SHA;
- a Git diff failure;
- a submodule or symlink mode;
- any file-type change;
- a rename or copy crossing documentation, protected or unknown boundaries;
- classifier, workflow or test changes;
- any dependency or runtime lock change; and
- every `workflow_dispatch` execution.

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
payloadDigest
```

The digest is SHA-256 over canonical JSON excluding `payloadDigest`. The payload must
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

Only `FULL_SUITE` may enter the deterministic FFmpeg installation step. Existing
tests are not deleted, excluded, reclassified as slow or weakened.

## 8. Observability

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

## 9. Authority boundary

This policy changes CI execution selection only. It changes no production source,
Public API, DTO, SQLite schema, dependency, Frontend behavior or Core/Frontend pin.
It authorizes no runtime, model, provider, GPU, A100, M12-C3/C4, M13 Extension G0,
asset admission, Master/Export or publication action.
