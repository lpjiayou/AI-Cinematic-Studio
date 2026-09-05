# Core Recoverable Project Foundation Command — 2026-09-05

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / FAIL-CLOSED`

Owner: `Project Lead / Creator Public Contract Owner / Project Foundation Command Owner`

Task: `ACS-CORE-RECOVERABLE-PROJECT-FOUNDATION-COMMAND-C`

## Result

This checkpoint closes the Core portion of I4 by replacing the lossy multi-request
composition with one durable, idempotent Project foundation command. It does not
change the Frontend, make the legacy multi-POST sequence recoverable, create a new
domain authority, invoke a Provider/GPU, establish production readiness or authorize
the next task.

```text
CORE_RECOVERABLE_PROJECT_FOUNDATION_COMMAND=IMPLEMENTED_AND_VERIFIED
I4_RED_REPRODUCTION=PASS
SERIES_RESPONSE_LOSS_DUPLICATION_REPRODUCED=true
PROJECT_STEP_FAILURE_DUPLICATION_REPRODUCED=true
EPISODE_STEP_FAILURE_DUPLICATION_REPRODUCED=true

PROJECT_FOUNDATION_COMMAND_SCHEMA=creator.project-foundation-command.v1
PROJECT_FOUNDATION_RESULT_SCHEMA=creator.project-foundation-result.v1
PROJECT_FOUNDATION_EXECUTION_MODE=DURABLE_INTENT_PLUS_SINGLE_LIFECYCLE_ATOMIC_TRANSACTION
DOMAIN_OBJECTS_COMMITTED_WITH_RESULT_RECEIPT_ATOMICALLY=true

SHARED_SQLITE_TRANSACTION_FEASIBLE=true
IN_MEMORY_ATOMIC_ROLLBACK_FEASIBLE=true
NESTED_LIFECYCLE_LEASE_REQUIRED=false
DIRECT_V5_TABLE_SQL_REQUIRED=false

PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT=/creator/api/v1/project-foundations
PUBLIC_RESOURCE_SET_DIFF=ADD_PROJECT_FOUNDATIONS_ONLY
PUBLIC_ROUTE_SET_DIFF=ADD_PROJECT_FOUNDATIONS_POST_AND_GET_ONLY

COMMAND_STORE_MARKER=creator_project_foundation_schema
COMMAND_STORE_TABLE=creator_project_foundation_commands
COMMAND_STORE_INDEX=ux_creator_project_foundation_commands_idempotency
COMMAND_STORE_SCHEMA_VERSION=1

FIRST_REQUEST_HTTP_STATUS=201
EXACT_REPLAY_HTTP_STATUS=200
PENDING_RECOVERY_HTTP_STATUS=200
CHANGED_REPLAY_HTTP_STATUS=409
FOUNDATION_REF_SERVER_OWNED=true
WORKSPACE_SCOPE_SERVER_OWNED=true
REQUEST_DIGEST_VERIFIED=true
RESULT_DIGEST_VERIFIED=true

RESPONSE_LOSS_RECOVERY=PASS
PROCESS_RESTART_RECOVERY=PASS
PENDING_INTENT_RECOVERY=PASS
CONCURRENT_EXACT_REPLAY=PASS
CONCURRENT_CHANGED_REPLAY_CONFLICT=PASS
FOREIGN_WORKSPACE_ISOLATION=PASS

ATOMIC_ROLLBACK_AFTER_INTENT=PASS
ATOMIC_ROLLBACK_AFTER_SERIES=PASS
ATOMIC_ROLLBACK_AFTER_PROJECT=PASS
ATOMIC_ROLLBACK_AFTER_EPISODE=PASS
ATOMIC_ROLLBACK_BEFORE_RESULT=PASS
PARTIAL_SERIES_COUNT=0
PARTIAL_PROJECT_COUNT=0
PARTIAL_EPISODE_COUNT=0

DIRECT_SQL_TO_V5_AUTHORITY_TABLES=0
SERIES_AUTHORITY_DUPLICATED=false
PROJECT_AUTHORITY_DUPLICATED=false
EPISODE_AUTHORITY_DUPLICATED=false
SECOND_AUTHORITY_DATABASE_CREATED=false

PROJECT_FOUNDATION_RECEIPT_IS_CANONICAL_FACT=false
PROJECT_FOUNDATION_RECEIPT_IS_APPROVAL=false
PROJECT_FOUNDATION_RECEIPT_GRANTS_AUTHORITY=false
PROJECT_FOUNDATION_RECEIPT_IS_PROJECT_AUTHORITY=false
PROJECT_FOUNDATION_RECEIPT_IS_SERIES_AUTHORITY=false
PROJECT_FOUNDATION_RECEIPT_IS_EPISODE_AUTHORITY=false
PROJECT_FOUNDATION_RECEIPT_PUBLICATION_ALLOWED=false

LEGACY_MULTI_POST_COMBINATION_IS_RECOVERABLE=false
NEW_PROJECT_FOUNDATION_COMMAND_IS_RECOVERABLE=true
CURRENT_FRONTEND_STILL_USES_LEGACY_MULTI_POST=true
FRONTEND_CUTOVER_REQUIRED=true

CANONICAL_REGISTRATION_PRODUCTION_DIFF=0
CANONICAL_REGISTRATION_TABLE_DIFF=0
CANONICAL_TARGET_REQUIRED_FOR_PROJECT_FOUNDATION=false
SCRIPT_ACCEPTANCE_REQUIRED_FOR_PROJECT_FOUNDATION=false
CANONICAL_MUTATION_COUNT=0

DATABASE_SCHEMA_DIFF=ADDITIVE_OPTIONAL_APPLICATION_PROJECT_FOUNDATION_COMMAND_STORE_ONLY
GLOBAL_LIFECYCLE_SCHEMA_VERSION_DIFF=0
LIFECYCLE_V2_MARKER_UNCHANGED=true
EXISTING_V5_TABLE_DDL_DIFF=0
EXISTING_TABLE_COLUMN_DIFF=0
HISTORICAL_ROW_REWRITE_COUNT=0

I4_CORE_VECTOR_CLOSED=true
I4_FRONTEND_VECTOR_CLOSED=false
I4_FULLY_CLOSED=false
CLEAN_STATE_PUBLIC_API_E2E=NOT_STARTED
AUTOMATIC_SUBTITLE_G0=NOT_STARTED
SPIKE_0=NOT_STARTED
NEXT_TASK=ACS-CORE-CLEAN-STATE-PUBLIC-API-E2E-D
```

## Transaction and authority boundary

Phase A validates and canonicalizes the complete request, then durably records only a
`PENDING` application intent. Phase B revalidates that intent and calls the existing
Series/Episode and Project participants under one Lifecycle lease. The optional
Series, Project relationship, optional Episode and `COMPLETED` result commit on the
same SQLite connection. A pre-commit fault rolls back every domain object and leaves
the durable intent recoverable; a post-commit response loss replays the original refs.

The result receipt duplicates no domain authority. Startup validation reparses its
canonical JSON, recomputes request/result digests, validates exact schema and scope,
and compares refs and immutable creation facts with the existing V5 repositories.
Even a forged ref with a recomputed receipt digest fails closed. The store contains no
direct V5 authority `INSERT`, `UPDATE` or `DELETE` statement.

## Persistence and compatibility evidence

The marker, table and unique index form one optional exact-validated component in the
existing `CREATOR_DATA_PATH`. Absent and complete states pass; every partial schema,
DDL/marker/row corruption, undeclared object and non-standard JSON state fails without
repair. The component coexists with candidate receipts, Script Acceptance and
Canonical Registration while Lifecycle remains V2.

Focused unit, contract and real public HTTP tests cover all command shapes, strict
integers and JSON, exact/changed replay, four concurrency arrangements, all six fault
points, full process restart, foreign-workspace non-disclosure, authority tampering,
subsequent server recovery and legacy Series/Project/Episode routes. No full local
suite, Provider call, GPU call, Frontend change, canonical mutation or publication
operation was performed.
