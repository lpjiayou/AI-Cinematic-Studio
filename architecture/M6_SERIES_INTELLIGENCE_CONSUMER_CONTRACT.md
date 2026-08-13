# M6 Series Intelligence Consumer and Reconciliation Contract

> Status: `PROPOSED FOR PROJECT LEAD REVIEW / NO IMPLEMENTATION AUTHORITY`
>
> Proposed authority: `ADR-0005`
>
> Proposal base: `8227c6c616140824fd70de920dc6fcf459bb734d`
>
> Work package: `M6-P3-G0`

## 1. Purpose

This proposal defines how a downstream Core domain may consume the active M6 Series
Intelligence baseline without copying or taking ownership of M6 facts. It freezes a
candidate Ref/Digest, Scope, staleness and reconciliation contract for review.

M6-P3-G0 is governance-only. Every item below is proposed, not implemented or
authorized.

## 2. Owners and first direct consumer

| Fact or responsibility | Authoritative owner |
| --- | --- |
| SeriesPlanVersion and digest | M5 Series Planning |
| Project identity and Project-to-Series context | M4 Project Context |
| Series/Episode identity and Series-to-Episode membership | M2 Episode |
| Proposed EpisodePlanItemBinding and resolver inside an exact SeriesPlanVersion | M5 Series Planning |
| SeriesBible, CharacterContinuity and M6BaselineSnapshot | M6 Series Intelligence |
| Script and immutable ScriptVersion | M3 Script Studio |
| ConsistencyValidation, Finding, PASS/WARN/BLOCK and staleness | M7, only after separate authorization |
| AssetRequirement and asset-resolution readiness | M9, only after separate authorization |

The first proposed direct consumer is M3 Script Studio. M4 supplies trusted
Project-to-Series context, M2 supplies Series-to-Episode membership and a future M5
versioned binding would resolve the EpisodePlanItem inside an exact plan version. None
may persist a duplicate M6 baseline. M7 and M9 are named future consumers only so that
ownership and lineage are not redefined later.

## 3. Proposed consumer port

The future internal port is conceptually:

```text
ActiveM6BaselineReader
  get_active_episode_baseline(
    workspaceRef,
    projectRef,
    seriesRef,
    episodeRef
  )
  → M6EpisodeBaselineInput
```

The port is:

- read-only;
- internal to Core;
- persistence-neutral;
- authority-aware;
- coherent across the M5 source and M6 active baseline;
- identical in domain meaning for InMemory and SQLite adapters.

It is not an HTTP endpoint, external DTO, raw repository, SQL handle or Outbox
dispatcher.

The only proposed M3 observable read surface for the first consumer slice is:

```text
ScriptStudioPublicBoundary.get_m6_episode_baseline(
  workspaceRef,
  projectRef,
  seriesRef,
  episodeRef
) → M6EpisodeBaselineInput
```

This is an internal Core boundary, not an HTTP or external DTO surface. Existing
`get_workspace`, `create_version`, `confirm_version`, rewrite and storyboard behavior
remain unchanged. The method returns one complete `v5.m6-episode-baseline-input.v1`
object or raises one stable fail-closed domain error; it never returns partial or
typed-null baseline data. M3 accepts no unknown input schema version.

## 4. Complete Scope and trust

The complete key remains:

```text
businessDomain + tenantId + workspaceRef + projectRef + seriesRef
```

An Episode-aware consumer also supplies `episodeRef`, but Episode does not replace or
weaken the five-dimensional M6 Scope. M4 resolves trusted Project-to-Series context;
M2 resolves trusted Series-to-Episode identity and membership; the future M5 binding
resolves the EpisodePlanItem inside the exact plan version. Domain, tenant, actor,
role, Project or Series claims from client payloads are not authority.

Cross-domain, cross-tenant, cross-Workspace, cross-Project or cross-Series resolution
fails closed before any consumer binding is created.

## 5. Proposed EpisodePlanItemBinding prerequisite

The accepted Core has no shared stable key between M2 Episode and M5 EpisodePlanItem:
M2 persists `episodeRef`, while the accepted M5 version persists a distinct
`episodePlanItemRef`. Episode number, title, array position, route text and display name
are explicitly non-authoritative. A read-only resolver over the current records would
therefore have no valid success path.

ADR-0005 proposes a new M5-owned immutable fact embedded in an exact SeriesPlanVersion:

```text
EpisodePlanItemBinding
├── episodeRef
└── episodePlanItemRef
```

The proposed binding contract is:

- the exact v2 top-level field is `episodePlanItemBindings`;
- the v2 candidate has the v1 candidate's closed-world fields plus exactly that one
  field; the v2 version/source projection likewise exposes exactly that field in
  addition to its versioned contract;
- `episodePlanItemBindings` is an array of zero or more closed-world objects, and each
  object has exactly `episodeRef` and `episodePlanItemRef`; unknown fields are rejected;
- each `episodeRef` and each `episodePlanItemRef` occurs at most once in that exact
  SeriesPlanVersion; duplicate identity is rejected;
- `episodePlanItemRef` must exist in that exact version;
- M2 must resolve `episodeRef` as an existing Episode in the same Workspace and Series;
- M4 must resolve the same Project-to-Series relationship;
- the first durable v2 candidate/version write, not a later read, creates the explicit
  association and validates the trusted M2/M4 reads;
- confirmation remains human-gated and revalidates the trusted M2/M4 relationship;
- input order is non-authoritative: normalization sorts bindings by the referenced
  EpisodePlanItem's canonical position in that exact version, then by `episodeRef`;
  the normalized order is used by the stored version, source projection and digest;
- changing, adding or removing a binding creates a new M5 version and never mutates
  history;
- a missing binding for the requested Episode fails closed with
  `m6_episode_mapping_unavailable`.

The proposed versioned payload names are `creator.series-plan.candidate.v2` and
`v5.series-plan-version.v2`; the proposed M6 source projection is
`v5.series-plan.m6-source-snapshot.v2` and carries the binding set in its canonical
digest. These are data-contract versions, not permission to change the SQLite schema.
Accepted v1 records remain valid historical facts but are `UNBOUND` for Episode-level
M6 consumption. They are never inferred or backfilled. A compatible v2 version must be
created and confirmed explicitly.

This binding must be implemented, independently tested, pushed, remote-verified and
Owner Accepted in a separately authorized prerequisite checkpoint before any M6
consumer implementation is authorized. If implementation requires a table, column,
migration or other persistence expansion, execution stops for a separate ADR; the
current proposal does not grant that authority.

Every stored M5 version containing a binding, including historical versions, creates
a lifecycle dependency on the referenced M2 Episode. Episode deletion preserves the
existing precedence `not-found → dependent_script_exists`, then checks the M5 binding
and returns stable `dependent_series_plan_binding_exists`. No cascade, inferred
tombstone or dangling binding is allowed. Same refs in another Workspace or Series do
not block deletion. This is a bounded extension of ADR-0002; M2 Episode ownership and
M5 Series Planning ownership do not change.

## 6. Proposed immutable input snapshot

`M6EpisodeBaselineInput` is a closed-world
`v5.m6-episode-baseline-input.v1` object containing exactly:

```text
schemaVersion
businessDomain
tenantId
workspaceRef
projectRef
seriesRef
episodeRef
episodePlanItemRef
m6BaselineSnapshotRef
activationRevision
m6BaselineCanonicalDigest
seriesPlanVersionRef
seriesPlanVersionDigest
seriesBibleVersionRef
seriesBibleVersionDigest
characterContinuityVersionRef
characterContinuityVersionDigest
compatibility
applicableFacts
```

`compatibility` is `CURRENT` only when the active baseline's M5 Ref and Digest match
the current confirmed M5 source in one coherent read. `STALE` and absence are not
readiness.

`m6BaselineCanonicalDigest` equals the authoritative M6BaselineSnapshot
`canonicalDigest`; it does not introduce a third digest definition.

`applicableFacts` has deterministic semantics:

```text
applicableFacts
├── episodePlanItem
├── worldRules[]
├── glossaryTerms[]
├── locations[]
├── factions[]
├── props[]
├── timelineEvents[]
├── visualConstraints[]
├── prohibitedNarrativePatterns[]
├── characters[]
├── stateIntervals[]
└── relationships[]
```

- `episodePlanItem` is the exact bound item from the locked SeriesPlanVersion;
- all eight SeriesBible collections are included from the locked Bible version and
  retain their canonical stable-ref order;
- all CharacterDefinitions are included and sorted by `characterRef`;
- a CharacterStateInterval applies when its start position is less than or equal to
  the bound item position and its exclusive end is null or greater than that position;
- a RelationshipEdge uses the same start-inclusive/end-exclusive rule;
- intervals sort by `intervalRef`; relationships sort by `relationshipRef`;
- an applicable collection may be empty and remains an empty array;
- IdentityBinding is excluded until its separate authority is accepted.

Every item preserves stable refs and source lineage. The consumer must not persist a
mutable local Bible or treat copied text as authority.

## 7. Future M3 binding

A new or rewritten ScriptVersion influenced by M6 must immutably retain a binding
equivalent to:

```text
M6ConsumerBinding
├── projectRef
├── seriesRef
├── episodeRef
├── seriesPlanVersionRef + Digest
├── m6BaselineSnapshotRef + Digest + activationRevision
├── seriesBibleVersionRef + Digest
└── characterContinuityVersionRef + Digest
```

The binding is lineage, not a consistency verdict. Script Studio continues to own the
ScriptVersion. M6 cannot confirm, edit or supersede a ScriptVersion. Adding this
binding to Script persistence is not part of the first proposed read-only G1 slice and
requires separate authorization.

Existing ScriptVersions are historical facts. They remain readable and are not
backfilled with an invented baseline. Any rewrite produces a new ScriptVersion and a
new exact binding.

## 8. Future binding staleness and readiness

For a binding `B` and current M6 active snapshot `A`:

- `CURRENT`: all full-Scope, M5 and M6 component Ref/Digest values match;
- `STALE`: `B` remains historically valid but no longer matches `A` or current M5;
- `MISMATCH`: Scope or immutable lineage is internally inconsistent;
- `UNAVAILABLE`: trusted context, active baseline or required immutable fact cannot be
  resolved.

Only `CURRENT` may enter a future downstream readiness calculation. `STALE` does not
rewrite the ScriptVersion and does not automatically create a replacement.

The first proposed synchronous G1 slice has no persisted ScriptVersion binding and no
binding-evaluation input. It therefore returns only a coherent `CURRENT` input or one
of the fail-closed errors in section 11. It does not evaluate or return `STALE` for a
previously returned DTO. Historical-binding staleness requires a separately accepted
ScriptVersion-binding/evaluation contract and is not a G1 acceptance gate.

M7, not M6 or M3, will own future PASS/WARN/BLOCK, findings and corrected-script
readiness. M9 will own future AssetRequirement and asset-resolution readiness.

## 9. Domain events

The existing M6 events remain:

- `M6BaselineConfirmed`;
- `M6BaselineSuperseded`.

Their accepted envelope continues to carry full Scope, event/aggregate identity,
operation/correlation/causation refs, occurrence time and versioned payload.

An event communicates that authority may have changed. It does not replace an
authoritative read and must not directly mutate historical consumer facts.

No new event type is accepted by this proposed contract. `IdentityBindingChanged`
remains reserved and cannot be emitted while identity authority is unavailable.

Acceptance of ADR-0005 accepts only event-as-notification semantics, not an event
consumer. Event-driven reconciliation, consumer checkpoints, dispatch and
acknowledgement require a new accepted ADR and task and are not part of the first G1
slice.

## 10. Reconciliation semantics

A future event-driven consumer must tolerate:

- duplicate delivery;
- delayed delivery;
- out-of-order delivery;
- a missed event followed by restart;
- redelivery after a consumer crash;
- an event whose aggregate is no longer active.

Reconciliation uses the trusted full Scope to re-read the authoritative active
snapshot, then compares `activationRevision` and Ref/Digest lineage. The event payload
alone is insufficient.

A future durable consumer checkpoint, if separately accepted, must be keyed by full
Scope plus consumer identity and record at least the last reconciled activation
revision and digest. It cannot share identity with the M6 command idempotency table or
be silently added to the P2 schema.

M6-P3-G0 and the first proposed synchronous M3 slice do not implement a dispatcher,
checkpoint table, acknowledgement or broker.

## 11. Proposed stable domain failures

| Code | Meaning |
| --- | --- |
| `m6_baseline_not_available` | No active baseline can be resolved for trusted Scope |
| `m6_baseline_stale` | The active baseline does not match the current confirmed M5 source |
| `m6_lineage_mismatch` | Scope, Ref or Digest lineage is inconsistent |
| `m6_consumer_authority_unavailable` | Trusted consumer Scope/context is unavailable |
| `m6_episode_mapping_unavailable` | Episode cannot be authoritatively mapped to an EpisodePlanItem in the locked M5 source |
| `m6_reconciliation_required` | Reserved for a later event-driven slice; not returned by the first synchronous G1 slice |

These are proposed internal domain meanings. HTTP status, public DTO and UI copy are
out of scope.

## 12. Proposed two-checkpoint implementation sequence

ADR acceptance would authorize no implementation. The smallest safe future sequence
has two independently authorized and accepted checkpoints.

### 12.1 Binding prerequisite — `ACS-M6-P3-B1`

This checkpoint would only implement the M5 `EpisodePlanItemBinding` v2 data contract,
trusted M2/M4 validation, immutable-version behavior and source projection. It would
not implement the M6 reader or any M3 consumer.

Its proposed maximum file allowlist is:

```text
services/v5_core_os/series_planning/foundation.py
services/v5_core_os/series_planning/public.py
services/v5_core_os/series_episode/foundation.py
services/v5_core_os/series_intelligence/record_integrity.py
services/v5_core_os/lifecycle_integrity/composition.py
services/v5_core_os/lifecycle_integrity/coordinator.py
tests/unit/test_series_planning_m5.py
tests/unit/test_deletion_lifecycle_integrity.py
tests/contract/test_creator_series_episode_contract.py
tests/contract/test_creator_series_planning_contract.py
tests/contract/test_creator_series_intelligence_sqlite_contract.py
tests/integration/test_creator_series_planning.py
tests/integration/test_creator_series_intelligence.py
tests/integration/test_creator_series_intelligence_sqlite_p2.py
tests/integration/test_creator_lifecycle_sqlite_p2.py
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md
governance/ADR-0005-m6-series-intelligence-consumer-boundary.md
governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md
```

The M6 integrity file is allowed only to validate/recompute the M5 v2 source projection
and digest for existing durable M6 facts; it may not add consumer behavior. The
Series/Episode foundation is allowed only to add
`dependent_series_plan_binding_exists` to the stable lifecycle dependency-error set;
the Series/Episode contract test freezes its existing public `409` mapping. B1 permits
no M2 identity/write-model change, SQLite table/column/marker/migration, M6 consumer,
M3 change, Public HTTP or Frontend change. A later authorization may narrow this list;
widening it requires explicit Project Lead review.

### 12.2 Read-only consumer — `ACS-M6-P3-G1`

Only after B1 is Owner Accepted and a compatible bound M5/M6 test baseline exists may
a separate G1 implement:

1. one internal `ActiveM6BaselineReader`;
2. the exact M3 `get_m6_episode_baseline(...)` read surface;
3. current/stale and Episode-applicability resolution;
4. InMemory and temporary-file SQLite parity;
5. no ScriptVersion write, event consumer or M7/M9 behavior.

Its proposed maximum file allowlist is:

```text
services/v5_core_os/series_intelligence/contracts.py
services/v5_core_os/series_intelligence/errors.py
services/v5_core_os/series_intelligence/foundation.py
services/v5_core_os/series_intelligence/public.py
services/v5_core_os/series_intelligence/composition.py
services/v5_core_os/script_studio/foundation.py
services/v5_core_os/script_studio/public.py
services/v5_core_os/lifecycle_integrity/composition.py
tests/unit/test_series_intelligence_consumer_m6_p3.py
tests/contract/test_creator_series_intelligence_consumer_contract.py
tests/integration/test_creator_series_intelligence_consumer.py
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md
governance/ADR-0005-m6-series-intelligence-consumer-boundary.md
governance/ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER.md
```

A later authorization may narrow this list. Widening it requires explicit Project Lead
review. This proposed list permits no `__init__` export, schema/migration, M6 SQLite
adapter, M3 create/confirm/rewrite behavior, ScriptVersion persistence change, public
HTTP/DTO, Frontend, event consumer, dispatcher or checkpoint state. This proposal does
not itself authorize any listed file to change.

## 13. Proposed acceptance gates

### 13.1 Binding prerequisite gates

A separately authorized B1 must prove:

1. explicit v2 bindings are created only in a new M5 candidate/version, validated
   against trusted M2 Episode membership plus M4 Project-to-Series context before the
   first durable write, and revalidated at human-gated confirmation;
2. binding identities are unique within the exact version and never inferred from
   number, title, index, route or name;
3. `episodePlanItemBindings` is closed-world, rejects duplicates/unknown fields and
   normalizes arbitrary input order to EpisodePlanItem position then `episodeRef`;
4. v1 histories remain byte/field stable and unbound; there is no automatic backfill;
5. binding changes create a new immutable version with correct parent lineage;
6. the M5 source v2 digest includes the normalized binding set and is deterministic;
7. Episode deletion is blocked by any historical M5 binding with stable precedence and
   `dependent_series_plan_binding_exists`, while other Workspace/Series refs remain
   isolated; a binding-create/delete race has exactly one valid outcome—either the
   binding commits and deletion is rejected, or deletion commits and binding creation
   fails without a durable binding; rejected deletes and ordinary or pre-commit
   injected failures leave no mutation; rollback failure or commit-outcome uncertainty
   poisons the Assembly and forbids connection reuse until restart re-reads and
   reconciles durable facts; no outcome may leave a partial dependency or orphan;
8. existing M6 source/digest activation semantics accept a valid v2 source without
   weakening v1 history or cross-Scope isolation;
9. InMemory/SQLite behavior and restart agree without SQLite DDL or migration changes;
10. full Core, AST, architecture, secret and diff checks pass; and
11. execution stops after push and remote verification for Project Lead review.

### 13.2 Read-only consumer gates

At minimum, a separately authorized implementation must prove:

1. trusted M4 Project-to-Series context plus trusted M2 Series-to-Episode membership
   resolve the exact full M6 Scope and Episode identity;
2. the accepted M5 binding resolves the exact Episode to one EpisodePlanItem in the
   locked M5 source without number/name inference, while an unbound v1 source fails
   closed;
3. the read-only baseline input fails closed when M6 is absent, stale or mismatched;
4. `ScriptStudioPublicBoundary.get_m6_episode_baseline(...)` is the only new M3 read
   surface, returns exact schema v1 or one stable error, and does not alter
   `get_workspace`, create, confirm or rewrite behavior;
5. applicable facts follow the exact filtering, stable ordering and empty-array rules;
6. existing ScriptVersions remain byte/field stable and are never silently backfilled;
7. same names or copied content cannot resolve identity;
8. cross-business-domain, tenant, Workspace, Project, Series and Episode cases fail
   closed with no write;
9. after M6 baseline replacement, a subsequent read returns the new coherent
   `CURRENT` input while a previously returned DTO remains immutable; this slice does
   not evaluate historical-binding `STALE` state;
10. duplicate/retry reads are deterministic and create no write, operation or event;
11. InMemory/SQLite semantics, restart and coherent-read behavior match;
12. M1-M6-P2 plus accepted B1 full Core regression does not weaken;
13. formal 8765, HTTP/API, Auth/RBAC, Frontend, M7/M9 and M6-P4+ diffs are zero;
14. AST, architecture, secret, `git diff --check`, commit, push and remote equality
    pass;
15. execution stops for Project Lead owner review.

## 14. Explicit exclusions

This proposal does not authorize:

- any production or test implementation;
- M6-P3-B1 binding implementation or M6-P3-G1 consumer implementation;
- modification of existing ScriptVersion persistence;
- consumer checkpoints, schema, migration or formal database work;
- Outbox dispatch, acknowledgement, broker or external bus;
- HTTP/Public API, DTO, Auth/RBAC or Frontend;
- M7 validation, findings, PASS/WARN/BLOCK or script correction;
- M9 AssetRequirement, Identity/Rights/Asset or asset-resolution readiness;
- V4/V3, Provider, GPU, Worker or ComfyUI;
- M6-P4+, M7-M19 implementation or Production Ready status.

## 15. G0 stop rule

After this Proposed contract and ADR-0005 are committed, pushed and remote-verified:

```text
STOP — M6-P3-G0 GOVERNANCE / ARCHITECTURE CHECKPOINT CANDIDATE
OWNER REVIEW PENDING
```

No implementation begins until the Project Lead accepts the architecture decision.
The B1 binding prerequisite must then be separately authorized and accepted before G1
can be separately authorized.
