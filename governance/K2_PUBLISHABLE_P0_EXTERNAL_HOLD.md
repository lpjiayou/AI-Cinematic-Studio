# K2 Publishable P0 External Hold

- Status: `SAFE IMPLEMENTATION VERIFIED / EXTERNAL FACT HOLD / P0 NOT PASSED`
- Date: `2026-08-17`
- Scope: existing K2 `EpisodeProductionRun`; no parallel project or media chain
- Governing ADR: `ADR-0009-k2-publishable-media-production.md`

## Implemented evidence

The P0 change adds one immutable policy bundle on the existing K2 run:

```text
ProductionPolicyVersion
+ RightsManifestVersion
+ ProviderExecutionPolicyVersion
→ production-readiness projection
```

It is available only through the authenticated Creator Public API and the existing
Frontend Experience Adapter. The browser receives `production-readiness` as a
read-only projection; it cannot provide workspace or actor scope, compute a
publication flag, insert secrets or turn a blocker into an accepted fact. A trusted
server-side write derives the recording actor from its authenticated credential.

The implementation includes:

- exact frozen output, budget, retry, retention, destination and decision contracts;
- exact input digest, rights owner/grant/use/territory/term/consent/scope/evidence
  validation;
- separate external rights-evidence resolution over the complete canonical grant;
- separate external provider-policy resolution over media kind, provider, model,
  region, endpoint, safety and privacy policy;
- opaque capability, credential-source, usage-terms and budget-authority refs only;
- additive SQLite persistence, schema/column/integrity verification, restart recovery,
  idempotent replay and payload/embedded-digest tamper detection;
- truthful `BLOCKED_POLICY` / `BLOCKED_EXTERNAL_EVIDENCE` projection with
  `publicationAllowed=false`;
- Frontend capability states and K2 inspector blocker mapping without a rights,
  provider, approval or publication fabrication form.

Same-tree verification completed with Core `528 / 528`, Frontend `119 / 119` across
24 files, TypeScript, ESLint, Next.js production build, targeted public HTTP tests,
Python compilation and whitespace validation all passing.

## Observed environment facts

The execution environment was probed without reading or printing secret values:

- `ffmpeg` and `ffprobe` are installed for deterministic local evidence;
- no NVIDIA device or `nvidia-smi` runtime is present;
- no approved live image, video or audio provider credential source was discoverable;
- no injected rights-evidence authority or provider-policy authority is configured;
- the current K2 identity references remain non-authoritative local evidence;
- no production object store, production relational store, destination authority or
  publication authority is configured for this wave.

These are blockers, not inferred failures of any named commercial provider.

## Hard blockers before P1

P1 may not execute until the Project Lead supplies or connects all of the following as
external facts:

1. rights-cleared exact input digests and resolvable evidence for script, every
   identity/reference image, any reference video, voice, music, font, brand or other
   selected input;
2. approved image, video and audio provider/model/region capabilities;
3. server/worker credential-source refs, accepted usage-terms refs, safety/privacy
   policy and expiry facts (never secret values in Git or browser state);
4. an explicit currency/cost ceiling and budget-authority ref;
5. target release destination and territories compatible with every grant;
6. a production runtime choice capable of recording real execution-device/GPU facts.

Later P8/P9 still require separate human decision and publication-authority facts;
they cannot be supplied in advance by P0 or inferred from machine QC.

## Stop decision

Automatic progression stops at the P0→P1 transition. No live provider call, GPU claim,
rights-cleared assertion, provider success, production asset, publishable master or M16
scale run has been generated. Independent safe implementation may resume only after
the missing authorities are connected to this same lineage.
