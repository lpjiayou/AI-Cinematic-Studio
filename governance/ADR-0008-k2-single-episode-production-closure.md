# ADR-0008 — K2 Single-Episode Production Closure

- Status: `Accepted`
- Date: `2026-08-17`
- Decision owners: Project Lead / Architecture Owner
- Authorization source: explicit Project Lead instruction to execute `G0 → G7`
  automatically without interim review

## Context

The repository has accepted M1–M6 capability surfaces, an authenticated public API
and an isolated workspace boundary. It does not yet have an accepted single chain
from a confirmed script through executable shots, media execution, composition, QC,
approval and a playable episode master. Broadly implementing every future milestone
would hide this missing evidence behind platform breadth.

The delivery baseline also distinguishes M6 series intelligence from V5 identity and
asset authority, and V4 execution from V3 deterministic rendering. Those boundaries
must remain visible in the first vertical slice.

## Decision

Implement one fixed-scope K2 Golden Episode before any batch or generalized production
platform.

The ownership boundaries are:

```text
Frontend Creator UI
  → Frontend Experience Adapter
  → authenticated Creator Public API
  → Creator Application
  → V5 authoritative episode-production facts
  → V4 single-episode jobs/workers/adapters
  → V3 deterministic media composition
```

Specific decisions:

1. `EpisodeProductionRun` is the authoritative root for K2 downstream lineage.
2. M6 provides an explicit authority decision; it does not own Identity Lock.
3. Identity Lock is a separate immutable V5 fact over accepted character and reference
   versions.
4. Script compilation produces versioned creative shots and an executable Shot Graph;
   the latter is the production contract, not a presentation-only storyboard.
5. V5 owns production requirements and accepted immutable artifact records. V4 owns
   queues, leases, retries, cancellation and adapter execution. V3 owns deterministic
   composition and render facts.
6. Generated outputs remain candidates. Creative, identity, QC and final-master
   decisions are separate records and cannot be inferred from job success.
7. A deterministic local adapter may produce real playable `LOCAL_EVIDENCE` when a
   live model/GPU is unavailable. It must use the same V4 boundary and may never be
   described as live provider/GPU or production-quality evidence.
8. K2 local durable evidence may use additive SQLite storage. It may not destructively
   migrate or silently replace a production database.
9. Every new public route is authenticated, derives workspace from the principal and
   rejects client-selected scope.
10. G5 is a single-episode worker closure only; it does not authorize M16 batch
    production.

## Consequences

Positive:

- one end-to-end result can be inspected, replayed and traced;
- provider/GPU absence is represented honestly without blocking deterministic
  integration work;
- stable refs, versions, staleness and approvals are exercised before scale;
- the frontend can expose a coherent task flow instead of disconnected capability
  demonstrations.

Costs and limitations:

- the first implementation is deliberately narrow;
- local evidence does not measure model quality, GPU throughput or provider
  reliability;
- rights, budget, production credentialing, publication and batch scale remain
  separate gates;
- generalized scheduling and multi-episode orchestration are deferred.

## Rejected alternatives

- **Implement M7–M19 broadly first:** rejected because breadth does not prove one
  episode can close.
- **Put identity lock into M6:** rejected because it violates the accepted capability
  boundary.
- **Let the frontend call workers/providers directly:** rejected because it bypasses
  public/application/V5 authority.
- **Treat generated files or job success as approval:** rejected because candidate and
  human decision semantics must remain separate.
- **Return mocked success when a provider/GPU is absent:** rejected because it creates
  false production evidence.

## Verification

Verification is the gate contract in
[`AI_CINEMATIC_STUDIO_DELIVERY_GOVERNANCE_PACKAGE_V1.md`](AI_CINEMATIC_STUDIO_DELIVERY_GOVERNANCE_PACKAGE_V1.md)
and the object/state contract in
[`K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT.md`](../architecture/K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT.md).
Each gate must be committed, published without force, fetched and remote-verified
before automatic progression.
