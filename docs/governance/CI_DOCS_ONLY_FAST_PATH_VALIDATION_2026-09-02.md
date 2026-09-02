# Documentation-Only Required-Check Fast-Path Validation

Status: `VALIDATED / DOCS_ONLY / EVIDENCE-BASED`

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

GitHub Actions observed the initial evidence-capture tree of Core PR-D2 #53:

```text
EVIDENCE_CAPTURE_HEAD=ea753c4727279359f803516e75b08da01af3519b
EVIDENCE_CAPTURE_TREE=95d616c52b627e1afc4368460c6f98fddf38bf72
EVIDENCE_CAPTURE_WORKFLOW_RUN=33620842337
```

The job wall times below are calculated from each job's GitHub `started_at` to
`completed_at`. They exclude runner queue time.

| Required context | Conclusion | Job wall time |
| --- | --- | ---: |
| Markdown | `SUCCESS` | `9 seconds` |
| Documentation Links | `SUCCESS` | `12 seconds` |
| Unit Tests | `SUCCESS_DOCS_FAST_PATH` | `13 seconds` |
| Contract Tests | `SUCCESS_DOCS_FAST_PATH` | `12 seconds` |
| Integration Tests | `SUCCESS_DOCS_FAST_PATH` | `12 seconds` |

```text
VALIDATION_STATE=PASS
CI_SCOPE=DOCS_ONLY
DOCS_ONLY_REQUIRED_CHECKS=5_SUCCESS
DOCS_ONLY_INTEGRATION_JOB_SECONDS=12
DOCS_ONLY_TOTAL_REQUIRED_CHECK_WINDOW_SECONDS=13
FULL_SUITE_EXECUTED=false
FFMPEG_INSTALL_EXECUTED=false
```

All five jobs started at `2026-09-02T10:42:28Z`; the last completed at
`2026-09-02T10:42:41Z`. The three test jobs' full-suite media-runtime step had the
step-level conclusion `skipped`, while every required job concluded `success`.
Decoded logs contained no `apt-get`, `ffmpeg -version` or full-suite discovery
marker. Every job reported `DOCS_ONLY_FAST_PATH=PASS`,
`FULL_SUITE_EXECUTED=false` and `FFMPEG_INSTALL_EXECUTED=false`.

This evidence amendment changes only this allowlisted document. Its final tree must
also complete all five required checks before squash merge; that final result is a
merge gate and does not rewrite the immutable evidence-capture facts above.

## 5. Authority boundary

This validation does not authorize M12-C3/C4, M13 Extension G0, A100/GPU use, model
download, wheelhouse creation, provider calls, production assets, Master/Export or
publication. It changes no runtime or product behavior.
