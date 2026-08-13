# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: `AUTO-SEQUENTIAL`
>
> Project Lead Authorization: `ADR-0006 ACCEPTED / BOUNDED G0 → G1 REMEDIATION WAVE AUTHORIZED 2026-08-13`
>
> Authorized Wave: `ACS-ARCH-R1-V5-TEXT-GENERATION-G0 → ACS-ARCH-R1-V5-TEXT-GENERATION-G1`
>
> Current Task: `ACS-ARCH-R1-V5-TEXT-GENERATION-G0 — GOVERNANCE / ARCHITECTURE SYNCHRONIZATION`
>
> Current Work Package: `G0 IN PROGRESS / G1 AUTHORIZED ONLY AFTER G0 REMOTE VERIFICATION`
>
> M6 Authorization: `P0-P2 OWNER ACCEPTED / G3-P3-G0 REMOTE-VERIFIED CANDIDATE ON HOLD / P3 IMPLEMENTATION NOT AUTHORIZED`
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

`Architecture Remediation R1 — V5-owned Text Generation Capability Boundary`

Title:

ACS-ARCH-R1 V5 Text Generation G0 → G1

Status:

`ADR-0006 ACCEPTED / G0 IN PROGRESS / G1 CONDITIONALLY AUTHORIZED / P3 ON HOLD`

Purpose:

1. preserve the remote-verified PRE-M6 checkpoints and accepted M6-P0/P1/P2 evidence;
2. keep the remote-verified c524 G3/P3-G0 candidate on HOLD without accepting P3;
3. record `R-CORE-ARCH-001 / CONFIRMED / HIGH / MITIGATING`;
4. record ADR-0006 and its V5 Text Generation contract as accepted for bounded G1;
5. remote-verify G0 before automatically entering G1;
6. migrate the four active Application/V4 contact points while preserving accepted
   M1/M3/M5 and public API behavior;
7. stop after G1 remote verification for Project Lead owner review;
8. keep M6-P3, M7-M19, formal database deployment and Frontend unauthorized and
   Production Ready as `NO`.

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

# 3. PRE-M6 Closeout Record

Decision date: `2026-08-13`.

PRE-M6-RB1.3-R2-P1 is `ACCEPTED`. PRE-M6-RB1.3-R2-P2 is `OWNER ACCEPTED /
COMPLETE / REMOTE-VERIFIED` at
`0aa14b4e426a3d968ec314029d60a47ea30cbc4d`. RB13-F001 and RB13-F002 are
closed in the current tested Core baseline. PRE-M6-RB1.3 is `REMEDIATION COMPLETE /
FORMALLY CLOSED BY PROJECT LEAD OWNER REVIEW`.

At the G1 closeout recorded below, Architecture Review and M6 Preconditions were
satisfied only for bounded InMemory M6-P0/P1. That historical decision is preserved;
the later ADR-0004 decision separately extends the active authorization to bounded
M6-P2 local-development SQLite. Formal 8765 deployment remains unperformed and
unauthorized. The Frontend remains frozen and untouched. `P3-RV1-003` remains open
and non-blocking.

PRE-M6-RB1.3-CLOSEOUT-G1-R1 is `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`
at `dc9ab881b9f82ecd4a5927c456d5fe531f6850fa`. ADR-0003 is
`ACCEPTED FOR BOUNDED M6-P1 IMPLEMENTATION`. P1 authority comes from G1-R1; P0
records its bounded design and does not create a new authorization.

`ACS-M6-P0-P1-R2` is `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED` at
`e38c75aa4ff26bdea80c82d8a24096f799dad860`. The accepted full Core result is
`332/332 PASS`; targeted M6 is `44/44 PASS`. ADR-0004 and
`M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md` are accepted for bounded M6-P2 local
development implementation only.

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

# 6. Accepted Route and Current Transition

Strict order:

`PRE-M6-RB1.1 Source-of-Truth Rebaseline`
→ `PRE-M6-RB1.2 Legacy UI Decommission`
→ `PRE-M6-RB1.3 Full Core Current-State Audit`
→ `Architecture Review`
→ `M6 Preconditions`
→ `M6-P1`

`PRE-M6-RB1.1`, `PRE-M6-RB1.2` and `PRE-M6-RB1.3` are closed. R2-P1 and R2-P2
are accepted, and R2-P2 is remote-verified at
`0aa14b4e426a3d968ec314029d60a47ea30cbc4d`.

`ACS-M6-P0-P1-R2` is `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED` at
`e38c75aa4ff26bdea80c82d8a24096f799dad860`. ADR-0004 and the M6 SQLite
contract are accepted. `ACS-M6-P2-G1` is now `OWNER ACCEPTED / COMPLETE /
REMOTE-VERIFIED` at `8227c6c616140824fd70de920dc6fcf459bb734d`.

The G3/P3-G0 governance revision is remote-verified at
`c524486c05c21b270a7dd75e89fae4312430736a`, but remains an Owner Review
Pending checkpoint candidate and is now on HOLD. It does not accept ADR-0005 or
authorize M6-P3 implementation.

The current authorized transition is:

```text
ACS-ARCH-R1-V5-TEXT-GENERATION-G0
→ ACS-ARCH-R1-V5-TEXT-GENERATION-G1
→ STOP FOR PROJECT LEAD OWNER REVIEW
```

G1 may begin only after the G0 commit is pushed and Local SHA equals Remote SHA. No
M6-P3 implementation or later milestone may be silently entered.

---

# 7. Preserved M6-P3-G0 Proposal and Current Hold

M6-P0/P1 and M6-P2-G1 are `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`.
The G3/P3-G0 revision is `REMOTE-VERIFIED / OWNER REVIEW PENDING / HOLD`. ADR-0005
and the M6 consumer contract remain `PROPOSED / NO IMPLEMENTATION AUTHORITY`.
M6-P3-B1 and M6-P3-G1+ remain `NOT AUTHORIZED / NOT STARTED`.

M6 Character Intelligence must include at least background, motivation, belief,
conflict, goal, personality, behavior rules, dialogue rules, forbidden behavior,
visual identity rules, `CharacterState`, `RelationshipContext`, timeline and
continuity.

`M6 ≠ V5 Identity Lock`. M6 does not implement M7, GPU Render, ComfyUI, Worker or
cross-repository UI.

The completed P0/P1 gate order is:

1. R1 implementation completes and passes independent review;
2. R2 deletion lifecycle remediation completes;
3. InMemory/SQLite consistency, concurrency and TOCTOU validation pass;
4. the RB1.3 full regression passes;
5. RB1.3 is formally closed;
6. Architecture Review passes;
7. all M6 Preconditions are satisfied;
8. the Project Lead separately authorizes M6-P1.

All eight gates are satisfied for bounded M6-P0/P1. The accepted M6-P2 gate order was:

1. use only temporary file SQLite databases;
2. preserve the accepted M6 domain and full Scope authority;
3. migrate fresh/V2/no-op atomically and fail closed on invalid input;
4. persist M6 facts, operations and Outbox in one lifecycle transaction;
5. pass restart, rollback, commit-uncertainty, delete and cross-Assembly concurrency;
6. pass InMemory/SQLite contract parity and the complete Core regression;
7. commit, push, fetch and verify Local SHA equals Remote SHA;
8. report a checkpoint candidate and stop.

All M6-P2 gates passed and the Project Lead accepted the remote technical baseline.

M6-P3-G0 now defines only a Proposed internal, read-only, persistence-neutral M6
Episode baseline consumer for M3 Script Studio. M4 owns trusted Project-to-Series
context; M2 owns Series/Episode identity and membership. The accepted records have no
shared stable key, so ADR-0005 proposes an immutable M5 EpisodePlanItemBinding inside a
new exact SeriesPlanVersion. M6 keeps its existing facts; M7 remains owner of future
consistency verdicts; M9 remains owner of future AssetRequirement and asset-resolution
readiness.

Number, title, array position and display name matching are forbidden. The future
sequence is two independent checkpoints: first P3-B1 implements the proposed M5 v2
binding, then P3-G1 implements the read-only M6/M3 consumer. P3-B1 must be separately
authorized, tested, pushed, remote-verified and Owner Accepted before P3-G1 can be
authorized. Neither implementation is authorized by this document.

The current ADR-0006 remediation wave neither accepts nor rejects this proposal. P3
may resume only through a later explicit Project Lead decision after G1 owner review.

This document does not authorize M6-P3 implementation, M7-M19, formal database
deployment, HTTP/API/Auth/RBAC or Frontend implementation.

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
- PRE-M6-RB1.3: `REMEDIATION COMPLETE / FORMALLY CLOSED BY PROJECT LEAD OWNER REVIEW`
- PRE-M6-RB1.3-IR1: `COMPLETED`
- FULL CORE AUDIT REPORT v1.2 ACCEPTANCE LABEL: `PRESERVED`; REPOSITORY PROVENANCE:
  `R-CORE-GOV-002 / OPEN / NON-BLOCKING / NOT IMPLEMENTATION AUTHORITY`
- PRE-M6-RB1.3-R1-RV1: `INDEPENDENTLY ACCEPTED`
- RB13-F001: `R1 IMPLEMENTED / INDEPENDENTLY ACCEPTED / CLOSED`
- ADR-0002 STATUS: `ACCEPTED FOR BOUNDED R2 IMPLEMENTATION`
- RB13-F002: `REMEDIATED / CLOSED IN CURRENT TESTED CORE BASELINE`
- EXECUTION MODE: `AUTO-SEQUENTIAL`
- AUTHORIZED WAVE: `ACS-ARCH-R1-V5-TEXT-GENERATION-G0 → G1`
- CURRENT TASK: `G0 GOVERNANCE / ARCHITECTURE SYNCHRONIZATION`
- G0 BASE: `c524486c05c21b270a7dd75e89fae4312430736a`
- ADR-0006 STATUS: `ACCEPTED FOR BOUNDED G1`
- V5 TEXT GENERATION CONTRACT: `ACCEPTED FOR BOUNDED G1`
- R-CORE-ARCH-001: `CONFIRMED / HIGH / MITIGATING / G1 REMEDIATION AUTHORIZED`
- R-CORE-GOV-002: `OPEN / NON-BLOCKING`
- G1 STATUS: `AUTHORIZED ONLY AFTER G0 REMOTE VERIFICATION / NOT STARTED`
- ACS-M6-P0-P1-R2: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860`
- R2-P1 STATUS: `ACCEPTED`
- R2-P2 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 0aa14b4e426a3d968ec314029d60a47ea30cbc4d`
- LEGACY REPOSITORY CAPABILITY PROVENANCE: `MEDIUM / OPEN / NON-BLOCKING`
- P3-RV1-003: `OWNER GATE / OPEN / NON-BLOCKING EOL AUDIT DEBT`
- RB1.3 CLOSEOUT: `FORMALLY CLOSED`
- ARCHITECTURE REVIEW: `SATISFIED FOR BOUNDED M6-P0/P1 AND M6-P2 LOCAL SQLITE ONLY`
- M6 PRECONDITIONS: `SATISFIED FOR BOUNDED M6-P0/P1 AND M6-P2 LOCAL SQLITE ONLY`
- M6: `P0-P2 OWNER ACCEPTED / P3-G0 REMOTE-VERIFIED CANDIDATE ON HOLD / P3-B1 AND P3-G1+ NOT AUTHORIZED`
- M6-P0 STATUS: `CONTRACT ACCEPTED / COMPLETE`
- M6-P1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860`
- ADR-0004 STATUS: `ACCEPTED FOR BOUNDED M6-P2 IMPLEMENTATION`
- M6-P2-G0 STATUS: `CONTRACT ACCEPTED / COMPLETE`
- M6-P2-G1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 8227c6c616140824fd70de920dc6fcf459bb734d`
- M6-P2-G1-CLOSEOUT-G3 STATUS: `REMOTE-VERIFIED CHECKPOINT CANDIDATE AT c524486c05c21b270a7dd75e89fae4312430736a / OWNER REVIEW PENDING / HOLD`
- M6-P3-G0 STATUS: `ARCHITECTURE PROPOSAL DEFINED / BINDING PREREQUISITE OPEN / REMOTE-VERIFIED CHECKPOINT CANDIDATE / OWNER REVIEW PENDING / HOLD`
- ADR-0005 STATUS: `PROPOSED / NO IMPLEMENTATION AUTHORITY`
- M6 CONSUMER CONTRACT: `PROPOSED / NO IMPLEMENTATION AUTHORITY`
- M6-P3-B1 EPISODE-PLAN-ITEM BINDING: `PROPOSED / NOT AUTHORIZED / NOT STARTED / BLOCKS M6-P3-G1`
- M6-P3-G1+ STATUS: `NOT AUTHORIZED / NOT STARTED`
- M7-M19: `NOT STARTED / NOT AUTHORIZED`
- FORMAL 8765 DEPLOYMENT: `UNTOUCHED / NOT DEPLOYED`
- FRONTEND: `FROZEN / UNTOUCHED`
- PRODUCTION READY: `NO`
- PRODUCTION CODE CHANGED BY THIS G0: `NO`
- TEST CODE CHANGED BY THIS G0: `NO`
- REUSED ACCEPTED C524 EVIDENCE — NOT RERUN FOR GOVERNANCE-ONLY G0:
  `M6-P2 STRICT 52/52 PASS / FULL CORE 385/385 PASS — UNIT 210 / CONTRACT 78 /
  INTEGRATION 97 / PYTHON AST 58/58 PASS`

The Project Lead acceptance of bounded M6-P2-G1 at
`8227c6c616140824fd70de920dc6fcf459bb734d` remains unchanged. The later c524
G3/P3-G0 checkpoint remains a remote-verified candidate on HOLD and does not accept
ADR-0005. The Project Lead selected and accepted ADR-0006 and authorizes only the
bounded G0 → G1 architecture remediation wave. This is not Production Ready and does
not authorize formal database deployment, Frontend, M6-P3-B1, M6-P3-G1+ or M7-M19.

---

# 9. Stop Rule

G0 is governance-only. It must pass Markdown structure, local links, secret scan,
`git diff --check`, production/test diff zero, commit, push, Local SHA equals Remote
SHA, ahead/behind `0/0` and clean-status gates before G1 begins.

After G0 remote verification, Codex may automatically enter only the bounded G1
defined by ADR-0006 and
[`V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md`](architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md).

G1 must migrate the four active Application/V4 production contact points, add an
executable `apps → V4` prohibition, preserve public HTTP/API and M1/M3/M5 behavior,
pass targeted and full Core regression, commit, push and remote-verify.

After G1 is pushed and remote-verified:

```text
STOP — ARCHITECTURE REMEDIATION TECHNICAL CHECKPOINT CANDIDATE
PROJECT LEAD OWNER REVIEW REQUIRED
```

Do not enter M6-P3-B1, M6-P3-G1, M7-M19, formal database deployment, HTTP/Auth/RBAC
expansion or Frontend work.

---

# 10. Current Authorized Task

`ACS-ARCH-R1-V5-TEXT-GENERATION-G0 — GOVERNANCE / ARCHITECTURE SYNCHRONIZATION`

Status:

`IN PROGRESS`

M6-P0/P1 and bounded M6-P2-G1 remain Owner Accepted at their remote-verified technical
baselines. The c524 G3/P3-G0 revision remains a remote-verified checkpoint candidate
on HOLD; ADR-0005 remains Proposed and no P3 implementation is authorized.

ADR-0006 accepts the single production path:

```text
Creator Application
→ V5 Text Generation Capability
→ V4 TextGenerationPort
→ Provider Adapter
```

The Project Lead authorizes G0 governance synchronization and, only after G0 remote
verification, bounded G1 production/test remediation. The normative contract is
[`V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md`](architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md).

Formal port-8765 database access/deployment, HTTP/Public API, Auth/RBAC, Frontend,
Schema/Migration, public feature expansion, P3-B1/G1+, M7-M19, V3, GPU, Worker and
ComfyUI remain unauthorized and not started. G1 must not create a second Provider
stack or change existing Domain ownership, candidate semantics or Production Spine.

# End of CURRENT_MILESTONE.md
