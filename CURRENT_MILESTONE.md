# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: MANUAL
>
> Current Task: `PRE-M6-RB1.3 — Core Full Audit`
>
> Current Work Package: `RB1.2 checkpoint authorized / RB1.3 authorized but not started`
>
> M6 Authorization: `NOT AUTHORIZED`
>
> M7 Authorization: `NOT AUTHORIZED`

---

# 0. Canonical Baseline

Canonical Workspace:

`D:\Codex使用\AI CINEMATIC STUDIO`

Pre-Rebaseline Accepted HEAD:

`602a78fe68fc5c69ecc31d9436ee166f5dff8a64`

Pre-Rebaseline Branch:

`codex/creator-ui-r2a-layout-freeze`

RB1.1 Accepted Checkpoint:

`00793953e71711ab95724353d97d3a913be2b853`

RB1.1 Local / Remote Verification:

`PASS`

Accepted milestones and integration checkpoints:

- M1 — AI Director Core — ACCEPTED
- M2 — Series + Episode Foundation — ACCEPTED
- M3 — Script Studio — ACCEPTED
- M3-H — Script Candidate Robustness — ACCEPTED
- Story Projection — ACCEPTED
- UI-R1 — Enterprise Cinematic UI — ACCEPTED HISTORY
- M4 — Project Context Foundation — ACCEPTED
- M5 — Series Planning + Series Director — ACCEPTED
- UI-R2 — Professional Workspace Layout Optimization — ACCEPTED HISTORY
- UI-R2A — Product acceptance status — NO SEPARATE ACCEPTANCE EVIDENCE / CANDIDATE
- UI-R2A — Remote verification status — PASS AT `602a78fe68fc5c69ecc31d9436ee166f5dff8a64`
- UI-R2A — Active architecture status — SUPERSEDED AS CURRENT TASK

UI-R2A remains historical implementation evidence after the legacy Core browser UI
decommission. It is no longer an active Core work package and does not authorize M6.

---

# 1. Current Control Stage

Current stage:

`PRE-M6-RB1.3`

Title:

Core Full Audit

Status:

`AUTHORIZED / NOT STARTED`

Purpose:

1. preserve `PRE-M6-RB1.1` as `CLOSED` at remote-verified checkpoint
   `00793953e71711ab95724353d97d3a913be2b853`;
2. record the independent RB1.2 review as `ACCEPTED` and its checkpoint as
   `AUTHORIZED`;
3. close RB1.2 when the authorized checkpoint commit becomes remote-verified;
4. authorize RB1.3 as the next task without beginning it in the RB1.2 checkpoint task;
5. require the RB1.3 code-first Core audit and Architecture Review before M6-P1;
6. keep M6 and M7 not started and not authorized.

---

# 2. Proposed Responsibility Contract

ONE CREATOR UI remains mandatory.

ADR-0001 is `Accepted`, and the RB1.1 governance baseline is remote-verified at
`00793953e71711ab95724353d97d3a913be2b853`. The current interpretation is:

ONE CREATOR UI
=
the customer-facing Commercial Frontend in the separate
`AI-Cinematic-Studio-Frontend` repository.

Core repository responsibility:

- Creator Server Runtime;
- Creator Public HTTP/API;
- Creator Application commands, queries, DTOs and services;
- authorization and tenant/workspace enforcement;
- Domain and V5 Core OS;
- V4 Platform;
- V3 Render Core;
- Compute/Foundation integration;
- persistence, migrations and infrastructure;
- backend/application/domain/contract/integration tests.

Frontend repository responsibility:

- customer-facing Commercial SaaS pages and routes;
- experience adapters;
- frontend state and presentation;
- responsive/accessibility/visual behavior;
- customer workflow browser validation.

Proposed cross-repository dependency chain:

```text
Commercial Frontend
↓
Frontend Experience Adapter
↓
Creator Public HTTP/API
↓
Creator Application
↓
V5
↓
V4
↓
V3
↓
Compute/Foundation
```

Canonical form:
`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

The Frontend Experience Adapter belongs to the Frontend repository and may consume
only Creator Public HTTP/API. The two repositories do not share customer UI source.

Forbidden:

- Frontend → Core source imports;
- Frontend → Creator Application direct calls;
- Frontend → Domain direct calls;
- Frontend → SQL, Persistence or persistence adapters;
- Frontend → Provider;
- Frontend → private V5 adapters;
- Frontend → GPU, Worker or ComfyUI;
- Core → second customer-facing Commercial SaaS UI.

---

# 3. Current Authorized RB1.2 Work Package

RB1.2 may remove only files and connections proven to be Legacy UI-only, update
invalidated UI-specific tests, add targeted no-UI Core contract tests, and minimally
update related architecture documentation and this execution record.

Public API contracts, Application use-case semantics, Domain rules, Persistence schema
and migrations, runtime/API responsibilities, and the separate Frontend repository are
outside scope. RB1.2 implementation results stop at `IMPLEMENTED / REVIEW PENDING` and
must not be staged, committed or pushed by this work package.

---

# 4. Legacy Core Creator UI Status

`apps/creator-workspace-mvp` is `DECOMMISSIONED / REVIEW PENDING`.

Repository dependency analysis classified all 98 tracked files under the hyphenated
`apps/creator-workspace-mvp` path as customer UI-only. They were removed without
removing the underscore package `apps/creator_workspace_mvp`, which continues to own
Creator Server public HTTP/API and Application runtime responsibilities.

Removed after UI-only classification:

- customer-facing pages and routes;
- dashboard/workspace presentation;
- page components and page-only CSS;
- page-only visual evidence/assets;
- UI-only browser tests;
- presentation-only client state.

Must be preserved:

- Creator Server Runtime;
- HTTP/API handlers;
- Application services;
- commands, queries and public DTO/contracts;
- auth and tenant/workspace enforcement;
- Domain, V5/V4/V3, ports and adapters;
- persistence and migrations;
- backend/application/domain tests.

Mixed UI/server files are `AMBIGUOUS_SHARED_FILE` until classified. Whole-directory
deletion is not authorized.

---

# 5. Replacement Gate Model

## Gate A — Frontend Experience Gate

Owner: separate Frontend repository.

Covers frontend tests, build, browser QA, responsive behavior, accessibility, visual
quality and customer workflows.

## Gate B — Core HTTP Runtime Gate

Owner: Core repository.

Covers Creator Server startup, public HTTP/API contracts, Application commands and
queries, authorization, tenant/workspace, persistence, idempotency, application
integration and error contracts.

## Gate C — Cross-Repo Integration Gate

Future gate validating:

```text
Commercial Frontend
↓
Frontend Experience Adapter
↓
Creator Public HTTP/API
↓
Creator Application
↓
V5
↓
V4
↓
V3
↓
Compute/Foundation
```

The Frontend Experience Adapter belongs to Frontend and may consume only Creator
Public HTTP/API. Gate C must validate public contracts rather than shared source
imports. Gate C is not implemented by this documentation work package.

---

# 6. PRE-M6 Route

Strict order:

`PRE-M6-RB1.1 Source-of-Truth Rebaseline`
→ `PRE-M6-RB1.2 Legacy UI Decommission`
→ `PRE-M6-RB1.3 Full Core Current-State Audit`
→ `Architecture Review`
→ `M6 Preconditions`
→ `M6-P1`

`PRE-M6-RB1.1` is `CLOSED`; its checkpoint and Local/Remote verification are `PASS` at
`00793953e71711ab95724353d97d3a913be2b853`. RB1.2 is independently accepted and closes
when this authorized checkpoint becomes remote-verified. RB1.3 is the next authorized
task but remains `NOT STARTED`; no later step may be silently skipped or inferred complete.

---

# 7. M6 Entry Conditions

M6 remains `NOT STARTED / NOT AUTHORIZED`.

M6 Character Intelligence must include at least background, motivation, belief,
conflict, goal, personality, behavior rules, dialogue rules, forbidden behavior,
visual identity rules, `CharacterState`, `RelationshipContext`, timeline and
continuity.

`M6 ≠ V5 Identity Lock`. M6 does not implement M7, GPU Render, ComfyUI, Worker or
cross-repository UI.

M6 cannot begin until all are true:

1. authoritative responsibility rebaseline accepted and remote-verified;
2. legacy Core customer UI decommission completed safely;
3. Gate B passes after decommission;
4. full Core current-state audit completed;
5. Project Lead architecture review completed;
6. M6 prerequisites explicitly accepted;
7. M6-P1 explicitly authorized in a later `CURRENT_MILESTONE.md` revision.

This document does not authorize M6 or M7 implementation.

Legacy Phase 0 governance drift is `OPEN / DEFERRED TO PRE-M6-RB1.3`. It is not
silently changed by this seven-file work package.

`P3-RV1-003` remains `OPEN` as non-blocking EOL audit debt.

---

# 8. Current Work Package Gates

- PRE-M6-RB1.1: `CLOSED`
- RB1.1 CHECKPOINT: `00793953e71711ab95724353d97d3a913be2b853`
- RB1.1 LOCAL / REMOTE VERIFICATION: `PASS`
- ADR-0001 STATUS: `Accepted`
- PRE-M6-RB1.2 INDEPENDENT REVIEW: `ACCEPTED`
- RB1.2 CHECKPOINT: `AUTHORIZED / THIS COMMIT`
- PRE-M6-RB1.2: `CLOSED WITH REMOTE-VERIFIED CHECKPOINT`
- PRE-M6-RB1.3: `AUTHORIZED / NOT STARTED`
- P3-RV1-003: `OPEN / NON-BLOCKING EOL AUDIT DEBT`
- M6: `NOT STARTED / NOT AUTHORIZED`
- M7: `NOT STARTED / NOT AUTHORIZED`
- RUNTIME CODE CHANGED: YES, static customer UI mounting removed only
- TEST CODE CHANGED: YES, UI-only tests removed and no-UI Core contract added

RB1.3 execution must not begin within the RB1.2 checkpoint task.

---

# 9. Stop Rule

After the RB1.2 checkpoint is remote-verified:

STOP.

Report the checkpoint and wait for execution of the separately authorized RB1.3 task.

Do not begin the full Core audit within this checkpoint task.

Do not enter M6 or M7.

---

# 10. Next Authorized Task

`PRE-M6-RB1.3 — Core Full Audit`

Status:

`AUTHORIZED / NOT STARTED`

RB1.3 must perform the code-first Core current-state audit and complete its required
Architecture Review before any M6 precondition or implementation authorization can be
considered. This checkpoint does not begin RB1.3, M6 or M7.

# End of CURRENT_MILESTONE.md
