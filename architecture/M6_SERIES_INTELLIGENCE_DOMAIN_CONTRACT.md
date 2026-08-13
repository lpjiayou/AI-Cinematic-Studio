# M6 Series Intelligence Domain Contract

> Status: `ACCEPTED FOR BOUNDED M6-P1 INMEMORY IMPLEMENTATION`
>
> Authority: `ADR-0003`
>
> Base: `dc9ab881b9f82ecd4a5927c456d5fe531f6850fa`

## Ownership and dependency

V5 owns SeriesBible, CharacterContinuity, immutable versions, active baseline snapshots
and outbox facts. M5 remains sole owner of SeriesPlanVersion content and digest. M6
consumes only M5's confirmed source snapshot. Creator HTTP, Frontend and providers do
not own M6 facts.

```text
LifecycleAssembly
├── SeriesPlanningPublicBoundary (read-only confirmed source)
└── SeriesIntelligencePublicBoundary
    ├── trusted authority ports
    ├── domain service
    └── in-memory repository / operation registry / outbox participant
```

## Scope and trusted authorities

`M6Scope = businessDomain + tenantId + workspaceRef + projectRef + seriesRef`.
Root indexes use the complete tuple. Commands contain workspace/project/series refs;
client business domain, tenant, actor, role and approver claims are not authority.
M6ScopeAuthorityPort resolves scope, ApprovalAuthorityPort resolves a verified actor,
and IdentityAuthorizationPort validates identity bindings. Defaults fail closed. P1
rejects non-empty `ipUniverseRef` and non-empty IdentityBinding.

## M5 source snapshot

`get_confirmed_m6_source_snapshot(workspaceRef, projectRef, seriesRef)` returns scope,
seriesPlanRef, seriesPlanVersionRef, seriesPlanVersionDigest, confirmed status,
mainArcs, episodePlanItems, characterArcIntents, worldIntent, continuityIntent and
foreshadowingContext. M5 calculates the digest. Unconfirmed versions are rejected.
Activation re-reads and compares current confirmed ref and digest.

## Roots, versions and facts

Roots store complete scope, root ref, current/confirmed version refs, revision and
timestamps. Versions store version ref/number, parent ref, source plan ref/digest,
schema/status/digest, timestamps and approval ref. Character versions additionally
lock source Bible ref/digest.

Content is immutable. Changes create versions. AI/provider may create candidates but
cannot confirm. DRAFT must be submitted before confirmation. Historical rollback
creates a new candidate.

Bible fact kinds are WorldRule, GlossaryTerm, LocationDefinition, FactionDefinition,
PropDefinition, TimelineEvent, VisualConstraint and ProhibitedNarrativePattern.
Character facts are CharacterDefinition, CharacterStateInterval, RelationshipEdge and
IdentityBinding. Rich text cannot be sole authority.

Character refs remain stable per scope. Intervals use EpisodePlanItem refs, start
inclusive/end exclusive; null end means through plan end. Location, Health, Appearance
and PrimaryGoal are exclusive; Knowledge and Possession may coexist. Relationships are
directed. Unknown or inconsistent references are rejected.

## Canonical digest

`canonical-json-v1` normalizes strings to NFC, rejects floats, sorts object keys, writes
compact UTF-8 JSON and returns lowercase SHA-256. Optional scalars are null. Narrative
arrays retain order; fact sets sort by stable ref. Time, actor, approval and activation
revision are excluded.

Bible digest covers schema, scope, source plan ref/digest and facts. Character digest
also covers source Bible ref/digest, facts and IdentityBinding refs/digests. Baseline
digest covers schema, scope and selected source/component refs plus digests.

## Commands, idempotency and concurrency

Every write has operationRef and idempotencyKey. Same key/input returns the original
result; same key/different input raises `idempotency_conflict`. Existing-root mutations
require expectedRevision; mismatch raises `version_conflict`.

## Activation and outbox

M6BaselineSnapshot stores snapshot ref, scope, M5 ref/digest, Bible ref/digest,
Character ref/digest, activation revision, confirmation metadata, canonical digest and
status. Exactly one snapshot per scope is ACTIVE.

One shared lifecycle lease resolves scope, re-reads M5, validates confirmed components
and references, registers full pre-image undo, supersedes old active, creates new
active, appends ordered events and commits. Envelopes include event/aggregate identity,
scope, correlation/causation/operation refs, time and payload. Replacement emits
Superseded before Confirmed. Failure creates no partial snapshot, dual active or orphan
event; undo failure poisons the Assembly.

## P1 boundary

P1 supplies only InMemory repository, operation registry and outbox registered in the
accepted LifecycleAssembly. It adds no HTTP endpoint and no durable/global outbox or
operation claim. SQLite, migration, formal data, Frontend, M7+ and M6-P2+ remain out of
scope.
