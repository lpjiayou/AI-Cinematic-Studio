# AI Cinematic Studio Delivery Governance Package v1

> Status: `ACCEPTED EXECUTION CONTRACT`
>
> Date: `2026-08-17`
>
> Mode: `AUTO-SEQUENTIAL / EVIDENCE-GATED / FAIL-CLOSED`
>
> Authorized wave: `G0 → G1 → G2 → G3 → G4 → G5 → G6 → G7 → REMOTE VERIFY`

## 1. Authorization and objective

The Project Lead instruction dated `2026-08-17` authorizes one bounded vertical
delivery wave. The objective is to close one inspectable **K2 Golden Episode** from
accepted M1–M6 inputs through a playable episode master and a connected production
workspace.

This is not authorization to restart M1–M19 as a broad platform programme. It does
not authorize M16 batch production, M17–M19 commercialization, speculative
microservices, destructive persistence changes, or claims of live provider/GPU
production readiness.

Automatic progression means that a passing machine-verifiable gate may enter the
next listed gate without an interim review request. It never means automatic human
approval of creative, identity, QC, or final-master decisions.

## 2. K2 fixed scope

K2 contains exactly one production chain with:

- one authenticated tenant/workspace principal;
- one content profile, Series Project, Series and Episode;
- one confirmed creative plan;
- one confirmed `SeriesPlanVersion` and `EpisodePlanItem` binding;
- one active M6 authority baseline;
- one confirmed `ScriptVersion` and one consistency validation;
- one `StoryboardVersion` and one executable Shot Graph;
- one episode production run;
- resolved asset requirements and immutable generated media results;
- one `TimelineVersion`, one `PreviewCandidate` and one QC report;
- separate recorded creative, identity, QC and final-master decisions;
- one immutable `EpisodeMaster` and one playable MP4 export.

At least two named characters must be present. Exact scene, shot and media counts are
frozen by the G1 episode manifest and may not drift silently after that checkpoint.
Every downstream record must retain stable upstream refs, versions, content digests
and lineage sufficient to explain and reproduce its state.

## 3. G0 fact baseline

| Surface | Verified fact at wave start | Consequence |
| --- | --- | --- |
| Core | Branch base `79eda3c0bc3d20b97fdca3751a9c5e6247303962`; `480/480` tests pass | Preserve accepted M1–M6 and AUTH-W1 behavior |
| Frontend | Branch base `05c3647b1f1fa76d6d67da90cab297ea029fd27d`; `112/112` tests pass | Extend the single Creator UI; do not create another frontend |
| Public boundary | Authenticated Creator Public API derives workspace from the principal | Every new public route must use the same fail-closed boundary |
| M6 | Accepted internal surfaces exist; external authority is still required | Connect authority without expanding M6 schema or making M6 own Identity Lock |
| M7–M15 | No accepted end-to-end implementation exists | Implement only the K2 single-episode slice gate by gate |
| V4/V3 | Text dispatch exists; media worker/render closure does not | Add one bounded execution path with explicit ownership |
| Local media tool | FFmpeg/ffprobe are available in the execution environment | A deterministic, real playable evidence path can be verified locally |
| Production readiness | `NO` | K2 technical closure is evidence, not a production-readiness claim |

## 4. Gate contract

### G0 — facts and contracts

Input: accepted repository baselines and authoritative plans.

Output: this package, ADR-0008, the K2 production contract, current milestone update
and risk entries.

Pass: documents are internally consistent, links resolve, diff checks pass, the
checkpoint is committed, published without force and remote-verified.

### G1 — K2 Golden Episode roots

Input: accepted M1–M6 public/application surfaces.

Output: one reproducible episode manifest and an authoritative production-run root
whose upstream refs are resolved through public/application boundaries.

Pass: rerun is idempotent, missing/foreign/stale refs fail closed, counts are frozen,
tests pass and evidence is remote-verified.

### G2 — M6 authority plus Identity Lock

Input: G1 run and accepted M6 baseline.

Output: an explicit M6 authority decision plus a separate V5-owned identity lock for
the required characters and approved references.

Pass: authority and identity cannot be conflated, a lock is versioned and immutable,
foreign/stale/ambiguous references fail, and no M6 schema expansion occurs.

### G3 — script to executable Shot Graph

Input: confirmed script, M6 authority decision and identity lock.

Output: versioned scenes, creative shots and an executable Shot Graph with camera,
duration, character, asset and continuity requirements.

Pass: stable IDs, deterministic ordering, total duration/accounting, validation,
staleness and lineage tests all pass.

### G4 — asset resolution and media generation

Input: executable Shot Graph.

Output: resolved asset requirements, generation requests, immutable results and
registered asset versions for K2.

Pass: every requirement is either resolved or explicitly blocked; provenance,
rights-state, provider/adapter identity, parameters, digests and lineage are present;
no fabricated remote success is allowed.

### G5 — V4 dispatch and worker

Input: valid generation requests.

Output: a single-episode V4 queue/lease/retry/cancel worker lifecycle with artifact
handoff to V5-owned records.

Pass: leases, retries, idempotency, cancellation, crash recovery, path isolation and
orphan-artifact handling are covered. This gate does not open M16 batch production.

### G6 — composition, QC, approval and master

Input: immutable media results and the executable Shot Graph.

Output: deterministic timeline, playable preview, machine QC report, explicit
approval decisions and immutable episode master/export.

Pass: FFmpeg composition and ffprobe verification succeed, approvals remain separate
from candidates, rejected/stale inputs cannot finalize, and the master retains full
lineage.

### G7 — frontend production workspace

Input: authenticated public K2 endpoints from G1–G6.

Output: connected Story/Shot, Assets/Jobs, Preview/QC/Approval and Delivery surfaces
inside the existing Creator UI.

Pass: a non-architect user can follow one clear next action from episode selection to
playable export; all writes go through the Frontend Experience Adapter and public
API; connected/disconnected/blocked/local-evidence states are explicit; all Core and
Frontend suites and builds pass.

## 5. Dependency-unavailable policy

If a live model provider, GPU runtime, external authority, rights decision or budget
credential is unavailable, the wave must not fabricate it. Work may continue only
through a deterministic adapter marked `LOCAL_EVIDENCE` when all of the following are
true:

1. the adapter uses the same V4 job and artifact contract as a future live provider;
2. outputs are real, inspectable and playable rather than mocked success envelopes;
3. every result records the adapter, parameters, digest and local-evidence status;
4. UI and API never call it provider/GPU/production output;
5. publication and commercial-release actions remain disabled;
6. the missing live dependency stays recorded as an open production gate.

## 6. Safety and persistence rules

- V5 owns authoritative domain facts and stable refs.
- V4 owns scheduling, execution state and provider/worker adapters.
- V3 owns deterministic composition/render behavior.
- Frontend owns presentation and user interaction only.
- M6 owns series intelligence/authority inputs, not Identity Lock or GPU execution.
- AI/model/adapter output is a candidate until a separate decision accepts it.
- Public inputs never choose workspace scope; the authenticated principal does.
- Persistence changes must be additive and migration-safe; production data may not be
  destructively rewritten for this wave.
- Artifact paths must be workspace/run scoped and traversal-safe.
- Every gate is restartable; no partial failure may be presented as a completed gate.

## 7. Automatic stop conditions

The wave stops immediately on any of the following:

- conflict with an accepted architecture/source-of-truth document;
- a required rights/license or external-authority decision that cannot be represented
  as blocked or local evidence;
- a destructive migration or irreversible production-data operation;
- a missing mandatory credential for the exact gate being claimed;
- a security/workspace-isolation regression;
- a failing required test, unresolved lineage ambiguity or unreproducible evidence;
- inability to publish without force and verify local/remote integrity.

Routine implementation choices inside the accepted K2 contracts are not review
stops.

## 8. Final evidence package

The closeout must include gate-by-gate commits and remote SHAs, exact test/build
commands, artifact manifests and digests, ffprobe facts for the exported MP4, security
and workspace-isolation evidence, failure-injection results, lineage from master back
to accepted M1–M6 roots, and a truthful list of remaining live provider/GPU/rights/
publication gaps.

The allowed closeout label is `K2 TECHNICAL CHECKPOINT CANDIDATE`. This package does
not authorize the labels `FEATURE ACCEPTED` or `PRODUCTION READY`.
