# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: MANUAL
>
> Current Task: `PRE-M6-RB1.3-R2-P2 — SQLite Lifecycle Integrity / FK / Migration`
>
> Current Work Package: `PRE-M6 RB1.3 Remediation / ADR-0002 accepted / R2-P1 complete / R2-P2 implemented pending owner review`
>
> M6 Authorization: `NOT AUTHORIZED`
>
> M7 Authorization: `NOT AUTHORIZED`
>
> Production Ready: `NO`

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

Core Full Audit Remediation

Status:

`EXECUTED / REJECTED / REMEDIATION IN PROGRESS`

Purpose:

1. preserve PRE-M6-RB1.1 and PRE-M6-RB1.2 as closed remote-verified checkpoints;
2. record PRE-M6-RB1.3-IR1 as `COMPLETED`;
3. record Full Core Audit Report v1.2 as `INDEPENDENTLY ACCEPTED`;
4. record PRE-M6-RB1.3-R1-RV1 as `INDEPENDENTLY ACCEPTED` and close RB13-F001;
5. keep RB13-F002 blocking and record R2-P2 as `IMPLEMENTED / PENDING OWNER REVIEW`;
6. keep RB1.3 Closeout unauthorized, Architecture Review pending, and M6/M7 not
   started and not authorized.

---

# 2. Accepted Responsibility Contract

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

Accepted cross-repository dependency chain:

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

# 3. Current RB1.3 Remediation Work Package

PRE-M6-RB1.3 was executed and rejected for remediation. PRE-M6-RB1.3-IR1 is
`COMPLETED`, Full Core Audit Report v1.2 is `INDEPENDENTLY ACCEPTED`, and
PRE-M6-RB1.3-R1-RV1 is `INDEPENDENTLY ACCEPTED`.

RB13-F001 is `R1 IMPLEMENTED / INDEPENDENTLY ACCEPTED / CLOSED`.

ADR-0002 is `ACCEPTED FOR BOUNDED R2 IMPLEMENTATION`. RB13-F002 remains
`HIGH / CONFIRMED / BLOCKING / R2-P2 IMPLEMENTED / PENDING OWNER REVIEW`.
`PRE-M6-RB1.3-R2-P2` is the current task. R2-P2 adds SQLite lifecycle transactions,
foreign keys and explicit V1-to-V2 migration tested only on temporary databases. Formal
database migration, public API changes, Auth/RBAC/Permission, the separate Frontend
repository, M6 and M7 remain outside this work package.

---

# 4. Legacy Core Creator UI Status

`apps/creator-workspace-mvp` is `DECOMMISSIONED / CLOSED / REMOTE-VERIFIED`.

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

`PRE-M6-RB1.1` and `PRE-M6-RB1.2` are closed with remote-verified checkpoints.
PRE-M6-RB1.3 is `EXECUTED / REJECTED / REMEDIATION IN PROGRESS`. IR1 is `COMPLETED`,
Full Core Audit Report v1.2 and R1-RV1 are `INDEPENDENTLY ACCEPTED`, and RB13-F001 is
closed. RB13-F002 remains blocking; R2-P2 is implemented pending owner review. No later step may
be silently skipped or inferred complete.

---

# 7. M6 Entry Conditions

M6 remains `NOT STARTED / NOT AUTHORIZED`.

M6 Character Intelligence must include at least background, motivation, belief,
conflict, goal, personality, behavior rules, dialogue rules, forbidden behavior,
visual identity rules, `CharacterState`, `RelationshipContext`, timeline and
continuity.

`M6 ≠ V5 Identity Lock`. M6 does not implement M7, GPU Render, ComfyUI, Worker or
cross-repository UI.

M6 cannot begin until all are true, in this order:

1. R1 implementation completes and passes independent review;
2. R2 deletion lifecycle remediation completes;
3. InMemory/SQLite consistency, concurrency and TOCTOU validation pass;
4. the RB1.3 full regression passes;
5. RB1.3 is formally closed;
6. Architecture Review passes;
7. all M6 Preconditions are satisfied;
8. the Project Lead separately authorizes M6-P1.

This document does not authorize M6 or M7 implementation.

Legacy repository capability provenance remains `MEDIUM / OPEN / NON-BLOCKING` under
Owner Gate `P3-RV1-003`. Old-repository implementation is not current Core production
capability.

---

# 8. Current Work Package Gates

- PRE-M6-RB1.1: `CLOSED`
- RB1.1 CHECKPOINT: `00793953e71711ab95724353d97d3a913be2b853`
- RB1.1 LOCAL / REMOTE VERIFICATION: `PASS`
- ADR-0001 STATUS: `Accepted`
- PRE-M6-RB1.2: `CLOSED WITH REMOTE-VERIFIED CHECKPOINT`
- PRE-M6-RB1.3: `EXECUTED / REJECTED / REMEDIATION IN PROGRESS`
- PRE-M6-RB1.3-IR1: `COMPLETED`
- FULL CORE AUDIT REPORT v1.2: `INDEPENDENTLY ACCEPTED`
- PRE-M6-RB1.3-R1-RV1: `INDEPENDENTLY ACCEPTED`
- RB13-F001: `R1 IMPLEMENTED / INDEPENDENTLY ACCEPTED / CLOSED`
- ADR-0002 STATUS: `ACCEPTED FOR BOUNDED R2 IMPLEMENTATION`
- RB13-F002: `HIGH / CONFIRMED / BLOCKING / R2-P2 IMPLEMENTED / PENDING OWNER REVIEW`
- CURRENT TASK: `PRE-M6-RB1.3-R2-P2`
- R2-P1 STATUS: `COMPLETE`
- R2-P2 STATUS: `IMPLEMENTED / PENDING OWNER REVIEW`
- LEGACY REPOSITORY CAPABILITY PROVENANCE: `MEDIUM / OPEN / NON-BLOCKING`
- P3-RV1-003: `OWNER GATE / OPEN / NON-BLOCKING EOL AUDIT DEBT`
- RB1.3 CLOSEOUT: `NOT AUTHORIZED`
- ARCHITECTURE REVIEW: `PENDING`
- M6: `NOT STARTED / NOT AUTHORIZED`
- M7: `NOT STARTED / NOT AUTHORIZED`
- PRODUCTION READY: `NO`
- PRODUCTION CODE CHANGED BY R1: `NO`
- TEST CODE CHANGED BY R1: `NO`

The accepted R1 checkpoint closes RB13-F001. The bounded R2-P1 checkpoint alone did not
authorize R2-P2; the later explicit Project Lead instruction authorizes this P2 work package only.
Neither checkpoint closes RB13-F002 or RB1.3, passes Architecture Review, or authorizes M6.

---

# 9. Stop Rule

After the R2-P2 implementation checkpoint is remote-verified:

STOP.

Report the P2 checkpoint and wait for independent owner review.

Do not migrate the formal database or begin RB1.3 Closeout or Architecture Review within this work package.

Do not enter M6 or M7.

---

# 10. Current Authorized Task

`PRE-M6-RB1.3-R2-P2 — SQLite Lifecycle Integrity / FK / Migration`

Status:

`AUTHORIZED / IN PROGRESS`

R2-P2 may proceed under the explicit Project Lead instruction dated `2026-08-12`.
This authorization does not permit formal database migration and does not authorize
RB1.3 Closeout, Architecture Review, M6 or M7.

# End of CURRENT_MILESTONE.md
