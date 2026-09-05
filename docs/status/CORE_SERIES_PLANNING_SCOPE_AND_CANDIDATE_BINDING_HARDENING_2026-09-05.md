# Core Series Planning Scope and Candidate Binding Hardening — 2026-09-05

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / FAIL-CLOSED`

Owner: `Project Lead / Creator Public Contract Owner / M5 Domain Owner`

Task: `ACS-CORE-SERIES-PLANNING-SCOPE-AND-CANDIDATE-BINDING-HARDENING-B`

## Result

This checkpoint closes the bounded B2 Series-scope failure and the F4 Core
candidate-provenance vector. It does not change the public route/resource set,
SeriesPlan or SeriesPlanVersion schemas, the global Lifecycle V2 schema version,
Frontend code, Provider/runtime authority, asset admission or publication authority.

```text
CORE_SERIES_PLANNING_SCOPE_AND_CANDIDATE_BINDING=IMPLEMENTED_AND_VERIFIED

B2_SERIES_PLANNING_SCOPE_ERROR=CLOSED
STANDALONE_NO_SERIES_HTTP_STATUS=409
STANDALONE_NO_SERIES_ERROR_CODE=series_scope_required
STANDALONE_PROVIDER_CALL_COUNT=0
STANDALONE_CANDIDATE_RECEIPT_COUNT=0
STANDALONE_SERIES_PLAN_COUNT=0

CANDIDATE_PROVENANCE_MODE=APPLICATION_OWNED_DURABLE_CANDIDATE_RECEIPT
SERVER_VERIFIABLE_CANDIDATE_PROVENANCE=true
CLIENT_DECLARED_SCOPE_BINDING=false
CANDIDATE_RECEIPT_OPTIONAL_SCHEMA_REGISTERED=true
CANDIDATE_RECEIPT_SCHEMA_EXACT_VALIDATION=PASS

CROSS_PROJECT_CONFIRM=REJECTED
CROSS_SERIES_CONFIRM=REJECTED
FOREIGN_WORKSPACE_CONFIRM=REJECTED
CHANGED_CANDIDATE_CONTENT=REJECTED
STALE_SOURCE_CONTEXT=REJECTED
UNISSUED_CANDIDATE=REJECTED

CURRENT_FRONTEND_BODY_WITHOUT_CANDIDATE_REF=SUPPORTED_SECURELY
CANDIDATE_RECEIPT_SQLITE_RESTART=PASS
CANDIDATE_RECEIPT_TAMPER_REJECTION=PASS

CANDIDATE_RECEIPT_IS_CANONICAL_FACT=false
CANDIDATE_RECEIPT_GRANTS_AUTHORITY=false
PUBLICATION_ALLOWED=false

GLOBAL_LIFECYCLE_SCHEMA_VERSION_DIFF=0
LIFECYCLE_INTEGRITY_SQLITE_SCHEMA_DIFF=0
LIFECYCLE_INTEGRITY_MIGRATION_DIFF=0
LIFECYCLE_COMPOSITION_DIFF=0
V5_SERIES_PLAN_TABLE_DIFF=0
V5_SERIES_PLAN_AUTHORITY_DUPLICATED=false
DATABASE_SCHEMA_DIFF=ADDITIVE_OPTIONAL_APPLICATION_CANDIDATE_RECEIPT_COMPONENT_ONLY

F4_FRONTEND_VECTOR_CLOSED=true
F4_CORE_VECTOR_CLOSED=true
F4_CORE_CANDIDATE_SOURCE_BINDING=CLOSED
F4_FULLY_CLOSED=true
```

## Candidate provenance boundary

Successful Series Director generation now atomically issues an append-only receipt
with schema `creator.series-plan-candidate-receipt.v1`. The server-owned opaque
`candidateRef` binds authenticated workspace, content profile, Project, Series,
source Project/Series versions, the canonical trusted source context and canonical
candidate content. Raw `creativeInput` is never persisted; only its SHA-256 digest is
stored.

Confirmation rebuilds the trusted context through Project Context. With
`candidateRef`, Core performs an exact workspace/ref lookup. Without it, the existing
Frontend body is accepted only when one exact receipt matches workspace, Project,
Series, source-context digest and candidate digest. Core reparses and validates the
stored candidate and passes that value—not the client object—to the unchanged V5
Series Planning confirmation boundary.

The receipt table, unique lookup index and marker form an optional, exact-validated
component in the same Creator SQLite file. Series Intelligence continues to reject
partial receipt schemas and undeclared tables, indexes, views and triggers. The
component is application provenance only: it does not create a Series Plan, grant an
approval or duplicate canonical V5 authority.

## Evidence boundary

Focused unit, contract and real HTTP tests cover standalone/no-Series rejection,
server recovery, explicit and current-Frontend confirmation shapes, unissued and
cross-scope candidates, foreign-workspace non-disclosure, content/source staleness,
receipt write failure, strict Provider integers, exact optional-schema combinations,
DDL/row tampering and a full close/reopen server sequence. The restart path invokes
normal Lifecycle/M6 closed-world validation before reopening the receipt store.

```text
PR_C_RECOVERABLE_PROJECT_CREATION=NOT_STARTED
M12_C3_LOCAL_VM_LINE=PAUSED
NEXT_TASK=ACS-CORE-RECOVERABLE-PROJECT-FOUNDATION-COMMAND-C
```
