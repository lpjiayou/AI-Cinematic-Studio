# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: `MANUAL / BOUNDED / FAIL-CLOSED`
>
> Project Lead Authorization: `CCV-R1 SEED-TYPE CORRECTION OWNER ACCEPTED AT 0c2552bf; PR #4 REBASE AND MERGE AUTHORIZED; CAPTURE G0 DIRECTLY OWNER ACCEPTED AT 9094a466; CAPTURE G1 REMOTE-VERIFIED AT af34ac07; ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2 AUTHORIZED ON 2026-08-14`
>
> Authorized Wave: `CAPTURE G2 GOVERNANCE CHECKPOINT → REMOTE VERIFY → ONE-WINDOW READ-ONLY COLLECTION → OFFLINE NORMALIZATION → STOP`
>
> Current Task: `ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2`
>
> Current Work Package: `ONE-WINDOW READ-ONLY EXTERNAL HISTORICAL EVIDENCE COLLECTION / NO RERUN / NO PRODUCT OR TEST TREE CHANGE`
>
> M6 Authorization: `P0-P2 OWNER ACCEPTED / P3-G0 OWNER ACCEPTED AS ARCHITECTURE / P3-B1 OWNER ACCEPTED THROUGH B1-R1 / P3-G1 OWNER ACCEPTED THROUGH G1-R1 / LATER M6 NOT AUTHORIZED`

> Next Checkpoint: `CCV-R2 / NOT AUTHORIZED / NOT STARTED`
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

`Character Consistency Evidence Hardening`

Title:

ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2

Status:

`CAPTURE G0 OWNER ACCEPTED AT 9094a466 / G1 REMOTE-VERIFIED AT af34ac07 / G2 ONE-WINDOW READ-ONLY COLLECTION AUTHORIZED / INDEPENDENT REPRODUCTION NOT POSSIBLE`

Purpose:

1. preserve `ACS-GOV-POST-M6-P3-G1-CLOSEOUT` as Owner Accepted at
   `20207e7f2d2123468698f453c70ce725a293976a`, tree
   `e3638838dd0c79201a1962bb247ec7c773b62ffa`;
2. correct the Character Consistency report's `40 → 50` accounting and overclaims;
3. establish `experiments/ccv-r1/` as an evidence-only structure with no generated
   image or model binary;
4. provide hardened successor scripts, config-driven parameters, manifest schema and
   no-GPU fail-closed validation;
5. record all unavailable historical scripts/workflows/seeds/hashes/logs as pending,
   without guessing;
6. preserve production, tests, HTTP/API, Frontend, schema/migration and event semantics;
7. preserve the Owner-accepted CCV-R1 tree now converged to `main` through PR #4;
8. derive SD1.5/SDXL conditioning width from actual safetensors headers during
   finalization rather than trusting declarations;
9. make captured manifest completeness and exact run counts independently enforceable;
10. register the five Round 3 skeleton inputs as five digest-bearing artifacts.

G1 closed the three G0 evidence-tooling blockers and is remote-verified at
`af34ac074cb8bfbf334e4f56aad0c0d479b741be`. G2 authorizes one read-only source
access window to collect the exact registered historical evidence into isolated
external custody storage. It does not rerun the GPU experiment and authorizes no
CCV-R2, Character Visual Identity ADR implementation, M6 schema change or production
GPU integration.

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

The G3/P3-G0 proposal is remote-verified at
`c524486c05c21b270a7dd75e89fae4312430736a`; its later review-open state is preserved
at `dec102b2d70b95d6b69a96ae98d768a32723d4ba`. The Project Lead and Architecture
Owner have now accepted ADR-0005 and the M6 Consumer Contract as architecture only.
That architecture checkpoint is remote-verified at
`6bb9d165a693057f38e5789c408293ff0eaf5bcc`. The Project Lead, Architecture Owner,
Repository Governance Owner and affected M2/M4/M5/M6 Domain Owners now authorize the
bounded B1 sequence recorded in
[`ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md`](governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md).

The completed architecture-remediation transition is:

```text
ACS-ARCH-R1-V5-TEXT-GENERATION-G0
→ ACS-ARCH-R1-V5-TEXT-GENERATION-G1
→ STOP FOR PROJECT LEAD OWNER REVIEW
```

G0 is remote-verified at `92d1f3ac9e08c71458af04514baa659555fc55a7` and G1 is
remote-verified at `0c283eb653e74784301620bdaf64bf451bb687dd`. Independent
review then confirmed that the production migration is intact but the guard can miss
programmatic-import aliases. The original G1 candidate is therefore `REVISION
REQUIRED / NOT OWNER ACCEPTED`.

The corrected remediation transition is complete:

```text
ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-AUTHORIZATION
→ G1-R1 TEST-ONLY GUARD CORRECTION
→ OWNER ACCEPTED AT d44f471c644e319bb4a5bf73707c3274ecbaa426
```

The original G1 remains historical `REVISION REQUIRED / NOT OWNER ACCEPTED` and is
superseded by the accepted G1-R1 result. B1 candidate
`8449b521c96bb8340806ecda8649698f4771914a` is also `REVISION REQUIRED / NOT OWNER
ACCEPTED`. B1-R1 corrected that defect and is Owner Accepted at
`5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`. M6-P3-G1 and G1-R1 were later completed
as recorded below. The governance closeout is now Owner Accepted; the current
authorized transition is evidence-only:

```text
ACS-GOV-POST-M6-P3-G1-CLOSEOUT OWNER ACCEPTED AT 20207e7f
→ ACS-CCV-R1 EVIDENCE HARDENING
→ ORIGINAL CANDIDATE 57cbbd49 REVISION REQUIRED
→ ACS-CCV-R1-R1 EVIDENCE VALIDATOR CORRECTION
→ COMMIT / NON-FORCE PUSH / DRAFT PR / CI / REMOTE VERIFY
→ STOP
```

No CCV-R2, schema work or later milestone may be silently entered after this
checkpoint.

---

# 7. Authorized M6-P3-B1 Binding Prerequisite

M6-P0/P1 and M6-P2-G1 are `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`.
The Project Lead and Architecture Owner accepted the G3/P3-G0 target architecture,
ADR-0005 and the M6 consumer contract on `2026-08-13`. M6-P3-G0 is complete only as a
governance/architecture decision. The later explicit Owner decision authorized
M6-P3-B1, and the corrected B1-R1 checkpoint is Owner Accepted. M6-P3-G1 was later
separately authorized and is Owner Accepted only through G1-R1 at
`e172cc7c9bfca04066153d9edad70d9074bb37e5`. All work after G1 remains
`NOT AUTHORIZED / NOT STARTED` until its own explicit governance authorization.

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

The accepted M6-P3-G0 target defines a future internal, read-only, persistence-neutral
M6 Episode baseline consumer for M3 Script Studio. M4 owns trusted Project-to-Series
context; M2 owns Series/Episode identity and membership. The accepted records have no
shared stable key, so ADR-0005 requires a future immutable M5 EpisodePlanItemBinding
inside a new exact SeriesPlanVersion. M6 keeps its existing facts; M7 remains owner of
future consistency verdicts; M9 remains owner of future AssetRequirement and
asset-resolution readiness.

Number, title, array position and display name matching are forbidden. The future
sequence is two independent checkpoints: P3-B1 implemented the accepted target M5 v2
binding and is Owner Accepted through corrected B1-R1; separately authorized P3-G1
may implement the read-only M6/M3 consumer. The affected M2/M4/M5/M6 Domain
Owners accepted the bounded binding result. The separate G1 authorization was granted
on `2026-08-14` and remains gated by governance remote verification.

Initial plan creation stays v1. B1 allows v1→v1, explicit v1→v2 and v2→v2, forbids
v2→v1 and requires a new explicit v2 version for unbinding. The only new operation is
Core-only `create_episode_plan_item_binding_version`.

The G1 authorization record alone authorizes its bounded Core-only read slice. It does
not authorize M7-M19, formal database deployment, DDL/Migration, HTTP route/handler/
external DTO source-file changes, any HTTP contract expansion, Auth/RBAC or Frontend
implementation.

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
- EXECUTION MODE: `MANUAL / BOUNDED / FAIL-CLOSED`
- AUTHORIZED WAVE: `CAPTURE G2 GOVERNANCE CHECKPOINT → REMOTE VERIFY → ONE-WINDOW READ-ONLY COLLECTION → OFFLINE NORMALIZATION → STOP`
- CURRENT TASK: `ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2`
- G0 BASE: `c524486c05c21b270a7dd75e89fae4312430736a`
- ADR-0006 STATUS: `ACCEPTED FOR BOUNDED G1`
- V5 TEXT GENERATION CONTRACT: `ACCEPTED FOR BOUNDED G1`
- R-CORE-ARCH-001: `CONFIRMED / HIGH / MONITORING / G1-R1 OWNER ACCEPTED`
- R-CORE-GOV-002: `OPEN / NON-BLOCKING`
- G0 STATUS: `COMPLETE / REMOTE-VERIFIED AT 92d1f3ac9e08c71458af04514baa659555fc55a7`
- G1 STATUS: `REMOTE-VERIFIED CANDIDATE AT 0c283eb653e74784301620bdaf64bf451bb687dd / REVISION REQUIRED / NOT OWNER ACCEPTED / SUPERSEDED BY G1-R1`
- G1-R1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT d44f471c644e319bb4a5bf73707c3274ecbaa426`
- ACS-M6-P0-P1-R2: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860`
- R2-P1 STATUS: `ACCEPTED`
- R2-P2 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 0aa14b4e426a3d968ec314029d60a47ea30cbc4d`
- LEGACY REPOSITORY CAPABILITY PROVENANCE: `MEDIUM / OPEN / NON-BLOCKING`
- P3-RV1-003: `OWNER GATE / OPEN / NON-BLOCKING EOL AUDIT DEBT`
- RB1.3 CLOSEOUT: `FORMALLY CLOSED`
- ARCHITECTURE REVIEW: `SATISFIED FOR BOUNDED M6-P0/P1 AND M6-P2 LOCAL SQLITE ONLY`
- M6 PRECONDITIONS: `SATISFIED FOR BOUNDED M6-P0/P1 AND M6-P2 LOCAL SQLITE ONLY`
- M6: `P0-P2 OWNER ACCEPTED / P3-G0 OWNER ACCEPTED AS ARCHITECTURE / P3-B1 OWNER ACCEPTED THROUGH B1-R1 / P3-G1 OWNER ACCEPTED THROUGH G1-R1 / LATER M6 WORK NOT AUTHORIZED`
- M6-P0 STATUS: `CONTRACT ACCEPTED / COMPLETE`
- M6-P1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860`
- ADR-0004 STATUS: `ACCEPTED FOR BOUNDED M6-P2 IMPLEMENTATION`
- M6-P2-G0 STATUS: `CONTRACT ACCEPTED / COMPLETE`
- M6-P2-G1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 8227c6c616140824fd70de920dc6fcf459bb734d`
- M6-P2-G1-CLOSEOUT-G3 STATUS: `REMOTE-VERIFIED HISTORICAL PROPOSAL CHECKPOINT AT c524486c05c21b270a7dd75e89fae4312430736a / PRESERVED`
- M6-P3-G0 STATUS: `OWNER ACCEPTED / COMPLETE AS GOVERNANCE-ARCHITECTURE / NO IMPLEMENTATION AUTHORITY`
- ADR-0005 STATUS: `ACCEPTED AS ARCHITECTURE DECISION / B1 OWNER ACCEPTED THROUGH B1-R1 / G1 OWNER ACCEPTED THROUGH G1-R1`
- M6 CONSUMER CONTRACT: `ACCEPTED NORMATIVE ARCHITECTURE / B1 OWNER ACCEPTED THROUGH B1-R1 / G1 OWNER ACCEPTED THROUGH G1-R1`
- M6-P3-B1 EPISODE-PLAN-ITEM BINDING: `ORIGINAL CANDIDATE AT 8449b521c96bb8340806ecda8649698f4771914a REVISION REQUIRED / CORRECTED AND OWNER ACCEPTED THROUGH B1-R1 AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`
- M6-P3-B1 AUTHORIZED BASE: `6bb9d165a693057f38e5789c408293ff0eaf5bcc`
- M6-P3-B1 DOMAIN OWNERS: `M2 / M4 / M5 / M6 APPROVED`
- M6-P3-B1 FROZEN SCOPE: `8 GOVERNANCE / 6 PRODUCTION / 9 TEST PATHS`
- M6-P3-B1 VERSION POLICY: `INITIAL V1 / V1→V1 / EXPLICIT V1→V2 / V2→V2 / V2→V1 FORBIDDEN / UNBIND VIA NEW V2`
- M6-P3-B1 CORE OPERATION: `create_episode_plan_item_binding_version / NO ROUTE, HANDLER OR EXTERNAL DTO SOURCE CHANGE`
- M6-P3-B1 MANUAL V2 RULE: `create_manual_version REJECTS CURRENT V2 WITHOUT WRITE / DEDICATED METHOD ALONE CREATES V2→V2`
- M6-P3-B1 OWNER HTTP CLARIFICATION: `EXISTING CANONICAL V2 PROJECTION IN WORKSPACE VERSIONS PASSES THROUGH episodePlanItemBindings / MANUAL + BOOTSTRAP V1 BEHAVIOR UNCHANGED / NO OTHER HTTP CONTRACT EXPANSION`
- M6-P3-B1-F001: `CLOSED BY OWNER-ACCEPTED B1-R1 / SQLITE SAME-PROJECT CROSS-SERIES FALSE DEPENDENCY`
- M6-P3-B1-R1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`
- M6-P3-B1-R1 AUTHORIZED BASE: `8449b521c96bb8340806ecda8649698f4771914a`
- M6-P3-B1-R1 SCOPE: `8 GOVERNANCE → 1 PRODUCTION + 1 TEST → REMOTE VERIFY → STOP FOR OWNER REVIEW`
- M6-P3-B1-R1 EVIDENCE: `PRE-FIX SQLITE 409 REPRODUCED / POST-FIX SQLITE MODULE 30/30 / ORIGINAL B1 174/174 / FULL CORE 449/449 / NON-TEST PYTHON AST 63/63`
- M6-P3-G1 ORIGINAL STATUS: `REMOTE-VERIFIED AT 3696d6af12222d30eb99b65d67e6db18897eb42f / G1 14/14 / FULL CORE 463/463 / REVISION REQUIRED / NOT OWNER ACCEPTED / SUPERSEDED`
- M6-P3-G1-R1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e172cc7c9bfca04066153d9edad70d9074bb37e5 / TREE be7447c3d60510262e428b86cd1a6a83972f64c0 / FULL CORE 464/464`
- CORE MAIN CONVERGENCE: `OWNER ACCEPTED / PR #2 REBASE AND MERGE / MAIN 5976263f92f7f9cbe9c091719eccb036ee8c0c2d / SAME TREE / POST-MERGE CI PASS`
- ACS-GOV-POST-M6-P3-G1-CLOSEOUT: `OWNER ACCEPTED AT 20207e7f2d2123468698f453c70ce725a293976a / TREE e3638838dd0c79201a1962bb247ec7c773b62ffa`
- ACS-CCV-R1-EVIDENCE-HARDENING: `REMOTE CANDIDATE 57cbbd49 / REVISION REQUIRED / NOT OWNER ACCEPTED`
- ACS-CCV-R1-R1-EVIDENCE-VALIDATOR-HARDENING: `OWNER ACCEPTED THROUGH 0c2552bf49923d45c2c5542cdb39f512a7e7d15d / TREE 8ee5c3ba7ef214bfa3e56ca97cee0b73a3666bb4 / FULL CORE 464/464`
- CCV-R1 MAIN CONVERGENCE: `PR #4 REBASE AND MERGE / MAIN 9c13e8f8d7ccef079dd382fe11b1d173fdef13d7 / SAME TREE / LOCAL 464/464 / POST-MERGE CI PASS`
- ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G0: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 9094a46615f2be9ca45f95418ac441326d326315 / TREE d372581f0f0f434e10df78542ef4ac9bbefbfb51 / PR #5 DRAFT / CI PASS`
- ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G1: `REMOTE-VERIFIED CHECKPOINT AT af34ac074cb8bfbf334e4f56aad0c0d479b741be / TREE 0cec29c8de8777c5c3dbb824b2a7f421d9cb9c36 / PR #6 DRAFT / CI PASS / FULL CORE 464/464`
- ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2: `AUTHORIZED / ONE-WINDOW READ-ONLY EXTERNAL HISTORICAL EVIDENCE COLLECTION / NO RERUN`
- CCV-R2 / CHARACTER VISUAL IDENTITY SCHEMA WORK: `NOT AUTHORIZED / NOT STARTED`
- M6-P3 AFTER G1 / M6-P4+ STATUS: `NOT AUTHORIZED / NOT STARTED`
- M7-M19: `NOT STARTED / NOT AUTHORIZED`
- FORMAL 8765 DEPLOYMENT: `UNTOUCHED / NOT DEPLOYED`
- FRONTEND: `FROZEN / UNTOUCHED`
- PRODUCTION READY: `NO`
- PRODUCTION CODE CHANGED BY G1-R1: `NO`
- TEST CODE CHANGED BY G1-R1: `ONE AUTHORIZED CONTRACT TEST FILE`
- G1-R1 ACCEPTED EVIDENCE: `TARGETED 124/124 / FULL CORE 404/404 — UNIT 226 /
  CONTRACT 81 / INTEGRATION 97 / M6-P2 STRICT 52/52 / LIFECYCLE 31/31 /
  PYTHON AST 63/63 / APPLICATION V4 IMPORTS 0 / LOCAL=REMOTE / OWNER ACCEPTED`.

The Project Lead acceptance of bounded M6-P2-G1 at
`8227c6c616140824fd70de920dc6fcf459bb734d` remains unchanged. The later c524
G3/P3-G0 proposal and dec102 review-open checkpoint remain preserved historical
evidence. ADR-0005 and the M6 Consumer Contract are now accepted as architecture only,
and that G0 acceptance remains immutable timepoint evidence. The Project Lead selected
and accepted ADR-0006 and later accepted corrected G1-R1 at
`d44f471c644e319bb4a5bf73707c3274ecbaa426`. This closes the architecture-remediation
wave but does not establish Production Ready or authorize formal database deployment,
Frontend, later M6 work or M7-M19. B1 is accepted only through the explicit B1-R1
correction and did not itself create G1 implementation authority; G1 was later
separately authorized and accepted through G1-R1.

---

# 9. Stop Rule

The current checkpoint changes only the G2 governance allowlist in
[`ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2.md`](governance/ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2.md).
Product and existing test-tree diff must remain zero. After source-read-only capture,
two-inventory agreement and offline fail-closed normalization:

```text
ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2 CHECKPOINT CANDIDATE
EXTERNAL EVIDENCE COLLECTED OR EXPLICITLY MARKED UNAVAILABLE
INDEPENDENT REVIEW REQUIRED
DO NOT ENTER CCV-R2 OR PRODUCT SCHEMA WORK
```

Stop before any production/test change, M6 schema change, DDL/Migration,
route/handler/external DTO change, Script write, later M6, M7-M19, formal database,
Auth/RBAC, Frontend, Worker, ComfyUI execution or evidence regeneration.

---

# 10. Current Authorized Task

`ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2`

Status:

`ONE-WINDOW READ-ONLY EXTERNAL EVIDENCE COLLECTION / PRODUCT AND TEST TREE DIFF ZERO / NO RERUN`

Accepted technical evidence:

```text
ORIGINAL M6-P3-G1: 3696d6af12222d30eb99b65d67e6db18897eb42f
STATUS: REVISION REQUIRED / NOT OWNER ACCEPTED / SUPERSEDED

M6-P3-G1-R1: e172cc7c9bfca04066153d9edad70d9074bb37e5
TREE: be7447c3d60510262e428b86cd1a6a83972f64c0
STATUS: OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED / FULL CORE 464/464

CCV-R1 OWNER ACCEPTED: 0c2552bf49923d45c2c5542cdb39f512a7e7d15d
TREE: 8ee5c3ba7ef214bfa3e56ca97cee0b73a3666bb4

CURRENT CORE MAIN: 9c13e8f8d7ccef079dd382fe11b1d173fdef13d7
TREE: 8ee5c3ba7ef214bfa3e56ca97cee0b73a3666bb4
STATUS: PR #4 REBASE AND MERGE / FULL CORE 464/464 / POST-MERGE CI PASS
```

The accepted parent checkpoint is `ACS-GOV-POST-M6-P3-G1-CLOSEOUT` at `20207e7f`.
The current report remains `EXPERIMENT REPORTED / INDEPENDENT REPRODUCTION NOT
POSSIBLE`. CCV-R2 and any Identity/Asset/M6/M8/M10 schema or production work remain
unauthorized.

Formal port-8765 deployment, later M6 work, M7-M19, Schema/Migration, Frontend,
production GPU/Worker/ComfyUI integration and Production Ready remain unauthorized.

# End of CURRENT_MILESTONE.md
