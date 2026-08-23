# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: `AUTO-SEQUENTIAL / CONTRACT-FIRST / FAIL-CLOSED`
>
> Project Lead Authorization: `K2 INTERNAL P1 HOST-PASSED / IMAGE-FIRST M10→M11 REVISION AUTHORIZED FOR SAFE AUTOMATIC IMPLEMENTATION / COMMERCIAL PUBLICATION REMAINS CLOSED`
>
> Authorized Wave: `P1 CLOSEOUT → M10 IMAGE PLAN → LIVE MULTI-REFERENCE CAPABILITY GATE → IMAGE CANDIDATES → EXACT SELECTION → M11 VIDEO`
>
> Current Task: `ACS-K2-INTERNAL-IMAGE-FIRST-REAL-MEDIA-REVISION`
>
> Current Work Package: `G2→G6 COMPLETE / P1 HOST-PASSED / M10 PLAN + FOUR LIVE CANDIDATES COMPLETE / EXACT SELECTION + ADMISSION HOST-IMPLEMENTED AND 638-PASS / RUNTIME ADMISSION NEXT`
>
> M6 Authorization: `ACCEPTED SURFACES + K2 EXTERNAL AUTHORITY CONNECTION / NO M6 SCHEMA EXPANSION`
>
> M7–M15 Authorization: `K2 PUBLISHABLE SINGLE-EPISODE SLICE ONLY / GATE-BY-GATE`
>
> M16 Authorization: `BOUNDED 1 → 3 → 10 → 30 ONLY AFTER P9 + GATE A/B/C`
>
> M17–M19 Authorization: `NOT AUTHORIZED`
>
> Integration Baseline: `K2 G0→G7 PRESERVED — CORE 518 / FRONTEND 118 / LOCAL PLAYABLE EVIDENCE`
>
> Production Ready: `NO — FOUR REAL SHOT-IMAGE CANDIDATES EXIST; EXACT IMAGE ADMISSION, REAL SHOT VIDEOS, MASTER/EXPORT/PUBLICATION ABSENT`

---

## 0. Accepted baselines

Core accepted baseline:

- branch source: `origin/main`
- commit: `9c13e8f8d7ccef079dd382fe11b1d173fdef13d7`
- accepted backend suite: `464 / 464`

Frontend accepted integration baseline:

- repository: `lpjiayou/AI-Cinematic-Studio-Frontend`
- branch: `feat/fe-g5-production-workspace-v2`
- commit: `efaaa2546c37ed7c514f10b3bec2fb9893009260`

Accepted capability state:

- M1 AI Director: accepted and verified;
- M2 Series + Episode Foundation: accepted and verified;
- M3 Script Studio: accepted and verified;
- M4 Project Context: accepted and verified;
- M5 Series Planning + Series Director: accepted and verified;
- M6 Series Intelligence: accepted only through the owner-accepted P0–P3 G1-R1
  surfaces already present on the Core baseline;
- M7–M19: not started or not authorized as production capability.

Historical CCV evidence branches remain preserved. XR1 does not rewrite their evidence,
generated artifacts, validators or conclusions.

---

## 1. Purpose

XR1 connects the closed Frontend page baseline to the accepted Core capability baseline
without inventing a second domain model or presenting unavailable capability as real.

The only accepted runtime chain is:

```text
Commercial Frontend
→ Frontend Experience Adapter
→ Creator Public HTTP/API
→ Creator Application
→ V5 Core OS
→ V4 Platform
→ V3 Render Core
→ Compute/Foundation
```

The Frontend must not import Core source, call Application/Domain objects, access SQL,
or contact model providers, workers, GPU services or private/internal HTTP routes.

---

## 2. Authorized scope

### G0 — governance and contract freeze

- publish the M1–M19 capability mapping matrix;
- freeze Creator Public HTTP/API v1 resource names, envelopes and error semantics;
- preserve existing `/creator/internal/*` routes as compatibility-only surfaces;
- define the Frontend Experience Adapter boundary and runtime configuration;
- define connected, disconnected, unavailable and local-demo states.

### G1 — Creator Public HTTP/API

- add versioned `/creator/api/v1/*` routes over accepted Creator Application/V5 public
  boundaries only;
- expose M1–M5 commands and queries already supported by the accepted Core;
- expose only the accepted M6 workspace/command surfaces and preserve external
  authority fail-closed behavior;
- expose a truthful capability projection for M1–M19;
- retain stable JSON envelopes, request-size limits, no-store responses and sanitized
  errors;
- add public HTTP contract and integration tests.

### G2 — Frontend Experience Adapter

- add a server-only adapter using `CREATOR_CORE_BASE_URL`;
- proxy browser mutations through same-origin Next Route Handlers;
- inject the configured workspace scope server-side;
- validate and normalize Core envelopes before they enter presentation state;
- connect the existing Project, AI Director, Series Planning, Script Studio and accepted
  M6 entry surfaces to public v1 routes;
- keep `LOCAL_FIXTURE` only as an explicit, visibly labelled local-demo mode;
- render missing authority, disconnected Core and not-open capability as product states,
  never as fabricated records.

### G3 — Gate C and closeout

- run Core unit/contract/integration tests;
- run Frontend lint, typecheck, unit tests and production build;
- run a real two-process smoke flow through
  `Browser/HTTP → Experience Adapter → Creator Public API → Core`;
- verify error, timeout, scope, version-conflict and unavailable-authority behavior;
- verify local and remote commit equality and clean worktrees.

---

## 3. Historical XR1 explicit non-scope

This section records the completed XR1 connection package and is superseded for the
new K2 publishable-production wave only by section 16. It remains binding for any
work outside that exact K2 wave.

XR1 did not authorize:

- M7–M15 implementation outside the subsequently authorized K2 single-episode slice;
- M16 outside the subsequently authorized bounded `1 → 3 → 10 → 30` sequence;
- M17–M19 implementation;
- new Core domain facts, schema migrations or event families;
- direct Frontend access to `/creator/internal/*`;
- fake `projectRef`, `seriesRef`, `episodeRef`, `scriptRef`, `scriptVersionRef`,
  `characterRef`, `versionRef` or provider/job identifiers;
- treating AI candidates as confirmed facts;
- production provider calls, production database writes, GPU execution or deployment;
- removal of historical evidence or accepted tests.

M7–M19 may appear only in the capability projection with an explicit `not_open` state,
accepted dependency explanation and no executable control.

---

## 4. Truth and data rules

1. Core owns authoritative references, versions, lifecycle and persistence.
2. Frontend owns client-only presentation keys and UI state.
3. A client key must never be upgraded to a Core reference by naming convention.
4. AI output remains a candidate until the corresponding Core confirmation command
   succeeds.
5. `LOCAL_FIXTURE` data is non-authoritative and must remain visibly identified.
6. When Core is unreachable, the Frontend reports `disconnected`; it does not silently
   substitute demo data.
7. When an accepted boundary lacks external authority, the result is `unavailable`, not
   an empty successful workspace.
8. Public responses must not leak provider credentials, internal diagnostics, SQL
   details or raw exceptions.

---

## 5. Public API acceptance rules

The v1 API is an adapter over accepted boundaries, not a new domain layer.

- prefix: `/creator/api/v1`;
- success envelope: `{ "ok": true, ... }`;
- error envelope: `{ "ok": false, "error": { "code": string, "message": string } }`;
- media type for commands: `application/json`;
- maximum body: `512000` bytes;
- cache policy: `no-store`;
- unknown route: HTTP `404 / not_found`;
- invalid JSON or shape: HTTP `400 / invalid_request`;
- unsupported media type: HTTP `415 / unsupported_media_type`;
- public DTOs may include accepted Core references required for subsequent commands,
  but may not expose adapters, repositories, provider transports or private diagnostics.

Existing internal endpoints remain covered by their historical contract tests and are
not the Frontend integration surface.

---

## 6. Frontend Experience Adapter acceptance rules

- `CREATOR_CORE_BASE_URL` is server-only and defaults to `http://127.0.0.1:8765` for
  local development;
- required `CREATOR_CORE_TOKEN` is server-only and maps to exactly one Core-owned
  workspace through the digest-only credential registry;
- `CREATOR_WORKSPACE_REF` is removed; the adapter must never forward a browser or
  Frontend-configured workspace claim;
- `CREATOR_CONTENT_PROFILE_REF` remains server-owned creation configuration only;
- browser code calls only `/api/creator/*` on the Frontend origin;
- the adapter uses bounded timeouts and returns stable disconnected/error states;
- incoming mutation bodies are size-limited and JSON-validated;
- Core response status and stable product errors are preserved;
- `401 / authentication_required` and `403 / authority_unavailable` remain distinct;
- redirect targets are created only from references returned by successful Core
  commands;
- no `NEXT_PUBLIC_*` variable may expose the Core origin, bearer credential or scope.

---

## 7. Stop conditions

XR1 must fail closed if any of the following occurs:

- a required UI action has no accepted Core public boundary;
- a command would require a guessed reference or version;
- a proposed route bypasses Creator Application/V5 public boundaries;
- M7–M19 implementation becomes necessary;
- a test requires a real provider secret, production database or GPU;
- scope isolation, lifecycle protection or confirmation semantics regress;
- the Frontend silently falls back to fixtures after a Core error;
- local and remote trees cannot be proven equal.

In a stop condition, preserve the truthful unavailable/not-open UI state and continue
with other independently authorized mappings.

---

## 8. Definition of done

XR1 is complete only when:

1. the M1–M19 mapping matrix is committed in both responsibility context and executable
   Frontend capability state;
2. public v1 routes are covered by Core contract/integration tests;
3. Frontend code contains a server-only Experience Adapter and no calls to internal
   Core routes;
4. accepted M1–M6 surfaces either execute against Core or expose an exact unavailable
   reason;
5. M7–M19 remain non-executable and truthfully labelled;
6. local-demo fixtures are opt-in and visibly non-authoritative;
7. all Core and Frontend checks pass;
8. Gate C proves at least one real Project-first vertical flow through both processes;
9. both repository branches are pushed without force, remote-verified and clean.

---

## 9. Local closeout evidence — 2026-08-17

Implementation commits:

- Core public contract and routes: `cc284d3`;
- Core public candidate lineage and final error-contract fix: `9199b4b`;
- Frontend Experience Adapter and connected Creator pages: `bb47914`.

Local validation:

- Core: `471 / 471` tests passed with the repository full-suite command;
- Frontend: `108 / 108` tests passed across `23` test files;
- Frontend: TypeScript, ESLint and Next.js production build passed;
- build contains the same-origin dynamic `/api/creator/[...path]` route and connected
  Project, Story World, Character and Script routes.

Gate C ran a real Core process on `127.0.0.1:8765` and a production Next.js process on
`127.0.0.1:3100`, then executed the project-first flow through the Frontend origin.
Observed results:

- capability projection: `19` items — `5 available`, `1 authority_required`,
  `13 not_open`;
- adapter response origin: `CORE`;
- browser-supplied workspace/profile claims were replaced by server configuration;
- Series and Project received Core-issued references and were returned by list/detail;
- direct read of the forged workspace returned zero projects;
- missing text provider failed closed as `provider_unavailable`;
- missing M6 external authority failed closed as `authority_unavailable`.

The local integration gate is closed. Force push remains forbidden. Remote SHA equality
and clean worktrees are the remaining publication checks; neither changes the accepted
capability scope.

---

## 10. AUTH-W1 accepted baseline and fact audit — 2026-08-17

AUTH-W1 branches from the remote-verified XR1 Core commit
`b7cfe40e3ff35514ef9a0b8bca8c91c2ff010d74` and the Frontend remote fluid-layout
commit `95dc3f6b20ed679db6bc3da55906be94f6963630`. Local Frontend commit
`0420b64caf7cab6e83b045cf8ea018e603609159` has the same tree and parent as the remote
commit; it is preserved as duplicate publication history and is not treated as a code
conflict.

Verified baseline evidence:

- Core full suite: `471 / 471` passed;
- Frontend unit/component suite: `109 / 109` passed across `23` files;
- Core public contract declares 27 endpoint constants under `/creator/api/v1`;
- Core has no bearer authentication and accepts request `workspaceRef` in query/body;
- server composition is hard-coded to `127.0.0.1:8765`;
- Frontend removes browser scope claims, but currently injects `workspaceRef` from
  server configuration and has no credential with which Core can identify it;
- Core has no CORS implementation, which is correct for the accepted same-origin
  Browser → Frontend Adapter → Core topology.

The fact audit rejects the submitted draft's claims that CORS, a browser token, full
M19 multi-tenancy or “the only remaining production blocker” are part of this wave.
AUTH-W1 is bounded public-boundary hardening only. Production Ready remains `NO`.

## 11. AUTH-W1 automatic execution contract

Project Lead instruction on `2026-08-17` authorizes the following contract-first,
fail-closed automatic sequence after the G0 checkpoint is committed, pushed and
remote-verified:

```text
G0  ADR-0007 + normative contract + API amendment + risk registration
 ↓
G1  Core bearer authentication + principal workspace injection
 ↓
G2  host/port/config composition + non-loopback public-only route exposure
 ↓
G3  Frontend server-only token + removal of Frontend workspace forwarding
 ↓
Gate C  full suites + production build + real two-process isolation/security smoke
 ↓
Remote Verify  no-force push + SHA equality + ahead/behind 0/0 + clean worktrees
```

The sequence stops only on a contract stop condition, failing test, credential leak,
required M6/M7–M19 expansion, persistent-schema requirement, or inability to prove
remote integrity. Routine transition between these listed gates requires no additional
interim review. This is execution authorization, not final feature acceptance.

## 12. AUTH-W1 definition of done

1. every `/creator/api/v1/*` route is authenticated and `/health` is liveness-only;
2. public clients cannot send `workspaceRef`; Core derives it from the credential;
3. `CREATOR_CORE_TOKEN` remains Frontend-server-only and is absent from browser assets;
4. non-loopback composition refuses invalid/missing auth configuration and exposes no
   internal compatibility routes;
5. Core remains no-CORS and browser code remains same-origin;
6. 401 authentication and existing 403 application-authority semantics stay distinct;
7. complete Core and Frontend suites, build, Gate C and secret scans pass;
8. both repositories are pushed without force and remotely verified.

AUTH-W1 does not change M6 authorization and does not open M7–M19.

## 13. Reference-video merged baseline disposition

The reviewed
[`REFERENCE_VIDEO_CAPABILITY_AND_WORKSPACE_MERGED_BASELINE.md`](docs/14-application-design/REFERENCE_VIDEO_CAPABILITY_AND_WORKSPACE_MERGED_BASELINE.md)
is part of the local cross-repository work and is now repository-resident. Its scope is
partitioned:

- implemented Frontend layout rules and stale documentation are current closeout work;
- reference-video and multi-character decomposition is a design/evidence baseline;
- M6 expansion is rejected;
- M7–M16 implementation and provider/GPU experiments remain outside AUTH-W1 and require
  separate rights, budget, ADR and milestone authorization.

The file must not be cited as evidence that reference-video generation is implemented.

## 14. AUTH-W1 local implementation and Gate C evidence — 2026-08-17

Implemented boundaries:

- Core protects all 27 declared public endpoint constants with a digest-backed bearer
  principal and exposes only unauthenticated liveness at `/health`;
- public query/body `workspaceRef` is rejected and the principal workspace is injected
  before existing Application/V5 dispatch;
- host, port and credential registry are validated before listening; non-loopback
  composition disables the complete internal route class;
- Frontend holds `CREATOR_CORE_TOKEN` only in the server adapter, sends no
  `workspaceRef`, and injects only the configured content profile for Series/Project
  creation;
- the canonical layout document now matches the fluid implementation tokens.

Local verification:

- Core full suite: `480 / 480` passed;
- Frontend suite: `112 / 112` passed across `23` files;
- Frontend TypeScript, ESLint and Next.js production build passed;
- built browser assets contain neither the runtime test token nor
  `CREATOR_CORE_TOKEN`;
- `git diff --check` passed in both repositories.

Gate C used a runtime-generated raw token, a digest-only Core registry, fresh migrated
SQLite lifecycle storage, one Core process and one production Next.js process. It
proved:

- exact capability state `5 available / 1 authority_required / 13 not_open`;
- browser claims cannot select a workspace and authoritative Series/Project references
  complete a create/list/detail round trip;
- an authenticated direct workspace claim fails `400 /
  client_workspace_scope_forbidden`;
- a missing credential fails `401 / authentication_required`;
- the authenticated M6 authority boundary remains distinct at `403 /
  authority_unavailable`;
- an absent text provider remains fail-closed as `provider_unavailable`.

The runtime token, registry, logs and temporary SQLite evidence database were deleted
after the gate. Initial implementation publication and verification evidence is:

- Core remote branch `feat/acs-auth-workspace-isolation`, implementation commit
  `a2297d952fa726e2d093f24869c9f0be0e417963`, tree
  `d52fe5b9b2f2abf577298687c97ec31537b37026`;
- Frontend remote branch `feat/fe-auth-workspace-isolation`, commit
  `05c3647b1f1fa76d6d67da90cab297ea029fd27d`, tree
  `27a82cc0bbc3c873435a52e3a6add888982f81dc`;
- both remote refs were fetched after no-force publication and their trees matched the
  corresponding local commits exactly.

This evidence closes AUTH-W1 G1–G3, Gate C and implementation publication. No M6
expansion, M7–M19 opening, provider/GPU readiness, production multi-tenancy or feature
acceptance is claimed. `R-CORE-SEC-003` moves to monitoring rather than closure because
credential rotation, user/RBAC policy and production operations remain future work.

## 15. K2 G0 → G7 automatic delivery wave — 2026-08-17

The Project Lead has explicitly authorized the following fail-closed sequence without
interim review requests:

```text
G0  Facts Baseline
→ G1  K2 Golden Episode
→ G2  M6 Authority + V5 Identity Lock
→ G3  Confirmed Script → Executable Shot Graph
→ G4  Asset Resolution + Media Generation
→ G5  V4 Dispatch + Single-Episode Worker
→ G6  Composition + QC + Explicit Approval + Episode Master
→ G7  Connected Frontend Production Workspace
→ Remote Verify
```

Normative documents:

- [`AI_CINEMATIC_STUDIO_DELIVERY_GOVERNANCE_PACKAGE_V1.md`](governance/AI_CINEMATIC_STUDIO_DELIVERY_GOVERNANCE_PACKAGE_V1.md)
- [`ADR-0008-k2-single-episode-production-closure.md`](governance/ADR-0008-k2-single-episode-production-closure.md)
- [`K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT.md`](architecture/K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT.md)

Wave facts and boundaries:

- Core starts from `79eda3c0bc3d20b97fdca3751a9c5e6247303962` with
  `480 / 480` tests passing;
- Frontend starts from `05c3647b1f1fa76d6d67da90cab297ea029fd27d` with
  `112 / 112` tests passing;
- AUTH-W1 authentication, principal-derived workspace isolation and public-only
  deployment topology remain mandatory;
- M6 may supply the K2 external-authority decision, but Identity Lock remains a
  separate V5 identity/asset fact and M6 schemas are not expanded;
- FFmpeg and ffprobe are available for real deterministic local composition evidence;
- when a live provider/GPU is unavailable, a real playable deterministic adapter may
  be used only when every result is visibly `LOCAL_EVIDENCE`, follows the same V4
  worker/artifact contract and leaves publication disabled;
- G5 is limited to one episode and does not open M16 batch production;
- creative, identity, QC and final-master approvals remain separate explicit records;
- K2 technical closure does not establish live model quality, GPU throughput, rights,
  publication, commercial release or production readiness.

G0 is documentation and contract freeze only. G1 begins only after the G0 checkpoint
is committed, published without force, fetched and remote-verified. Thereafter a gate
may advance automatically only when its required tests and evidence pass. Any contract
stop condition, security regression, unresolved lineage ambiguity, failing required
test or remote-integrity failure stops the wave.

### G0 remote verification

- branch: `feature/acs-k2-golden-episode`;
- remote commit: `fe56986eabccd30e79e749e38314633f20e03341`;
- remote tree: `2a15e59943ef1423ff53ce6e2abdf5fa3bd02900`;
- local and fetched remote trees matched, ahead/behind was `0 / 0`, and the worktree
  was clean before G1 implementation began.

### G1 implementation evidence

- V5 owns a new immutable `EpisodeProductionRun`; Creator Application and public HTTP
  use only its public boundary;
- creation resolves Project, Series, Episode, confirmed SeriesPlanVersion with its
  Core-only EpisodePlanItem binding, and confirmed ScriptVersion through existing
  accepted boundaries;
- the frozen manifest records exact scene/shot counts, output dimensions, frame rate,
  named characters and `LOCAL_EVIDENCE / publicationAllowed=false`;
- every run stores canonical upstream and payload SHA-256 digests and complete stable
  refs/version lineage;
- bearer authentication and principal-derived workspace scope apply to create, list
  and detail routes; body/query `workspaceRef` remains forbidden and foreign-workspace
  refs remain hidden;
- idempotent replay is stable while the same key with different content fails `409`;
- the durable local adapter uses a dedicated additive SQLite file and exact schema,
  survives restart and does not modify the accepted lifecycle/M6 database;
- no public binding command was added: EpisodePlanItem binding remains Core-only as
  required by the accepted M5/M6 contract;
- targeted contract/public integration gate: `20 / 20`;
- complete Core regression after the final G1 boundary hardening: `489 / 489`.

### G1 remote verification

- branch: `feature/acs-k2-golden-episode`;
- remote commit: `9aec2a478d3b13a5d3b55e6cd97527800f09ad2b`;
- remote tree: `828124f934af7a1ed17f1f1662691bff2d97e227`;
- fetched local and remote trees matched, ahead/behind was `0 / 0`, and the worktree
  was clean before G2 implementation began.

### G2 implementation evidence

- the accepted M6 read-only Episode baseline is resolved through the existing Script
  Studio boundary; missing scope/approval authority remains fail-closed;
- `M6AuthorityDecision` and `IdentityLock` are two separate immutable V5 facts with
  distinct refs, versions, canonical digests, creators and complete root/M5/M6/M3
  version lineage;
- Script character names are never converted into Core refs by convention: the G2
  command requires an explicit one-to-one mapping covering the frozen manifest;
- every identity reference carries an independently authorized ref/version, SHA-256,
  media type, rights state, provenance and approval ref; the default runtime authority
  rejects all references;
- current G1 roots and current M6 baseline are re-read before the append-only state
  transition, and changed inputs fail `409 / stale_input`;
- a dedicated additive evidence journal records exact gate facts and
  `ROOTS_READY → AUTHORITY_READY`; its InMemory and SQLite implementations preserve
  workspace isolation, idempotency and ordered transitions without changing accepted
  lifecycle or M6 schemas;
- authenticated public create/read routes derive workspace scope from the bearer
  principal and reject client-supplied workspace or run scope;
- targeted G1/G2 unit and HTTP integration gate: `17 / 17`;
- complete Core regression: `497 / 497`.

### G2 remote verification

- branch: `feature/acs-k2-golden-episode`;
- remote commit: `fcb604ec7a8706c6283c684bbe44db7575f87989`;
- remote tree: `bbe54ee113afc5296072f57fe6c0dcde1fc54db9`;
- fetched local and remote trees matched, ahead/behind was `0 / 0`, and the worktree
  was clean before G3 implementation began.

### G3 implementation evidence

- the compiler re-reads the confirmed ScriptVersion, frozen G1 root, current M6
  authority baseline and G2 Identity Lock before compiling; drift fails closed as
  `stale_input`;
- every Script scene requires an explicit binding to accepted M6 location and prop
  refs; missing, duplicate, invented or partial authority refs fail validation and
  no name-based Core ref inference is permitted;
- consistency validation uses exact integer-frame accounting at the frozen frame rate;
  the K2 30-second episode compiles to exactly `720` frames and four versioned shots;
- immutable StoryboardVersion, CreativeShotVersion and ExecutableShotGraph facts carry
  stable refs, canonical digests, source Script JSON pointers, camera/action/audio
  instructions, identity locks, asset requirement seeds and complete G1/G2 lineage;
- chronology is complete and contiguous, continuity edges are explicit, and the graph
  validator rejects duplicate refs/orders, non-positive durations, unresolved identity
  or asset requirements, inconsistent frame totals and cycles;
- append-only evidence records
  `AUTHORITY_READY → SCRIPT_VALIDATED → SHOTS_COMPILED`; reads remain workspace-isolated
  and SQLite restart-safe without adding or changing M3/M5/M6 schemas;
- authenticated public compile/read routes derive workspace scope from the bearer
  principal, reject client-supplied run/workspace scope and preserve replay semantics;
- targeted G1–G3 unit and HTTP integration gate: `22 / 22`;
- complete Core regression: `502 / 502`.

### G3 remote verification

- branch: `feature/acs-k2-golden-episode`;
- remote commit: `885245146cb497710fbaa616e0b16b1413f119dd`;
- remote tree: `0419b486a6f43de9ff70afb10616b158696ba766`;
- fetched local and remote trees matched, ahead/behind was `0 / 0`, and the worktree
  was clean before G4 implementation began.

### G4 implementation evidence

- G4 re-verifies current G1 roots, confirmed script, M6 authority, G2 Identity Lock
  and the complete validated G3 Shot Graph before resolving any requirement;
- five deduplicated semantic requirements bind immutable character/location/prop/style
  authority refs, versions and digests; conflicting reuse of a requirement key fails;
- every one of four K2 shots receives separate versioned video and audio requirements
  plus provider-neutral GenerationRequests, giving 13 requirements and 8 dispatchable
  requests with no blocked or silently omitted requirement;
- requests carry exact dimensions, frames, frame rate, codec/container or audio sample
  parameters, shot/version/digest lineage and deterministic adapter capability, while
  provider selection remains honestly `UNSELECTED` until V4 dispatch;
- all local-evidence requests retain `rightsState=LOCAL_EVIDENCE_ONLY` and
  `publicationAllowed=false`; G4 creates no path-only asset, fabricated provider result
  or GPU-success claim;
- append-only evidence records `SHOTS_COMPILED → ASSETS_READY`; authenticated public
  create/read routes remain principal-scoped, replay-safe and workspace-isolated;
- targeted G1–G4 unit and HTTP integration gate: `26 / 26`;
- complete Core regression: `506 / 506`.

G4 remains a local technical checkpoint until this exact tree is committed, published
without force, fetched and proven equal to the remote branch. Actual adapter execution
and immutable verified media registration occur only through the G5 V4 worker gate.

### G4 remote verification

- branch: `feature/acs-k2-golden-episode`;
- remote commit: `2841526a7d505b2fca7722a24392dc48d0558283`;
- remote tree: `3dbd58d685579353c26e2f9ed357ec01d9a33f11`;
- fetched local and remote trees matched, ahead/behind was `0 / 0`, and the worktree
  was clean before G5 implementation began.

### G5 implementation evidence

- V4 now owns a bounded single-episode job lifecycle with `QUEUED`, `LEASED`,
  `RUNNING`, `FAILED`, `RETRYING`, `SUCCEEDED` and `CANCELLED` states, optimistic
  revisions, scoped idempotency, expiring leases and crash recovery;
- InMemory and exact-schema SQLite adapters preserve jobs across restart without
  changing V5 or accepted lifecycle databases; retries create distinct attempts and
  do not duplicate the accepted artifact;
- all artifact directories are derived from workspace/run hashes beneath one configured
  root; traversal and adapter path escape fail, incomplete temporary artifacts are
  quarantined, and accepted paths are never exposed by the public API;
- the deterministic local FFmpeg adapter produces eight real K2 files—four exact-frame
  H.264 video segments and four 48 kHz stereo WAV tracks—and ffprobe validates duration,
  frame count, dimensions, channels and sample rate;
- V5 independently re-hashes, re-probes and checks every V4 handoff before recording
  immutable GenerationResult and AssetVersion facts with request/shot lineage,
  parameters, byte size, SHA-256, adapter identity, rights and provenance;
- all evidence remains explicitly `LOCAL_EVIDENCE`, `CPU_FFMPEG`, `gpuUsed=false`,
  `publicationAllowed=false`; no GPU, provider quality or production readiness is
  claimed, and an unconfigured worker fails `503 / worker_unavailable`;
- the append-only gate records `ASSETS_READY → MEDIA_READY`; the public media command
  is authenticated, workspace-derived, replay-safe, and changed replay keys do not
  trigger duplicate execution;
- targeted G1–G5/V4/public integration gate: `33 / 33`;
- complete Core regression: `513 / 513`.

G5 remains a local technical checkpoint until this exact tree is committed, published
without force, fetched and proven equal to the remote branch. Only verified immutable
media may enter G6 composition.

### G5 remote verification

- branch: `feature/acs-k2-golden-episode`;
- remote commit: `5af806bb909ac50fc770f2b696cce03635c12ae0`;
- remote tree: `f080936c7767719ff33afda56fac9e3d214750c0`;
- fetched local and remote trees matched, ahead/behind was `0 / 0`, and the worktree
  was clean before G6 implementation began.

### G6 implementation evidence

- V5 creates one immutable `TimelineVersion` mapping the exact four Creative Shot
  versions to four verified video and four verified audio AssetVersions; frame ranges
  are contiguous and total exactly `720` frames at the frozen `24 fps` output contract;
- V4 owns the composition execution boundary and delegates deterministic audiovisual
  composition to V3; V3 uses FFmpeg to produce a real H.264/AAC MP4 and ffprobe proves
  one video stream, one 48 kHz stereo audio stream, exact dimensions and exact frame
  count;
- V5 independently re-hashes and re-probes the composed artifact before appending a
  versioned `PreviewCandidate`; all storage remains run-scoped and path-escape checks
  remain active;
- the machine `QCReport` records six separate checks for artifact integrity, video,
  audio, timeline continuity, identity-lock lineage and the local-evidence publication
  lock; machine `PASS` does not create an approval;
- creative direction, identity continuity, technical QC and final master remain four
  separate append-only `ApprovalDecision` facts tied to the exact preview, timeline and
  QC digests; the default authority rejects, a rejected decision blocks finalization,
  and only an explicitly injected authority can validate external approval refs;
- finalization copies the exact accepted preview into one immutable `EpisodeMaster`
  and versioned `ExportArtifact`; the authenticated download route re-verifies digest,
  probe and complete decision lineage before serving the playable MP4;
- all output remains `LOCAL_EVIDENCE / LOCAL_EVIDENCE_ONLY`, `gpuUsed=false` and
  `publicationAllowed=false`; no human, live-provider, GPU, rights or publication
  readiness is inferred from automatic gate progression;
- InMemory and additive SQLite evidence survive restart; replay preserves refs and
  creates no duplicate master, while preview tampering fails
  `422 / artifact_verification_failed`;
- targeted K2/V4/public integration gate: `38 / 38`;
- complete Core regression: `518 / 518`.

G6 remains a local technical checkpoint until this exact tree is committed, published
without force, fetched and proven equal to the remote branch. G7 may consume only the
authenticated public preview, delivery and export contracts from that verified tree.

### G6 remote verification

- branch: `feature/acs-k2-golden-episode`;
- remote commit: `ace668f13a30d964a4b4978a04d4fe1e2795ade2`;
- remote tree: `0ab80e38d593bbe580817fdaf1f25a0d3b31ac87`;
- fetched local and remote trees matched, ahead/behind was `0 / 0`, and the worktree
  was clean before G7 implementation began.

### G7 local implementation evidence

- Core exposes an authenticated, principal-scoped preview-content route in addition
  to the existing delivery/export route; it re-verifies the preview digest and media
  probe before serving `video/mp4` inline and never returns an internal path;
- the Frontend Experience Adapter allowlists only the bounded K2 collection, run,
  stage, delivery, preview-content and export-content routes, strips browser run/scope
  claims, retains server-only bearer authentication, and streams only verified video
  response types with safe headers;
- project-level `制作 / 后期 / 交付` routes now form one state-driven workspace with
  a left run/gate navigator, central shot/asset/review/delivery canvas and right
  current-state/next-action inspector; the page root remains viewport-fluid rather
  than introducing a narrow centered shell;
- the UI maps exact Core `projectRef`, immutable refs, versions, digests and state;
  local fixtures cannot become production runs, unknown routes fail before Core and
  browser input cannot create workspace or run authority;
- preview playback is available before approval; six machine QC checks remain
  evidence only; four approval kinds require separate external approval and actor
  refs plus an explicit acknowledgement, and no field or decision is automatically
  supplied by the UI;
- the master/export view retains `LOCAL_EVIDENCE`, `gpuUsed=false` and
  `publicationAllowed=false`, provides authenticated playback/download, and exposes
  no publication control;
- Core full regression: `518 / 518`;
- Frontend: TypeScript and ESLint passed, `118 / 118` tests passed across `24` files,
  and the Next.js `16.3.0` production build passed with all three dynamic project
  workspace routes and the same-origin adapter route;
- a real two-process HTTP gate exercised
  `Node HTTP → Next Experience Adapter → authenticated Creator Public API →
  Application → V5 → V4 → V3`: four shots, eight media jobs, six QC checks and four
  externally verified `HUMAN` decisions advanced one run from `MEDIA_READY` to
  `MASTER_READY`; the inline preview and attachment export were both real
  `526636`-byte MP4 files with SHA-256
  `5377f6147a7f02c3c1d181372e85d3fe8f7a3dec5274773bc30e5786853f881a`;
- publication remained disabled and GPU usage remained false throughout the gate.

The real-browser portion of Gate C is `ENVIRONMENT HOLD`, not passed: this execution
environment contains the Playwright API but no local Chromium executable, while the
approved Cloud Browser security policy blocks localhost/private-network URLs and
explicitly forbids CDP or alternate-surface circumvention. No jsdom, static parsing or
HTTP-only result is being represented as browser evidence. G7 is therefore an
`IMPLEMENTED TECHNICAL CANDIDATE / BROWSER GATE HOLD`; final browser console, page
error, horizontal-overflow and visual checks remain required in an approved Chrome
environment that can reach the two local processes.

---

## 16. K2 publishable-production automatic wave — 2026-08-17

The Project Lead has authorized automatic execution of the next bounded wave. This
authorization extends ADR-0008; it does not convert local evidence into production
evidence and does not waive rights, credentials, budget, validation, selection or
human approval gates.

The one accepted chain remains:

```text
verified canonical K2 Project / Series / Episode / Script / M6 authority / Identity Lock
→ M7 narrative closure
→ M8 executable Shot Graph
→ M9 asset requirements
→ M10 live image candidates
→ M11 live video candidates
→ M12 live audio candidates
→ M13 deterministic composition
→ M14 machine QC + local regeneration + separate human decisions
→ M15 immutable master + publication eligibility
→ Gate A / Gate B / Gate C
→ M16 bounded 1 → 3 → 10 → 30 production evidence
```

No parallel project, character identity, shot model, asset registry, queue, timeline,
approval model, publication flag or frontend data source may be introduced. All work
must extend the existing Creator Public API → Application → V5 → V4 → V3 → Compute
chain and preserve exact refs, versions, digests, workspace scope and upstream lineage.

The previous durable K2 instance was not found. On `2026-08-21`, the Project Lead and
Architecture Owner authorized ADR-0010: one replacement canonical lineage may be
created through a bounded Operator Application over existing V5 public boundaries.
This is not a second active project and not recovery. Until its receipt and read-only
verification exist, the chain above has no current durable root. The bootstrap stops
at `ROOTS_READY`; M6, Identity Lock and all P0→P1 external gates remain separate.

### Authorized checkpoints

| Checkpoint | Required outcome | Automatic progression rule |
| --- | --- | --- |
| P0 | freeze target, rights manifest, production policy and provider/GPU evidence contract | machine-verifiable contract and tests pass |
| P1 | execute rights-cleared provider experiments through V4 adapters | real provider facts, cost/latency/provenance and reproducible artifacts exist |
| P2 | production runtime, durable persistence, object storage, secret injection and recovery | restart, retry, isolation and failure-injection gates pass |
| P3 | close K2 M7–M9 facts on the existing lineage | narrative, shot and requirement gates pass without stale or unresolved refs |
| P4 | generate and select M10 image assets | candidates are validated and explicitly selected before V5 admission |
| P5 | generate and select M11 video shots | identity, motion, duration and continuity evidence pass |
| P6 | generate and select M12 dialogue, ambience, effects and music | rights, loudness, sync and stem lineage pass |
| P7 | compose M13 timeline and preview through V3 | deterministic A/V render and exact timeline evidence pass |
| P8 | perform M14 QC, local regeneration and separate approvals | machine QC and human decisions remain distinct and exact-version scoped |
| P9 | create M15 immutable master and publication-eligibility decision | publication remains blocked until every required fact is true |
| Gate A/B/C | contract, integration, browser and evidence validation | all gates pass against the same committed tree |
| P10 | run M16 at 1, then 3, then 10, then 30 | each size must pass before the next; no jump and no 100-run authorization |

### Non-waivable stop conditions

Automatic progression stops truthfully when any of the following is absent or
ambiguous:

- rights-cleared source/reference material or a versioned rights decision;
- approved provider/GPU credentials, endpoint, budget or usage terms;
- required human creative, identity, technical or final-master decision;
- publication rights, release destination or publication authority;
- safe migration, recovery or object-retention evidence;
- exact upstream lineage, digest, workspace isolation or provider provenance;
- a non-destructive resolution to a remote-history or architecture conflict.

Missing external authority is a blocked production gate, not permission to fabricate
a provider result, approval, rights state, GPU execution or publishable master.

The normative package for this wave is:

- `governance/ADR-0009-k2-publishable-media-production.md`;
- `architecture/K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md`;
- `governance/K2_PUBLISHABLE_PRODUCTION_EXECUTION_PACKAGE.md`;
- `governance/RISK_REGISTER.md` entries `R-K2-LIVE-006` through `R-K2-PUB-010`.

### P0 implementation and external hold

The same existing K2 `EpisodeProductionRun` now exposes an immutable, additive
`ProductionPolicyVersion + RightsManifestVersion + ProviderExecutionPolicyVersion`
bundle and a read-only production-readiness projection through the authenticated
Creator Public API. The Frontend reads that projection through the same Experience
Adapter and displays exact blockers alongside the existing production workspace.

P0 does not trust request-body declarations as authority. Exact rights grants must be
resolved through an injected rights-evidence authority; provider/model/region
selections must be resolved through an injected provider-policy authority that returns
safe refs for the capability, credential source, usage terms and budget authority.
The default runtime rejects both. The Frontend projection is read-only, and any
server-side policy write derives its actor from the authenticated credential rather
than accepting a caller-supplied `actorRef`. Reference video, identity, voice, music or other
inputs can enter only as exact digest-bound rights entries, so the reviewed reference
video baseline cannot become an implicit provider input.

The current local K2 facts remain blocked because its identity references are
`LOCAL_EVIDENCE`, no rights-evidence/provider-policy authorities are configured, no
rights-cleared live image/video/audio provider execution exists, and no
authority-approved GPU/runtime attestation or publication authority is present.
Governed P1 execution has therefore not started and no downstream publishable claim
is made. See
`governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md` for the exact evidence and required
external inputs.

Same-tree verification before publication of this checkpoint:

- Core complete regression: `528 / 528`;
- Frontend complete suite: `119 / 119` across `24` files;
- Frontend TypeScript, ESLint and Next.js `16.3.0` production build: passed;
- Python compile, targeted public HTTP/integration tests and `git diff --check`: passed;
- committed Core `eba265322f66ff5e3e7aabb215e57e7f4d54d278` plus Frontend
  `ca3af84b406815df73989498d7f2963e261f354d` passed the two-process P0 HTTP Gate C;
- real-browser visual Gate C remains an explicit environment hold because this
  checkout lacks both the Playwright package and a usable browser binary; HTTP
  evidence is not being substituted for browser evidence.

### P1 bounded video safe prerequisite — 2026-08-18

Independent safe implementation has now closed the video-only P1 dispatch prerequisite
without advancing the blocked gate:

- V4 has a fail-closed `ComfyUIWan22VideoAdapter` behind the existing media-job
  contract; it probes exact native nodes, model names, one CUDA device and the approved
  endpoint class before dispatch;
- the approved Provider Policy, V5 request, V4 worker configuration and returned
  runtime facts must carry one identical external-authority runtime-attestation ref and
  digest; mismatch, unsafe redirects, wrong output identity, path escape, cost overflow,
  timeout or media-probe failure is rejected;
- V5 derives one fixed 49-frame experiment from an existing current M9 video
  `GenerationRequest` and verifies the current K2 root, M6 authority/Identity Lock,
  M9 plan, Rights Manifest and Provider Policy before calling V4;
- a successful result remains `UNTRUSTED_PROVIDER_CANDIDATE / UNSELECTED /
  NOT_ADMITTED`, is stored separately from AssetVersions and cannot advance G5, satisfy
  an approval or set publication eligibility;
- the authenticated Public API exposes only the bounded POST/GET
  `provider-experiments` subresource and strips credential-source refs, internal paths
  and storage keys;
- the operator attestation utility hashes the three files actually present on the
  compute host, probes ComfyUI and emits a secret-free technical record for external
  authority review.

A separate operator-controlled A100/ComfyUI smoke produced a real 49-frame MP4. Its
independent probe and digest are recorded in
`governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md`. It is deliberately classified as
`OUT_OF_LINEAGE_OPERATOR_SMOKE / TECHNICAL_EVIDENCE_ONLY`, not as a governed provider
attempt or production asset.

Same-tree verification for this prerequisite:

- bounded P0/P1 policy, V4, V5 and HTTP regression: `34 / 34`;
- complete Core regression: `541 / 541`;
- Python compile and `git diff --check`: passed;
- sample MP4 SHA-256 and full ffprobe facts: independently reproduced;
- repository secret/endpoint scan: passed; no credential, SSH destination or private
  endpoint was added.

P1 is still `NOT PASSED`. The default Rights and Provider authorities remain rejecting,
no governed same-lineage live call has run, image/audio experiments and explicit
candidate selection are absent, and P2 production persistence/object storage/secret
injection/recovery has not started. Automatic gate progression therefore remains
stopped at P0→P1 while independent safe prerequisites may continue.

### P1-A external-authority activation prerequisite — 2026-08-18

The Creator server can now connect the existing Rights Evidence and Provider Policy
ports to operator-managed authority bundles without accepting request-body or plain
environment declarations as authority:

- both external JSON files require absolute paths plus independently injected exact
  SHA-256 digests, and activation is all-or-nothing;
- duplicate JSON keys, partial configuration, digest mismatch, unknown fields and
  secret-shaped provider fields fail startup closed;
- V5 receives only canonical rights facts and opaque provider refs, including a
  `credentialSourceRef`; actual credentials remain in the worker secret environment;
- no configuration preserves the existing rejecting authorities;
- the Creator environment factory injects both validated authorities into the
  existing K2 production boundary, while the existing V4 ComfyUI adapter remains the
  only live video execution path;
- `scripts/k2_external_authority_activate.py` validates operator-supplied bundles and
  prints four secret-free, digest-pinned environment assignments; it never authors or
  approves the underlying facts.

Verification on the implementation tree:

- P1-A focused authority tests: `5 / 5`;
- operator script import/bootstrap tests: `2 / 2`;
- bounded P0/P1/V4/Public HTTP regression: `34 / 34`;
- complete Core regression: `548 / 548`;
- Python compile, whitespace validation and repository diff secret scan: passed.

This is an independent safe prerequisite, not a P1 pass. No real authority bundle was
created, no credential was injected, no governed same-lineage provider call ran, and
no candidate or AssetVersion was admitted. P0→P1 remains blocked on the external
facts listed in `governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md`.

### P1-B runtime technical-evidence closeout — 2026-08-20

The operator started the current ComfyUI runtime on one A100 40GB device, verified
the exact three Wan2.2 model files against the previously recorded SHA-256 values,
and successfully generated a schema `v4.comfyui-runtime-attestation.v1` record. The
record carries all ten required native nodes, PyTorch `2.11.0+cu126`, one CUDA device,
`LOCAL_FILE_SHA256_VERIFIED`, exact object-info/facts/payload digests,
`authorityState=TECHNICAL_EVIDENCE_ONLY` and `publicationAllowed=false`.

The operator then archived the attestation, model digest list, `system_stats` and
`object_info` before shutting down the GPU. The external archive
`k2-runtime-evidence-20260820T142014Z.tar.gz` has SHA-256
`c3701a1877cd9e715dcadbca93fc24eb38221f8e2c7a9f758cd978308c0b9f09`. Its exact
attestation and digest facts are recorded in
`governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md`. On `2026-08-21`, an
operator-downloaded copy plus sidecar was imported into a controlled audit workspace
outside Git. Its outer digest, safe member types and paths, original internal manifest
and all four evidence payloads were independently verified. The repository utility
then produced byte-identical normalized archives at SHA-256
`282bbd955022d47ece4f696704e97d4a12b04e2e140bea21e49390ca6b890022`, with local
model paths removed. Neither source nor normalized evidence is repository-resident.

The operator flow is hardened on the implementation tree without changing authority:

- runtime-attestation missing-value errors now name the actual CLI option instead of
  an environment-derived non-existent option;
- a portable evidence-archive utility verifies the attestation facts/payload digests,
  normalized model digests, runtime versions, exact CUDA device and full object-info
  digest before emitting a deterministic archive and SHA-256 sidecar;
- the archive utility rejects relative paths, cross-file tampering, unsafe authority
  state, publication claims and overwrite attempts, and removes model-local paths from
  its normalized archive payload;
- the runbook now requires one exact Python interpreter across dependency install,
  ComfyUI startup and evidence capture, and preserves an undisclosed provider region
  as a blocker rather than inferring geography.

Verification on the implementation tree:

- operator utility tests: `8 / 8`;
- complete Core regression: `554 / 554`;
- Python compile, `git diff --check`, Markdown validation, local documentation-link
  validation and repository-diff secret scan: passed.

P1 remains `NOT PASSED`. The runtime records `region=provider-not-disclosed`, no
external Provider Authority has reviewed and accepted the exact attestation ref plus
payload digest, no Rights Authority bundle exists, and no governed same-lineage live
image/video/audio experiment has run. P2 remains out of sequence.

### P1-C offline preboot package — 2026-08-21

While the GPU instance remains shut down, an independent safe prerequisite now turns
the existing K2 local-evidence target into a fail-closed offline creative and operator
candidate package:

- the Project Lead's current K2 single-episode hard ceiling is recorded as
  `currency=CNY / maxTotalCostMinor=100000`, with zero committed spend, no provider
  sub-allocation and no implied `budgetAuthorityRef` or paid-call authorization;
- K2-001 《记忆回声》 remains the current 30-second, 24-fps, two-scene, four-shot
  local-evidence target, with the exact `168 + 168 + 192 + 192 = 720` frame sequence;
- script, storyboard, shot description, performance, continuity, image preflight,
  four Wan2.2 prompt pairs, audio cue sheet and two eight-view character-turnaround
  designs are documented as `DRAFT / CANDIDATE / NOT DOMAIN FACT`;
- audio is text-only neutral TTS planning with no real-person imitation, voice cloning,
  external audio or P1 music; no media was generated;
- a machine-readable manifest binds the candidate to the exact three reviewed model
  digests and the technical attestation ref/digest while preserving
  `TECHNICAL_EVIDENCE_ONLY / publicationAllowed=false`;
- video/audio experiment plans require runtime resolution from the existing current
  G4 `GenerationRequest` lineage; G4 has no image request, so image remains explicitly
  blocked pending an authorized same-lineage contract extension, and human-readable
  `K2-001-SH-*` design keys cannot be promoted to Core refs;
- the offline validator rejects budget expansion or spend claims, missing character
  angles, external audio, voice cloning, secret-shaped fields, model/attestation
  tampering, frame discontinuity, domain admission and publication claims;
- the operator runbook reconnects the package to the existing Creator Public API →
  Application → V5 → V4 → V3 → Compute chain and stops truthfully where image/audio
  adapters or external authority remain unavailable.

Focused preboot validation passes `12 / 12` and the complete Core regression passes
`566 / 566` without GPU, provider credentials or paid calls. This work does not create
a Rights or Provider bundle, credential, MediaJob, ProviderAttempt, AssetVersion,
Identity Lock, approval, master or export.
P1 remains `NOT PASSED`; P2/P3 remain out of sequence until the external facts and all
three governed same-lineage media experiments exist.

### P1-D current-boot technical-evidence refresh — 2026-08-21

The operator restarted the same bounded A100/ComfyUI technical runtime and completed
the Stage-1 gate again with the repository's exact interpreter, CUDA contract and
three reviewed Wan2.2 model digests. The current attestation is
`technical-k2-funhpc-a100-20260821T130634Z`, observed at
`2026-08-21T13:07:19.528120Z`, with payload digest
`be03a079d17cad524b5e2e061e0c651a8f41f6f5221dfe80a8244398817ded53`.

The uploaded deterministic archive
`k2-runtime-evidence-20260821T130634Z.tar.gz` was independently audited outside Git:

- its SHA-256 and sidecar both resolve to
  `77348f23aebcd2f4029c20f4d05cb910c726dbfbb7eaf9757ac44c4cf6a2e24a`;
- all five members are regular relative files with no traversal, links or device
  entries, and all four payloads match the internal manifest;
- the facts and payload digests, one exact CUDA device, Python/PyTorch versions,
  all ten required nodes, three model digests and canonical full-object-info digest
  cross-validate through the repository archive utility;
- an independent deterministic rebuild is byte-identical to the upload at the same
  archive SHA-256;
- 29,573 JSON string values contain no recognized credential, bearer/JWT, credentialized
  URL, sensitive query, host absolute path or non-empty sensitive scalar field.

A new operator utility now locates existing K2 SQLite lineage with
`mode=ro + query_only`, selects no payload, creative text, idempotency or credential
field, and returns `NOT_FOUND` without initializing a database. Its three focused
no-write/redaction/bounds tests pass, the combined evidence/preboot/operator focus is
`23 / 23`, and the complete Core regression is `569 / 569`.

The subsequent `2026-08-21` location audit covered `/data`, `/root`, `/home` and
`/tmp`, plus 15 archives. The only two SQLite candidates were ComfyUI databases;
neither contained known K2 Core tables, and no archive contained a database member.
The audit digest is
`7aaa36333f08be3bdfd09c6b4632804f3b7bf14a0bd1bc35f359df0391fa167b`.
The current durable K2 lineage status is therefore `NOT_FOUND`. Test fixture refs and
historical local evidence are not recoverable production lineage. Creator remains
stopped because its default environment path would initialize a new empty database.
The next transition requires either an exact external database/snapshot or an
explicit Project Lead decision to establish a new canonical lineage; the latter is a
new bootstrap, not restoration.

The current record remains `TECHNICAL_EVIDENCE_ONLY /
publicationAllowed=false / region=provider-not-disclosed`. The `2026-08-20` record is
preserved as historical evidence. No external Provider Authority has accepted the
current ref/digest, no Rights Authority bundle has been activated, and no current K2
same-lineage provider attempt or asset admission occurred. P1 therefore remains
`NOT PASSED`, and P2 remains out of sequence.

### Canonical lineage bootstrap authorization — 2026-08-21

The Project Lead explicitly authorized establishment of a new canonical K2 lineage
after the read-only location audit proved the previous durable instance unavailable.
ADR-0010 and `K2_CANONICAL_LINEAGE_BOOTSTRAP_CONTRACT.md` freeze the replacement path.

The authorized implementation may add one checked-in K2-001 bootstrap specification,
one validator/operator utility and focused tests. It must use existing V5 public
boundaries, may invoke the existing Core-only M5 EpisodePlanItemBinding operation,
must not add an HTTP route or import tests, and must publish a new canonical directory
only after staging, restart, receipt and read-only lineage verification pass.

The maximum checkpoint result is one `EpisodeProductionRun` at `ROOTS_READY` with
`publicationAllowed=false`. M6 Authority, Identity Lock, Rights/Provider/budget
authority, live provider execution, asset admission and publication remain absent.

The governance checkpoint is remote-verified at PR #9 head
`976416bdd1a5a93001e1f271d406ed41e1415208`, tree
`99fd75de064a6d93077667d7e427f440bfb90b19`; Repository Validation #43 completed
with all five jobs successful.

The G1 implementation now includes the exact
`k2.canonical-lineage-bootstrap.v1` specification, payload SHA-256
`0dfa64aa23e7120415a58b48eb00bb5d92274518d16051f2cb419525ea3b364c`,
the write-free/default plus explicitly acknowledged apply utility, an authenticated
GET-only Public API exact-match verifier, and eighteen focused tests. A local temporary
apply proved staging, V5-only root creation, restart,
idempotent replay, exact read-only scanner projection, private receipt/inventory,
no-replace atomic publish, failure cleanup and repeated-apply refusal.
The final local checkpoint regression passes `587 / 587`: Unit `356 / 356`,
Contract `91 / 91`, Integration `140 / 140`; the bootstrap/API-focused subset passes
`18 / 18`.

The implementation was remote-verified at commit
`57ce3d0bf3e5772f57cea7a8a79726237ef366ba`, tree
`a3eece796fafcaeead8b525cbe039a69782602c3`; Repository Validation #44 passed all
five jobs. The formal host then completed one write-free validation, one acknowledged
apply, inventory verification, SQLite quick checks and an independent read-only scan.
The scan found five databases, one production database and exactly one production run
at `ROOTS_READY`.

Authenticated loopback Creator Public API verification passed exact matching for all
seven required resources. The secret-free verification receipt SHA-256 is
`d4c2a52d1c141ed5f0b8b24a13a985e47e38b3b78eac27eb5d59b452c18ca8a6`; the
bootstrap receipt SHA-256 is
`94fad69a2fdffe50e599c08fdc0e7c94aa3a381a30d1515b126a1f8b88076234`.
Canonical G1 is therefore host-verified and no longer blocks on missing lineage.
M6 Authority and Identity Lock remain `NOT_CREATED`; P1 remains `NOT_PASSED` and
publication remains disabled. The next valid transition is same-lineage G2 preparation,
not provider dispatch. See
[`K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21.md`](governance/K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21.md).

### G2 external-authority preparation checkpoint — 2026-08-22

The repository now connects the existing accepted M6 and EpisodeProduction authority
ports to operator-managed, digest-pinned external facts without changing an M6 domain
schema, HTTP route or external Creator DTO:

- one closed-world `v5.external-m6-authority-bundle.v1` binds trusted
  business/tenant/workspace/project/series scope plus each exact M6 action and human
  approval; approval refs cannot be reused and AI/Provider actor kinds fail closed;
- one closed-world `v5.external-identity-reference-authority-bundle.v1` binds each
  immutable reference decision to one exact
  `workspaceRef + productionRunRef + characterRef`; cross-run, cross-workspace and
  cross-character lookup fails closed;
- both loaders require an absolute operator-managed file and an independently injected
  exact SHA-256 digest, reject partial configuration, duplicate JSON keys, unknown
  fields, invalid refs, oversized files and inconsistent identity rights/provenance,
  and preserve the existing rejecting authorities when absent;
- the Lifecycle environment composition injects only the validated M6 scope/approval
  authorities, while the EpisodeProduction environment composition injects only the
  validated identity-reference authority into the existing G2 boundary;
- `scripts/k2_g2_external_authority_activate.py` is validate-only and prints two M6
  assignments during scope-only draft preparation or four assignments once an
  Identity bundle is supplied; it cannot create M6 facts, select identity, approve
  decisions, call Creator writes or advance the production run;
- `K2-G2-AUTHORITY-PREPARATION-RUNBOOK.md` freezes the two external bundle shapes,
  non-inference rules, activation sequence and authenticated post-write verification
  boundary.

Verification on the implementation tree:

- combined G2/legacy external-authority/operator focus: `25 / 25`;
- complete repository regression: `599 / 599` — Unit `368 / 368`, Contract `91 / 91`,
  Integration `140 / 140`;
- Python compile, whitespace validation and Markdown structure validation: passed.

This checkpoint creates connection capability only. No production M6 bundle, identity
bundle, approval, SeriesBibleVersion, CharacterContinuityVersion, M6 baseline,
`M6AuthorityDecision` or `IdentityLock` was authored. The canonical K2 run therefore
remains `ROOTS_READY`; M6 and Identity Lock remain `NOT_CREATED`; G2 and P1 remain
`NOT_PASSED`; `publicationAllowed=false`. Full M6 confirmation/baseline activation and
the existing G2 authorize-and-lock command require the exact canonical refs, three
real human M6 approvals and one approved immutable identity-reference decision for
each required character.

### G2 scope-authority designation checkpoint — 2026-08-22

The Project Lead explicitly designated the first same-lineage trusted M6 draft scope:

- `businessDomain=series-production`;
- `tenantId=tenant-k2-001-canonical`;
- `workspaceRef=workspace-6c2c70926cf64cd68435537ffd4de92d`;
- `projectRef=project-00482509a3a14837be7f29f1467c0ced`;
- `seriesRef=series-c0a74d5580b44aeea75747ad1d33438a`;
- `authorityRef=m6-scope-authority-k2-001-v1`.

An operator-controlled scope-only bundle was prepared outside Git using
`v5.external-m6-authority-bundle.v1`. Its exact SHA-256 is
`d4f4fcb0a71cc734c06478e80ef8ce09c188d5be46a9e741472b7673959554e7`.
The independently re-extracted operator package SHA-256 is
`02fddbfa68ba16f8faccb054d7b61328053ef5738d199beaff0adc6b9d2e111b`.
The repository validator resolved the exact canonical scope and emitted the two
digest-pinned M6 environment assignments. Independent negative verification confirmed
that approval lookup still fails closed.

The bundle intentionally contains `approvals: []`. No Creator process on the
canonical host has inherited it yet, and no M6 write occurred. SeriesBibleVersion,
CharacterContinuityVersion, M6 baseline, M6AuthorityDecision and IdentityLock all
remain `NOT_CREATED`; the run remains `ROOTS_READY`; G2 and P1 remain `NOT_PASSED`;
`publicationAllowed=false`. The next host transition is limited to deploying this
exact digest-pinned scope bundle and authoring one Series Bible candidate for human
review. Confirmation and baseline activation remain prohibited until their exact
human approvals exist.

### G2 M6 staged-draft operator checkpoint — 2026-08-22

Contract review corrected the previously over-broad scope-only sequence. The existing
M6 service requires Character Continuity creation to reference a `CONFIRMED`
SeriesBibleVersion. An empty-approval scope bundle can therefore create only the
Series Bible candidate; it cannot create both M6 candidates in one stage.

The repository now contains one explicit K2-001 operator-input candidate and a narrow
authenticated loopback utility that:

- validates the exact designated authority ref, bundle SHA-256 and canonical
  business/tenant/workspace/project/series scope before any API request;
- defaults to read-only preflight and requires explicit `--apply` plus a new absolute
  receipt path for one candidate write;
- creates or exactly verifies a Bible candidate while the scope-only bundle remains
  approval-empty;
- refuses the Character phase until an immutable Bible version is independently
  `CONFIRMED` with a non-empty approval ref, then resolves the real M5
  `episodePlanItemRef` from authenticated bootstrap data rather than human-readable
  design keys;
- never calls confirmation, baseline activation, Identity, G2, Provider or publication
  endpoints, never accepts a command-line token and writes only a mode-`0600`
  secret-free receipt;
- keeps `identityBindings=[]`, `G2 NOT PASSED`, `P1 NOT PASSED` and
  `publicationAllowed=false`.

This is an offline repository checkpoint only. No Creator process on the canonical
host has used the tool and no Bible/Character version, baseline, authority decision or
Identity Lock was created. The next host action is bounded to scope-bundle deployment,
Bible-candidate preflight and one Bible-candidate apply. A real human Bible review and
a newly digest-pinned approval bundle are mandatory before the Character stage.

Focused operator verification passes `6 / 6`. The complete repository regression
passes `605 / 605` — Unit `374 / 374`, Contract `91 / 91`, Integration `140 / 140`.

### K2 G2–G6 host advancement and Internal P1 rebaseline — 2026-08-22

Subsequent host execution advanced the new canonical K2 lineage beyond the older
offline checkpoint recorded above. The operator-reported current facts are:

- G2 Authority/Identity completed on the canonical run;
- G3 compiled the four-shot graph;
- G4 resolved 18 AssetRequirements and emitted eight GenerationRequests — four video
  and four audio — with provider selection still unselected;
- G5 used CPU FFmpeg to create/register four MP4 and four WAV immutable
  `LOCAL_EVIDENCE` AssetVersions; receipt
  `k2-g5-local-media-20260822T121920Z.json`;
- G6 composed one preview, machine QC passed six checks, and the preview remains a
  human-unapproved candidate; receipt
  `k2-g6-local-preview-qc-20260822T123403Z.json`;
- the copied preview SHA-256 is
  `0a49b44121a02aec43836f3a3222a675c4d8b1d88e2fd4a2f1c88fafd0d33516`;
- Episode Master and export artifact remain absent;
- Provider Authority remains inactive, the legacy P1 gate remains not passed and
  publication remains disabled.

A read-only repository audit at Core head
`abbe6fdb8590274cf556488dbb1f16221928bc4f` selected 76 governing/implementation
files. All inner file digests and the outer archive digest
`97fa3fe2bae56cbf6465b3e093cd694503015f381b9695c4c3fc5ad92b3b80fb`
verified. The audit made zero canonical, runtime or repository mutations.

The Project Lead then rebaselined P1 for the Internal Content Lab:

- Rights Manifest, external Provider Policy/Authority and Budget Authority are not
  required for the exact K2 internal self-hosted P1 run;
- the legacy commercial/publication mode is preserved and remains fail-closed;
- the accepted path is the existing authenticated Public API → V5 current G4 lineage
  → V4 MediaJob/Attempt → self-hosted ComfyUI/Wan2.2 adapter;
- the internal grant is server-held and exact-scoped to one workspace/run; a browser
  cannot supply a provider capability or authority claim;
- runtime attestation, model digests, GPU facts, bounded execution, artifact digest,
  independent probe and current lineage remain mandatory;
- one verified same-lineage 49-frame video smoke passes the bounded internal P1;
- the candidate remains unselected/not admitted and publication remains false.

ADR-0011 and `K2_INTERNAL_SELF_HOSTED_P1_CONTRACT.md` govern the rebaseline. The
current repository package is an implementation candidate only: it has not yet been
applied to or tested on the canonical host, and no internal P1 dispatch has occurred.
The next valid action is repository patch validation and full Core regression. Only
after those pass may the exact host run execute one internal video smoke. Frontend/G7,
full four-shot P2 production, Master/export and publication are not part of this P1
checkpoint.

### P1 host closeout and image-first M10 rebaseline — 2026-08-23

Later host evidence supersedes the pre-execution statements in the preceding
historical subsection:

- Core implementation commit:
  `9fa17347b48e455db39fcabe6b545829738f0f0d` on
  `feature/k2-publishable-production`;
- P1 receipt:
  `k2-p1-internal-video-smoke-20260822T153945Z/receipt.json`;
- P1 state: `PASSED_INTERNAL_VIDEO_EXECUTION`;
- one self-hosted Wan2.2 candidate: 49 frames, 24 fps, 640×352;
- artifact SHA-256:
  `e2faf5b50527fd8dfcb3b7b63e00ac4d7b4e147fe3303fabc505d50e9c7dff43`;
- GPU execution verified; candidate remains `UNSELECTED`, `NOT_ADMITTED` and
  publication-disabled;
- Master and Export remain absent.

Repository review also confirmed that every current G3 shot binds both locked
characters. The earlier candidate proposal to use one character reference directly
as every Wan start image is therefore rejected. The correct connected flow is:

```text
G2 selected visual references
→ M10 four two-identity shot/keyframe image requests
→ exact image selection and immutable image AssetVersions
→ M11 four image-to-video requests
→ exact video selection and immutable video successors
→ real preview/QC
→ later explicit final decisions and Master
```

ADR-0012 and
`architecture/K2_INTERNAL_IMAGE_FIRST_REAL_MEDIA_REVISION_CONTRACT.md` govern this
revision. The current automatic CPU wave may implement and test state compatibility,
M10 request derivation, Public API plumbing, closed-world validation, audit and host
apply/preflight scripts. It must not start a paid GPU instance, fabricate a live
multi-reference capability PASS, select unseen media, create Master/Export, publish or
merge unverified code to `main`.

The next paid-server action is not video generation. It is a fresh read-only ComfyUI
`/object_info` and model/runtime inventory proving an accepted multi-reference image
workflow. If that capability is absent, execution stops at
`REAL_IMAGE_PLAN_READY`; text-only fallback is forbidden.

### M10 host candidate execution and exact-selection work package — 2026-08-23

Later host evidence supersedes the final pre-execution paragraph above:

- current Core base: `1650c3462b32899151cdba795ddc10e5171ff1da`;
- real-image plan ref:
  `real-image-plan-8d1405aa194747e0b40fc4892f81f382`;
- plan state: `REAL_IMAGE_PLAN_READY` with four 1280×720 requests, each bound to
  both exact G2 reference digests;
- multi-reference technical-smoke receipt:
  `k2-m10-dual-reference-technical-smoke-20260823T080545Z/receipt.json`;
- four-candidate receipt:
  `k2-m10-four-image-candidates-20260823T081016Z/receipt.json`;
- candidate receipt SHA-256:
  `2b4d0ad87e10542ec6bd7c74db0a0c2e84d4db0c6b5411de5122c240e8d1c192`;
- all four candidates remain publication-disabled until the exact selection gate is
  applied.

The Project Lead has now reviewed those four exact receipt-bound candidates and
explicitly chosen all four. The missing canonical `real-image-selection` Public API,
digest-pinned V4 evidence adapter and atomic V5 admission gate have passed 29 focused
tests and the complete 638-test Core suite on the canonical host. The next authorized
mutation is the one exact authenticated selection/admission command; M11 remains
blocked until that command independently verifies the pinned evidence and advances
the same run to `REAL_IMAGE_READY`.
