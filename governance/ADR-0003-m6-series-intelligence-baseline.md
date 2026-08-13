# ADR-0003 — M6 Series Intelligence Baseline

## Metadata

| Field | Value |
| --- | --- |
| Status | `ACCEPTED FOR BOUNDED M6-P1 IMPLEMENTATION` |
| Decision date | `2026-08-13` |
| Project Lead / Architecture Owner / Repository Governance Owner | `蔺鹏` |
| Accepted implementation base | `dc9ab881b9f82ecd4a5927c456d5fe531f6850fa` |
| Authorized implementation | `M6-P1 InMemory only` |

## Context and decision

M5 owns confirmed SeriesPlan and immutable SeriesPlanVersion facts. M6 adds a
versioned Series intelligence baseline without copying M5 authority, trusting client
scope or approval claims, inventing a second lifecycle lock, or entering M7 and later
capabilities.

Adopt one V5 Series Intelligence domain:

```text
M5 Confirmed Source Snapshot
→ SeriesBible / SeriesBibleVersion
→ CharacterContinuity / CharacterContinuityVersion
→ M6BaselineSnapshot
→ ordered InMemory Outbox
```

`SeriesBible` and `CharacterContinuity` are the only M6 roots. Their immutable versions
use `DRAFT → CANDIDATE → CONFIRMED`. Component confirmation and baseline activation are
separate. Activation creates an immutable snapshot, supersedes the previous active
snapshot and appends ordered events atomically through the existing LifecycleAssembly
and InMemoryLifecycleState.

The authoritative scope is the complete tuple
`businessDomain + tenantId + workspaceRef + projectRef + seriesRef`. Commands provide
only workspace/project/series refs. Trusted Authority Ports resolve scope and approval;
missing authority fails closed. P1 rejects non-empty `ipUniverseRef` and non-empty
IdentityBinding.

M5 exposes internal read-only `get_confirmed_m6_source_snapshot` and is the sole owner
of `SeriesPlanVersionDigest`. M6 re-reads the current confirmed ref and digest during
activation and does not depend directly on M1.

Every write requires operation/idempotency identity and expected revision where
applicable. Repository facts, operation registry and outbox share the existing
InMemory pre-image rollback boundary. Undo failure inherits Assembly `POISONED`.

Canonical digests use `canonical-json-v1`: NFC Unicode, lexicographic keys, compact
UTF-8 JSON, no floats/NaN/Infinity and lowercase SHA-256. Stable-ref sets are sorted;
narrative arrays retain semantic order. Actor, approval, timestamps and activation
revision do not enter content digests.

## Structured facts and activation

SeriesBibleVersion owns stable-ref WorldRule, GlossaryTerm, LocationDefinition,
FactionDefinition, PropDefinition, TimelineEvent, VisualConstraint and
ProhibitedNarrativePattern facts. CharacterContinuityVersion owns CharacterDefinition,
CharacterStateInterval, directed RelationshipEdge and IdentityBinding facts.

State intervals use stable M5 EpisodePlanItem refs with start-inclusive/end-exclusive
semantics. Exclusive state categories cannot overlap. All references resolve in the
exact source version.

Activation requires confirmed components with identical scope and M5 source; Character
must lock the selected Bible. First activation is revision 1. Replacement increments
the revision and emits `M6BaselineSuperseded` before `M6BaselineConfirmed`. Repeating
the same inputs is fully idempotent and emits no event.

## Exclusions

P1 is InMemory only. It does not modify SQLite schema/migration/FK, HTTP endpoints,
public DTOs, Auth/RBAC/Permission, Frontend, M3, M7, M9, V4/V3, Provider, GPU, Worker,
ComfyUI, formal 8765 data or Production Ready status. M6-P2+ and M7-M19 remain
unauthorized.

The normative detail is
[`M6_SERIES_INTELLIGENCE_DOMAIN_CONTRACT.md`](../architecture/M6_SERIES_INTELLIGENCE_DOMAIN_CONTRACT.md).
