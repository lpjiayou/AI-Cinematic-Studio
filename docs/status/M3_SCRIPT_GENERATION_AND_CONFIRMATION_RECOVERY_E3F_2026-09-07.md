# M3 Script Generation and Confirmation Recovery — E3F

Status: `BOUNDED_IMPLEMENTATION / LOCAL_VALIDATION / REQUIRED_CI_GATE`

Owner: Project Lead / M3 Script Studio Owner / Creator Application Recovery Owner / Lifecycle Transaction Integrity Owner

## Authority and baseline

```text
TASK_ID=ACS-M3-SCRIPT-GENERATION-AND-CONFIRMATION-RECOVERY-E3F
CORE_START_MAIN=710687ec402482da0d3d2352d5c3b2b66333ec48
CORE_START_TREE=f7bb39009fc76cc2c715af756ae5329d38dd7350
BRANCH=fix/m3-script-generation-confirmation-recovery-e3f
AUDIT_REPORT_SHA256=56aaa2d3d5312158e4426ffac95b72f6b51196fef12927b30824a9f1cd3671f9
AUDIT_EVIDENCE_INDEX_SHA256=63cd2e484f4fabc81531905fcada135907d8db3fa6c91a9b863b020928e7d183
CI_SCOPE=FULL_SUITE
```

The two exact authenticated public Script generation/confirmation endpoints gain a
bounded recovery contract. The four accepted V1/M6_BOUND_V2 audit counterexamples
remain historical observations under an unspecified replay contract. Their original
classification, report and evidence are unchanged; the full audit is not rerun.
PR #79 is merged at the baseline above. No live Spike-0 lineage is authorized.
One task commit and one PR-head FULL_SUITE CI wait precede the authorized squash
merge and verified automatic branch deletion. This document does not predict its
own commit, PR number or merge identity.

## Frozen implementation and transaction design

Generate requires `seriesRef`, `episodeRef`; optional fields are `projectRef` and
`idempotencyKey`. Confirm requires `seriesRef`, `episodeRef`, `scriptRef`,
`scriptVersionRef`, `humanConfirmed`; optional fields are `projectRef` and
`expectedScriptVersion`. Workspace is authenticated. Unknown fields, duplicate JSON
keys, nonfinite values, client binding/digest/authority/result fields and query input
are rejected. The expected version is a strict positive JSON integer identifying the
Script root. Keys are strict nonempty strings of at most 200 characters, without
surrounding whitespace, controls, slash/backslash or dot path components. Raw keys
are never persisted or logged.

Generation mode follows the existing optional Project/M6 rule: absent Project uses
v1, present Project requires a current trusted M6 consumer context and creates v2.
Invalid M6 configuration never falls back. A versioned canonical JSON digest binds
Workspace, `SCRIPT_GENERATION` and key; unkeyed calls use an internal random identity.
A separate request digest binds normalized scope; the source digest binds the actual
server bootstrap and optional M6 context before any text call.

`creator_script_generation_schema` and `creator_script_generation_commands` are
optional application recovery metadata in the existing Creator SQLite database.
The frozen DDL is validated exactly at startup:

```sql
CREATE TABLE creator_script_generation_schema (
    component TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL
);
CREATE TABLE creator_script_generation_commands (
    workspace_ref TEXT NOT NULL,
    identity_digest TEXT NOT NULL,
    series_ref TEXT NOT NULL,
    episode_ref TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('PENDING','RESULT_READY','COMPLETED','FAILED')),
    record_json TEXT NOT NULL,
    PRIMARY KEY(workspace_ref, identity_digest)
);
CREATE UNIQUE INDEX ux_creator_script_generation_episode_pending
ON creator_script_generation_commands(workspace_ref, series_ref, episode_ref)
WHERE state IN ('PENDING','RESULT_READY');
```

The sole marker is `(script_generation_recovery, 1)`. Canonical `record_json` has
the closed fields `schemaVersion`, `workspaceRef`, `seriesRef`, `episodeRef`,
`projectRef`, `keyed`, `identityDigest`, `requestDigest`, `sourceDigest`, `source`,
`state`, `result`, `resultDigest`, `response`, `failureCode`, `createdAt`, `updatedAt`,
`version`, `rowDigest`. Its schema is `creator.script-generation-command.v1`.
The indexed scope/identity/state must exactly equal the validated record. No raw
key, unvalidated output, credential or provider exception is stored. Unique
Workspace/identity and a partial unique Workspace/Series/Episode
index for PENDING/RESULT_READY exclude competing first generation across processes.
Rows retain request/source digests, canonical source JSON, state, validated result
JSON/digest, original response JSON, safe failure classification, timestamps,
monotonic version and row integrity digest. No domain tables or schema versions change.

The existing V5 Script boundary owns short operations under the existing
CREATE_SCRIPT_VERSION lease; Application receives no connection, lease, private
repository or arbitrary transaction callback. The sequence is:

1. Validate authenticated scope, bootstrap and current M6 context; reject an existing
   Script before reserving a new execution. Exact keyed commands are resolved first.
2. Commit PENDING and Episode exclusion before entering the existing Script Studio
   text capability. No transaction or Lifecycle lock spans that capability call.
3. Validate strict legal content against the reserved bootstrap and commit
   RESULT_READY with its original source association.
4. Recheck source/scope/absence of Script inside one V5 transaction. Invoke the
   existing ScriptStudioService creation and save its actual refs/stable response
   with COMPLETED in that same transaction. Any failure rolls both changes back.

RESULT_READY recovery performs only step 4. COMPLETED replay verifies the actual
immutable ScriptVersion association and returns the original command result, without
claiming current edit/confirmation state. PENDING is uncertain and never resubmits.
Timeout/unknown execution outcome retains the Episode exclusion. Only a known
terminal invalid-output outcome becomes FAILED and releases it; same-key retry
remains terminal. The existing one-schema-repair attempt inside the original text
service is unchanged; command retry never adds another generation or repair attempt.
A source change or competing manual/import creation is never overwritten.

Confirmation validates scope, immutable target/lineage, reviewed-import protection
and applicable current M6 before any no-op. In the same linearizable transaction:
first confirmation accepts omitted CAS or matching CAS; the same current target
accepts omitted CAS, matching CAS or one-step expected+1, with zero business writes;
a different confirmed target requires matching current root CAS. Later advancement,
missing switch precondition or stale CAS returns 409. No expected value is refreshed.
This is current-target satisfaction, not a keyed historical confirmation receipt.

## Focused evidence and limits

Four authenticated ThreadingHTTPServer/new-SQLite regressions failed at the frozen
baseline: each generation retry added one capability call; each same-target
confirmation advanced the root and timestamp. All four now pass. Original audit
classification and evidence bytes are unchanged; these tests establish the new
contract without reclassifying the earlier unspecified behavior.

The 34 new unit/contract/HTTP tests pass with both V1 and M6_BOUND_V2 subcases.
They cover closed input, changed replay, foreign Workspace, source drift,
cross-key/cross-process exclusion, independently persisted capability counts,
response loss and new Python interpreters. InMemory and SQLite both roll back the
Script write and completion transition on fault; only SQLite proves persistence.
Startup rejects partial/altered components, unknown objects and states, tampered
rows, invalid results and missing/mismatched completed domain associations.

| Abrupt child exit point | Durable state | Domain Script count | Counted text calls | Same-key new-process recovery |
| --- | --- | --- | --- | --- |
| After reservation | PENDING | 0 | 0 | 409; no additional call |
| During text capability | PENDING | 0 | 1 | 409; no additional call |
| After return, before result persistence | PENDING | 0 | 1 | 409; lost output is not recoverable |
| After result persistence | RESULT_READY | 0 | 1 | 200 local completion; no additional call |
| After Script insert, before completion update | RESULT_READY | 0 after process death | 1 | Both writes rolled back; local recovery only |
| After atomic commit, before HTTP response | COMPLETED | 1 | 1 | 200 original stable payload; no additional call |

The transaction fault checks that ScriptVersion exists inside the uncommitted
transaction before terminating the interpreter. The parent observes zero domain
rows without deleting any. Same-key, different-key and unkeyed two-process races
admit one capability invocation. RESULT_READY source drift preserves the pending
exclusion and never rebinds old content. V2 drift uses an actual legal M5/M6 source
advance; V1 has no public mutation of its immutable Episode bootstrap, so its
upstream-drift fault is injected at the existing source reader, without inventing a
business mutation API or changing production source ownership.

Confirmation tests cover same/different-target HTTP and two-process races, old
delayed targets, strict CAS, approval/M6/source checks before no-op, response loss
and restart. V1 and v2 ProductionRun snapshots remain exact across repeated
confirmation. Current M7 requires a bound v2 Script; its real authenticated
validation remains current after no-op. Actual edits and explicit target switches
still make old downstream inputs stale. These checks compare full business payloads
and complete disposable database dumps, not only the Script root.

The exact composed Creator inventory is 30 tables (28 existing plus the two recovery
tables), 34 when the server's M1/M5 command components are installed, and 36 with the
optional historical v1 candidate-receipt component. A third unknown table remains
rejected. Public route and resource sets are unchanged. Only directly affected
target-switch callers gain explicit root CAS; their stale/currentness assertions
are preserved. Local validation is focused; complete suites belong to the one PR CI.

Local evidence comprises 329 distinct focused tests: 34 new E3F tests, 56 existing
Script/approval/M6 core tests, 78 affected public HTTP/contract/M7 tests, 88 directly
affected CAS and E3D/E3E compatibility tests, and 73 shared Lifecycle/optional-schema
tests. An additional run uses the actual CI integration-discovery function and
passes all 21 E3F HTTP tests under bare discovery names while children use the fixed
full package entrypoint and checkout cwd. All 61 integration files are assigned
exactly once across four shards; 192 test module basenames have no collision.
The five documentation validators, changed-file compilation, diff check and secret
scan pass. `CURRENT_MILESTONE.md` remains 195 splitlines. No local full suite or
complete audit sweep was executed.

Unkeyed first success and original script/scriptVersion envelope remain compatible;
unkeyed response loss cannot promise exact command receipt replay. First/same-target
confirmation keeps old requests; switching an already confirmed target now requires
`expectedScriptVersion`. Frontend CAS wiring is not implemented in this task.
M5 historical confirmation recovery remains UNPROVEN. R6, real Providers, GPU and
downstream execution remain unauthorized; E3F green cannot replace R6 acceptance.

```text
M3_KEYED_GENERATION_RECOVERY=IMPLEMENTED_AND_VERIFIED
M3_GENERATION_PRECALL_RESERVATION=IMPLEMENTED_AND_VERIFIED
M3_GENERATION_DOMAIN_RECEIPT_ATOMICITY=IMPLEMENTED_AND_VERIFIED
M3_SAME_TARGET_CONFIRMATION_NO_OP=IMPLEMENTED_AND_VERIFIED
M3_CONFIRMATION_TARGET_CHANGE_CAS=IMPLEMENTED_AND_VERIFIED
UNKEYED_GENERATION_EXACT_RECEIPT_REPLAY_NOT_GUARANTEED=true
PENDING_GENERATION_AUTOMATIC_RESUBMISSION=false
CONFIRMATION_HISTORICAL_RECEIPT_RECONSTRUCTION=false
CONFIRMED_TARGET_SWITCH_REQUIRES_EXPECTED_SCRIPT_VERSION=true
FRONTEND_SWITCH_CAS_WIRING=NOT_IMPLEMENTED_IN_THIS_TASK
APPLICATION_COMPONENT_DDL_DIFF=ADDITIVE
SCRIPT_DOMAIN_TABLE_DDL_DIFF=0
LIFECYCLE_SCHEMA_VERSION_DIFF=0
M6_SCHEMA_VERSION_DIFF=0
HISTORICAL_ROW_REWRITE_COUNT=0
M5_CONFIRM_VERSION_HISTORICAL_RECEIPT=UNPROVEN_CONTRACT_DECISION_PENDING
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
R6_LIVE_LINEAGE_STARTED=false
E4_STARTED=false
REAL_PROVIDER_CALL_COUNT=0
A100_START_COUNT=0
COMFYUI_START_COUNT=0
VIDEO_METHOD_ROUTE_COUNT=0
MEDIA_JOB_COUNT=0
EXECUTION_ATTEMPT_COUNT=0
```

Only after verified E3F merge and cleanup is the next task
`ACS-M10-M11-SPIKE-0-ELIGIBLE-LINEAGE-PREPARATION-E3-RESUME-R6`, requiring separate
authorization, affected-contract review and the M5 confirmation checkpoint. No full
28-endpoint rescan or automatic M5 historical receipt store is authorized.
