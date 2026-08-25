# K2 Internal Image-First Real-Media Revision Contract

> Historical/closed as of 2026-08-25: this exact-scope K2-001 contract remains
> audit evidence only. It is not a current dispatch runbook and is not transferable
> to K2-002.

## 1. Status and scope

- Status: `M10 v1 ADMITTED / M11 v1 TECHNICALLY VERIFIED / SEMANTIC VISUAL QC FAIL / CONTROL-PLANE CORRECTION AUTHORIZED / NO VIDEO ADMISSION`
- Date: `2026-08-23`
- Project: `K2-001`
- Required Core base: `1650c3462b32899151cdba795ddc10e5171ff1da`
- Control-plane source base: `0a6962be`
- Control-plane decision: `governance/ADR-0013-k2-control-plane-convergence.md`
- Parent run: `episode-production-run-f918dc281320440b9848bcb476f5605a`
- Publication invariant: `publicationAllowed=false`

> This contract is the normative executable detail for ADR-0012 as amended by
> ADR-0013. It may narrow implementation but may not broaden either ADR. On conflict,
> execution stops until the ADR and contract are reconciled.

This contract corrects the post-P1 sequence. P1 proved only that the existing
Public API → V5 → V4 → ComfyUI/Wan2.2 path can execute one real 49-frame video on
the A100. It did not prove identity conditioning, full-shot production or media
admission.

The next production chain is:

```text
current G2 IdentityLock and selected visual references
→ current G3 four CreativeShotVersions
→ M10 four multi-reference shot/keyframe image requests
→ Candidate and TechnicalValidation
→ append-only SemanticVisualQCDecision
→ exact human HumanSelectionDecision resolved by digest-pinned ApprovalAuthority
→ V5 AssetAdmission and immutable image AssetVersion
→ M11 four Wan2.2 video requests, each using its selected shot image
→ Candidate and TechnicalValidation
→ append-only SemanticVisualQCDecision
→ exact human HumanSelectionDecision resolved by digest-pinned ApprovalAuthority
→ V5 AssetAdmission and immutable video AssetVersion successor
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
- M10 v1 contains four admitted historical image AssetVersions. They remain
  immutable, but assisted review found them unsuitable as action-ready sources for
  formal M11 production.
- M11 v1 contains four technically verified runtime candidates. Assisted semantic
  visual QC is `FAIL`; all four are unselected, not admitted and non-publishing.

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

Technical success and semantic visual QC do not select media. Image admission
requires an applicable canonical append-only visual-QC `PASS`, followed by one
explicit human decision identifying one exact candidate ref and digest for each of
the four current shot-image requests. The actor and exact scope are resolved by a
server-held, digest-pinned ApprovalAuthority result; client actor, role, approver or
authority claims are rejected. V5 then creates immutable image AssetVersions and
advances:

```text
REAL_IMAGE_PLAN_READY → REAL_IMAGE_READY
```

The authenticated command surface is:

```text
POST /creator/api/v1/episode-production-runs/{runRef}/real-image-admission
```

`/real-image-selection` is retained only as a read-compatible and write-schema
compatible alias. The command accepts `idempotencyKey` plus exactly four
closed-world selection items. Each item contains only `visualQcRef`,
`visualQcVersion`, `visualQcDigest`, `selectionRef`, `selectionVersion` and
`approvalRef`. Workspace, production-run scope and actor/authority facts are
server-resolved; client actor, reviewer, subject, authority or private-path claims
are rejected. Before the single append-only admission gate, V4 revalidates the
digest-pinned execution receipt, technical-smoke receipt, four workflow graphs,
both G2 reference bytes and all four PNG artifacts. V5 revalidates the applicable
visual-QC and ApprovalAuthority evidence, then atomically appends four typed
`HumanSelectionDecision → AssetAdmission → AssetVersion` lineages and one admission
manifest. Partial, duplicate, missing, extra or cross-slot coverage fails closed.

M10 v1 remains immutable historical admission under the original exact-selection
contract. ADR-0013 does not rewrite that history or fabricate retrospective
authority evidence. Every successor image version uses the converged visual-QC and
ApprovalAuthority rule, retains the logical `assetRef`, increments the version and
binds the prior version through `supersedesAssetVersionRef` plus digests.

For post-M10 successor revisions, ADR-0013 supersedes the exact-four-item command
rule in ADR-0012 decisions 7 and 10 and in this section only to permit one exact shot
successor at a time. The existing exact-four endpoint and its historical semantics
remain backward-compatible. A successor selection plus AssetVersion admission is
atomic for its exact scoped candidate; it does not activate a complete replacement
image set or advance the production state. Complete four-shot image-manifest
activation remains one atomic append-only batch.

The first M11 video admission requires exactly four unique current slots. It appends
four typed selection/admission/AssetVersion lineages and advances exactly once,
only after canonical visual QC and digest-pinned ApprovalAuthority both pass:

```text
REAL_VIDEO_PLAN_READY → REAL_VIDEO_READY
```

After `REAL_VIDEO_READY`, a successor command contains exactly the changed-slot set
(one to four selections). Unchanged slots reuse their current Candidate,
AssetAdmission and AssetVersion. The atomic append contains the new changed-slot
lineages plus one four-slot `v5.k2-real-video-batch-activation.v2`; every activation
slot is marked `NEW_ADMISSION` or `REUSED_CURRENT`. Each activation directly
supersedes the preceding activation and supports immediate request/revision
successors such as v2→v3. It creates no new production gate, does not rewind state
and does not advance `REAL_VIDEO_READY` again. A changed current source image,
GenerationRequest or candidate byte lineage makes the old activation
`STALE_BLOCKED`; canonical video admissions/assets remain hidden until another
complete four-slot activation is current.

General instructions to continue automatically, technical QC, Project Lead code
authorization and successful GPU execution are not substitutes for choosing unseen
creative media.

## 6. M11 request contract

Only after all four image AssetVersions are admitted may V5 derive four video
requests. Each request carries one selected shot-image AssetVersion ref and digest;
V4 privately resolves and verifies the corresponding bytes before connecting them to
`Wan22ImageToVideoLatent.start_image`.

The authenticated planning surface is:

```text
POST /creator/api/v1/episode-production-runs/{runRef}/real-video-revision
```

It accepts only `idempotencyKey`. Before deriving requests, V5 revalidates the M10
plan, admission manifest, four candidate/decision/AssetVersion lineages and asks the
digest-pinned V4 evidence adapter to rehash the four selected PNG bytes. Each request
then binds one exact `sourceImageAssetVersionRef`, AssetVersion digest and content
digest. It carries no browser path and cannot substitute another image.

Frame counts remain exactly `168 / 168 / 192 / 192` at 24 fps, total 720. M11 may
reuse the existing four audio v1 AssetVersions for the first real-preview revision;
live audio remains a later M12 branch.

The first exact A100/5B execution profile is `640×352`, 20 steps, `uni_pc/simple`,
CFG 5.0 and model shift 8.0. The plan records this bounded profile and advances only
`REAL_IMAGE_READY → REAL_VIDEO_PLAN_READY`; it does not start ComfyUI, dispatch a
job, create a video candidate, select media or create a video AssetVersion.

At the historical plan-only checkpoint, canonical execution of that planning command
was closed by
`k2-m11-real-video-plan-20260823T091831Z/receipt.json` with SHA-256
`137c24c31cc8ddf7cc79d20b20e3d6f9038911b53bfb19dfc543671796b421fd`.
The production state became `REAL_VIDEO_PLAN_READY`; no GPU job or video candidate
existed at that checkpoint. The later M11 execution facts below supersede only that
historical no-candidate observation, not the production state.

Execution reuses the existing V4 `MediaJobCoordinator`. The M11 adapter accepts no
client path: it selects a private PNG only by the plan's exact content digest,
rehashes and probes it, stages a digest-named file under the configured ComfyUI input
root, and connects `LoadImage` to `Wan22ImageToVideoLatent.start_image`. Wan model
length is `durationFrames + 1` (169/193); V4 then produces the exact requested
168/192-frame artifact through a recorded `v4.ffmpeg-exact-frame-trim.v1` step before
the coordinator's independent ffprobe verification.

The 2026-08-23 M11 execution produced four independently verified H.264 candidates
at 640×352/24 fps with exact frame counts 168/168/192/192. These are runtime
candidate facts only. Assisted semantic visual QC is `FAIL`: all four remain
unselected and not admitted, the canonical production state remains
`REAL_VIDEO_PLAN_READY`, and no video AssetVersion exists. The FAIL must be
preserved as canonical append-only QC evidence; neither human review nor authority
alone permits an admission without an exact replacement candidate, applicable QC
`PASS` and exact human selection.

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

Rework does not rewind this production-state graph or reuse a completed transition.
It appends `revisionRef`/active-revision lineage. A Shot 01 replacement keeps the
same logical image `assetRef` and, only after exact QC, selection and admission,
becomes an immutable successor AssetVersion without activating a complete image
manifest or advancing production state. Complete successor image-manifest
activation and `REAL_VIDEO_READY` each remain reserved for one atomic manifest
covering all four exact current shots.

M11 follows the same non-rewinding rule. Initial admission covers four newly
admitted slots. A post-ready successor may append one to four changed-slot
admissions, but its activation always covers four unique slots by combining
`NEW_ADMISSION` with `REUSED_CURRENT`. A stale activation remains immutable audit
history and never remains visible as the canonical current video manifest.

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
The current ADR-0013 control-plane wave is narrower and stops before that GPU gate.

The maximum automatic result before unseen-media review is technically verified
candidates plus canonical append-only QC facts, including `FAIL`, with zero inferred
selection decisions and zero admitted AssetVersions. Master, Export and publication
remain prohibited.

## 10. Control-plane convergence

ADR-0013 adds four orthogonal public projections without changing the meaning of the
existing compatibility field:

- `rootState`: immutable production-root/readiness fact;
- `productionState`: latest valid append-only V5 gate; existing `state` remains its
  compatibility alias;
- `runtimeState`: V4 queue/lease/attempt/job projection only; and
- `visualQcState`: latest applicable canonical V5 append-only semantic assessment
  for the exact candidate lineage.

No axis may be inferred from another. Runtime `SUCCEEDED` is not visual-QC `PASS`,
and visual-QC `PASS` is not human selection or V5 admission.

The exact documentation-checkpoint values are `rootState=ROOTS_READY` and
`productionState=REAL_VIDEO_PLAN_READY`; all four current M11 candidates are
technically verified in V4 and the assisted semantic verdict is `FAIL`. Until the
canonical assessment records are appended, the public visual-QC projection reports
not-recorded/blocked rather than synthesizing `PASS`. The authorized first
convergence append makes the current candidate-set aggregate
`visualQcState=FAIL` without changing `productionState`.

V5 Core OS is the sole AssetVersion authority. For this run, the existing Episode
Production append-only evidence journal and production-gate projection are the
durable admitted-media source of truth. V4 databases/receipts, provider experiments,
filesystem artifacts and process-local asset registries are verification inputs
only and may not become a parallel admission authority.

Canonical `SemanticVisualQCDecision` records append `PASS|FAIL` and bind exact
workspace/run/revision/request/shot/candidate scope, payload/artifact/content and
source-AssetVersion digests, criteria,
assessment profile/version/digest, assessor kind/ref, evidence, time,
`publicationAllowed=false` and supersession/staleness lineage. Assisted QC remains
distinct from human selection and final approval.

Currentness is never inferred solely from the highest record version. A later
assessment explicitly supersedes the prior one. A changed shot, request, source
image AssetVersion, candidate bytes/content digest or assessment profile makes the
old assessment `STALE`; `FAIL`, `STALE`, missing or superseded QC
cannot authorize selection.

Despite its record-family name, `SemanticVisualQCDecision` is an assessor verdict,
not a `HumanSelectionDecision`, creative approval or final approval. The v1 result
set is exactly `PASS|FAIL`; adding `INCONCLUSIVE` requires a later accepted contract
extension.

## 11. Replay, recovery and single-frontend boundary

Candidate, technical-validation and QC facts may append without a production-state
transition. Exact idempotent replay returns the same canonical result; changed
content conflicts. Selection/admission is atomic for its exact scoped candidate set;
complete manifest activation is separately atomic across the exact four shots. V4
owns runtime lease/attempt recovery, while V5 restart reprojects from immutable
roots, append-only evidence and V4 runtime facts without inventing approval,
duplicating AssetVersions or trusting unrehashable bytes.

Every V5 real-media read consumes one immutable `EvidenceSnapshot`: `currentState`,
all gates and all typed records are observed under one in-memory lock or one SQLite
read transaction and sealed by `evidenceRevisionToken`. The real-media bundle and
four-axis state projection must consume that same snapshot rather than combine
separate reads. V4 runtime is an independently observed authority and is deliberately
outside the evidence token; its value cannot be used to infer or mutate V5 state.

Before success or replay, each typed write validates the complete ordered batch:
record kind/ref/version, idempotency key, request digest and sealed payload digest
must match exactly. Partial prior existence, missing or extra records, duplicate refs,
wrong ordering and mismatched slot coverage all fail closed. Initial M10/M11
admission covers exactly four unique selections, admissions and AssetVersions; an
M11 successor selection set equals the changed slots while its activation still
covers all four unique slots.

The authenticated Creator Public API and the single existing Creator Frontend are
the only user-facing control plane. The existing read projection adds, without
removing or rebinding fields:

```text
state                         # retained; exactly productionState
evidenceRevisionToken
rootState
productionState
runtimeState
visualQcState
activeRevision
activeRevision.activationState
videoLineageState
activeVideoAdmission          # immutable history; not canonical assets when stale
candidates[*].technicalState
candidates[*].visualQcState
candidates[*].selectionState
candidates[*].admissionState
```

The browser may render those fields and submit closed-world refs/digests; it may not
access SQL, V4/provider/private routes, filesystem paths or approval authority
directly. The response exposes no absolute/internal path, ComfyUI endpoint,
credential, raw provider payload or authority evidence body. No parallel
review/admin frontend is authorized.

The opaque `approvalRef`, actor/authority refs, authority-decision ref/digest/time
and `subjectDigest` recorded in a canonical `HumanSelectionDecision` are public
lineage pins, not an authority evidence body. Core may return those sealed scalar
pins so the Frontend can fail closed on a broken chain. It must never return the
external authority bundle, its `approvals` collection, nested subject body, raw
bundle bytes, credentials or operator configuration location.

This is a non-GPU control-plane correction. It authorizes governance, contract,
append-only persistence/projection, public API compatibility and their verification
work only. It does not authorize GPU dispatch, candidate generation, waiver-based
admission, Master/Export, publication, deployment or merge to `main`. Implementation
and test results must be reported against an exact repository, SHA, command and
scope; this contract text itself makes no acceptance claim.

## 12. Typed evidence ledger and additive migration

Episode Production evidence schema v2 adds one non-transition append-only record
ledger. Appending a record creates no gate or transition, changes no `current_state`
and rewrites no existing gate/fact/transition row. Application code uses typed V5
operations and independent validators for this closed v1 set:

- `Candidate`;
- `TechnicalValidation`;
- `SemanticVisualQCDecision`;
- `HumanSelectionDecision`;
- `AssetAdmission`; and
- `AssetVersion`.

The public caller cannot choose `recordKind`, submit an arbitrary payload, internal
path, producer/runtime claim, `actorRef` or authority claim. Every record is sealed
by its canonical `payloadDigest`. `Candidate` binds its source GenerationRequest
ref/digest back to the exact current root lineage; every downstream record binds the
prior record ref/version/payload digest. V4 must revalidate request, job/attempt,
workflow, runtime/model attestation, artifact bytes/digest and media probe before it
supplies sanitized candidate and technical evidence to V5. `TECHNICALLY_VERIFIED`
never means visual-QC `PASS`, human selection, admission, AssetVersion, approval or
publication.

The SQLite v1-to-v2 migration runs only against the exact known v1 schema, in one
transaction with rollback, restart-safe idempotency and fail-closed handling of
unknown/future/partial schemas. It preserves every existing gate/fact/transition
row, row order and digest byte. Before use, migration verifies integrity, foreign
keys, old row counts/digests and typed readback. Application services execute no SQL.

An admission batch emits `AssetAdmission` and the canonical `AssetVersion` together
only through V5. Neither is a caller-selected record kind, and the new ledger is not
a second asset registry.

Typed replay never trusts an operation key alone. It reconstructs and compares the
complete expected ordered record batch, including kind/ref/version, idempotency key,
request digest, payload digest and exact slot set. Initial admission requires four
unique selection/admission/AssetVersion chains. An M11 successor contains exactly
the changed-slot chains and one activation whose four unique slots are the exact
union of those new chains and the reusable current chains.

## 13. Initial convergence and stop state

The first authorized write after implementation and verification is exactly four
M11 v1 `Candidate` records, four matching `TechnicalValidation` records and four
assisted `SemanticVisualQCDecision(FAIL)` records. It appends zero
`HumanSelectionDecision`, zero `AssetAdmission`, zero `AssetVersion` and zero
production transitions. It does not forge a retrospective M10 or M11 QC `PASS`.

The resulting stop state remains:

```text
rootState=ROOTS_READY
productionState=REAL_VIDEO_PLAN_READY
runtimeState=TECHNICALLY_VERIFIED
visualQcState=FAIL
M11_SELECTIONS=0
M11_ADMISSIONS=0
VIDEO_ASSET_VERSIONS=0
EPISODE_MASTER=NOT_CREATED
EXPORT_ARTIFACT=NOT_CREATED
PUBLICATION_ALLOWED=false
```
