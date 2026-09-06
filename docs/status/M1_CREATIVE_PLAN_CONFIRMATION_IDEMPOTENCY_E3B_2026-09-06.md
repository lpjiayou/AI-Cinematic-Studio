# M1 Creative Plan Confirmation Idempotency E3B — 2026-09-06

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / REQUIRED_CI_GATE`

Owner: `Project Lead / M1 Creative Plan Confirmation Owner / Lifecycle Integrity Owner`

Task: `ACS-M1-CREATIVE-PLAN-CONFIRMATION-IDEMPOTENCY-CORRECTIVE-E3B`

## Bounded correction

The E3 R3 upstream check demonstrated two durable confirmed plans after identical
authenticated confirmation requests. The HTTP handler dropped the idempotency key
and the domain method allocated a random reference for each call. A formal test over
the real authenticator, handler, ThreadingHTTPServer, LifecycleAssembly and temporary
SQLite reproduced `201 + 201`, distinct refs and two rows before production changes.
The same committed test now requires `201 + 200`, the identical plan and one row.

The [public contract](../04-interface-contract/creator-public-http-v1.md) keeps the
existing endpoint and adds a narrow idempotent domain/public-boundary method.
The internal non-idempotent method and historical random-reference records retain
their original behavior. Series/Episode remains the only confirmed-plan authority;
the existing Lifecycle transaction and workspace/ref primary key arbitrate writes.
There is no new persistence component or in-memory-only replay cache.

```text
CORE_START_MAIN=617a25218e4e290ddf924ea158b87c7d67b622e7
CORE_START_TREE=d041529243f079546ed961f321e879cd39e49945
CREATIVE_PLAN_CONFIRMATION_IDEMPOTENCY_E3B=IMPLEMENTED_AND_VERIFIED
CREATIVE_PLAN_IDEMPOTENCY_RED_REPRODUCTION=PASS
PUBLIC_ENDPOINT=/creator/api/v1/creative-plans/confirm
PUBLIC_IDEMPOTENCY_MODES=EXPLICIT_CLIENT_KEY,CORE_ISSUED_SOURCE_PLAN_IDENTITY
CONFIRMED_PLAN_IDEMPOTENCY_IDENTITY_SCHEMA=v5.confirmed-creative-plan-idempotency-identity.v1
FIRST_REQUEST_HTTP_STATUS=201
EXACT_REPLAY_HTTP_STATUS=200
CHANGED_REPLAY_HTTP_STATUS=409
CONFLICT_CODE=creative_plan_idempotency_conflict
DETERMINISTIC_CREATIVE_PLAN_REF=true
CREATIVE_PLAN_REF_DIGEST_BITS=256
RAW_IDEMPOTENCY_KEY_PERSISTED=false
RAW_IDEMPOTENCY_KEY_LOGGED=false
```

## Identity, replay and compatibility

The versioned canonical identity contains authenticated workspace plus a distinct
mode: explicit client key, or the validated Core-issued source plan ref/schema/version.
Its full SHA-256 forms `creative-plan-<64 lowercase hex>`. Request content, time,
credentials and randomness do not participate in identity. No raw key is persisted
or exposed. Content participates in the exact semantic comparison instead.

Both accepted public bodies are closed. Server-owned claims and unknown fields are
rejected as `400 / invalid_request`, including body `workspaceRef`; query scope
rejection and authentication remain unchanged. Duplicate JSON keys and the existing
strict finite-number, depth, token-length and positive-integer rules remain enforced.

Exact replay preserves every confirmed-plan field, including the first timestamp and
version. A competing insert reads the durable winner in the existing transaction,
then either returns that plan or rejects changed content with the stable 409 code.
Different workspaces are isolated. Different explicit keys are independent commands.
The current Frontend body without a key remains accepted and retains its two-field
`ok`/`confirmedPlan` envelope. The keyed envelope adds `idempotentReplay`.

```text
FIRST_AND_REPLAY_PLAN_EQUAL=true
CONFIRMED_AT_UNCHANGED=true
CONFIRMED_CREATIVE_PLAN_COUNT_AFTER_EXACT_REPLAY=1
SECOND_WRITE_COUNT=0
RESPONSE_LOSS_RECOVERY=PASS
PROCESS_RESTART_EXACT_REPLAY=PASS
CONCURRENT_EXACT_REPLAY=PASS
CONCURRENT_CHANGED_REPLAY_CONFLICT=PASS
SAME_KEY_DIFFERENT_WORKSPACE=ISOLATED
CURRENT_FRONTEND_CONFIRM_BODY_COMPATIBILITY=PASS
HISTORICAL_RANDOM_REF_RECORDS_READABLE=true
PROJECT_FOUNDATION_REGRESSION=PASS
EPISODE_PLAN_BINDING_REGRESSION=PASS
```

## Validation and frozen boundaries

The new unit, public contract and HTTP/SQLite modules cover canonical identity vectors,
key validation, semantic equality, changed conflicts, detached return values, raw-key
non-persistence, response loss, fresh composition restart, independent SQLite assembly
concurrency, workspace isolation and downstream Project Foundation/Episode binding.
Read-only SQLite checks verify unchanged schema and unchanged bytes on exact replay
and rejected changed requests. Historical random refs survive restart and remain
bindable without rewrites.

Focused regressions cover Series/Episode, public HTTP, recoverable Project Foundation,
clean-state public E2E, Lifecycle SQLite, strict JSON/numeric handling, Canonical
Registration and E3A. The new integration file is assigned exactly once to shard-2;
all three new test basenames differ. Local full-suite execution remains prohibited;
the one PR tree requires the five normal full-suite CI checks before merge.

```text
DATABASE_DDL_DIFF=0
GLOBAL_LIFECYCLE_SCHEMA_VERSION_DIFF=0
CONFIRMED_CREATIVE_PLAN_SCHEMA_VERSION_DIFF=0
HISTORICAL_ROW_REWRITE_COUNT=0
PUBLIC_ROUTE_SET_DIFF=0
PUBLIC_RESOURCE_SET_DIFF=0
PROJECT_FOUNDATION_PRODUCTION_DIFF=0
CANONICAL_REGISTRATION_PRODUCTION_DIFF=0
SERIES_PLANNING_PRODUCTION_DIFF=0
SCRIPT_STUDIO_PRODUCTION_DIFF=0
EPISODE_PRODUCTION_PRODUCTION_DIFF=0
E1_WORKER_SEMANTICS_DIFF=0
E2_RESULT_INTAKE_SEMANTICS_DIFF=0
E3A_INPUT_ADMISSION_SEMANTICS_DIFF=0
FRONTEND_DIFF=0
FRONTEND_PIN_DIFF=0
DEPENDENCY_DIFF=0
LOCKFILE_DIFF=0
WORKFLOW_DIFF=0
LOCAL_FULL_SUITE_EXECUTED=false
```

## E3 evidence quarantine and next boundary

The failed R3 staging database remains immutable evidence only. Its two plans must
not be merged, deleted, rewritten or used for a new Project Foundation. E3B tests use
fresh temporary test databases and create no E3 lineage facts. The following external
evidence filenames and digests identify the preserved history without making a
transient agent path an execution authority.

| Evidence | SHA-256 |
| --- | --- |
| `E3_ANCHOR_VISUAL_INSPECTION_R0_FAILED.json` | `fad7a88363a85a0e4c1521030f7d987abeecc592ffc04acc1642018759aac94e` |
| `E3_ANCHOR_TARGET_SPECIFICATION_CORRECTION_R1.json` | `0ea2b1d0c757a442621fbd277a4a735030559cb6ea56c4350b214cea528bcab6` |
| `E3_ANCHOR_VISUAL_INSPECTION_R1_CORRECTED_FAILED.json` | `5cbcf295e241fee1a4a3cfab8db9d3fd8df378f29cdf7f8cbbcb801e94c71e10` |
| `E3_ANCHOR_OBSERVABLE_TARGET_CORRECTION_R2.json` | `2a25cc83af7d4b9963b28808ad037c44da4eaf9771a810dfb9025b7f94b97d53` |
| `E3_ANCHOR_VISUAL_INSPECTION_R2_OBSERVABLE_TARGET.json` | `d9a9a031b6985c8f7302a1a995046f957c77c5b3f3abcf57ef0dc5d8449e3d4e` |
| `E3_UPSTREAM_PUBLIC_HTTP_REPLAY_CHECK.json` | `44937374fb7a906d576f1b4471dc0ccbcf325d6081fbc4651e0ffc09f5ec242e` |
| `E3_R3_BLOCKED_RECEIPT.json` | `076cb9839f4ba93dce93571357afe30618eddd7197a3c3803ece132b176a8a70` |

```text
E3_PARTIAL_ISOLATED_CONFIRMED_PLAN_COUNT=2
E3_PARTIAL_STAGING_DISPOSITION=QUARANTINED_EVIDENCE_ONLY
E3_PARTIAL_STAGING_REUSABLE=false
E3_PARTIAL_DATABASE_REUSABLE=false
E3_ELIGIBLE_LINEAGE_FACT_COUNT=0
E3_R4_FRESH_STAGING_ROOT_REQUIRED=true
E3_R4_FRESH_DATABASE_REQUIRED=true
R0_VISUAL_INSPECTION_RESULT=FAIL
R1_VISUAL_INSPECTION_RESULT=FAIL
R2_OBSERVABLE_TARGET_VISUAL_INSPECTION_RESULT=PASS
R2_VISUAL_REINSPECTION_REQUIRED=false
ANCHOR_SHA256=3b4f871ab59332625f0d343bde0ca1686477a135a3a2f9d6373f474f22e252ea
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
E3_LINEAGE_BUNDLE_CREATED=false
VIDEO_METHOD_ROUTE_CREATED=false
MEDIA_JOB_CREATED=false
A100_START_COUNT=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
GPU_OR_PROVIDER_CALLS=0
E3_RESUME_R4_STARTED=false
NEXT_TASK=ACS-M10-M11-SPIKE-0-ELIGIBLE-LINEAGE-PREPARATION-E3-RESUME-R4
```

R4 requires separate authorization, a fresh staging root/database, and byte-for-byte
copy plus SHA verification of the preserved evidence. It must reverify the same
Anchor bytes without repeating the accepted visual inspection. E3B does not authorize
R4, E4, A100, ComfyUI, a video route/job/worker, Frontend, M12-C3 or automatic subtitles.
