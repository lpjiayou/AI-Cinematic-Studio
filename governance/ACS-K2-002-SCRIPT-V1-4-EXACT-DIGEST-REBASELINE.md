# ACS-K2-002 Script v1.4 Exact-Digest Repository Rebaseline

| Field | Decision |
| --- | --- |
| Record ID | `ACS-K2-002-SCRIPT-RB2` |
| Record Type | Exact script revision, repository lineage, and fail-closed machine-mapping decision |
| Decision Date | `2026-08-26` |
| Status | `OWNER AUTHORIZED FOR EXACT REPOSITORY INGEST / ACTIVE ON PROTECTED MERGE / NON-GPU ONLY` |
| Decision Owner | Project Lead / Architecture Owner / Repository Governance Owner `蔺鹏` |
| Parent Authority | [ADR-0014](ADR-0014-k2-001-archive-k2-002-changan-start.md) and [ACS-K2-002-GOV-RB1](ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md) |
| Architecture Baseline | AI Cinematic Studio V2.3; unchanged |
| Active Project / Episode | `K2-002-CHANGAN / EP01 ONLY` |
| Exact Uploaded Owner Revision Source | `source/K2-002-CHANGAN-UPLOADED-OWNER-REVISION-v1.4.md` at `33067592eb3c0c632d10f2fea3ef20b77ab319ee5aec9990ad0b285bfb548580` |
| Repository-Reviewed v1.4 Candidate | `K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md` at `a954cc970c71f73028ecf5a6f5fe5d2603776cf49d21fb33da676bedf4093faf` |
| Exact Source Byte Form | `49,096 bytes / UTF-8 / no BOM / LF / final LF` |
| Repository Ingest Authorization | `OWNER AUTHORIZED` |
| Script Content Acceptance | `PENDING EXPLICIT CONTENT ACCEPTANCE` |
| Domain Fact / Live Registration | `false / NOT_APPLIED` |
| ShotPlan / Camera / ExecutableShotGraph | `DRAFT ONLY / NOT_APPROVED / NOT_READY / NOT_COMPILED` |
| Assets / Provider / GPU / Publication | `NONE_ADMITTED / NOT_AUTHORIZED / NOT_STARTED / false` |

> Later decision overlay — `2026-08-26`:
> [ACS-K2-002-SCRIPT-ACC3](ACS-K2-002-SCRIPT-V1-4-ACCEPTANCE-AND-EP01-IMPLEMENTATION.md)
> accepts the exact repository-reviewed v1.4 digest and authorizes the ordered EP01
> non-GPU implementation. This RB2 record remains immutable evidence of the earlier
> repository-ingest checkpoint; its pending-acceptance statements are historical after
> ACC3, not current execution authority.

## 1. Decision

The Decision Owner directed the uploaded v1.4 to be written into Core. The uploaded
document itself states that it supersedes only the external v1.3 and requires a separate
Core rebaseline. A direct replacement would also regress Core-reviewed disclosure,
identity, pronoun, Shot authority, frame/profile and fail-closed constraints that were
outside the six directed changes.

This record therefore authorizes a two-layer ingest: preserve the uploaded bytes exactly,
then replay the six directed logic fixes on the Core-reviewed v1.3 predecessor. The
resulting repository-reviewed v1.4 becomes the current repository revision candidate
after protected merge. This does not infer final Script Owner content acceptance.

The source file is preserved byte-for-byte at:

```text
docs/16-k2-production/k2-002-changan/source/K2-002-CHANGAN-UPLOADED-OWNER-REVISION-v1.4.md
```

The rebase result is separate:

```text
docs/16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md
```

The source file's embedded `NOT_REPOSITORY_BASELINE` remains true for that source
artifact. Only the separately reviewed rebase result can become the current repository
candidate; neither file is promoted to a live domain fact.

## 2. Preserved provenance and supersession

The following lineage is mandatory and additive:

| Evidence | SHA-256 / state |
| --- | --- |
| Uploaded v1.2 bytes | `8dec72d6bde85768c846ec93dd7f06adfa1f5dd9bcddb0f118455b2f9abe37de` |
| Repository LF-normalized v1.2 | `7773438973da8fa0b0bd5e51d7adac542cdadf273c4eaf1cc5afcc5504d87f8b` |
| External v1.3 direct source | `5d8f35560648bc6a3b3e02d6267782c3f8e422cc7a76aea1cffb70014a90cee8` |
| Prior Core reviewed v1.3 | `5e33f3469765a79c91ef0c4ffa150e259d500bc596d2eef94da1fc6441a7ae8f` |
| Uploaded Owner revision source v1.4 | `33067592eb3c0c632d10f2fea3ef20b77ab319ee5aec9990ad0b285bfb548580` |
| Repository-reviewed rebase candidate v1.4 | `a954cc970c71f73028ecf5a6f5fe5d2603776cf49d21fb33da676bedf4093faf` |

The repository-reviewed v1.4 supersedes the current repository candidate pointer. It does not delete, edit or
retroactively alter the v1.2 source, the Core v1.3 review candidate, or the historical
`k2-002-changan-preproduction.v1.json` machine ledger.

Any byte change to either v1.4 artifact requires a new file name, new digest, new review and a new
applicable decision. Rollback changes the current pointer only; historical evidence is
never overwritten.

## 3. Frozen v1.4 corrections

The repository-reviewed rebase candidate binds these corrections while retaining the
Core v1.3 safeguards:

1. EP01 Pei Yun remains silent and does not confirm identity, relationship or prior
   events.
2. EP13 uses only `校书郎` or `你` before the surname disclosure boundary.
3. EP28 handles `册` and the blank nameplate landing; EP29 recognizes `之`, stabilizes
   its world change, and only then unlocks `外`.
4. The lantern bearer moves at cumulative counts 3, 6, 9, …, 30. A movement episode
   has no second independent durable change; EP30 uses one atomic
   `D0_TERMINAL_CLOSURE`.
5. The visible nameplate chain is EP01 rack → EP09 gap → EP15 bearer → EP28 L1 north
   floor → EP30 restored.
6. EP29 ends at `unlocked=30 / recognized=29`; Pei Yun's last-trace confirmation is
   required before `last_trace_damage_state=DESTROYABLE`.

The uploaded source was not adopted wholesale. In particular, the rebase preserves the
Core EP01 narration boundary (`浮出了一个不该存在的字`), Pei Yun's `它` pronoun,
the prior identity anchors, face-lock boundary, frame/profile contract, lip-sync
fail-closed rule, historical-fantasy boundary and non-executable Shot authority.

## 4. Versioned machine mapping

The current fail-closed mapping is additive:

```text
HISTORICAL_MACHINE_LEDGER=k2-002-changan-preproduction.v1.json / V1.3
CURRENT_MACHINE_LEDGER=k2-002-changan-preproduction.v2.json / V1.4 EP01
MACHINE_MAPPING_STATE=V1_4_EP01_MAPPED_FAIL_CLOSED
```

The v2 ledger maps the repository-reviewed v1.4, not the uploaded source directly. It
preserves the Core SH03 narration and updates the blank nameplate in SH08, silent SH10,
the blank-nameplate requirement, and the EP01 end continuity state. It preserves 12
shots and 720 frames.

The mapping is not a `ScriptVersion`, approved ShotPlan, `CreativeShotVersion`,
`StoryboardVersion` or `ExecutableShotGraph`. It has no canonical refs and may be used
only by isolated tests and the already authorized zero-write preflight path.

## 5. External asset evidence

The uploaded `final-assets-v1.2.zip` is recorded as external evidence at SHA-256
`532765d91b56692e611cabb9fcbd3d8ecc916f169f5c4e2b3b9e82a56bbe99c6`.
Its bytes are not copied into Core and are not AssetVersions.

The package remains bound to v1.3 and requires v1.4 rebaseline. Its EP01 audio/shotgraph,
L1/nameplate continuity, state manifests and later terminal requirements are stale or
failed semantic/visual review. Rights, exact requirement mapping and admission are
unverified. Therefore:

```text
EXTERNAL_ASSET_BYTES=PRESENT_AS_EVIDENCE
CANONICAL_ASSET_VERSION_MAPPING=NOT_VERIFIED
ASSET_ADMISSION=NONE
PROVIDER_DISPATCH_ALLOWED=false
```

## 6. Unchanged fail-closed boundary

```text
SCRIPT_OWNER_ACCEPTANCE=PENDING_EXPLICIT_CONTENT_ACCEPTANCE
DOMAIN_FACT=false
CANONICAL_REGISTRATION=NOT_APPLIED
DURABLE_REGISTRATION_RECEIPT=NOT_IMPLEMENTED_FAIL_CLOSED
M5_EPISODE_PLAN_ITEM_BINDING=PENDING
SHOT_PLAN_AUTHORITY=LOCAL_STRUCTURAL_REPRESENTATION_NOT_APPROVED
SHOT_PLAN_APPROVAL=NOT_VERIFIED
CAMERA_CONTRACT=NOT_READY
EXECUTABLE_SHOT_GRAPH=NOT_COMPILED
LIVE_CANONICAL_MEDIA_APPEND=NOT_IMPLEMENTED
ASSET_VERSION_ADMISSION=NONE
PROVIDER_OR_GPU_DISPATCH=false
CANDIDATE_SELECTION_OR_ADMISSION=false
BULK_GENERATION_ALLOWED=false
PUBLICATION_ALLOWED=false
```

No K2-001 ref, receipt, exception, media asset or production authority transfers to
K2-002. No part of this decision authorizes live canonical mutation, M10/M11 append,
V4 dispatch, GPU use, media selection, admission, master/export, release or publication.

## 7. Protected merge gate

This exact candidate must independently satisfy the current Core governance controls:

1. an independent technical review bound to the exact candidate SHA/tree with no open
   blocker, high or medium finding;
2. Markdown checks;
3. Documentation Links;
4. Unit Tests;
5. Contract Tests;
6. Integration Tests;
7. resolved review threads, strict current-head checks, linear history, squash-only
   protected merge, no force push, no deletion and no bypass.

Core's zero-approval single-operator exception does not waive independent technical
review or any required check. Evidence from PR #11 or another tree cannot be reused.
