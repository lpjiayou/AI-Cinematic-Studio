# M6 Series Intelligence Consumer and Reconciliation Contract

> Status: `ACCEPTED NORMATIVE ARCHITECTURE / B1 BOUNDED IMPLEMENTATION AUTHORIZED / G1 UNAUTHORIZED`
>
> Authority: `ADR-0005 — ACCEPTED AS ARCHITECTURE DECISION`
>
> Evidence base: `8227c6c616140824fd70de920dc6fcf459bb734d`; G0 proposal checkpoint `c524486c05c21b270a7dd75e89fae4312430736a`
>
> Work package: `ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING`
>
> Owner HTTP clarification: `EXISTING CANONICAL V2 PROJECTION RETURNED BY WORKSPACE VERSIONS PASSES THROUGH episodePlanItemBindings / MANUAL AND BOOTSTRAP V1 BEHAVIOR UNCHANGED / NO ROUTE-HANDLER-EXTERNAL-DTO SOURCE CHANGE / NO OTHER HTTP EXPANSION`

## 1. Purpose

This accepted architecture contract defines how any future separately authorized
downstream Core domain implementation shall consume the active M6 Series Intelligence
baseline without copying or taking ownership of M6 facts. It freezes the normative
target Ref/Digest, Scope, staleness and reconciliation boundary.

M6-P3-G0 was governance-only. The later B1 authorization permits only the exact
EpisodePlanItemBinding prerequisite, version policy and frozen files recorded in
section 12.1 after the governance checkpoint is remote-verified. Every consumer type,
method and implementation item outside B1 remains unimplemented and unauthorized.

## 2. Owners and first direct consumer

| Fact or responsibility | Authoritative owner |
| --- | --- |
| SeriesPlanVersion and digest | M5 Series Planning |
| Project identity and Project-to-Series context | M4 Project Context |
| Series/Episode identity and Series-to-Episode membership | M2 Episode |
| Future EpisodePlanItemBinding and resolver inside an exact SeriesPlanVersion | M5 Series Planning |
| SeriesBible, CharacterContinuity and M6BaselineSnapshot | M6 Series Intelligence |
| Script and immutable ScriptVersion | M3 Script Studio |
| ConsistencyValidation, Finding, PASS/WARN/BLOCK and staleness | M7, only after separate authorization |
| AssetRequirement and asset-resolution readiness | M9, only after separate authorization |

The first target direct consumer is M3 Script Studio. M4 supplies trusted
Project-to-Series context, M2 supplies Series-to-Episode membership and a future M5
versioned binding would resolve the EpisodePlanItem inside an exact plan version. None
may persist a duplicate M6 baseline. M7 and M9 are named future consumers only so that
ownership and lineage are not redefined later.

## 3. Accepted target consumer port

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

The only accepted target M3 observable read surface for the first future consumer
slice is:

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

## 5. Accepted EpisodePlanItemBinding prerequisite architecture

The accepted Core has no shared stable key between M2 Episode and M5 EpisodePlanItem:
M2 persists `episodeRef`, while the accepted M5 version persists a distinct
`episodePlanItemRef`. Episode number, title, array position, route text and display name
are explicitly non-authoritative. A read-only resolver over the current records would
therefore have no valid success path.

ADR-0005 defines a future M5-owned immutable fact embedded in an exact
SeriesPlanVersion:

```text
EpisodePlanItemBinding
├── episodeRef
└── episodePlanItemRef
```

The authorized bounded B1 binding implementation shall satisfy:

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

The accepted target versioned payload names are `creator.series-plan.candidate.v2` and
`v5.series-plan-version.v2`; the accepted target M6 source projection is
`v5.series-plan.m6-source-snapshot.v2` and carries the binding set in its canonical
digest. These are data-contract versions, not permission to change the SQLite schema.
Accepted v1 records remain valid historical facts but are `UNBOUND` for Episode-level
M6 consumption. They are never inferred or backfilled. A compatible v2 version must be
created and confirmed explicitly.

B1 adds only the Core operation `create_episode_plan_item_binding_version`. Initial
plan creation remains v1. The exact allowed transitions are v1→v1, explicit v1→v2 and
v2→v2. A v2→v1 downgrade is forbidden. Unbinding must create an explicit new v2
version and may not mutate or downgrade an existing version. The operation is not an
HTTP route, handler or external DTO. Owner clarification: this does not hide a stored
v2 version from the existing HTTP workspace versions projection. Without changing any
route, handler or external DTO source file, that projection may and shall include
`episodePlanItemBindings` when it serializes a canonical v2 version. No other HTTP
response, including manual-version, receives v2 authority from this clarification.

The operation contract is closed-world:

```text
create_episode_plan_item_binding_version({
  workspaceRef,
  projectRef,
  seriesRef,
  seriesPlanRef,
  expectedPlanVersion,
  episodePlanItemBindings
}) -> {plan, version}
```

Those six command fields are exact. `humanConfirmed`, `content` and unknown fields
are rejected. `episodePlanItemBindings` is the complete desired replacement set;
`[]` explicitly unbinds in a new v2 draft. Confirmation remains a separate,
human-gated operation.

`confirm_candidate` always creates v1. Existing `create_manual_version` remains the
v1→v1 non-binding edit path and rejects a current v2 version without a durable write.
It cannot create, replace, remove, remap or return bindings. Only
`create_episode_plan_item_binding_version` may create v1→v2 or v2→v2 versions and
change that set, including explicit unbinding. Trusted M2/M4 context is validated
before each v2 durable write and the stored binding set is revalidated before
confirmation.

All v2 mutation and confirmation behavior requires the accepted lifecycle-bound
`LifecycleAssembly`. Standalone or independently composed compatibility boundaries
fail closed with `lifecycle_unavailable / 503`. The write reuses the existing
`LifecycleOperation.APPEND_SERIES_PLAN_VERSION`; B1 adds no lifecycle operation or
enum value.

This binding must be implemented, independently tested, pushed, remote-verified and
Owner Accepted in the bounded B1 prerequisite checkpoint before any M6 consumer
implementation is authorized. If implementation requires a table, column, marker,
migration or other persistence expansion beyond existing SQLite `content_json`,
execution stops for a separate ADR; B1 grants no such authority.

Every stored M5 version containing a binding, including historical versions, creates
a lifecycle dependency on the referenced M2 Episode. Episode deletion preserves the
existing precedence `not-found → dependent_script_exists`, then checks the M5 binding
and returns stable `dependent_series_plan_binding_exists`. No cascade, inferred
tombstone or dangling binding is allowed. Same refs in another Workspace or Series do
not block deletion. This is a bounded extension of ADR-0002; M2 Episode ownership and
M5 Series Planning ownership do not change.

The dependency read covers all exact-scope historical v2 versions, including draft,
current and confirmed records. Malformed, unknown or unreadable relevant-scope version
data is fail-closed: it cannot return false and is conservatively reported as
`dependent_series_plan_binding_exists / 409`. A later explicit unbind does not erase
the dependency created by an older bound version. Other Workspace/Series data remains
isolated.

Version dispatch uses `SeriesPlanVersionRecord.schemaVersion` and its durable SQLite
`schema_version` projection, never the presence or absence of a binding field. v1
content bytes, fields, source projection and digest remain unchanged and are never
rewritten. A v2 M5 source snapshot adds only the normalized binding set to the v2
digest. SQLite reads/writes only existing `content_json`, uses strict Python JSON
validation without JSON1, and changes no DDL, table, column, index, marker or migration.
M6 `record_integrity` is limited to validating/recomputing the v1/v2 M5 source digest;
it adds no consumer behavior.

The binding-aware v2 result and M5 source snapshot remain owned by Core. The existing
HTTP workspace versions projection passes through stored canonical versions. When it
returns v2, its version object includes `episodePlanItemBindings`; when it returns v1,
its shape is unchanged. This is an Owner-approved v2 field pass-through, not a new
route, handler, external DTO source file or general HTTP contract expansion. Existing
manual-version behavior remains v1-only, and `build_m6_bootstrap` retains its exact v1
DTO with no binding field. No B1 path may modify route, handler or external DTO source
files.

## 6. Accepted target immutable input snapshot

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
binding to Script persistence is not part of the first future read-only G1 slice and
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

The first future synchronous G1 slice has no persisted ScriptVersion binding and no
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

No new event type is accepted by this architecture contract. `IdentityBindingChanged`
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

M6-P3-G0 and the first future synchronous M3 slice do not implement a dispatcher,
checkpoint table, acknowledgement or broker.

## 11. Accepted target stable domain failures

| Code | Meaning |
| --- | --- |
| `m6_baseline_not_available` | No active baseline can be resolved for trusted Scope |
| `m6_baseline_stale` | The active baseline does not match the current confirmed M5 source |
| `m6_lineage_mismatch` | Scope, Ref or Digest lineage is inconsistent |
| `m6_consumer_authority_unavailable` | Trusted consumer Scope/context is unavailable |
| `m6_episode_mapping_unavailable` | Episode cannot be authoritatively mapped to an EpisodePlanItem in the locked M5 source |
| `m6_reconciliation_required` | Reserved for a later event-driven slice; not returned by the first synchronous G1 slice |

These are accepted target internal domain meanings for future separately authorized
implementation. HTTP status, public DTO and UI copy are out of scope.

## 12. Authorized B1 and future separately authorized G1 sequence

The smallest safe sequence has two independently authorized and accepted checkpoints.
B1 alone is authorized; G1 remains a future separate decision.

### 12.1 Binding prerequisite — `ACS-M6-P3-B1`

After its governance checkpoint is remote-verified, this checkpoint may implement only
the M5 `EpisodePlanItemBinding` v2 data contract, trusted M2/M4 validation,
immutable-version behavior and source projection. It may not implement the M6 reader
or any M3 consumer.

The B1 technical implementation allowlist is frozen to exactly six production paths:

```text
services/v5_core_os/series_planning/foundation.py
services/v5_core_os/series_planning/public.py
services/v5_core_os/series_episode/foundation.py
services/v5_core_os/series_intelligence/record_integrity.py
services/v5_core_os/lifecycle_integrity/composition.py
services/v5_core_os/lifecycle_integrity/coordinator.py
```

and exactly nine test paths:

```text
tests/unit/test_series_planning_m5.py
tests/unit/test_deletion_lifecycle_integrity.py
tests/contract/test_creator_series_episode_contract.py
tests/contract/test_creator_series_planning_contract.py
tests/contract/test_creator_series_intelligence_sqlite_contract.py
tests/integration/test_creator_series_planning.py
tests/integration/test_creator_series_intelligence.py
tests/integration/test_creator_series_intelligence_sqlite_p2.py
tests/integration/test_creator_lifecycle_sqlite_p2.py
```

The governance authorization checkpoint and later factual status synchronization are
limited to exactly these eight document paths:

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md
governance/ADR-0005-m6-series-intelligence-consumer-boundary.md
governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md
```

The M6 integrity file would be allowed only to validate/recompute the M5 v2 source
projection and digest for existing durable M6 facts; it may not add consumer behavior.
The Series/Episode foundation would be allowed only to add
`dependent_series_plan_binding_exists` to the stable lifecycle dependency-error set;
the Series/Episode contract test freezes its existing public `409` mapping. B1 would permit
no M2 identity/write-model change, SQLite table/column/marker/migration, M6 consumer,
M3 change, Frontend change, route/handler/external DTO source-file change or HTTP
contract expansion beyond the Owner-approved existing canonical v2 pass-through in
workspace versions. Any need to widen the frozen allowlist is a
hard stop for explicit Project Lead review.

### 12.2 Read-only consumer — `ACS-M6-P3-G1`

Only after B1 is Owner Accepted and a compatible bound M5/M6 test baseline exists may
a separate G1 implement:

1. one internal `ActiveM6BaselineReader`;
2. the exact M3 `get_m6_episode_baseline(...)` read surface;
3. current/stale and Episode-applicability resolution;
4. InMemory and temporary-file SQLite parity;
5. no ScriptVersion write, event consumer or M7/M9 behavior.

The following list is a future planning envelope only and grants no write authority.
Any later G1 authorization may narrow this maximum file allowlist:

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

Widening the planning envelope requires explicit Project Lead review. This planning
envelope permits no `__init__` export, schema/migration, M6 SQLite
adapter, M3 create/confirm/rewrite behavior, ScriptVersion persistence change, public
HTTP/DTO, Frontend, event consumer, dispatcher or checkpoint state. This architecture
acceptance does not authorize any listed file to change.

## 13. Implementation acceptance gates

### 13.1 Binding prerequisite gates

The authorized bounded B1 must prove:

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
10. `create_manual_version` rejects a current v2 version without a durable write; only
    the dedicated binding-version method creates v2→v2;
11. the existing HTTP workspace versions projection includes
    `episodePlanItemBindings` for canonical v2 versions without any route, handler or
    external DTO source-file change; v1 projections, manual-version behavior and the
    v1 bootstrap remain unchanged, and no other HTTP contract expands;
12. full Core, AST, architecture, secret and diff checks pass; and
13. execution stops after push and remote verification for Project Lead review.

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

The current B1 authorization does not authorize:

- any production or test implementation outside the exact B1 allowlist;
- M6-P3-G1 consumer implementation;
- modification of existing ScriptVersion persistence;
- consumer checkpoints, schema, migration or formal database work;
- Outbox dispatch, acknowledgement, broker or external bus;
- any route, handler or external DTO source-file change, or Creator Public HTTP/API
  expansion other than the Owner-approved existing canonical v2 field pass-through
  in workspace versions; Auth/RBAC and Frontend remain excluded;
- M7 validation, findings, PASS/WARN/BLOCK or script correction;
- M9 AssetRequirement, Identity/Rights/Asset or asset-resolution readiness;
- V4/V3, Provider, GPU, Worker or ComfyUI;
- M6-P4+, M7-M19 implementation or Production Ready status.

## 15. B1 authorization and Owner Review stop rule

The only authorized automatic sequence is:

```text
B1 GOVERNANCE AUTHORIZATION CHECKPOINT
→ COMMIT / NON-FORCE PUSH / REMOTE VERIFY
→ BOUNDED B1 IMPLEMENTATION AND TESTS
→ COMMIT / NON-FORCE PUSH / REMOTE VERIFY
→ STOP FOR PROJECT LEAD B1 OWNER REVIEW
```

The affected M2, M4, M5 and M6 Domain Owner review is approved for B1. Production and
test editing begins only after the governance checkpoint is remote-verified. If B1
needs any unlisted path, DDL/migration, route/handler/external DTO source-file change,
HTTP expansion beyond the approved existing canonical v2 pass-through in workspace
versions, M3/M6 consumer, G1, Frontend or M7+ behavior, execution
stops before that change.

After the B1 implementation candidate is remote-verified:

```text
STOP — M6-P3-B1 REMOTE-VERIFIED IMPLEMENTATION CANDIDATE
PROJECT LEAD B1 OWNER REVIEW REQUIRED
M6-P3-G1 NOT AUTHORIZED / NOT STARTED
NEXT AUTHORIZED MILESTONE: NONE
```

B1 is not Owner Accepted by remote verification. G1 requires a new explicit Project
Lead authorization even after a later B1 Owner Acceptance.
