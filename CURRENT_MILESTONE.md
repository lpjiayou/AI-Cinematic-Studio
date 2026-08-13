# AI Cinematic Studio — Current Execution State

> Document: `CURRENT_MILESTONE.md`
>
> Execution Mode: `AUTO-SEQUENTIAL / BOUNDED / FAIL-CLOSED`
>
> Project Lead Authorization: `M6-P3-B1-R1 SQLITE SERIES ISOLATION CORRECTION AUTHORIZED BY PROJECT LEAD / ARCHITECTURE / REPOSITORY GOVERNANCE / M2-M5 DOMAIN OWNERS ON 2026-08-13`
>
> Authorized Wave: `B1-R1 EIGHT-PATH GOVERNANCE CHECKPOINT → REMOTE VERIFY → ONE PRODUCTION + ONE TEST CORRECTION → REMOTE VERIFY → STOP FOR B1-R1 OWNER REVIEW`
>
> Current Task: `ACS-M6-P3-B1-R1-SQLITE-SERIES-ISOLATION`
>
> Current Work Package: `TECHNICAL CORRECTION CANDIDATE → REMOTE VERIFY → OWNER REVIEW`
>
> M6 Authorization: `P0-P2 OWNER ACCEPTED / P3-G0 OWNER ACCEPTED AS ARCHITECTURE / P3-B1 CANDIDATE REVISION REQUIRED / P3-B1-R1 BOUNDED CORRECTION AUTHORIZED / P3-G1 NOT AUTHORIZED`
>
> M7 Authorization: `NOT AUTHORIZED`
>
> Frontend Governance Authorization: `FE-G0-R1 GOVERNANCE-ONLY REV.3 CORRECTION AUTHORIZED ON 2026-08-14 / FRONTEND BASE 1cf2515 / CHECKPOINT CANDIDATE / CODE IMPLEMENTATION NOT AUTHORIZED`
>
> Frontend Implementation Authorization: `FE-G1 / FE-G2 / FE-G3 / EXPERIENCE ADAPTER / API INTEGRATION / M6 BINDING / GATE C NOT AUTHORIZED`
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

`M6-P3-B1-R1 SQLite Same-Project Cross-Series Isolation`

Title:

ACS-M6-P3-B1-R1 SQLite Series Isolation Correction

Status:

`B1 CANDIDATE 8449b521c96bb8340806ecda8649698f4771914a REVISION REQUIRED / B1-R1 GOVERNANCE REMOTE-VERIFIED AT 716b4d298173f8123cafd93114dfc67339943ff3 / TECHNICAL CORRECTION CANDIDATE / GATES PASS / G1 NOT AUTHORIZED`

Purpose:

1. preserve the remote B1 candidate at
   `8449b521c96bb8340806ecda8649698f4771914a` as immutable evidence;
2. record B1 Owner Review as `REVISION REQUIRED / NOT OWNER ACCEPTED` because SQLite
   falsely treats a legitimate same-Project other-Series plan as an Episode binding
   dependency;
3. establish and remote-verify the same exact eight-path governance authorization
   checkpoint before any production or test edit;
4. modify only `services/v5_core_os/series_planning/foundation.py` so exact/suspicious
   target-Series history remains fail-closed while legitimate other-Series history is
   isolated;
5. modify only `tests/integration/test_creator_lifecycle_sqlite_p2.py` to freeze the
   same-Workspace, same-Project, other-Series SQLite regression;
6. preserve all B1 v1/v2, historical binding, lifecycle precedence, HTTP projection,
   digest, SQLite `content_json` and no-DDL semantics;
7. test, commit, non-force push, remote-verify and stop for B1-R1 Owner Review.

The exact selection semantics and allowlists are frozen by sections 10–15 of the B1
authorization record. Implementation may not select a looser interpretation.

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

On `2026-08-13`, the Project Lead authorized FE-G0 as a governance-only limited
unfreeze in `AI-Cinematic-Studio-Frontend`, with sole application-code baseline
`codex/frontend-character-studio-v1` at
`1cf2515ceec6c6415cae2e21360782174525d3a5`. The resulting Frontend checkpoint
`df3ccf098d1b2eeaef2a21a1a397ea7fb24adceb` and Core synchronization checkpoint
`61a94cd41e56d651d057c5f9529aef6adf5ede85` passed Git scope and remote-evidence
review, but Rev. 2 failed Owner Review because it conflated New Project with the
Global Creative Sandbox and removed page-owned headers before the pages entered the
Creator layout. Those commits remain immutable historical evidence with disposition
`REVISION REQUIRED / NOT OWNER ACCEPTED`.

On `2026-08-14`, the Project Lead authorized only FE-G0-R1 governance correction:
Rev. 3, the FE-G0-R1 record, the Frontend/Core Domain Alignment standard and this
synchronized Core status. Rev. 3 directs the current `/create` New Project page to
`/creator/projects/new`, keeps `/creator/create` unavailable for the separate Global
Creative Sandbox, leaves existing headers untouched in additive FE-G1, and moves
header removal into FE-G2 after route relocation. The sole application-code baseline
remains `1cf2515`; the stale GitHub default branch remains prohibited as a development
base. FE-G1, FE-G2, FE-G3, Experience Adapter, Creator Public HTTP/API integration,
M6 data binding, real Project/Series/Episode state and Cross-Repo Gate C remain
unauthorized. Script Studio remains unmigrated and no Ref may be fabricated.

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
unauthorized. At that historical closeout point, the Frontend was frozen and
untouched. Its current governance-only FE-G0-R1 Rev. 3 correction state is recorded
in sections 2 and 8; Frontend implementation remains frozen. `P3-RV1-003` remains open
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
ACCEPTED`. The only current authorized transition is:

```text
B1-R1 GOVERNANCE AUTHORIZATION CHECKPOINT
→ COMMIT / NON-FORCE PUSH / REMOTE VERIFY
→ ONE PRODUCTION + ONE TEST SQLITE ISOLATION CORRECTION
→ COMMIT / NON-FORCE PUSH / REMOTE VERIFY
→ STOP FOR PROJECT LEAD B1-R1 OWNER REVIEW
```

No G1 or later milestone may be silently entered.

---

# 7. Authorized M6-P3-B1 Binding Prerequisite

M6-P0/P1 and M6-P2-G1 are `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`.
The Project Lead and Architecture Owner accepted the G3/P3-G0 target architecture,
ADR-0005 and the M6 consumer contract on `2026-08-13`. M6-P3-G0 is complete only as a
governance/architecture decision. The later explicit Owner decision authorizes only
M6-P3-B1 after its governance checkpoint is remote-verified. M6-P3-G1 and all later
M6 work remain `NOT AUTHORIZED / NOT STARTED`.

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
sequence is two independent checkpoints: first P3-B1 implements the accepted target
M5 v2 binding, then a future separately authorized P3-G1 may implement the read-only
M6/M3 consumer. The affected M2/M4/M5/M6 Domain Owners approve B1. P3-B1 is now
authorized within exactly six production, nine test and eight governance paths; it
must be tested, pushed, remote-verified and Owner Accepted before P3-G1 can be
authorized.

Initial plan creation stays v1. B1 allows v1→v1, explicit v1→v2 and v2→v2, forbids
v2→v1 and requires a new explicit v2 version for unbinding. The only new operation is
Core-only `create_episode_plan_item_binding_version`.

This document does not authorize M6-P3-G1, M7-M19, formal database deployment,
DDL/Migration, HTTP route/handler/external DTO source-file changes, any HTTP contract
expansion beyond the approved existing workspace versions v2 field pass-through,
Auth/RBAC or Frontend implementation.

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
- EXECUTION MODE: `AUTO-SEQUENTIAL / BOUNDED / FAIL-CLOSED`
- AUTHORIZED WAVE: `B1-R1 GOVERNANCE CHECKPOINT → REMOTE VERIFY → ONE PRODUCTION + ONE TEST CORRECTION → REMOTE VERIFY → STOP FOR OWNER REVIEW`
- CURRENT TASK: `ACS-M6-P3-B1-R1-SQLITE-SERIES-ISOLATION`
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
- M6: `P0-P2 OWNER ACCEPTED / P3-G0 OWNER ACCEPTED AS ARCHITECTURE / P3-B1 REVISION REQUIRED / P3-B1-R1 BOUNDED CORRECTION AUTHORIZED / P3-G1 AND LATER M6 WORK NOT AUTHORIZED`
- M6-P0 STATUS: `CONTRACT ACCEPTED / COMPLETE`
- M6-P1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860`
- ADR-0004 STATUS: `ACCEPTED FOR BOUNDED M6-P2 IMPLEMENTATION`
- M6-P2-G0 STATUS: `CONTRACT ACCEPTED / COMPLETE`
- M6-P2-G1 STATUS: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 8227c6c616140824fd70de920dc6fcf459bb734d`
- M6-P2-G1-CLOSEOUT-G3 STATUS: `REMOTE-VERIFIED HISTORICAL PROPOSAL CHECKPOINT AT c524486c05c21b270a7dd75e89fae4312430736a / PRESERVED`
- M6-P3-G0 STATUS: `OWNER ACCEPTED / COMPLETE AS GOVERNANCE-ARCHITECTURE / NO IMPLEMENTATION AUTHORITY`
- ADR-0005 STATUS: `ACCEPTED AS ARCHITECTURE DECISION / B1 BOUNDED IMPLEMENTATION AUTHORIZED / G1 UNAUTHORIZED`
- M6 CONSUMER CONTRACT: `ACCEPTED NORMATIVE ARCHITECTURE / B1 BOUNDED IMPLEMENTATION AUTHORIZED / CONSUMER UNIMPLEMENTED`
- M6-P3-B1 EPISODE-PLAN-ITEM BINDING: `REMOTE-VERIFIED CANDIDATE AT 8449b521c96bb8340806ecda8649698f4771914a / OWNER REVIEW REVISION REQUIRED / NOT OWNER ACCEPTED / BLOCKS M6-P3-G1`
- M6-P3-B1 AUTHORIZED BASE: `6bb9d165a693057f38e5789c408293ff0eaf5bcc`
- M6-P3-B1 DOMAIN OWNERS: `M2 / M4 / M5 / M6 APPROVED`
- M6-P3-B1 FROZEN SCOPE: `8 GOVERNANCE / 6 PRODUCTION / 9 TEST PATHS`
- M6-P3-B1 VERSION POLICY: `INITIAL V1 / V1→V1 / EXPLICIT V1→V2 / V2→V2 / V2→V1 FORBIDDEN / UNBIND VIA NEW V2`
- M6-P3-B1 CORE OPERATION: `create_episode_plan_item_binding_version / NO ROUTE, HANDLER OR EXTERNAL DTO SOURCE CHANGE`
- M6-P3-B1 MANUAL V2 RULE: `create_manual_version REJECTS CURRENT V2 WITHOUT WRITE / DEDICATED METHOD ALONE CREATES V2→V2`
- M6-P3-B1 OWNER HTTP CLARIFICATION: `EXISTING CANONICAL V2 PROJECTION IN WORKSPACE VERSIONS PASSES THROUGH episodePlanItemBindings / MANUAL + BOOTSTRAP V1 BEHAVIOR UNCHANGED / NO OTHER HTTP CONTRACT EXPANSION`
- M6-P3-B1-F001: `CONFIRMED / BLOCKING / SQLITE SAME-PROJECT CROSS-SERIES FALSE DEPENDENCY`
- M6-P3-B1-R1 STATUS: `GOVERNANCE REMOTE-VERIFIED AT 716b4d298173f8123cafd93114dfc67339943ff3 / TECHNICAL CORRECTION CANDIDATE / GATES PASS`
- M6-P3-B1-R1 AUTHORIZED BASE: `8449b521c96bb8340806ecda8649698f4771914a`
- M6-P3-B1-R1 SCOPE: `8 GOVERNANCE → 1 PRODUCTION + 1 TEST → REMOTE VERIFY → STOP FOR OWNER REVIEW`
- M6-P3-B1-R1 EVIDENCE: `PRE-FIX SQLITE 409 REPRODUCED / POST-FIX SQLITE MODULE 30/30 / ORIGINAL B1 174/174 / FULL CORE 449/449 / NON-TEST PYTHON AST 63/63`
- M6-P3-G1 STATUS: `SEQUENCE DEFINED / BLOCKED UNTIL B1 OWNER ACCEPTED / NOT AUTHORIZED / NOT STARTED`
- M6-P3 AFTER G1 / M6-P4+ STATUS: `NOT AUTHORIZED / NOT STARTED`
- M7-M19: `NOT STARTED / NOT AUTHORIZED`
- FORMAL 8765 DEPLOYMENT: `UNTOUCHED / NOT DEPLOYED`
- FRONTEND: `FE-G0-R1 GOVERNANCE-ONLY REV.3 CORRECTION AUTHORIZED / BASE 1cf2515 / REV.2 HISTORICAL REVISION REQUIRED / REV.3 + DOMAIN ALIGNMENT + CORRECTED FE-G1-FE-G2 ALLOWLISTS CHECKPOINT CANDIDATE / FE-G1-FE-G3 IMPLEMENTATION FROZEN / OWNER REVIEW REQUIRED`
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
Frontend, M6-P3-G1, later M6 work or M7-M19. B1 authority is limited to the explicit
record and takes effect for technical edits only after governance remote verification.

---

# 9. Stop Rule

B1 is remote-verified at `8449b521c96bb8340806ecda8649698f4771914a` but is
`REVISION REQUIRED / NOT OWNER ACCEPTED`. The B1-R1 exact eight-path governance
checkpoint was committed and remote-verified at
`716b4d298173f8123cafd93114dfc67339943ff3` with production and test diff zero.

The B1-R1 correction now passes its frozen one production, one test and eight governance
path scope, the updated SQLite lifecycle module `30/30`, all original B1 tests
`174/174`, complete Core regression `449/449` and non-test Python AST `63/63`. It must
still pass the final Markdown/local-link, secret and `git diff --check` gates, one
technical commit, non-force remote publication, Local SHA equals Remote SHA,
ahead/behind `0/0` and clean worktree.

After the correction candidate is remote-verified:

```text
STOP — M6-P3-B1-R1 REMOTE-VERIFIED CORRECTION CANDIDATE
PROJECT LEAD B1-R1 OWNER REVIEW REQUIRED
M6-P3-G1 NOT AUTHORIZED / NOT STARTED
NEXT AUTHORIZED MILESTONE: NONE
```

Stop before any need to exceed the frozen one production, one test and eight
governance paths, change InMemory production behavior, or add DDL/Migration,
route/handler/external DTO source-file changes, M3/M6 consumer, M6-P3-G1, M7-M19,
formal database deployment, Auth/RBAC expansion or Frontend implementation beyond
the separately authorized FE-G0-R1 governance-only documents and milestone-state sync.

---

# 10. Current Authorized Task

`ACS-M6-P3-B1-R1-SQLITE-SERIES-ISOLATION`

Status:

`B1 CANDIDATE REVISION REQUIRED / B1-R1 GOVERNANCE REMOTE-VERIFIED AT 716b4d298173f8123cafd93114dfc67339943ff3 / TECHNICAL CORRECTION CANDIDATE / GATES PASS`

M6-P0/P1 and bounded M6-P2-G1 remain Owner Accepted at their remote-verified technical
baselines. G1-R1 is Owner Accepted and complete at
`d44f471c644e319bb4a5bf73707c3274ecbaa426`. The original G1 remains historical
`REVISION REQUIRED / NOT OWNER ACCEPTED / SUPERSEDED BY G1-R1`.

ADR-0006 accepts the single production path:

```text
Creator Application
→ V5 Text Generation Capability
→ V4 TextGenerationPort
→ Provider Adapter
```

The Project Lead, Architecture Owner, Repository Governance Owner and affected M2/M5
Domain Owners authorized the exact B1-R1 auto-sequential correction recorded in
[`ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md`](governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md):
the eight-path governance checkpoint is remote-verified at
`716b4d298173f8123cafd93114dfc67339943ff3`; the one-production/one-test correction
passes its test gates. After technical commit and remote verification, STOP for B1-R1
Owner Review.

Formal port-8765 database access/deployment, HTTP route/handler/external DTO
source-file changes, HTTP expansion beyond the Owner-approved existing workspace
versions v2 field pass-through, Auth/RBAC, Frontend implementation beyond FE-G0-R1
governance, Schema/Migration, M3/M6 consumer, P3-G1 and later M6 work, M7-M19, V3,
GPU, Worker and ComfyUI remain unauthorized and not started. B1-R1 changes no
existing Domain ownership or Production Spine.

# End of CURRENT_MILESTONE.md
