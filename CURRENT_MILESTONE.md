# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: `AUTO-SEQUENTIAL / CONTRACT-FIRST / FAIL-CLOSED`
>
> Project Lead Authorization: `FRONTEND ↔ CORE ACCURATE MAPPING AUTHORIZED ON 2026-08-17`
>
> Authorized Wave: `ACS-XR1-G0 → G1 → G2 → G3 → REMOTE VERIFY`
>
> Current Task: `ACS-XR1-GATE-C-CLOSEOUT`
>
> Current Work Package: `LOCAL COMPLETE / REMOTE BRANCH VERIFY PENDING`
>
> M6 Authorization: `ACCEPTED P0-P3 G1-R1 SURFACES ONLY / LATER M6 NOT AUTHORIZED`
>
> M7–M19 Authorization: `STATUS MAPPING ONLY / IMPLEMENTATION NOT AUTHORIZED`
>
> Integration Gate: `LOCAL PASS — CORE 471 / FRONTEND 108 / BUILD / TWO-PROCESS SMOKE`
>
> Production Ready: `NO — M6 EXTERNAL AUTHORITIES AND M7–M19 REMAIN OUTSIDE THIS WAVE`

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
- `CREATOR_WORKSPACE_REF` and `CREATOR_CONTENT_PROFILE_REF` are server-owned scope
  configuration;
- browser code calls only `/api/creator/*` on the Frontend origin;
- the adapter uses bounded timeouts and returns stable disconnected/error states;
- incoming mutation bodies are size-limited and JSON-validated;
- Core response status and stable product errors are preserved;
- redirect targets are created only from references returned by successful Core
  commands;
- no `NEXT_PUBLIC_*` variable may expose the Core origin or server scope.

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
