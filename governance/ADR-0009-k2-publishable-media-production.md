# ADR-0009 — K2 Publishable Media Production

- Status: `Accepted for bounded automatic execution`
- Date: `2026-08-17`
- Decision owners: Project Lead / Architecture Owner
- Extends: `ADR-0008-k2-single-episode-production-closure.md`

> `2026-08-21` lineage addendum: the durable instance assumed below was not found.
> `ADR-0010-k2-canonical-lineage-bootstrap.md` authorizes one new canonical
> `ROOTS_READY` lineage and supersedes only ADR-0009's requirement to reopen that
> missing instance. All downstream rights/provider/selection/publication gates remain
> unchanged.

## Context

ADR-0008 proved one real, playable, deterministic audiovisual chain through the
accepted Creator Public API, Application, V5, V4 and V3 boundaries. Its output is
deliberately `LOCAL_EVIDENCE`: it used no live generative provider or GPU, carried no
publication rights, and could not establish commercial quality or release readiness.

The next objective is one genuinely publishable K2 episode, not a second demo system.
The existing project, series, episode, script, M6 authority, Identity Lock, Shot Graph,
requirements, jobs, assets, timeline, decisions and delivery objects must therefore be
extended in place.

## Decision

Implement the P0→P10 wave frozen in
`K2_PUBLISHABLE_PRODUCTION_EXECUTION_PACKAGE.md` under these decisions:

1. The K2 production run and its upstream refs remain the lineage root. When the
   original durable instance is unavailable, only the ADR-0010 controlled bootstrap
   may establish its replacement root. A live adapter may not invent another project,
   character identity or shot model.
2. A versioned `ProductionPolicyVersion`, `RightsManifestVersion` and
   `ProviderExecutionPolicyVersion` are required before live dispatch.
3. Rights are facts about exact source/reference and output versions. A missing,
   expired, ambiguous or incompatible grant blocks dispatch or publication.
4. Live image, video and audio integrations are V4 provider adapters behind the
   existing job contract. The Frontend and Application layers never call providers,
   workers or GPU runtimes directly.
5. Provider output is an untrusted candidate. Probe, digest, malware/path, policy,
   lineage and media-specific validation must pass; explicit selection is required
   before a V5 `AssetVersion` is admitted.
6. Provider success, worker success, machine QC, creative approval, identity approval,
   final-master approval and publication eligibility remain separate append-only
   facts.
7. V3 owns deterministic final composition only. It does not choose providers, accept
   rights, approve candidates or decide publication.
8. `publicationAllowed=true` may be derived only by V5 publication eligibility over
   the exact immutable master and its complete current lineage. It is never copied
   from provider metadata or supplied by the browser.
9. Local deterministic adapters remain test and recovery tools. Their artifacts keep
   `LOCAL_EVIDENCE_ONLY` and cannot satisfy a live-media or publication gate.
10. M16 begins only after one real K2 master passes P9 and Gate A/B/C. It progresses
    strictly `1 → 3 → 10 → 30`; 100-run scale and M17–M19 remain unauthorized.

## Required authority boundaries

```text
Frontend Creator UI
→ Frontend Experience Adapter
→ authenticated Creator Public API
→ Creator Application
→ V5 production/rights/asset/publication authority
→ V4 jobs, provider adapters and workers
→ V3 deterministic composition
→ approved compute/provider runtime
```

Secrets are injected only into server/worker processes. Provider credentials, signed
object URLs and internal storage paths never enter browser state, domain payloads,
logs, committed fixtures or public error messages.

## Consequences

Positive:

- the publishable chain reuses every accepted K2 object and gate;
- real provider quality, latency, cost and provenance become measurable facts;
- local evidence remains useful without being confused with production evidence;
- rights and publication decisions are inspectable and version-specific.

Costs and limitations:

- real execution requires external credentials, budget, usage terms and rights-cleared
  inputs that code cannot manufacture;
- production persistence, object storage and recovery must be validated before live
  provider scale;
- human approvals cannot be auto-generated or inferred from machine tests.

## Rejected alternatives

- **Build separate provider pages or scripts:** rejected as an integration island.
- **Upload provider results straight into the frontend:** rejected because it bypasses
  V4 execution and V5 authority.
- **Treat a successful generation as an accepted asset:** rejected because candidate,
  validation and selection are distinct.
- **Set publication from a UI toggle:** rejected because release eligibility is a V5
  derivation over immutable evidence.
- **Batch before one real episode closes:** rejected because throughput cannot repair
  a broken single-episode chain.

## Verification

Every checkpoint must satisfy the architecture contract, targeted tests, complete
regression, secret scan, remote SHA/tree equality and a clean worktree. Live evidence
must additionally record provider/model/region, request and attempt refs, parameters,
latency, cost units, seed where supported, output digest, probe facts, rights refs and
GPU/runtime facts. When attestation is required, the authority-approved attestation
ref/digest must match the immutable provider policy, V5 request, V4 configuration and
returned runtime facts. Absence or mismatch is a blocked gate, never a synthetic
success.
