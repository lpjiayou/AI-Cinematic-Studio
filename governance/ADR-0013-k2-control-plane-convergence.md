# ADR-0013 — K2 Control-Plane Convergence

- Status: `ACCEPTED / IMPLEMENTATION OWNER ACCEPTED / COMPLETE / MAIN-VERIFIED AT 6d28a53f3a077f032e341a87412b19b37c00bb1e / NON-GPU / NON-PUBLISHING`
- Date: `2026-08-23`
- Decision owner: Project Lead / Architecture Owner `蔺鹏`
- Required base: `0a6962be`
- Extends: `ADR-0012-k2-internal-image-first-real-media-revision.md`
- Amends: ADR-0012 decisions 7 and 10 only for post-M10 successor revisions
- Preserves: ADR-0011's exact internal-only exception and ADR-0009's commercial/publication fail-closed rules
- Contract: `architecture/K2_INTERNAL_IMAGE_FIRST_REAL_MEDIA_REVISION_CONTRACT.md`

> This ADR owns the architecture decision and exact amendment boundary. It amends
> ADR-0012 only where explicitly listed. `CURRENT_MILESTONE.md` records execution
> facts and authorization but cannot redefine these ownership or persistence rules.

## Context

The canonical K2-001 production run has admitted M10 v1 image AssetVersions and
four technically verified M11 v1 video candidates. Assisted semantic visual QC is
`FAIL` for the current four-video set. The candidates are unselected and not
admitted; no video AssetVersion, EpisodeMaster, ExportArtifact or publication
authorization exists.

The existing implementation exposes several valid but different kinds of state:
the immutable production root, the latest V5 production transition, V4 runtime-job
state and visual-review conclusions. Treating any one of them as a substitute for
the others would let technical completion appear as production admission. The
current replacement cycle also needs an append-only way to record failed candidates
and successor media without rewinding the production state or creating a second
asset, review or frontend stack.

This ADR refines ADR-0012 for that control-plane convergence. It does not rewrite
the historical M10 v1 admission, declare the current M11 candidates acceptable, or
authorize GPU work.

For post-M10 successor revisions only, this decision supersedes ADR-0012 decisions
7 and 10 where they require every selection/admission command to contain exactly
four items. The original M10 v1 four-item atomic batch remains immutable history.
Successor evidence may converge one exact shot at a time; activation of a complete
four-shot manifest remains atomic.

## Decision

### 1. Four state axes are projected separately

The canonical public projection has four orthogonal axes:

1. `rootState` is the immutable root/readiness fact for the production run. It is
   not advanced by media execution or review.
2. `productionState` is derived only from the latest valid append-only V5 production
   gate/transition. The existing public `state` field remains a compatibility alias
   of this axis; it must not be rebound to runtime or review state.
3. `runtimeState` is the V4 queue/lease/attempt/job projection. `SUCCEEDED` means
   only that execution and technical verification succeeded.
4. `visualQcState` is derived from the latest applicable canonical V5 append-only
   semantic visual-QC assessment for the exact candidate lineage. Missing, stale or
   superseded assessment is not `PASS`.

Consumers must not collapse these axes into one mutable lifecycle enum. A runtime
success or visual-QC pass cannot advance `productionState`; only the admission gate
defined below can do so.

At this documentation checkpoint, the exact current facts are:

- `rootState=ROOTS_READY`;
- `productionState=REAL_VIDEO_PLAN_READY`;
- all four current M11 V4 jobs/candidates are technically verified; and
- assisted semantic visual QC is `FAIL`, but its canonical V5 record and the new
  public axes remain implementation work.

Until that record exists, a public projection must report visual QC as not recorded
and blocked; it must not infer `PASS`. After the authorized initial convergence
append, the current four-candidate aggregate projects `visualQcState=FAIL`.

### 2. V5 is the sole AssetVersion authority

V5 Core OS is the sole authority that may admit an immutable `AssetVersion`. For
this exact K2 production run, the existing V5 Episode Production append-only
evidence journal and its production-gate projection are the durable authority for
admitted media lineage.

V4 jobs, provider/ComfyUI receipts, experiment evidence, filesystem artifacts and
process-local asset registries are inputs to verification only. None may create,
mutate or project an admitted AssetVersion independently. No parallel asset registry
or admission database is permitted.

A replacement keeps the same logical `assetRef`, increments its immutable version,
and binds the exact predecessor through `supersedesAssetVersionRef` plus digests.
Historical AssetVersions remain addressable and are never overwritten.

### 3. One candidate-to-AssetVersion chain is canonical

Both image and video revisions use one ordered chain:

```text
GenerationRequest
→ V4 runtime candidate and immutable execution receipt
→ V5 Candidate
→ V5 TechnicalValidation
→ V5 SemanticVisualQCDecision
→ exact human HumanSelectionDecision resolved by ApprovalAuthority
→ V5 AssetAdmission
→ immutable V5 AssetVersion
```

Every edge is closed-world and digest-bound to the same workspace, production run,
revision, request, shot and candidate. Technical verification, semantic QC, human
selection and admission are distinct facts. General authorization to continue,
successful GPU execution, an assisted review or a valid approver identity is not a
selection and cannot implicitly create an AssetVersion.

### 4. Semantic visual QC is canonical and append-only

V5 records `PASS` and `FAIL` semantic visual-QC verdicts; failures are not
discarded. Each verdict binds at minimum:

- workspace, production-run, revision, request, shot and candidate refs;
- candidate payload/content digest and immutable source-AssetVersion lineage;
- the evaluated criteria/profile, including identity, wardrobe, location,
  action/prop semantics and motion/deformation where applicable;
- reviewer/assessor provenance, evidence refs/digests and recorded time; and
- supersession/staleness lineage when a later assessment replaces its applicability.

Assisted semantic review remains evidence, not a human media-selection decision or
final approval. The current M11 v1 verdict is `FAIL`; convergence must preserve that
verdict as append-only canonical QC evidence before any successor admission path is
opened. It must not reinterpret the current candidates as passing.

### 5. The evidence ledger is closed-world and non-transitioning

The existing V5 Episode Production evidence database may migrate additively from
schema v1 to v2 to add a non-transition record ledger. Appending one of these records
does not create a gate or transition, change `current_state`, or rewrite an existing
gate, fact or transition row.

The application exposes typed operations with independent closed-world validators,
not a generic caller-selected `recordKind + payload` fact-injection surface. The
authorized v1 record families are:

- `Candidate`;
- `TechnicalValidation`;
- `SemanticVisualQCDecision`;
- `HumanSelectionDecision`;
- `AssetAdmission`; and
- `AssetVersion`.

`AssetAdmission` and `AssetVersion` are emitted together only by the V5 admission
operation; neither is a caller-selected record kind. Public callers cannot submit a
record kind, internal path, producer/runtime claim, `actorRef` or authority claim.
Every record is sealed by its canonical `payloadDigest`. `Candidate` additionally
binds its exact source GenerationRequest ref/digest back to the current root lineage;
each downstream record binds the exact prior record ref/version/payload digest.

The v1-to-v2 migration is permitted only when the exact known v1 schema matches. It
runs in one transaction, rolls back on any failure, is restart-safe and idempotent,
and preserves all existing gate/fact/transition rows, row order and digest bytes.
Unknown/future or partially matching schemas fail closed. Integrity, foreign keys,
row counts/digests and typed readback are verified before the migrated store is used.
Application services do not execute SQL.

### 6. Selection uses digest-pinned ApprovalAuthority

The authenticated caller supplies the requested decision, but client-supplied
`actorRef`, role, approver claims or authority flags are never authority. V5 resolves
the actor and exact decision scope through the existing ApprovalAuthority boundary.

For every new selection/admission, the authority result must be server-held and
digest-pinned. The recorded decision binds the authority evidence ref/digest, actor,
decision, workspace/run/revision scope, candidate ref/content digest and applicable
visual-QC ref/digest. Missing, stale, mismatched, unavailable or unverifiable
authority fails closed. An idempotency retry cannot substitute a different authority
or candidate payload.

M10 v1 remains immutable historical admission under the contract that produced it.
This ADR does not retroactively forge new authority evidence for that history. All
successor image admissions and all M11 video admissions use the converged rule.

This reuses the accepted M6 ApprovalAuthority boundary without expanding the M6
schema. `FAIL`, stale or missing semantic QC makes the candidate
ineligible for selection/admission even when the actor is otherwise authorized.

### 7. Recovery and replay remain deterministic

Candidate, technical-validation and visual-QC records may be appended without a
production-state transition. Exact replay of the same idempotency key and canonical
payload returns the same result; a changed payload conflicts. Selection plus
AssetVersion admission is atomic for the exact scoped candidate set, so restart or
failure cannot leave a decision without its matching admission or a partially
written AssetVersion lineage.

V4 retains runtime lease/attempt recovery. V5 restart reconstructs the four public
axes from the immutable root, append-only evidence and V4 runtime projection; it
must not infer an approval, repeat an admission or trust an unrehashable artifact.
Referenced receipts and media bytes are revalidated by their pinned digests at the
boundary where they are consumed. Missing or corrupted evidence fails closed.

Rework does not rewind `productionState` or reuse a one-time transition name. It is
identified by append-only `revisionRef`/active-revision lineage. A selected Shot 01
successor may be admitted as image AssetVersion v2 in one exact single-shot atomic
batch after its QC and authority requirements pass; only that admitted version may
seed the bounded 49-frame calibration. That single-shot successor does not activate
a new complete image manifest or advance the production state. Activation of a
complete successor image set, and `REAL_VIDEO_READY` for the complete successor
video set, each requires one atomic manifest covering all four exact current shots.

Assessment currentness is explicit rather than inferred from the highest record
version. A successor assessment binds and supersedes the prior assessment. Any
change to the upstream shot, generation request, source image AssetVersion,
candidate bytes/content digest or assessment profile/version/digest makes the prior
assessment `STALE`; it cannot authorize selection. A
`SemanticVisualQCDecision` records assessor kind/ref, criteria, evidence,
`PASS|FAIL`, creation time, publication-disabled state and explicit
supersession/stale reason.

Despite its record-family name, `SemanticVisualQCDecision` is only an assessor's
semantic-fitness verdict. It is never a `HumanSelectionDecision`, creative approval
or final approval. `INCONCLUSIVE` is not part of this v1 closed set and requires a
later accepted contract extension.

### 8. There is one Creator Frontend

The existing authenticated Creator Public API and single Creator Frontend remain the
only user-facing control plane. Review and replacement controls must extend that
surface; they must not create a parallel admin/review application.

The browser may render the four axes and submit closed-world refs/digests. It may not
read SQL, call V4/provider/private routes, send filesystem paths, resolve authority,
or treat local UI state as production truth.

The existing real-media-revision read projection is extended additively with:

```text
state                         # retained; exactly productionState
rootState
productionState
runtimeState
visualQcState
activeRevision
candidates[*].technicalState
candidates[*].visualQcState
candidates[*].selectionState
candidates[*].admissionState
```

It exposes no absolute/internal path, ComfyUI endpoint, credential, raw provider
payload or authority evidence body.

### 9. This correction is non-GPU and non-publishing

The authorized scope is governance, contracts, append-only persistence/projection,
public API compatibility and the tests needed to prove those control-plane changes.
It does not authorize GPU dispatch, candidate generation, media admission by waiver,
Master/Export creation, publication, deployment or merge to `main`.

At the time of this decision, implementation and test verification are pending. No
test result is claimed by this ADR.

The first authorized convergence write is limited to four exact M11 v1
`Candidate` records, their four exact `TechnicalValidation` records and four assisted
`SemanticVisualQCDecision(FAIL)` records. It creates zero
`HumanSelectionDecision`, zero `AssetAdmission`, zero `AssetVersion` and zero
production transitions; `productionState` remains `REAL_VIDEO_PLAN_READY`. No
retrospective M10 or M11 QC `PASS` may be fabricated.

## Rejected alternatives

- Use one mutable state for production, runtime and review: hides authority boundaries
  and makes a technical success look admitted.
- Overwrite M10 v1 or rewind the production state for rework: breaks immutable
  lineage and replay.
- Treat the assisted review document as the only QC store: loses canonical,
  digest-bound PASS/FAIL evidence.
- Let V4, a provider experiment or a process-local registry issue AssetVersions:
  creates a second source of truth.
- Trust client actor/role claims or an unpinned approval response: permits replay and
  scope substitution.
- Add a dedicated review frontend or direct browser-to-runtime route: creates a
  second control plane.
- Auto-admit the current M11 candidates after technical verification: contradicts
  their semantic visual-QC `FAIL` and the human-selection boundary.

## Consequences

The current canonical production projection remains `REAL_VIDEO_PLAN_READY`. The
four M11 v1 candidates remain technically verified but semantic-QC-failed,
unselected, not admitted and publication-disabled. No video AssetVersion,
EpisodeMaster, ExportArtifact or publication transition is created by this decision.

Implementation must converge the existing stores and public projection around the
rules above without deleting or rewriting accepted history. Compatibility clients
may continue reading `state` as `productionState`; new clients can render all four
axes explicitly. Only verified follow-on implementation may claim the persistence,
replay, API and recovery gates complete.

## Project Lead implementation acceptance — 2026-08-25

The Project Lead accepts the non-GPU control-plane implementation as
`OWNER ACCEPTED / COMPLETE / MAIN-VERIFIED` at Core commit
`6d28a53f3a077f032e341a87412b19b37c00bb1e`, tree
`369c3b1479f3136cc32fcbc4efd0fa24e4964058`.

This acceptance supersedes this ADR's earlier implementation-pending and no-main-
merge statements as current execution status. Those statements remain historical
facts about the authorization checkpoint at which they were written.

Acceptance is limited to the implemented ledger, four-axis projection, single V5
AssetVersion authority, digest-pinned approval boundary, candidate lifecycle,
recovery/replay controls, public API sanitization and verified tests. It does not
claim that the bounded first convergence append ran against the live canonical host.
It accepts no K2-001 media: semantic visual QC remains `FAIL`; all M11 v1 and Shot
01 R2–R7 candidates remain unselected and not admitted; no video AssetVersion,
EpisodeMaster, ExportArtifact or publication authorization exists.

The complete acceptance and evidence boundary is recorded in
`K2_001_ADR_0013_MAIN_CLOSEOUT_2026-08-25.md`.
