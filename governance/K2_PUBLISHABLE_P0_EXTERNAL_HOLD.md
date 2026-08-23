# K2 Publishable P0 External Hold

- Status: `SAFE IMPLEMENTATION VERIFIED / EXTERNAL FACT HOLD / P0 NOT PASSED`
- Date: `2026-08-17`
- Scope: existing K2 `EpisodeProductionRun`; no parallel project or media chain
- Governing ADR: `ADR-0009-k2-publishable-media-production.md`

> Historical/commercial scope notice (`2026-08-22`): this hold no longer blocks the
> exact K2 Internal Content Lab P1 run governed by ADR-0011. It remains active for
> commercial/publication execution.

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

On `2026-08-20`, the operator produced a fresh schema
`v4.comfyui-runtime-attestation.v1` record from the live loopback ComfyUI runtime.
The record has attestation ref
`technical-k2-funhpc-a100-20260820T141317Z`, observed timestamp
`2026-08-20T14:17:08.319411Z`, PyTorch `2.11.0+cu126`, Python `3.12.7`, one
`NVIDIA A100-PCIE-40GB` CUDA device with `42405855232` total VRAM bytes, all ten
required native nodes, and `LOCAL_FILE_SHA256_VERIFIED` for the same three model
digests above. Its exact safe digests are:

- object-info digest
  `df3dace362f18e7b35fdea119959cc12e879d9535844cba3d926624e3ecf988a`;
- facts digest
  `0c065fe83f542dd2870c1cd2577a2ddd52d31a912ddfaf9b71fbdd640a68a6a6`;
- attestation payload digest
  `3a0ad8e839545390b3baaf3de57903f57f0c40c5bcaa117cd9990cd616c1bec2`.

The operator archived the attestation, model digest list, `system_stats` and
`object_info` as `k2-runtime-evidence-20260820T142014Z.tar.gz`, SHA-256
`c3701a1877cd9e715dcadbca93fc24eb38221f8e2c7a9f758cd978308c0b9f09`, on the
persistent compute data volume before shutting down the GPU.

On `2026-08-21`, an operator-downloaded copy and its SHA-256 sidecar were imported
into a controlled audit workspace outside Git. Independent verification established:

- the recomputed outer archive digest exactly matches the sidecar and the value above;
- all five archive entries are regular, relative files with no traversal, link or
  device entry;
- the original internal manifest verifies the attestation, model digest list,
  `system_stats` and `object_info` bytes without error;
- the repository archive utility cross-validates the attestation schema, closed fact
  set, ten exact native nodes, three model digests, Python/PyTorch/CUDA facts and full
  object-info digest;
- two independent normalized builds are byte-identical at SHA-256
  `282bbd955022d47ece4f696704e97d4a12b04e2e140bea21e49390ca6b890022`, and the
  normalized model digest member contains filenames only, with no compute-host path.

The imported source and normalized evidence remain external audit artifacts rather
than repository content. This closes the byte-custody and reproducibility gap only;
it does not add authority. The runtime honestly records `region=provider-not-disclosed`,
`authorityState=TECHNICAL_EVIDENCE_ONLY` and `publicationAllowed=false`; therefore it
does not clear the missing-region or external provider-policy review blockers.

On `2026-08-21`, the operator restarted the bounded runtime and produced the current
schema record `technical-k2-funhpc-a100-20260821T130634Z`, observed at
`2026-08-21T13:07:19.528120Z`. It reports ComfyUI `0.28.0`, Python `3.12.7`, PyTorch
`2.11.0+cu126`, one `NVIDIA A100-PCIE-40GB` CUDA device with `42409000960` total VRAM
bytes, all ten required nodes and the same three verified model file digests. Its
exact safe digests are:

- object-info canonical digest
  `df3dace362f18e7b35fdea119959cc12e879d9535844cba3d926624e3ecf988a`;
- facts digest
  `d845c4c24fa0108f7574a028cce40eb6253c68c078b6cb99c4c82c6d201b8fba`;
- attestation payload digest
  `be03a079d17cad524b5e2e061e0c651a8f41f6f5221dfe80a8244398817ded53`;
- attestation file SHA-256
  `bd6ee9390e9733b68722ca19895836e823e264c9d9ab867ed78cc7c3ffe31fed`.

The current deterministic archive
`k2-runtime-evidence-20260821T130634Z.tar.gz` has SHA-256
`77348f23aebcd2f4029c20f4d05cb910c726dbfbb7eaf9757ac44c4cf6a2e24a`.
An operator-downloaded copy and sidecar were independently verified outside Git. All
five members are safe regular relative files, the internal manifest verifies every
payload, the repository utility validates every cross-file fact, and an independent
rebuild is byte-identical at the same archive digest. A structural scan of 29,573 JSON
string values found no recognized credential pattern, credentialized URL, sensitive
query, host absolute path or populated sensitive scalar field.

This refresh supersedes the `2026-08-20` attestation only as the current-boot technical
pair; it does not erase that historical evidence. The current record still states
`region=provider-not-disclosed`, `authorityState=TECHNICAL_EVIDENCE_ONLY` and
`publicationAllowed=false`, so all external-authority and same-lineage blockers below
remain in force.

## Hard blockers before P1

P1 may not execute until the Project Lead supplies or connects all of the following as
external facts:

1. rights-cleared exact input digests and resolvable evidence for script, every
   identity/reference image, any reference video, voice, music, font, brand or other
   selected input;
2. approved image, video and audio provider/model/region capabilities;
3. server/worker credential-source refs, accepted usage-terms refs, safety/privacy
   policy and expiry facts (never secret values in Git or browser state);
4. an external budget-authority ref plus exact image/video/audio sub-caps whose sum
   does not exceed the Project Lead's recorded `CNY 100000` minor hard ceiling;
5. target release destination and territories compatible with every grant;
6. the observed runtime attestation reviewed by the provider-policy authority and
   entered as its exact opaque ref plus SHA-256 digest; technical reachability alone
   does not authorize dispatch.

Later P8/P9 still require separate human decision and publication-authority facts;
they cannot be supplied in advance by P0 or inferred from machine QC.

## P1-A external-authority activation prerequisite

The Creator runtime now has a fail-closed operator connection for the two existing
authority ports. Rights and provider decisions remain external JSON files and are
loaded only when all four of the following are injected together:

- `CREATOR_RIGHTS_AUTHORITY_BUNDLE_PATH`;
- `CREATOR_RIGHTS_AUTHORITY_BUNDLE_SHA256`;
- `CREATOR_PROVIDER_AUTHORITY_BUNDLE_PATH`;
- `CREATOR_PROVIDER_AUTHORITY_BUNDLE_SHA256`.

The paths must be absolute, the bytes must match the independently injected digests,
the schemas and field sets are closed, duplicate JSON keys are rejected, and provider
files cannot contain a bearer token, API key or other credential value. The only
credential fact visible to V5 is an opaque `credentialSourceRef`; the actual secret
remains in the worker environment. `scripts/k2_external_authority_activate.py`
validates operator-supplied files and prints the four secret-free assignments. It
does not create a grant, approve a provider, or advance P1.

## P1-C offline preboot prerequisite

On `2026-08-21`, while the compute instance remained shut down, the Project Lead set
the current K2 single-episode experiment hard ceiling to CNY 1,000 and confirmed that
no external audio should be used. The implementation records this as
`currency=CNY / maxTotalCostMinor=100000 / committedSpendMinor=0` without inventing a
`budgetAuthorityRef`, allocating provider sub-caps or authorizing a paid call.

The offline package adds a non-authoritative K2-001 script/storyboard/shot/Wan2.2/audio
candidate, two eight-view character-turnaround designs, a three-media same-lineage
experiment plan, an operator runbook and a fail-closed validator. Audio remains a
text-only neutral-TTS plan with no real-person imitation, voice cloning, external
audio or P1 music. No GPU, provider, domain admission, candidate selection or
publication action occurred.

Focused validation passes `12 / 12` and the complete Core regression passes
`566 / 566`. Every creative item remains `DRAFT / CANDIDATE / NOT DOMAIN FACT`; the
human-readable shot design keys are not Core references. This prerequisite therefore
reduces operator ambiguity but supplies none of the missing external facts.

## Stop decision

Automatic progression stops at the P0→P1 transition. A bounded P1 video adapter and
candidate-recording path now exist, and the separate operator smoke above proves only
technical capability. No governed same-lineage live provider call, rights-cleared
provider success, production asset, publishable master or M16 scale run has been
generated. Independent safe implementation may continue, but P1 cannot pass until the
missing authorities are connected to this same lineage.
