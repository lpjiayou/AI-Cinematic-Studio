# Documentation-Only Required-Check Fast-Path Validation

Status: `VALIDATION IN PROGRESS / EVIDENCE CAPTURE`

Date: `2026-09-02`

Task: `ACS-DOCUMENTATION-GOVERNANCE-PR-D-AND-DOCS-ONLY-CI-FAST-PATH`

## 1. Validated implementation baseline

The required-check fast path was introduced by Core PR-D #52 and squash-merged at:

```text
PR_D_MERGE_COMMIT=c18de7edabc8b3a9d7a78dfad8498aaebcd04a6a
PR_D_MERGE_TREE=8b9fe3f8adfc722647a8f322222308e2f06568c7
```

The controlling policy is
[`CI_REQUIRED_CHECK_FAST_PATH_POLICY.md`](CI_REQUIRED_CHECK_FAST_PATH_POLICY.md).

## 2. Ruleset boundary

The active `main` ruleset was read before PR-D and exposes exactly these required
contexts:

```text
Markdown
Documentation Links
Unit Tests
Contract Tests
Integration Tests
```

Its relevant settings are strict required statuses, zero required approvals,
squash-only merge, linear history and zero bypass actors. PR-D did not modify the
ruleset.

## 3. Validation pull request boundary

The only new substantive document in this pull request is this evidence record.
The registry, complete index and authority map receive only their mandatory generated
entry for this document. Every changed path is inside the closed documentation-only
allowlist.

```text
PRODUCTION_SOURCE_DIFF=0
PUBLIC_API_DIFF=0
SQLITE_SCHEMA_DIFF=0
DEPENDENCY_DIFF=0
FRONTEND_BEHAVIOR_DIFF=0
FRONTEND_PIN_CHANGED=false
```

## 4. Required-check evidence

This section deliberately remains pending until GitHub Actions observes the pull
request. A pending result is not a formal pass.

| Required context | Conclusion | Job wall time |
| --- | --- | ---: |
| Markdown | `PENDING` | `PENDING` |
| Documentation Links | `PENDING` | `PENDING` |
| Unit Tests | `PENDING` | `PENDING` |
| Contract Tests | `PENDING` | `PENDING` |
| Integration Tests | `PENDING` | `PENDING` |

```text
VALIDATION_STATE=IN_PROGRESS
CI_SCOPE=AWAITING_OBSERVATION
DOCS_ONLY_REQUIRED_CHECKS=AWAITING_OBSERVATION
DOCS_ONLY_INTEGRATION_JOB_SECONDS=AWAITING_OBSERVATION
DOCS_ONLY_TOTAL_REQUIRED_CHECK_WINDOW_SECONDS=AWAITING_OBSERVATION
FULL_SUITE_EXECUTED=AWAITING_OBSERVATION
FFMPEG_INSTALL_EXECUTED=AWAITING_OBSERVATION
```

Queue delay is excluded from job wall time. The required-check window will be
calculated from the earliest required-job `started_at` to the latest required-job
`completed_at`.

## 5. Authority boundary

This validation does not authorize M12-C3/C4, M13 Extension G0, A100/GPU use, model
download, wheelhouse creation, provider calls, production assets, Master/Export or
publication. It changes no runtime or product behavior.
