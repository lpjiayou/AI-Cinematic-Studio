# K2 Golden Episode Production Contract

> Status: `Normative for ACS-K2-G0 → G7`
>
> Scope: one authenticated workspace, one episode production run

## 1. Ownership matrix

| Concern | Owner | Must not own |
| --- | --- | --- |
| Series intelligence and external authority decision | M6 / accepted V5 boundary | Identity Lock, GPU execution, final approval |
| Identity Lock and authoritative asset/character refs | V5 Identity/Asset authority | Provider scheduling |
| Episode production state, TimelineVersion and candidate lineage | V5 Episode Production / K2DeliveryService | Worker implementation, V3 persistence or a second Timeline/Preview authority |
| Queue, lease, retry, cancel and adapter invocation | V4 Platform | Domain acceptance or human approval |
| Deterministic Timeline execution, composition and render | V3 Render Core | Project/Timeline authority, provider policy, EpisodeMaster or ExportArtifact |
| User interaction and workflow presentation | Existing Frontend Creator UI | Domain facts, SQL, V4/V3/worker/provider access |

## 2. Authoritative object graph

```text
EpisodeProductionRun
├── upstream roots (workspace/content profile/project/series/episode/plan/script)
├── M6AuthorityDecision
├── IdentityLock
├── ConsistencyValidation
├── StoryboardVersion
├── CreativeShotVersion[*]
├── ExecutableShotGraph
├── AssetRequirement[*]
│   └── GenerationRequest[*]
│       └── GenerationResult[*]
│           └── AssetVersion[*]
├── TimelineVersion
│   ├── PreviewCandidate[*]
│   └── RenderCandidate[*]
│       └── RenderManifest
├── QCReport[*]
├── ApprovalDecision[*]
└── EpisodeMaster
    └── ExportArtifact[*]
```

Every node carries:

- a stable opaque ref;
- workspace and production-run ownership;
- an immutable version or revision;
- created-at and created-by/adapter identity;
- a canonical payload digest;
- explicit upstream refs and versions;
- state and, where applicable, stale/block reasons.

Refs are never reconstructed from display names or frontend routes.

## 3. Episode production state machine

```text
ROOTS_READY
  → AUTHORITY_READY
  → SCRIPT_VALIDATED
  → SHOTS_COMPILED
  → ASSETS_READY
  → MEDIA_READY
  → PREVIEW_READY
  → QC_READY
  → APPROVAL_READY
  → MASTER_READY
```

A state transition is append-only and requires its gate evidence. A downstream object
becomes `STALE` when any locked upstream version changes. A blocked or stale run may
be resumed only after a new valid version is explicitly selected; the previous lineage
is retained.

`PREVIEW_READY` means that an exact non-stale review candidate exists. A
`RenderCandidate` may satisfy only this candidate-ready boundary; it cannot skip
`QC_READY` or `APPROVAL_READY`, cannot directly cause `MASTER_READY`, and cannot
create an export.

## 4. V4 job state machine

```text
QUEUED → LEASED → RUNNING → SUCCEEDED
                    ├──→ FAILED → RETRYING → QUEUED
                    └──→ CANCELLED
```

Required invariants:

- an idempotency key identifies one logical request inside one workspace/run;
- a lease has an owner and expiry and may be safely recovered;
- retries create attempts without duplicating accepted results;
- cancellation is terminal for the attempt and cannot be reported as success;
- worker output is untrusted until digest, media probe and path checks pass;
- artifacts outside the run-scoped root or containing traversal are rejected;
- orphan temporary files are quarantined or removed without deleting accepted assets.

## 5. Shot Graph minimum contract

Each executable shot contains stable scene/shot refs, deterministic order, duration,
frame rate, aspect ratio, camera instruction, action, dialogue/audio requirements,
required character identity-lock refs, location/prop/style requirements, continuity
constraints and source script spans.

The graph includes edges for chronological order and explicit continuity dependencies.
Compilation must fail on duplicate order, missing identity, non-positive duration,
unresolved required asset, cyclic chronology or a stale script/authority/identity
input.

## 6. Assets and generated media

An `AssetRequirement` states what the Shot Graph needs. A `GenerationRequest` states
how an adapter is asked to satisfy it. A `GenerationResult` records an attempt. An
`AssetVersion` is the immutable validated artifact admitted to V5 authority.

No job, provider response or local file path alone is an authoritative asset. Each
accepted asset must record media type, byte size, SHA-256, probe facts, provenance,
rights state, adapter/provider identity, parameters and upstream requirement/shot/
identity refs.

`LOCAL_EVIDENCE` is a provenance class, not a quality label. It disables publication
and production-readiness claims.

## 7. Composition, QC and decisions

`TimelineVersion` deterministically maps selected media, audio and effect clips to
Shot Graph time.

`PreviewCandidate` is a playable preview. `RenderCandidate` is a non-publishing
technical render candidate that binds one exact `TimelineVersion` and records its
render profile, resolution, codec, subtitle mode and `RenderManifest`.

Every RenderCandidate is required to carry:

```text
publicationAllowed=false
masterState=NOT_CREATED
exportState=NOT_CREATED
```

Neither candidate is a Master, Export or approval. `ExportCandidate` does not exist
and must not be introduced in this contract.

`QCReport` is a machine-verifiable assessment of an exact candidate and does not
approve it. The following approval kinds remain distinct append-only decisions:

- `CREATIVE_DIRECTION`
- `IDENTITY_CONTINUITY`
- `TECHNICAL_QC`
- `FINAL_MASTER`

Only M15 may create `EpisodeMaster` and `ExportArtifact`. It may do so only when the
required decisions explicitly accept the exact non-stale PreviewCandidate or
RenderCandidate, TimelineVersion and AssetVersions. Rejection or any upstream change
prevents finalization.

## 8. Public boundary and errors

All K2 public routes are under `/creator/api/v1`, require the accepted bearer
principal and derive workspace ownership from that principal. Query/body
`workspaceRef` remains forbidden.

Minimum error families are stable and machine-readable:

- `authentication_required` (`401`)
- `authority_unavailable` / `authority_required` (`403`)
- `resource_not_found` (`404`, including foreign-workspace refs)
- `validation_failed` (`400`)
- `invalid_state_transition` (`409`)
- `stale_input` (`409`)
- `idempotency_conflict` (`409`)
- `provider_unavailable` / `worker_unavailable` (`503`)
- `artifact_verification_failed` (`422`)

## 9. K2 close sequence

```text
resolve roots
→ record authority decision
→ lock character identities
→ validate confirmed script
→ compile executable shots
→ resolve asset requirements
→ dispatch and execute media jobs
→ register verified immutable assets
→ compose timeline and produce a preview and/or non-publishing render candidate
→ run technical/continuity QC on the exact candidate
→ record explicit decisions
→ M15 finalizes the immutable master
→ M15 creates the ExportArtifact exposed by the existing Creator UI
```

Each arrow is a gate, not an optimistic UI transition. The next action remains blocked
until its authoritative predecessor is present and current.
