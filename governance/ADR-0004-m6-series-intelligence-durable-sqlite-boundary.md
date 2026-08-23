# ADR-0004 — M6 Series Intelligence Durable SQLite Boundary

## Metadata

| Field | Value |
| --- | --- |
| Status | `ACCEPTED FOR BOUNDED M6-P2 IMPLEMENTATION` |
| Decision date | `2026-08-13` |
| Project Lead / Architecture Owner / Repository Governance Owner | `蔺鹏` |
| Accepted implementation base | `e38c75aa4ff26bdea80c82d8a24096f799dad860` |
| Authorized implementation | `M6-P2 local-development SQLite only` |
| Extends | `ADR-0002`, `ADR-0003` |

## Context

ADR-0003 accepted the bounded M6 domain and an InMemory implementation. M6-P1 proved
the domain lifecycle, immutable versions, canonical digests, trusted authorities,
atomic baseline activation and ordered Outbox semantics, but intentionally excluded
durable persistence.

The next vertical slice must preserve those semantics across restart and concurrent
SQLite Assemblies without moving persistence rules into the domain, trusting client
scope, changing M1-M5 authority or touching the formal database.

## Decision

Add one local-development durable SQLite adapter for the existing M6 repository,
operation registry and Outbox contracts. It participates in the accepted
`SqliteLifecycleState` lease so that M6 facts, idempotency result and Outbox envelopes
commit through the same `BEGIN IMMEDIATE` transaction.

The domain and public boundary remain persistence-neutral. InMemory and SQLite must
pass the same repository/public-boundary contract tests.

The complete M6 Scope is:

```text
businessDomain + tenantId + workspaceRef + projectRef + seriesRef
```

Every M6 root, version, baseline, operation and Outbox key carries this complete Scope.
Internal M6 foreign keys use the complete Scope. Existing M5 tables do not yet own
`businessDomain` or `tenantId`; M6-P2 must not rewrite M1-M5 tenancy. The M6-to-M5
relationship therefore uses the strongest existing M5 Workspace/Project/Series/Plan
key, while trusted Scope authority and transaction-time M5 source re-read enforce the
full M6 Scope and close TOCTOU.

Immutable structured M6 facts may remain canonical JSON payloads. Scope, root and
version identities, lineage, lifecycle state, revisions, source refs/digests and
activation state are separately constrained columns. This avoids premature
normalization into many fact tables while preserving deterministic content digests.

## Transaction and failure semantics

- all writes require an active accepted lifecycle lease;
- SQLite uses `BEGIN IMMEDIATE` and foreign keys on every connection;
- activation re-reads the confirmed M5 source ref and digest inside that transaction;
- M6 facts, operation result and ordered Outbox commit atomically;
- one partial unique constraint permits at most one ACTIVE baseline per complete Scope;
- all lineage foreign keys use `RESTRICT` or `NO ACTION`;
- confirmed/superseded versions and snapshots have no physical-delete API;
- ordinary failure rolls back without partial facts, operations or events;
- rollback failure or uncertain commit poisons the Assembly and the connection is not
  reused;
- raw SQL, constraint and foreign-key errors are mapped to stable domain errors.

## Migration

M6 uses an additive component marker rather than a global Lifecycle V3. The four
accepted M1-M5 Lifecycle marker rows remain exactly at version `2`; the migration adds
`v5_series_intelligence_schema(component='series_intelligence', schema_version=1)`.
This prevents the existing M1-M5 SQLite adapters from rejecting an otherwise
compatible database.

The additive migration atomically creates the M6 schema and adds a five-column unique
parent key on `v5_series_plan_versions`:

```text
workspace_ref + project_ref + series_ref
+ series_plan_ref + series_plan_version_ref
```

Every durable M6 source relationship references that exact key. The same
LifecycleAssembly and lease connection also re-read the M5 version and recompute its
canonical digest before an M6 confirmation or activation can commit.

Supported paths are fresh creation, additive upgrade from accepted Lifecycle V2 plus
M6-uninitialized state, and repeated no-op validation of Lifecycle V2 plus M6 marker
v1. The V2 upgrade preserves every M1-M5 row and field; durable M6 data preservation
is proven by restart and repeated no-op validation after M6 initialization. There is
no InMemory-P1-to-SQLite import. Unsupported, partial, orphaned or cross-scope legacy
data fails closed without changing schema markers or row counts.

All migration tests use temporary file databases. The formal port-8765 database is not
an input, test fixture, migration target or deployment target.

## Durable operation and Outbox

The idempotency identity is the complete Scope plus `idempotencyKey`. The durable
record stores input digest and deterministic result so retry after restart returns the
original result and a different input produces `idempotency_conflict`.

The durable Outbox stores the ADR-0003 envelope and a transaction-assigned ordered
position. Baseline replacement persists `M6BaselineSuperseded` before
`M6BaselineConfirmed`. M6-P2 does not implement dispatch, acknowledgement, consumer
state or external messaging.

## Consequences

- M6 can restart without losing immutable versions, the active baseline, idempotency
  results or Outbox order.
- Cross-connection serialization and database constraints become part of the M6
  acceptance evidence.
- SQLite remains a local-development adapter, not the Production database.
- A future PostgreSQL adapter can implement the same contracts without changing M6
  domain semantics.
- M6-P3 consumers and M7 remain separate, unauthorized work.

## Deletion priority

Any M5 SeriesPlan/root/version or M6 Bible/Character root/version/snapshot lineage
blocks physical Series deletion. The stable evaluation order extends, but does not
reorder, ADR-0002:

```text
not_found
→ dependent_project_exists
→ dependent_script_exists
→ dependent_series_plan_exists
→ dependent_m6_series_intelligence_exists
```

Database `RESTRICT` is the final guard. SQLite and foreign-key details never cross the
domain boundary.

## Exclusions

This decision does not authorize formal database access/deployment, PostgreSQL,
Public API/HTTP DTO, Auth/RBAC, Frontend, M3/M4/M7/M9 consumers, Outbox dispatch,
Identity/Asset/Rights implementation, V4/V3, Provider, GPU, Worker, ComfyUI, M6-P3+
or Production Ready status.

The normative implementation and acceptance detail is
[`M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md`](../architecture/M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md).
