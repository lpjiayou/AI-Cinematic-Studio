# AI Cinematic Studio 参考视频能力与工作区布局合并基线

> Review date: `2026-08-17`
>
> Version: `REVIEWED / PARTITIONED BASELINE v2.0`
>
> Repository authority: `CROSS-REPOSITORY DESIGN AND EVIDENCE BASELINE`
>
> Current implementation authority: `FRONTEND LAYOUT/DOCUMENT CLOSEOUT ONLY`
>
> Future capability authority: `M7–M19 NOT OPEN; EXPERIMENT AND ADR REQUIRED`

## 0. Purpose and disposition

This document is the repository-resident, reviewed successor to the local merged draft
`REFERENCE_VIDEO_CAPABILITY_AND_WORKSPACE_MERGED_BASELINE.md` dated 2026-08-16. It
consolidates:

1. `WORKSPACE_LAYOUT_DIMENSION_PATCH.md`;
2. `MULTI_CHARACTER_M6_EXTENSION_AND_M10_NOTICE.md`;
3. the inspected 30-second reference-video characteristics;
4. the current Commercial Frontend implementation;
5. the accepted Core M1–M6 boundaries and M7–M19 status;
6. the V2.3 System Master Plan and R5C evidence route.

The original draft correctly found real layout and multi-character production gaps,
but mixed three different kinds of work. This revision splits them explicitly:

| Work | Current local scope | Authority |
| --- | --- | --- |
| Workspace geometry and responsive behavior | yes | Frontend closeout and documentation |
| Reference-video capability decomposition | yes | design/evidence baseline only |
| M6 schema expansion | no | rejected |
| M7–M16 implementation | no | future milestone authorization required |
| Provider/GPU experiment | no | separate rights, budget and experiment approval required |

Therefore this file **is part of the local project work**, but it is not proof that
reference-video generation, multi-character production or M7–M16 is implemented.

## 1. Current verified baselines

### 1.1 Frontend

Remote baseline:

- repository: `lpjiayou/AI-Cinematic-Studio-Frontend`;
- commit: `95dc3f6b20ed679db6bc3da55906be94f6963630`;
- tree-equivalent local duplicate: `0420b64caf7cab6e83b045cf8ea018e603609159`;
- current AUTH-W1 branch: `feat/fe-auth-workspace-isolation`;
- current suite: `112 / 112` tests passed across 23 files;
- TypeScript, ESLint and production build: passed.

The implementation already contains the reviewed geometry:

```css
--acs-object-nav-width: 15rem;
--acs-inspector-width: 22.5rem;
--acs-topbar-min-height: 3.5rem;
--acs-candidate-strip-results-min-height: 7.5rem;
```

`CandidateStrip` supports `hidden / progress / results`; hidden content is unmounted and
releases its grid row. Workspace and editor shells use flexible center columns and
responsive removal/drawer patterns. Media treatment is page-local rather than a global
replacement for every form surface.

The AUTH-W1 Frontend closeout synchronizes
`docs/design-system/ACS_LAYOUT_SYSTEM.md` with these implemented tokens and the fluid
`100%` application canvas. Page-level overrides, including Script Studio, remain
intentional when they have a task-specific reason and responsive proof.

### 1.2 Core

AUTH-W1 G0 remote checkpoint:

- branch: `feat/acs-auth-workspace-isolation`;
- commit: `33c0868dda7054f81c3a1475d0d331e477a0d8c5`;
- tree: `ccb317f9021eb26d310f3f6a219578cbea80b1f3`;
- baseline full suite: `471 / 471`.

Accepted capability state remains:

- M1–M5: available on accepted public boundaries;
- M6: only the owner-accepted P0–P3 G1-R1 surfaces; external authorities remain
  required;
- M7–M19: status projection only, implementation not open.

M6 already provides episode-baseline character, state, relationship, lineage and
identity/rights reference facts. It is not the owner of shot composition, masks,
generation parameters, GPU execution, video motion or crowd rendering.

### 1.3 Reference-video evidence

The inspected local video is approximately 30 seconds, 1920×890 H.264 with mono AAC,
and contains roughly 16 short cuts. It demonstrates a production target involving
recurring lead/supporting characters, wardrobe, props, locations, varied shot sizes,
two-person shots and anonymous background crowds.

It is a screen recording with platform controls rather than a clean master. It does
not establish how the source was produced, how many extras were present, whether it was
pure AI, or whether the quality is repeatable at scale. The following claims remain
forbidden without independent evidence:

- a precise crowd count;
- “global highest AI-video level”;
- stable one-click reproduction;
- proof of a pure-AI pipeline;
- a fixed one-GPU-day schedule or budget.

The video itself is not committed by this baseline. Rights and provenance must be
approved before it is used as a model/provider input or distributed test asset.

## 2. Workspace layout contract

### 2.1 Canonical geometry

| Region | Canonical rule |
| --- | --- |
| Object navigator | `15rem` default; page override requires documented task need |
| Project navigator | `13.75rem`; unchanged |
| Inspector | `22.5rem` default; may collapse to drawer at responsive threshold |
| Top bar | minimum `3.5rem`; content may grow |
| Candidate results | minimum `7.5rem`, bounded scroll when necessary |
| Candidate progress | intrinsic/automatic height |
| Candidate hidden | unmounted; no empty grid row |
| Center canvas | `minmax(0, 1fr)` and owns overflow behavior |

Exact fixed heights that can crop zoomed, localized, validation or error content are
not allowed. Character Studio uses the project navigator, not the object navigator, in
its outer workspace calculation. Visual compare/single/grid stages belong to the page
task that needs them; forms, relationships and continuity text remain normal surfaces.

### 2.2 Responsive and accessibility proof

The applicable Frontend checkpoint must verify:

- 2560, 1440, 1280, 1024, 640, 390 and 320px viewport widths;
- no root-level horizontal overflow;
- 200% zoom without clipped text or inaccessible controls;
- keyboard navigation, Escape close and focus restoration for drawers/overlays;
- hidden inspector/navigator content remains reachable through an accessible control;
- typecheck, lint, unit/component suite and production build all pass.

This contract changes presentation geometry only. It may not invent project, episode,
character, asset, provider or job facts.

## 3. Multi-character responsibility map

The gap is cross-module and must not be solved by expanding M6.

| Milestone | Responsibility for the target |
| --- | --- |
| M6 Series Intelligence | character definitions, state intervals, relationships, visual identity rules, episode baseline, lineage and rights references |
| M7 Narrative Closed Loop | stable character bindings in dialogue/action and narrative conflict checks |
| M8 Storyboard + Shot Domain | shot cast, role in frame, composition/pose/depth/occlusion intent and script/baseline provenance |
| M9 Asset Intelligence | identity, wardrobe, prop, scene and reusable crowd asset requirements, rights and provenance |
| M10 Image Generation | N-identity conditioning, region/pose resolution and generated AssetVersion binding |
| M11 Video Production | identity-to-body continuity through motion, occlusion, interaction and shot transitions |
| M12 Audio Production | voice identity, dialogue order, emotion, lip-sync and character/audio traceability |
| M13 Composition | deterministic timeline, subtitles, grade, tracks and preview |
| M14 QC + Approval | identity swap/bleed, position, wardrobe, crowd, lip-sync and local-regeneration checks |
| M15 Episode Master | clean master, version, archive, rights and final provenance |
| M16 Batch Orchestration | queue/DAG/worker/retry/recovery/cost/throughput at increasing scale |

Future M8 may introduce a shot-cast concept, but this file freezes only responsibility,
not a production schema. It must not predeclare model names, adapter weights, masks,
seeds or provider parameters as M6 character facts.

## 4. Crowd ownership

Crowd is a layered production concern:

| Layer | Owned fact |
| --- | --- |
| M6 | durable era/location/faction/culture/wardrobe/prohibition rules; no anonymous-extra identities |
| M8 | per-shot density, activity, spatial distribution, foreground/background and continuity intent |
| M9 | crowd plates/styles/assets, version, rights, provenance and reuse |
| M10/M11 | image/video generation or layered composition execution |
| M14 | duplicate face, anatomy, period mismatch, flicker and cross-shot drift QC |

No module may duplicate another layer's authoritative fact merely to simplify a page or
provider request.

## 5. Evidence gates before capability authorization

Schema must not be changed first and justified afterward. The valid order is:

### Gate 0 — rights and reproducible inputs

- two or three visually distinct, rights-cleared identity references;
- fixed wardrobe, hair, props, scene and prompt baseline;
- fixed provider/workflow and evidence format;
- digest, parameters, duration, retries, cost and failure reason for every output.

No GPU/provider run begins before Gate 0 rights and budget approval.

### Gate 1 — two-identity still images

Prove front-facing pair, over-shoulder, profile pair, depth-separated pair and occlusion.
Measure missing identity, identity swap/bleed, body-position mismatch, wardrobe/prop
crosstalk, retry count, duration and cost.

### Gate 2 — multi-shot still continuity

Use the same cast across close, medium, high-angle, two-person and group compositions.
Human blind review and machine similarity may support one another but neither replaces
the other.

### Gate 3 — multi-character short video

Progress from dialogue/expression to turn/gaze, parallel movement or hand-off, then
occlusion and crossing. Review identity-to-position frame by frame, not merely whether
both faces appeared somewhere in the clip.

### Gate 4 — 30-second edit specimen

Target approximately 14–16 cuts, three persistent characters, one principal location,
anonymous background crowd, dialogue/ambience/music/subtitles, human approval, clean
master and complete asset/rights/provenance records. The target reproduces production
difficulty, not the reference persons or copyrighted composition.

## 6. Failure routes

If Gate 1 fails, do not freeze a multi-identity schema or expand M6. Evaluate bounded
region conditioning, per-character generation plus composition, or another compliant
provider under a new experiment decision.

If Gate 2 or Gate 3 fails, a valid hybrid route may use separate character layers,
fixed scene/crowd plates, 1–3 second motion units, local repair, interpolation,
upscaling and professional editing. Precise contact motion may use rights-cleared live
action, 3D or motion capture followed by AI styling. Choosing a hybrid route is not an
architecture failure; it is an evidence-based execution decision.

## 7. R5C and product readiness

| R5C route | Required evidence contribution |
| --- | --- |
| R5C-2 Identity Lock | multi-view identity, rights, wardrobe and identity-asset lock |
| R5C-3 Pose Motion | pose, occlusion, interaction and motion continuity |
| R5C-4 DAG Render / GPU Worker | candidates, retries, local regeneration, execution evidence and scheduling |
| R5C-5 Full Video / Asset Registry | composition, audio, QC, master, versions, rights and provenance |

Earliest “similar preview is feasible” decision: M13 preview exists and M14
multi-character QC passes. Deliverable master: M15. Repeatable production: M16 proves a
real `1 → 3 → 10 → 30` progression with measured quality, recovery, throughput and
cost. One selected 30-second specimen does not prove scale.

## 8. Governance sequence

1. Keep current M6 schema and authorization unchanged.
2. Complete Frontend layout documentation/regression closeout independently.
3. Record shot-cast, multi-identity, crowd and identity-swap QC as forward gaps.
4. Obtain separate rights, security, budget and experiment authorization for Gates
   0–3; experiment code must not change production schemas.
5. Use evidence to propose an ADR for the M8–M14 cross-module contract.
6. Only an Accepted ADR plus a Project Lead milestone may authorize production
   schema/port/provider implementation.
7. Preserve no-force publication, exact scope, tests, provenance and remote verification
   at every checkpoint.

## 9. Final decision

- The Frontend layout portion is current local work; its canonical documentation is
  synchronized and its tests, typecheck, lint and production build are verified.
- Reference-video decomposition is current local design/evidence work and is now stored
  in this Core repository as the single cross-repository baseline.
- M6 expansion remains rejected.
- Multi-character/reference-video production belongs to future M7–M16 contracts and
  requires rights-cleared experiments plus a new ADR and explicit milestone.
- “Conditionally reachable” remains the accurate target status; no implementation,
  production-readiness or scale claim is made here.
