# K2 Internal Image-First Real-Media Revision Contract

## 1. Status and scope

- Status: `M10 COMPLETE / FOUR EXACT HUMAN SELECTIONS ADMITTED / REAL_IMAGE_READY / CORE 638 PASS / M11 NEXT`
- Date: `2026-08-23`
- Project: `K2-001`
- Required Core base: `1650c3462b32899151cdba795ddc10e5171ff1da`
- Parent run: `episode-production-run-f918dc281320440b9848bcb476f5605a`
- Publication invariant: `publicationAllowed=false`

This contract corrects the post-P1 sequence. P1 proved only that the existing
Public API → V5 → V4 → ComfyUI/Wan2.2 path can execute one real 49-frame video on
the A100. It did not prove identity conditioning, full-shot production or media
admission.

The next production chain is:

```text
current G2 IdentityLock and selected visual references
→ current G3 four CreativeShotVersions
→ M10 four multi-reference shot/keyframe image requests
→ technically verified image candidates
→ exact human image selection and immutable image AssetVersions
→ M11 four Wan2.2 video requests, each using its selected shot image
→ technically verified video candidates
→ exact human video selection and immutable video AssetVersion successors
→ M13 real preview revision
→ M14 machine QC and exact human final decisions
→ M15 Master only after those decisions
```

This is a same-production-run, append-only revision. It does not create a second
Project, Episode, Shot, Identity, Asset, Provider, Queue, Timeline or approval stack.

## 2. Current lineage facts

- G2 has one locked identity for 林澈 and one for 顾言.
- Eight earlier PNG files are four candidate turnaround boards per character.
- The selected G2 references are 林澈 candidate-01 and 顾言 candidate-01.
- Every current G3 shot binds both locked characters.
- G4 contains four video and four audio requests and no shot-image request.
- G5/G6 are immutable CPU-FFmpeg local evidence; G6 is at `QC_READY` and remains
  human-unapproved.
- P1 produced one unselected, non-admitted self-hosted video candidate.

Therefore a single character board cannot be used as the start image for all four
shots. Both G2 visual references must first condition a composed shot image. The
selected shot image—not a single-character board—is the one `start_image` used by
the corresponding M11 video request.

## 3. M10 request contract

`POST /creator/api/v1/episode-production-runs/{runRef}/real-media-revision`
accepts only `idempotencyKey`; authenticated workspace and path run scope are
server-injected.

The M10 plan creates exactly four provider-neutral `image/png` requests. Every
request is bound to:

- the current root payload digest;
- one exact CreativeShotVersion ref and digest;
- the current executable Shot Graph ref and digest;
- the current IdentityLock ref, version ref and digest;
- both character refs and both exact visual-reference refs, version refs, media
  types and content digests;
- camera, action and continuity facts copied from the current shot;
- the passed G6 QC report ref and digest.

Public commands cannot supply paths, provider/model names, runtime attestations,
identity refs, prompts, approval facts or publication fields. Absolute artifact paths
remain private V4 execution details.

Planning records `capabilityVerificationState=PENDING_LIVE_PREFLIGHT` and
`executionAuthorizationState=NOT_GRANTED_BY_PLAN`. Planning is not execution,
selection, admission or approval.

## 4. Live M10 capability gate

The running ComfyUI `/object_info`, installed custom nodes, exact model files and
model digests must prove one accepted multi-reference identity-conditioning image
workflow before the first image job is submitted. Text-only prompting, merely
including character names, or an unverified node guess is not a pass.

The live adapter must:

- resolve both reference artifacts only from server-held exact-scope mappings;
- hash bytes and match the two G2 content digests before upload;
- reject browser paths and path traversal;
- bind both references into the accepted image-conditioning workflow;
- preserve seed, node graph, model digests, runtime attestation, latency and attempt
  evidence;
- independently verify PNG dimensions, byte size and SHA-256;
- return candidates as unselected, non-admitted and publication-disabled.

If no compatible multi-reference workflow is installed, M10 stops at
`REAL_IMAGE_PLAN_READY`; it must not silently fall back to text-only generation.

## 5. Selection and admission

Technical success does not select media. Image admission requires one explicit human
decision identifying one exact candidate ref and digest for each of the four current
shot-image requests. It then creates immutable image AssetVersions and advances:

```text
REAL_IMAGE_PLAN_READY → REAL_IMAGE_READY
```

The authenticated command surface is:

```text
POST /creator/api/v1/episode-production-runs/{runRef}/real-image-selection
```

It accepts only `idempotencyKey` plus exactly four closed-world selection items
(`generationRequestRef`, `candidateRef`, `candidateContentDigest`). Workspace,
production-run scope and `actorRef` are server-injected from the authenticated
principal; a client-supplied actor or private path is rejected. Before the single
append-only admission gate, V4 revalidates the digest-pinned execution receipt,
technical-smoke receipt, four workflow graphs, both G2 reference bytes and all four
PNG artifacts. V5 then records four `RealImageCandidate` facts, four
`MediaSelectionDecision` facts, four immutable image `AssetVersion` facts and one
admission manifest. The batch is atomic: no partial selection or partial asset
admission is allowed.

The same rule applies to the four M11 video candidates. A valid exact selection
creates video successor AssetVersions and advances:

```text
REAL_VIDEO_PLAN_READY → REAL_VIDEO_READY
```

General instructions to continue automatically, technical QC, Project Lead code
authorization and successful GPU execution are not substitutes for choosing unseen
creative media.

## 6. M11 request contract

Only after all four image AssetVersions are admitted may V5 derive four video
requests. Each request carries one selected shot-image AssetVersion ref and digest;
V4 privately resolves and verifies the corresponding bytes before connecting them to
`Wan22ImageToVideoLatent.start_image`.

Frame counts remain exactly `168 / 168 / 192 / 192` at 24 fps, total 720. M11 may
reuse the existing four audio v1 AssetVersions for the first real-preview revision;
live audio remains a later M12 branch.

## 7. State graph

Historical G2-G6 facts and the original preview remain immutable. The accepted
legacy edge remains valid for unaffected runs:

```text
QC_READY → APPROVAL_READY → MASTER_READY
```

The image-first revision branch is:

```text
QC_READY
→ REAL_IMAGE_PLAN_READY
→ REAL_IMAGE_READY
→ REAL_VIDEO_PLAN_READY
→ REAL_VIDEO_READY
→ REAL_PREVIEW_READY
→ REAL_QC_READY
→ APPROVAL_READY
→ MASTER_READY
```

After entering the revision branch, a run cannot fall back to approval over the old
G6 preview.

## 8. Internal authority policy

For this exact internal self-hosted, non-publishing run, Rights Manifest, external
Provider Policy/Authority and external Budget Authority are not dispatch
prerequisites. They are not globally deleted: commercial/publication behavior remains
unchanged and fail-closed.

Current G2 lineage, a fresh live runtime attestation after each server restart,
model/file digests, one approved CUDA device, bounded timeout/cost, artifact
containment, independent verification and `publicationAllowed=false` remain
mandatory.

## 9. Automatic-work boundary

CPU/offline work may automatically complete contracts, request derivation, public
API plumbing, persistence/state compatibility, tests, audit and server execution
scripts. GPU execution starts only when the live capability gate can be evaluated.

The maximum automatic result before unseen-media review is technically verified
candidates with zero selection decisions and zero admitted AssetVersions. Master,
Export and publication remain prohibited.
