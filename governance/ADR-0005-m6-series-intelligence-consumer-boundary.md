# ADR-0005 — M6 Series Intelligence Consumer and Reconciliation Boundary

## Metadata

| Field | Value |
| --- | --- |
| Status | `ACCEPTED AS ARCHITECTURE DECISION / UNIMPLEMENTED / NO IMPLEMENTATION AUTHORITY` |
| Created | `2026-08-13` |
| Author | `Codex architecture proposal under Project Lead G3/P3-G0 authority` |
| Approval owners | `Project Lead / Architecture Owner — ACCEPTED; applicable Domain Owners — PENDING FOR AFFECTED IMPLEMENTATION` |
| Decision evidence base | `8227c6c616140824fd70de920dc6fcf459bb734d`; G0 proposal checkpoint `c524486c05c21b270a7dd75e89fae4312430736a` |
| Related task | `ACS-M6-P2-G1-CLOSEOUT-G3 / M6-P3-G0` |
| Extends | `ADR-0002`, `ADR-0003`, `ADR-0004` |
| Supersedes | `None` |

## Context

M6-P0/P1 established SeriesBible, CharacterContinuity, immutable versions, active
M6BaselineSnapshot and ordered domain events. M6-P2 added a local-development durable
SQLite adapter and persistent Outbox. The Project Lead accepted that bounded technical
baseline at `8227c6c616140824fd70de920dc6fcf459bb734d`.

The current Core still has no implemented downstream consumer contract that binds an M3
ScriptVersion, future M7 ConsistencyValidation or future M9 readiness decision to the
exact M6 baseline Ref and Digest. The existing M3 ScriptVersion record predates M6 and
does not contain this lineage. Reading copied Bible content would create a second
authority and would not support deterministic staleness.

The Project Lead-supplied
`AI_CINEMATIC_STUDIO_GLOBAL_ARCHITECTURE_M1-M19_V2.2-R1_2026-08-12.md`, used here as
non-authoritative design input, states in sections 8.11 and 8.14 that M6-P3 covers
M3/M4/M7/M9 integration contracts, domain events and reconciliation, requires P2
acceptance and must not silently implement M7+. The active repository Source-of-Truth,
not that target document, governs authorization.

The Project Lead and Architecture Owner accepted this target architecture on
`2026-08-13`. That acceptance changes the normative architecture only: it creates no
implementation authority. Applicable Domain Owner confirmation remains a prerequisite
for any affected implementation and blocks authorization of M6-P3-B1 until recorded.

## Decision — accepted target architecture

Any future separately authorized implementation shall introduce one internal,
read-only and persistence-neutral `ActiveM6BaselineReader`. The first bounded direct
consumer would be M3 Script Studio
through a read-only Episode baseline input. M4 owns Project identity and trusted
Project-to-Series context. M2 owns Series/Episode identity and Series-to-Episode
membership. The consumer composes those two accepted read boundaries; neither becomes
a second M6 consumer authority.

The accepted target method is conceptually:

```text
get_active_episode_baseline(
  workspaceRef,
  projectRef,
  seriesRef,
  episodeRef
) → M6EpisodeBaselineInput
```

The only first-slice M3 read surface would be
`ScriptStudioPublicBoundary.get_m6_episode_baseline(...)`. It would return exactly one
`v5.m6-episode-baseline-input.v1` object or one stable fail-closed error and would not
change existing workspace, create, confirm, rewrite or storyboard behavior.

`businessDomain` and `tenantId` are not client parameters; the existing trusted M6
Scope authority resolves them.

The port would resolve one immutable `M6EpisodeBaselineInput` for a trusted full
Scope:

```text
businessDomain + tenantId + workspaceRef + projectRef + seriesRef
```

The snapshot would carry, at minimum:

```text
m6BaselineSnapshotRef + activationRevision + m6BaselineCanonicalDigest
seriesPlanVersionRef + seriesPlanVersionDigest
seriesBibleVersionRef + seriesBibleVersionDigest
characterContinuityVersionRef + characterContinuityVersionDigest
episodeRef + episodePlanItemRef
applicable structured Bible/Character/continuity facts with stable refs
```

It would return only confirmed/current compatible lineage or a stable fail-closed
status. Consumers must not persist copied M6 authority. A future Script generation or
rewrite task that creates a new ScriptVersion would need to retain the exact binding
that influenced it, but that write belongs to a later accepted task and is not part of
the first future read-only slice. Existing ScriptVersions remain readable historical
facts and are not backfilled or silently rebound.

M6 applicability uses M5 `episodePlanItemRef`, while M2 owns `episodeRef` and Episode
membership. The accepted records have no common stable key: a read-only resolver alone
cannot produce a valid match without prohibited number/title/index inference.

This ADR therefore assigns M5 Series Planning ownership of a future immutable
`EpisodePlanItemBinding { episodeRef, episodePlanItemRef }` embedded in an exact
SeriesPlanVersion. A new M5 candidate/version would list explicit bindings and confirm
them only after trusted M2 Episode membership and M4 Project-to-Series validation.
Both sides are unique within the exact version. A change creates another immutable M5
version. Existing v1 versions stay historical and unbound; there is no inference or
backfill. Missing binding fails closed.

The exact field is `episodePlanItemBindings`. It is a closed-world array whose items
contain only `episodeRef` and `episodePlanItemRef`; duplicates and unknown fields are
rejected. Input order is normalized to the referenced EpisodePlanItem's position in
the exact plan version, then `episodeRef`, before storage, projection and digest.

Any stored historical M5 version containing a binding prevents deletion of that M2
Episode. This is a bounded extension of ADR-0002's lifecycle-integrity coordinator;
M2/M5 ownership remains unchanged. The stable lifecycle order remains not-found, then
existing Script dependency, then M5 binding dependency with
`dependent_series_plan_binding_exists`. Cross-Scope refs do not block, and no cascade,
tombstone inference or dangling binding is allowed. The first durable v2 write validates
the trusted M2/M4 relationship, and confirmation revalidates it before transition.

The accepted target data contracts are `creator.series-plan.candidate.v2`,
`v5.series-plan-version.v2` and `v5.series-plan.m6-source-snapshot.v2`. This decision
does not authorize those contracts to be implemented and does not authorize a SQLite
schema or migration. The binding prerequisite must be implemented and Owner Accepted
in its own bounded checkpoint before the reader or M3 consumer can be authorized.

`M6BaselineConfirmed` and `M6BaselineSuperseded` remain M6-owned events. A future
consumer may combine ordered event handling with authoritative read-model
reconciliation. The event is a notification, never the sole truth. Reconciliation
must handle missed, duplicate, delayed and out-of-order delivery by re-reading the
authoritative active baseline and comparing activation revision plus digest.

Acceptance of this ADR accepts only those event-as-notification semantics. It does not
accept an event consumer. Event-driven reconciliation, consumer checkpoints,
dispatch and acknowledgement require a new accepted ADR and task and are not part of
the first implementation slice.

The first future implementation slice must remain synchronous/read-only at the M3
boundary unless a later accepted decision explicitly introduces ScriptVersion writes,
dispatcher, checkpoint persistence or asynchronous infrastructure.

## Ownership preserved

- M5 remains sole owner of SeriesPlanVersion and its canonical digest.
- M5 will own the future immutable EpisodePlanItemBinding and resolver inside an
  exact SeriesPlanVersion; M2 retains Series/Episode identity and membership.
- M6 remains sole owner of SeriesBible, CharacterContinuity, active baseline and M6
  event facts.
- M3 remains sole owner of Script and immutable ScriptVersion.
- M4 remains sole owner of Project identity and Project-to-Series context.
- M7, when separately authorized, owns ConsistencyValidation, findings,
  PASS/WARN/BLOCK and validation staleness.
- M9, when separately authorized, owns AssetRequirement and asset-resolution
  readiness.

No consumer may modify M6 history, overwrite a ScriptVersion, infer authority from a
name, or treat an event payload as a mutable local Bible.

## Accepted target fail-closed semantics

Any future separately authorized contract shall distinguish:

- `m6_baseline_not_available` — no active baseline exists;
- `m6_baseline_stale` — active M6 no longer matches the current confirmed M5 source;
- `m6_lineage_mismatch` — Scope, Ref or Digest bindings disagree;
- `m6_consumer_authority_unavailable` — trusted Scope/context cannot be resolved;
- `m6_episode_mapping_unavailable` — no authoritative Episode-to-plan-item mapping is
  available;
- `m6_reconciliation_required` — observed event/checkpoint state cannot prove current
  authority and must be reconciled before readiness; reserved for a later event-driven
  slice and not returned by the first synchronous slice.

Public HTTP codes, UI wording and external DTOs are intentionally not decided here.

## Alternatives

### A. Keep M6 isolated

- Benefit: no current schema or dependency change.
- Cost: M6 cannot influence real Script lineage and remains disconnected from the
  Production Spine.
- Result: not recommended as the long-term direction; it remains the current state
  until a later implementation is separately authorized and completed.

### B. Copy Bible/Character JSON into Script Studio

- Benefit: superficially simple integration.
- Cost: duplicates authority, loses Ref/Digest lineage, breaks deterministic
  staleness and creates cross-tenant risk.
- Result: rejected by this decision.

### C. Internal immutable binding through a read-only port

- Benefit: preserves ownership, supports InMemory/SQLite parity and future
  reconciliation, and closes the next Production Spine edge without HTTP/UI work.
- Cost: future implementation requires an explicit ScriptVersion binding and may
  require a separately accepted persistence migration.
- Result: accepted as the target architecture.

### D. Implement all M3/M4/M7/M9 consumers and Outbox dispatch together

- Benefit: broad integration in one step.
- Cost: crosses multiple unstarted milestones, owners, persistence and security
  boundaries; violates vertical-closure and authorization rules.
- Result: rejected by this decision.

## Consequences of the decision

### Positive

- Future new ScriptVersions could identify the exact M5/M6 facts that influenced
  generation or rewrite after separately authorized implementation.
- M6 baseline changes can make downstream bindings deterministically stale without
  rewriting historical facts.
- M7 and M9 can later consume the same lineage contract without redefining M6
  authority.
- Reconciliation does not depend on perfect event delivery.

### Cost and risk

- M3 currently lacks an M6 binding, so a future implementation must explicitly design
  InMemory and SQLite persistence compatibility.
- Accepted M2 and M5 facts currently lack a shared stable Ref, so a separately accepted
  M5 v2 binding prerequisite must precede consumer implementation.
- Adding a persistent consumer checkpoint, dispatcher or schema migration would
  require its own accepted scope and tests; this decision does not authorize it.
- A broad consumer implementation could accidentally become M7. The first slice must
  stop at a read-only Episode baseline input and must not write a ScriptVersion or
  produce consistency verdicts.

## Future separately authorized implementation sequence

1. Project Lead and Architecture Owner accept this ADR and the normative architecture
   contract in a governance-only checkpoint, push, remote-verify and stop. This step is
   complete as an architecture decision; applicable Domain Owner implementation review
   remains pending.
2. Only after applicable Domain Owner confirmation, the Project Lead may separately
   authorize `ACS-M6-P3-B1` to implement only the M5 v2
   EpisodePlanItemBinding prerequisite and prove v1 historical compatibility.
3. Push, remote-verify and obtain Owner Acceptance for B1; stop if implementation needs
   a SQLite schema/migration or any unlisted path.
4. Only then separately authorize `ACS-M6-P3-G1` to implement the read-only M6 reader
   and exact M3 `get_m6_episode_baseline(...)` surface.
5. Prove InMemory/SQLite parity, cross-Scope isolation, deterministic fact filtering,
   historical immutability and coherent rollover to the new current input after M6
   replacement. Historical ScriptVersion-binding staleness evaluation remains a
   separately accepted later contract and is not part of G1.
6. Stop for Owner Review. M7 and M9 remain separate tasks.

There is no migration or data write in M6-P3-G0. Existing data is unchanged. Neither
B1 nor G1 is authorized by this decision. G1 remains blocked until B1 is independently
implemented, tested, remote-verified and Owner Accepted.

## Explicit exclusions

This decision does not authorize P3-B1 or P3-G1 implementation, production/test code,
schema/migration, consumer
checkpoint storage, Outbox dispatch/acknowledgement, broker integration, HTTP/Public
API/DTO, Auth/RBAC, Frontend, formal port-8765 access, PostgreSQL, M7 verdicts or
correction, M9 AssetRequirement/asset-resolution readiness, Identity/Rights/Asset implementation,
V4/V3, Provider, GPU, Worker, ComfyUI, M6-P4+ or Production Ready status.

## Approval record

| Role | Owner | Decision | Date | Notes |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `ACCEPTED AS ARCHITECTURE` | `2026-08-13` | No implementation authority granted |
| Architecture Owner | `蔺鹏` | `ACCEPTED AS ARCHITECTURE` | `2026-08-13` | Target boundary and two-checkpoint sequence accepted |
| M2/M3/M4/M5/M6/M7/M9 Domain Owners | `PENDING` | `PENDING FOR AFFECTED IMPLEMENTATION` | — | Required before any affected implementation; blocks B1 authorization |

## Change history

| Date | Change | Authority |
| --- | --- | --- |
| `2026-08-13` | Initial Proposed ADR | `ACS-M6-P2-G1-CLOSEOUT-G3 / M6-P3-G0` |
| `2026-08-13` | Accepted as architecture decision; implementation remains unimplemented and unauthorized | `Project Lead / Architecture Owner — M6-P3-G0 Owner Acceptance` |
