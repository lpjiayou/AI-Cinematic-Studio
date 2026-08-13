# M6 Series Intelligence Durable SQLite Contract

> Status: `ACCEPTED FOR BOUNDED M6-P2 IMPLEMENTATION`
>
> Authority: `ADR-0004`
>
> Implementation Base: `e38c75aa4ff26bdea80c82d8a24096f799dad860`

## 1. Purpose and ownership

M6-P2 adds local-development durable persistence to the already accepted M6 domain.
V5 continues to own SeriesBible, CharacterContinuity, immutable versions,
M6BaselineSnapshot and Outbox facts. M5 remains the sole owner of SeriesPlan and its
confirmed digest. SQLite is an adapter and does not become a domain authority.

```text
SeriesIntelligencePublicBoundary
→ persistence-neutral service/repository contracts
→ SqliteSeriesIntelligenceAdapter
→ accepted SqliteLifecycleState transaction
```

## 2. Complete Scope

The authoritative key is:

```text
businessDomain + tenantId + workspaceRef + projectRef + seriesRef
```

The complete key must appear in all M6 roots, versions, snapshots, durable operations
and durable Outbox rows. All M6-internal uniqueness and foreign-key relationships must
retain the full key. Same refs in a different dimension are different facts and must
not collide or resolve across Scope.

Commands still provide only Workspace/Project/Series refs. Trusted Authority Ports
resolve business domain, tenant and verified approval/identity context. Defaults fail
closed. P2 must not introduce client-authoritative domain, tenant, actor or approval
fields.

## 3. M5 source relationship

M5 currently stores Workspace/Project/Series/Plan identity but not businessDomain or
tenantId. P2 must not add tenancy columns across M1-M5.

The M6-to-M5 database relationship uses the strongest accepted M5 composite identity:

```text
workspaceRef + projectRef + seriesRef + seriesPlanRef + seriesPlanVersionRef
```

and the immutable digest stored in M6. Trusted Scope resolution enforces the remaining
M6 Scope dimensions. Create/confirm/activate operations re-read the current confirmed
M5 source ref and digest through the same lifecycle lease and SQLite connection before
writing M6 state. A source switch between validation and activation must reject the
operation atomically.

For SQLite foreign-key eligibility, P2 adds this exact unique parent key to
`v5_series_plan_versions`:

```text
UNIQUE(
  workspace_ref,
  project_ref,
  series_ref,
  series_plan_ref,
  series_plan_version_ref
)
```

Every durable M6 source foreign key references those same five columns in that order.
Separate partial foreign keys are forbidden because they could admit a split
Project/Series and Plan/Version identity. Digest validation is an additional
transaction-time canonical comparison, not a substitute for the composite foreign
key.

## 4. Required durable facts

The SQLite schema must persist at least:

- one M6 schema marker;
- SeriesBible roots and immutable versions;
- CharacterContinuity roots and immutable versions;
- M6BaselineSnapshots and their ACTIVE/SUPERSEDED lifecycle;
- durable idempotency operations and deterministic results;
- durable ordered Outbox envelopes.

Canonical immutable content may be stored as validated canonical JSON. The following
remain separately queryable and constrained columns: complete Scope, stable/root/version
refs, revision/version number, parent ref, status, source plan ref/digest, source Bible
ref/digest, component refs/digests, activation revision and canonical digest.

## 5. Database invariants

- exactly one Bible root and Character root per complete Scope;
- version numbers and stable refs are unique inside their complete root Scope;
- parent version refs resolve inside the same complete Scope and root;
- Character versions resolve their exact source Bible ref and digest;
- baseline component refs and source refs resolve inside the same complete Scope;
- at most one ACTIVE baseline exists per complete Scope;
- replacement preserves the old snapshot as SUPERSEDED;
- confirmed/superseded history is immutable and has no hard-delete API;
- all lineage foreign keys use `RESTRICT` or `NO ACTION`, never cascading historical
  deletion;
- non-empty `ipUniverseRef` and IdentityBinding remain fail-closed under the P1 rules.

## 6. Shared transaction

Every write runs under one accepted `SqliteLifecycleState` lease. Repositories must use
the lease connection rather than opening a second connection.

The transaction atomically covers:

```text
M5 source re-read
+ M6 facts/root/version/snapshot changes
+ durable operation result
+ durable ordered Outbox
```

Activation replacement inserts the Superseded event before the Confirmed event. Event
positions are monotonically assigned within the durable Outbox. No dispatcher,
delivery acknowledgement or external broker is part of P2.

Ordinary exceptions roll back every element. Commit outcome uncertainty or rollback
failure poisons the Assembly; later leases fail closed. The database adapter translates
SQLite exceptions to the existing M6 domain error contract.

The lifecycle state exposes one persistence-neutral mutation operation used by both
InMemory and SQLite. The M6 boundary must not depend on an InMemory-only
`apply_preimaged` method. The transaction-time M5 source reader belongs to the same
LifecycleAssembly and must use the active lease connection; a separately opened M5
connection is forbidden.

## 7. Idempotency and concurrency

Durable operation identity is the complete Scope plus `idempotencyKey`. Each record
stores operation type, input digest and deterministic result.

- same key and same input after restart returns the stored result and emits no event;
- same key with different input returns `idempotency_conflict`;
- expected revision permits exactly one winner under competing Assemblies;
- concurrent activation permits exactly one ACTIVE baseline;
- same refs in different Scope dimensions remain isolated;
- M5 confirmation/source switching cannot create an M6 baseline with stale lineage.

The Outbox position is a database-wide monotonically increasing `INTEGER PRIMARY KEY`.
Every Outbox row also carries the complete M6 Scope; Scope-local reads preserve the
global committed order. Snapshot activation additionally enforces
`UNIQUE(complete Scope, activationRevision)` and a partial unique index over complete
Scope where status is `ACTIVE`.

## 8. Migration

M6 is an additive component schema. These four accepted Lifecycle marker rows remain
at version `2`:

- `v5_series_episode_schema`;
- `v5_project_schema`;
- `v5_script_studio_schema`;
- `v5_series_planning_schema`.

P2 adds exactly:

```text
v5_series_intelligence_schema(
  component = 'series_intelligence',
  schema_version = 1
)
```

It must not introduce a global Lifecycle V3. The additive schema migration is one
atomic operation supporting:

1. fresh temporary database creation;
2. upgrade from accepted Lifecycle SQLite V2 to Lifecycle V2 plus M6 marker v1;
3. repeat execution of Lifecycle V2 plus M6 marker v1 as a validated no-op.

Before replacement, migration validates required tables, schema markers, row counts,
orphans and the strongest available scope/lineage relationships. Unsupported, partial,
orphaned or inconsistent input fails closed. Faults after copy, before marker update,
before verification and before commit leave the previous schema and data intact.

After migration:

```text
PRAGMA foreign_keys = 1
PRAGMA foreign_key_check = empty
PRAGMA integrity_check = ok
```

The V2 upgrade preserves all M1-M5 rows and fields. P1 was InMemory-only, so migration
must not claim or attempt an InMemory-to-SQLite import. Once initialized, M6 durable
rows must survive restart and repeated no-op migration unchanged.

Only temporary file databases are authorized. The formal port-8765 database must not
be opened, copied, migrated, deployed or used as evidence.

## 9. Delete and lifecycle integrity

Series, M5 Plan/Version, Bible/Character roots and versions, and M6 baseline snapshots
must not be physically deleted while protected lineage exists. Any M5 SeriesPlan root
or version and any M6 root, version or snapshot is a dependency, regardless of draft,
active or superseded status.

Series deletion preserves the accepted ADR-0002 checks and extends their stable
priority in this exact order:

```text
not_found
→ dependent_project_exists
→ dependent_script_exists
→ dependent_series_plan_exists
→ dependent_m6_series_intelligence_exists
```

Database `RESTRICT/NO ACTION` is the final guard. Every `IntegrityError` is mapped to
one applicable stable domain error; raw SQL, table, index and FK details never cross
the public boundary.

Identity/Asset/Rights revocation, when those authorities exist, changes current
readiness and does not cascade-delete historical M6 lineage.

## 10. Implementation scope

Allowed production paths are limited to:

- `services/v5_core_os/series_intelligence/` persistence-neutral contract,
  composition and SQLite adapter/schema/migration work;
- `services/v5_core_os/lifecycle_integrity/` composition, operation enum, SQLite
  schema/migration/state integration and M6 lifecycle dependency checks;
- `services/v5_core_os/series_episode/foundation.py` only if required to map an M6
  delete dependency to the accepted domain error contract.

Allowed tests are M6 unit/contract/integration tests and lifecycle SQLite integration
tests. Source-of-Truth documents may be synchronized only for this bounded task.

Forbidden paths/capabilities include Creator server HTTP endpoints, public DTOs,
Auth/RBAC/Permission, Frontend, M3/M4/M7/M9 consumers, Identity/Asset/Rights
implementation, V4/V3, Provider, GPU, Worker, ComfyUI, formal database deployment and
M6-P3+.

## 11. Acceptance gates

M6-P2 is a checkpoint candidate only when all gates pass:

1. fresh, V2 upgrade and repeated no-op migration on temporary file SQLite;
2. V2 upgrade preserves valid existing M1-M5 data byte-for-byte or field-for-field;
   M6 durable data survives restart and repeated no-op migration unchanged;
3. partial/unsupported/orphan/cross-scope migration input fails without schema, marker
   or row-count changes;
4. InMemory/SQLite contract parity for Bible, Character, lifecycle, lineage, digest,
   activation, supersession and read projections;
5. restart roundtrip for every M6 durable fact;
6. restart idempotency replay and different-input conflict across full Scope;
7. fact/operation/Outbox atomicity under injected version, snapshot, Outbox, migration,
   commit and rollback failures;
8. commit uncertainty and rollback failure poison the Assembly;
9. cross-connection/cross-Assembly concurrency has one revision winner and one ACTIVE
   baseline, with no stale M5 activation;
10. Series/M5/M6 deletion constraints create no orphan, cascade loss or raw SQL leak;
11. durable Outbox order, uniqueness and restart persistence;
12. `foreign_keys=1`, empty `foreign_key_check` and `integrity_check=ok`;
13. M1-M6/P1 and R2 full Core regression passes without weakening tests;
14. Python AST, architecture, secret and `git diff --check` pass;
15. formal 8765, Frontend, HTTP/API, M6-P3+ and M7+ diffs are zero.

## 12. Stop rule

After the M6-P2 implementation checkpoint is pushed and remote-verified, stop and
report `CHECKPOINT CANDIDATE / OWNER REVIEW PENDING`. Do not enter M6-P3 or M7.
