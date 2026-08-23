# ADR-0002 — V5 Lifecycle Integrity Boundary

## Document metadata

| Field | Value |
| --- | --- |
| ADR ID | `ADR-0002` |
| Status | `Accepted` |
| Author | `Codex / PRE-M6-RB1.3-R2 proposal` |
| Created | `2026-08-12` |
| Last updated | `2026-08-12` |
| Approval authority | Project Lead / Architecture Owner / Repository Governance Owner `蔺鹏` |
| Related finding | `RB13-F002 — Deletion Lifecycle Integrity` |
| Implementation authority | `PRE-M6-RB1.3-R2-P1 — InMemory Lifecycle Integrity Vertical Slice` |

## Context

The current V5 in-memory Project, Series/Episode and Script repositories are separate
mutable stores. Dependency checks performed before deletion do not share an atomic
boundary with Project relationship creation, Script/ScriptVersion creation or the
actual delete. Concurrent writes can therefore leave Project-to-Series or
Script/ScriptVersion-to-Episode orphans.

This decision preserves V2.3 ownership: domain services continue to own Project,
Series, Episode, Script and immutable Version facts. It does not change public HTTP
endpoints, DTOs, success responses, error codes or the `RESTRICT` deletion policy.

P1 is limited to InMemory behavior. SQLite foreign keys, schema, migration and formal
database access are explicitly outside P1 and require separate R2-P2 authorization.

## Decision

Adopt the following bounded V5 lifecycle boundary:

```text
LifecycleAssembly
├── LifecycleLeaseExecutor
├── LifecycleIntegrityCoordinator
└── domain-owned participants
```

The Assembly creates one identity and one shared InMemory lifecycle state. A lease is
unforgeable by contract and validates issuer identity, assembly identity, active
nonce, owner thread, workspace, operation and state. Forged, expired, nested,
cross-thread, cross-workspace, cross-assembly and terminal leases are rejected.

The Coordinator owns no business facts. It coordinates only:

1. `ProjectSeriesRelationship → Series`;
2. `Script → Episode`;
3. `ScriptVersion → Episode`.

The following operations share the authoritative workspace critical section:

- Project plus optional ProjectSeriesRelationship creation;
- Script plus first ScriptVersion creation;
- ScriptVersion append;
- Episode deletion;
- Series deletion.

Episode deletion checks not-found before Script/ScriptVersion dependencies. Series
deletion checks not-found, then Project dependency, then child Episode Script or
ScriptVersion dependency. `dependent_project_exists` has priority when both dependency
classes exist. Rejected deletion performs no mutation.

InMemory mutation uses `capture pre-image → register idempotent undo → mutate →
commit`. Undo registration failure performs no mutation. Mutation failure restores the
pre-image. Undo failure poisons the Assembly. A poisoned Assembly rejects normal reads,
writes, deletes and new leases; only `diagnostic_snapshot` remains available. A
poisoned Assembly cannot be recovered in place.

Existing standalone factories remain compatibility paths for accepted M1–M5 behavior,
but coordinated lifecycle guarantees apply only to boundaries produced by the accepted
`LifecycleAssembly` factory. P1 tests must prove deterministic race outcomes using
Barrier/Event coordination and must never rely on sleep timing.

## Alternatives

### Keep HTTP pre-checks

Rejected because checks and deletion remain separate and direct V5 calls bypass them.

### Let Series/Episode depend directly on Project and Script domains

Rejected because it reverses ownership direction and makes Series/Episode own foreign
domain facts.

### Cascade deletion

Rejected because it destroys accepted production lineage. The frozen policy is
`RESTRICT`.

## Consequences

- InMemory boundaries assembled together gain one atomic lifecycle critical section.
- Direct domain repositories remain domain fact owners and receive lease-aware internal
  participant operations rather than cross-domain dependencies.
- Public errors retain `dependent_project_exists` and `dependent_script_exists`, both
  mapped to HTTP 409.
- SQLite remains unchanged in P1; full backend parity is not claimed until R2-P2.
- P1 does not close `RB13-F002`, RB1.3, Architecture Review or authorize M6/M7.

## Verification

P1 must cover lease rejection, workspace isolation, deterministic dependency-write vs
delete ordering, no-orphan postconditions, error priority, complete rollback and the
POISONED state, followed by affected and full Core regression.

## Approval record

| Role | Assignee | Decision | Date | Scope |
| --- | --- | --- | --- | --- |
| Project Lead | 蔺鹏 | `ACCEPT` | `2026-08-12` | ADR-0002 and bounded R2-P1 |
| Architecture Owner | 蔺鹏 | `ACCEPT` | `2026-08-12` | LifecycleAssembly/Lease/Coordinator design |
| Repository Governance Owner | 蔺鹏 | `ACCEPT` | `2026-08-12` | Governance checkpoint and P1 branch |

Acceptance authorizes only bounded R2-P1 implementation. R2-P2, formal SQLite
migration, RB1.3 closeout, M6 and M7 remain unauthorized.
