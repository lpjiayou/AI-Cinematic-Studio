# M5 Series Plan Command Idempotency E3D — 2026-09-07

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / REQUIRED_CI_GATE`

Owner: `Project Lead / Creator Application Owner / M5 Series Planning Owner`

Task: `ACS-M5-SERIES-PLAN-CANDIDATE-AND-CONFIRMATION-IDEMPOTENCY-CORRECTIVE-E3D`

## Reproduced gap and bounded correction

R5 completed a valid upstream prefix and stopped at the M5 contract audit. Before
production edits, seven formal tests ran through authenticated public HTTP,
ThreadingHTTPServer, real temporary SQLite and LifecycleAssembly with a counting
deterministic text capability. Six recovery assertions failed: keyed generation and
confirmation returned 400, and candidate replay/restart and confirmation
replay/concurrency were unavailable. The unkeyed control passed: two text calls,
one content-deduplicated receipt, first confirmation 201, duplicate confirmation
409 `duplicate_record`. No unsupported keyed request reached generation. The red
log SHA-256 is `f463888576732721658174430d1f1e90a83cc93800e5d77471a1827f314f2c1d`.

Creator now reserves a keyed candidate command before calling the existing Series
Director. A completed command projects a v2 receipt through the existing receipt
facade. Keyed confirmation uses deterministic domain refs and exact winner replay
inside the existing Lifecycle transaction. The original unkeyed paths, historical
v1 receipts, domain schemas and manual/version-binding operations remain supported.
The [public contract](../04-interface-contract/creator-public-http-v1.md) defines
all accepted fields, canonical payloads, refs, state transitions and error codes.

```text
CORE_START_MAIN=85ddf84a6a59059020407b96001823659039c462
CORE_START_TREE=8b4f16e0eda179d736d973419cac16345f63fc7a
M5_CANDIDATE_KEYED_REQUEST_RED_REPRODUCTION=PASS
M5_CANDIDATE_DUPLICATE_GENERATION_RED_REPRODUCTION=PASS
M5_CANDIDATE_RESTART_RED_REPRODUCTION=PASS
M5_CONFIRMATION_KEYED_REQUEST_RED_REPRODUCTION=PASS
M5_CONFIRMATION_EXACT_REPLAY_RED_REPRODUCTION=PASS
M5_CONFIRMATION_CONCURRENCY_RED_REPRODUCTION=PASS
M5_SERIES_PLAN_CANDIDATE_IDEMPOTENCY_E3D=IMPLEMENTED_AND_VERIFIED
M5_SERIES_PLAN_CONFIRMATION_IDEMPOTENCY_E3D=IMPLEMENTED_AND_VERIFIED
M5_CANDIDATE_PRECALL_RESERVATION=IMPLEMENTED_AND_VERIFIED
M5_CONFIRMATION_EXACT_REPLAY=IMPLEMENTED_AND_VERIFIED
PUBLIC_ENDPOINTS=/creator/api/v1/series-plan-candidates,/creator/api/v1/series-plans/confirm-candidate
KEYED_CANDIDATE_FIRST_HTTP_STATUS=200
KEYED_CANDIDATE_REPLAY_HTTP_STATUS=200
KEYED_CANDIDATE_CHANGED_REPLAY_HTTP_STATUS=409
KEYED_CONFIRMATION_FIRST_HTTP_STATUS=201
KEYED_CONFIRMATION_REPLAY_HTTP_STATUS=200
KEYED_CONFIRMATION_CHANGED_REPLAY_HTTP_STATUS=409
CANDIDATE_CONFLICT_CODE=series_plan_candidate_idempotency_conflict
CONFIRMATION_CONFLICT_CODE=series_plan_confirmation_idempotency_conflict
CANDIDATE_REPLAY_ADDITIONAL_LOGICAL_GENERATION_COUNT=0
CANDIDATE_REPLAY_ADDITIONAL_PROVIDER_CALL_COUNT=0
DETERMINISTIC_KEYED_CANDIDATE_REF=true
DETERMINISTIC_KEYED_SERIES_PLAN_REF=true
DETERMINISTIC_KEYED_ROOT_VERSION_REF=true
DETERMINISTIC_KEYED_EPISODE_PLAN_ITEM_REFS=true
CANDIDATE_REF_DIGEST_BITS=256
RAW_IDEMPOTENCY_KEY_PERSISTED=false
RAW_CREATIVE_INPUT_PERSISTED=false
PENDING_AUTO_RETRY=false
FAILED_AUTO_RETRY=false
RESPONSE_LOSS_RECOVERY=PASS
PROCESS_RESTART_EXACT_REPLAY=PASS
CONCURRENT_EXACT_REPLAY=PASS
CONCURRENT_CHANGED_REPLAY_CONFLICT=PASS
CONFIRMATION_TIMESTAMPS_UNCHANGED=true
CURRENT_FRONTEND_UNKEYED_COMPATIBILITY=PASS
HISTORICAL_V1_RECEIPT_COMPATIBILITY=PASS
HISTORICAL_RANDOM_REF_SERIES_PLANS_READABLE=true
M6_BOOTSTRAP_FROM_KEYED_PLAN=PASS
```

## Lineage and storage

Trusted current Project/Series context and normalized creative input determine the
candidate request digest. Authenticated workspace and validated client key determine
a separate command identity and candidate identity. A short transaction commits
`PENDING`; generation runs after the connection closes. Another request reads the
same pending, failed or completed result and never infers permission to retry an
uncertain call. `COMPLETED` is durable before HTTP success. Failed rows contain only
one stable failure code; no provider body or partial candidate is saved.

One receipt facade performs existence, workspace/scope, source-currentness and
content checks for v1 and v2. Unknown/foreign/uncompleted candidates are concealed;
known content tampering returns `series_plan_candidate_content_mismatch` before
confirmation idempotency. Unkeyed lookup without a ref requires exactly one match
across both receipt generations. Keyed confirmation requires an explicit candidate
ref. Its request uses only the server receipt and canonical candidate.

Plan identity, root version and EpisodePlanItem refs use full 64-character digests
with distinct frozen namespaces. Replay compares all original Plan/root/current/
confirmed version fields and canonical content, including timestamps and item refs.
Another legitimate candidate or Project/Series with the same key conflicts. Another
key for an existing scoped Plan retains duplicate-record semantics. Later manual or
v2 binding history cannot be rewritten by replaying the old confirmation.

```text
APPLICATION_COMPONENT_TABLE=creator_series_plan_candidate_commands
APPLICATION_COMPONENT_MARKER_TABLE=creator_series_plan_candidate_command_schema
APPLICATION_COMPONENT_IDENTITY_INDEX=ux_creator_series_plan_candidate_commands_identity
APPLICATION_COMPONENT_CANDIDATE_REF_INDEX=ux_creator_series_plan_candidate_commands_candidate_ref
APPLICATION_COMPONENT_DDL_DIFF=ADDITIVE_OPTIONAL_M5_CANDIDATE_COMMAND_COMPONENT
SERIES_PLAN_DOMAIN_TABLE_DDL_DIFF=0
SERIES_PLAN_SCHEMA_VERSION_DIFF=0
SERIES_PLAN_VERSION_SCHEMA_DIFF=0
GLOBAL_LIFECYCLE_SCHEMA_VERSION_DIFF=0
M6_SCHEMA_VERSION_DIFF=0
SECOND_CREATOR_DATABASE_CREATED=false
SECOND_SERIES_PLAN_AUTHORITY_CREATED=false
SECOND_CANDIDATE_RECEIPT_AUTHORITY_CREATED=false
HISTORICAL_SERIES_PLAN_ROW_REWRITE_COUNT=0
HISTORICAL_V1_RECEIPT_ROW_REWRITE_COUNT=0
HISTORICAL_ROW_REWRITE_COUNT=0
PUBLIC_ROUTE_SET_DIFF=0
PUBLIC_RESOURCE_SET_DIFF=0
PUBLIC_M5_FIELD_SET_DIFF=ADD_OPTIONAL_IDEMPOTENCY_KEY_TO_TWO_EXISTING_RESOURCES_ONLY
E3B_PRODUCTION_SEMANTICS_DIFF=0
E3C_PRODUCTION_SEMANTICS_DIFF=0
PROJECT_FOUNDATION_PRODUCTION_DIFF=0
SCRIPT_STUDIO_PRODUCTION_DIFF=0
EPISODE_PRODUCTION_PRODUCTION_DIFF=0
FRONTEND_DIFF=0
FRONTEND_PIN_DIFF=0
WORKFLOW_DIFF=0
DEPENDENCY_DIFF=0
LOCKFILE_DIFF=0
```

## Verification and table inventory audit

The three distinct new modules cover golden UTF-8 identities, closed requests and
keys, stable envelopes, context/scope/content conflicts, failed and pending replay,
response loss, a new Python process, process death after reservation, separate
SQLite compositions, concurrent winner/replay and winner/conflict, and a second
write connection proving no transaction spans generation. Database bytes stay
unchanged on exact replay and rejected requests. The command component rejects
partial/altered DDL and indexes, duplicate identities/candidate refs, marker drift,
corrupt row/candidate/source JSON, unknown states and extra schema objects.
`integrity_check=ok` and `foreign_key_check` is empty. Keyed v1 roots remain usable
by M6 bootstrap, manual append and the existing v2 binding operation.

The inventory audit searched `sqlite_tables(`, `creator_tables`, `expected_tables`,
`undeclared SQLite table` and the three existing Creator application table names,
plus SQLite schema queries and table assertions. The affected method-aware HTTP
startup test now accepts exactly the two E3D tables alongside its two E3C tables;
it still checks no removed table, no third extra table and unchanged shutdown
inventory. The M6 allowlist validates a complete or absent E3D component and rejects
unknown tables/indexes/views/triggers. Foundation, M5 receipt and M6/Lifecycle schema
snapshots remain scoped to their existing components. Clean-state and strict-JSON
snapshots taken after server initialization remain unchanged across mutations they
reject. Generic upstream, narrative/method/audio/media and identity tests either do
not compose the HTTP server or inspect separate production/evidence/job databases.
Their expected inventories require no relaxation.

The new matrix contains 36 tests. The required focused batch passed 147 tests and the additional focused batch passed 260 tests: 407 distinct tests, zero failures, errors or skips. The new integration module is assigned exactly once to shard-2. The namespace and
complete shard coverage audits require no missing, duplicate or extra files. Local
verification runs only the new matrix and named focused regressions: M5, historical
v1 receipts, E3B/E3C, Foundation, M6 SQLite migration, clean-state E2E, method-aware
cutover, E1/E2/E3A and strict JSON/numeric integrity. Full suites belong to the one
PR head/tree CI gate. The first local component-test fixture required explicit
`initialize_or_upgrade=True`; correcting that fixture exposed all eight component
checks, which then passed. No production contract was weakened to accommodate it.

```text
TARGET_INTEGRATION_FILE_ASSIGNMENT_COUNT=1
DISCOVERED_INTEGRATION_TEST_FILE_COUNT=59
SHARDED_INTEGRATION_TEST_FILE_COUNT=59
LOCAL_FOCUSED_TEST_COUNT=407
LOCAL_FOCUSED_TEST_RESULT=PASS
MISSING_TEST_FILE_COUNT=0
DUPLICATE_TEST_FILE_COUNT=0
EXTRA_TEST_FILE_COUNT=0
UNIT_INTEGRATION_TEST_BASENAME_COLLISION_COUNT=0
LOCAL_FULL_SUITE_EXECUTED=false
CI_SCOPE=FULL_SUITE
MAX_TASK_COMMITS=1
NEW_PR_COUNT_MAX=1
```

## Quarantine and next gate

The R5 valid-prefix blocked receipt remains unchanged with SHA-256
`e9082d1ac25e000806a2523e7c12a37a295cf9b6b0de2ff7e15e6257b7407138`.
Its thirteen public HTTP calls created six upstream business rows and two
application command rows; no M5 plan, M6, script, production route/job or full E3
bundle was created. R5 staging, database, workspace refs and credentials are
quarantined valid-prefix evidence only. E3D uses isolated formal test databases;
these are not eligible lineage or a reusable production staging area. Historical
visual judgments and evidence bytes remain unchanged; no image was opened or rated.

```text
R5_VALID_UPSTREAM_PREFIX_EXISTS=true
R5_STAGING_REUSABLE_AFTER_E3D=false
R5_DATABASE_REUSABLE_AFTER_E3D=false
E3_R6_FRESH_STAGING_ROOT_REQUIRED=true
E3_R6_FRESH_DATABASE_REQUIRED=true
E3_R6_FRESH_TOKEN_REQUIRED=true
R0_VISUAL_INSPECTION_RESULT=FAIL
R1_VISUAL_INSPECTION_RESULT=FAIL
R2_OBSERVABLE_TARGET_VISUAL_INSPECTION_RESULT=PASS
R6_VISUAL_REINSPECTION_REQUIRED=false
VISUAL_REINSPECTION_COUNT=0
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
E3_LINEAGE_BUNDLE_CREATED=false
VIDEO_METHOD_ROUTE_CREATED=false
MEDIA_JOB_CREATED=false
EXECUTION_ATTEMPT_COUNT=0
A100_RUNTIME_VERIFIED=false
A100_CONTROL_CHANNEL_VERIFIED=false
EXECUTION_COST_CEILING_RESOLVED=false
A100_START_COUNT=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
GPU_OR_PROVIDER_CALLS=0
MODEL_DOWNLOAD_BYTES=0
WHEEL_DOWNLOAD_BYTES=0
E3_RESUME_R6_STARTED=false
NEXT_TASK=ACS-M10-M11-SPIKE-0-ELIGIBLE-LINEAGE-PREPARATION-E3-RESUME-R6
```

R6, E4, Spike execution, Frontend, M12-C3 and all live runtime/provider activity
require separate Project Lead authorization. E3D technical verification does not
claim feature acceptance, production readiness, QC, admission or publication.
