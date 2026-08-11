# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: MANUAL
>
> Current Task: `PRE-M6-RB1.2 — Legacy UI Decommission`
>
> Current Work Package: `Authorized Legacy UI classification and decommission / implementation not started`
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

UI-R2A remains historical implementation evidence until the legacy Core browser UI is
decommissioned. It is no longer the active work package and does not authorize M6.

---

# 1. Current Control Stage

Current stage:

`PRE-M6-RB1.2`

Title:

Legacy UI Decommission

Status:

`AUTHORIZED / NOT STARTED`

Purpose:

1. record `PRE-M6-RB1.1` as `CLOSED` at remote-verified checkpoint
   `00793953e71711ab95724353d97d3a913be2b853`;
2. execute only the authorized RB1.2 classification and safe removal of the Legacy
   Core customer UI while preserving Creator Server, Application and production
   authority;
3. keep the separate Commercial Frontend as the sole customer-facing UI source;
4. require independent RB1.2 review before closure or checkpoint authorization;
5. keep RB1.3 unauthorized until a later explicit Project Lead decision;
6. require the RB1.3 code-first Core audit and Architecture Review before M6-P1.

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

`apps/creator-workspace-mvp` is a controlled `DECOMMISSION CANDIDATE`.

This milestone is the explicit `PRE-M6-RB1.2` authorization. It permits removal only
after repository dependencies prove a target to be UI-only; runtime/API/application
responsibilities in the same directory remain protected.

Authorized for later removal only when proven UI-only:

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
`00793953e71711ab95724353d97d3a913be2b853`. The current stage is only the authorized
`PRE-M6-RB1.2` implementation. RB1.3 remains `NOT AUTHORIZED`; no later step may be
silently skipped or inferred complete.

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
- PRE-M6-RB1.2: `AUTHORIZED / NOT STARTED`
- PRE-M6-RB1.3: `NOT AUTHORIZED`
- P3-RV1-003: `OPEN / NON-BLOCKING EOL AUDIT DEBT`
- M6: `NOT STARTED / NOT AUTHORIZED`
- M7: `NOT STARTED / NOT AUTHORIZED`
- RUNTIME CODE CHANGED: NO, before RB1.2 implementation
- TEST CODE CHANGED: NO, before RB1.2 implementation

RB1.2 implementation results must not be staged, committed, pushed or tagged before
independent review and separate checkpoint authorization.

---

# 9. Stop Rule

After the RB1.2 implementation report:

STOP.

Wait for independent RB1.2 review and Project Lead decision.

Do not begin the full Core audit yet.

Do not enter M6 or M7.

---

# 10. Required RB1.2 Implementation Report

BRANCH:

HEAD:

AUTHORITY_FILES_CHANGED:

ADR:

OLD_ONE_CREATOR_UI_RULE:

NEW_ONE_CREATOR_UI_RULE:

CORE_REPOSITORY_ROLE:

FRONTEND_REPOSITORY_ROLE:

CREATOR_SERVER_ROLE:

LEGACY_UI_STATUS:

BROWSER_GATE_REPLACEMENT:

CROSS_REPO_CONTRACT:

RB1_1_CLOSURE:

RB1_1_CHECKPOINT:

RB1_2_STATUS:

M6_STATUS:

LEGACY_UI_SCOPE:

CORE_RUNTIME_GATE:

FRONTEND_EXCLUSION:

RUNTIME_CODE_CHANGED:

FINAL:

`RB1.2 IMPLEMENTED / REVIEW PENDING`

or

`BLOCKED`

# End of CURRENT_MILESTONE.md
