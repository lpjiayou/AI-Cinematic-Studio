# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: `AUTO-SEQUENTIAL / CONTRACT-FIRST / FAIL-CLOSED`
>
> Project Lead Authorization: `K2 SINGLE-EPISODE G0 → G7 AUTO-SEQUENTIAL WAVE AUTHORIZED ON 2026-08-17`
>
> Authorized Wave: `ACS-K2-G0 → G1 → G2 → G3 → G4 → G5 → G6 → G7 → REMOTE VERIFY`
>
> Current Task: `ACS-K2-G2-M6-AUTHORITY-V5-IDENTITY-LOCK`
>
> Current Work Package: `G2 EXPLICIT M6 AUTHORITY DECISION / SEPARATE V5 IDENTITY LOCK`
>
> M6 Authorization: `ACCEPTED SURFACES + K2 EXTERNAL AUTHORITY CONNECTION / NO M6 SCHEMA EXPANSION`
>
> M7–M15 Authorization: `K2 SINGLE-EPISODE CLOSURE ONLY / GATE-BY-GATE`
>
> M16–M19 Authorization: `NOT AUTHORIZED`
>
> Integration Baseline: `AUTH-W1 PRESERVED — CORE 480 / FRONTEND 112 / BUILD / SECURITY SMOKE`
>
> Production Ready: `NO — K2 CLOSURE DOES NOT PROVE LIVE MODEL, GPU, RIGHTS OR PUBLICATION READINESS`

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

## 3. Explicit non-scope

XR1 does not authorize:

- M7 Narrative Review implementation;
- M8 Storyboard or Shot Designer implementation;
- M9 Asset Requirement implementation;
- M10 Image Studio implementation;
- M11–M19 implementation;
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
