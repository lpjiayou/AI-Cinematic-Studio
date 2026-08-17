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

The committed Core `eba265322f66ff5e3e7aabb215e57e7f4d54d278` and Frontend
`ca3af84b406815df73989498d7f2963e261f354d` trees also passed a real two-process
HTTP gate through `Next Experience Adapter → authenticated Creator Public API →
Application/V5`: all 19 capabilities and the readiness projection came from Core,
browser policy write returned `404 / not_found`, a direct forged `actorRef` returned
`400 / invalid_request`, and an unauthenticated read returned
`401 / authentication_required`.

The separate real-browser visual gate remains an environment hold: this checkout has
neither the declared Playwright package nor a usable browser binary. No HTTP-only
result is represented as browser evidence.

## Observed environment facts

The repository validation container was probed without reading or printing secret
values:

- `ffmpeg` and `ffprobe` are installed for deterministic local evidence;
- no NVIDIA device or `nvidia-smi` runtime is present in that container;
- no approved live image, video or audio provider credential source was discoverable;
- no injected rights-evidence authority or provider-policy authority is configured;
- the current K2 identity references remain non-authoritative local evidence;
- no production object store, production relational store, destination authority or
  publication authority is configured for this wave.

These are blockers, not inferred failures of any named commercial provider.

On `2026-08-18`, a separate operator-controlled compute runtime supplied technical
smoke evidence for ComfyUI `0.28.0` on one NVIDIA A100 40GB device. The three Wan2.2
model names were recognized and their operator-reported file SHA-256 values were:

- UNET `456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e`;
- text encoder `c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68`;
- VAE `e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156`.

The resulting MP4 was independently probed as H.264/yuv420p, `640×352`, `24 fps`,
`49` frames, `2.041667 s`, `133257` bytes, with SHA-256
`1c3a8359d63eafbc733367331d85d1e5f5d4c4334d17deb3447dabd009d00cdd` and no audio
stream. This is `OUT_OF_LINEAGE_OPERATOR_SMOKE / TECHNICAL_EVIDENCE_ONLY`: it was not
dispatched by the authenticated Creator Public API, was not bound to a current K2
Rights Manifest or Provider Policy, and is not an AssetVersion, approval, master or
publishable result.

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
6. the observed runtime attestation reviewed by the provider-policy authority and
   entered as its exact opaque ref plus SHA-256 digest; technical reachability alone
   does not authorize dispatch.

Later P8/P9 still require separate human decision and publication-authority facts;
they cannot be supplied in advance by P0 or inferred from machine QC.

## Stop decision

Automatic progression stops at the P0→P1 transition. A bounded P1 video adapter and
candidate-recording path now exist, and the separate operator smoke above proves only
technical capability. No governed same-lineage live provider call, rights-cleared
provider success, production asset, publishable master or M16 scale run has been
generated. Independent safe implementation may continue, but P1 cannot pass until the
missing authorities are connected to this same lineage.
