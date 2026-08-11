# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: MANUAL
>
> Current Task: `PRE-M6-RB1.1 — Source-of-Truth Rebaseline`
>
> Current Work Package: `Source-of-Truth Rebaseline Contract Closure / R2 revision before independent re-verify`
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

`PRE-M6-RB1.1`

Title:

Source-of-Truth Rebaseline

Status:

`CURRENT / R2 REVISION BEFORE INDEPENDENT RE-VERIFY`

Purpose:

1. record that RV1 returned `BLOCKED` on P1-RV1-001 and P1-RV1-002;
2. execute only the M5 status synchronization and ADR central-risk semantic
   reconciliation required by R2, with a new independent read-only re-verify pending;
3. make the separate Commercial Frontend the sole customer-facing UI source only
   after ADR-0001 acceptance and a remote-verified checkpoint;
4. preserve Core Creator Server, Application and production authority;
5. protect Legacy UI until separately authorized RB1.2 classification and removal;
6. require the RB1.3 code-first Core audit and Architecture Review before M6-P1.

---

# 2. Proposed Responsibility Contract

ONE CREATOR UI remains mandatory.

Subject to later ADR-0001 acceptance and a remote-verified rebaseline checkpoint, the
proposed interpretation is:

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

# 3. Current Documentation-Only Work Package

The current work package may modify only these seven authority files:

- `AGENTS.md`;
- `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`;
- `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`;
- `CURRENT_MILESTONE.md`;
- `architecture/system-context.md`;
- `architecture/system-overview.md`;
- `governance/ADR-0001-separate-commercial-experience-layer-from-core-creator-runtime.md`.

Runtime, application, domain, test, migration, asset and separate Frontend repository
changes are prohibited in this work package.

This work package must stop at a PRE-COMMIT review. It does not commit or push.

---

# 4. Legacy Core Creator UI Status

`apps/creator-workspace-mvp` is a controlled `DECOMMISSION CANDIDATE`.

Actual customer UI removal requires separate `PRE-M6-RB1.2` authorization. This
work package does not delete, move or modify any file in that directory.

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

The current stage is only the `PRE-M6-RB1.1` contract-closure revision. No step may be
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

---

# 8. Current Work Package Gates

- RV1 RESULT: BLOCKED / P1-RV1-001 AND P1-RV1-002
- M5 STATUS SYNCHRONIZATION: R2 REVISION EXECUTED / INDEPENDENT RE-VERIFY PENDING
- ADR CENTRAL-RISK SEMANTIC RECONCILIATION: R2 REVISION EXECUTED / INDEPENDENT RE-VERIFY PENDING
- AUTHORITY HIERARCHY: UNCHANGED / INDEPENDENT RE-VERIFY PENDING
- SYSTEM MASTER PLAN: UNCHANGED BY R2 / INDEPENDENT RE-VERIFY PENDING
- AGENTS RULES: UNCHANGED BY R2 / INDEPENDENT RE-VERIFY PENDING
- ACTIVE ARCHITECTURE BASELINE RECONCILIATION: PENDING INDEPENDENT RE-VERIFY
- ADR STATUS: PROPOSED / NOT ACCEPTED
- ACTIVE AUTHORITY CONTRADICTION SCAN: PENDING INDEPENDENT RE-VERIFY
- DOCUMENT-ONLY SCOPE: R2 LOCAL VALIDATION EXECUTED / INDEPENDENT RE-VERIFY PENDING
- RUNTIME CODE CHANGED: NO
- TEST CODE CHANGED: NO
- `git diff --check`: R2 LOCAL VALIDATION EXECUTED / INDEPENDENT RE-VERIFY PENDING
- INDEPENDENT READ-ONLY RE-VERIFY: PENDING

No Git commit, push or tag is permitted in the current work package.

---

# 9. Stop Rule

After the PRE-COMMIT report:

STOP.

Wait for Project Lead source-of-truth rebaseline review.

Do not decommission UI code yet.

Do not begin the full Core audit yet.

Do not enter M6 or M7.

---

# 10. Required PRE-COMMIT Report

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

CURRENT_MILESTONE:

M6_STATUS:

CONTRADICTION_SCAN:

RUNTIME_CODE_CHANGED:

FINAL:

`R2 REVISION EXECUTED / INDEPENDENT READ-ONLY RE-VERIFY PENDING`

or

`BLOCKED`

# End of CURRENT_MILESTONE.md
