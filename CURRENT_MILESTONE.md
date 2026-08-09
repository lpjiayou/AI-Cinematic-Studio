# AI Cinematic Studio — Current Execution State

## Control Status

Document Role:

`CURRENT EXECUTION STATE ONLY`

This file does not redefine the System Master Plan, UI Master Plan, architecture, Domain ownership, or long-term milestone roadmap.

Project Lead acceptance and transition authority remain required.

---

## Current Execution Task

Task:

`Canonical Workspace Promotion`

Promotion Status:

`IN PROGRESS / SOURCE-OF-TRUTH RECONCILIATION`

Task Nature:

`CONTROL DOCUMENT RECONCILIATION + CANONICAL WORKSPACE PROMOTION`

This task is not a product milestone.

---

## Accepted UI Baseline

UI-R1:

`FEATURE ACCEPTED`

UI-R1 Accepted Branch:

`codex/creator-ui-enterprise-rebaseline-v3`

UI-R1 Accepted SHA:

`c9536fc0c745d0bf9e9c3eb543f4ab6c0566798a`

Accepted runtime rule:

`ONE CREATOR UI / CREATOR SERVER HTTP RUNTIME`

Canonical promotion candidate SHA:

`PENDING DOCS-ONLY RECONCILIATION COMMIT AND REMOTE VERIFICATION`

---

## Accepted Capability Baseline

M1 AI Director:

`ACCEPTED`

M2 Series + Episode:

`ACCEPTED`

M3 Script Studio:

`ACCEPTED`

M3-H Script Candidate Robustness Hotfix:

`ACCEPTED`

Story Projection Integration:

`ACCEPTED`

The current control-document task must preserve these accepted capabilities and their production lineage.

---

## Milestone Execution State

M4:

`PAUSED / NOT STARTED`

M5:

`NOT STARTED`

Execution Wave M4 → M5:

`PLANNED`

Execution Authorization:

`NOT YET AUTHORIZED TO EXECUTE`

M4 is not CURRENT.

M5 is not QUEUED or AUTO-NEXT.

No product milestone may start during Canonical Workspace Promotion.

---

## Current Allowed Scope

Until the Source-of-Truth reconciliation checkpoint is committed and remote verified, changes are limited to:

- `AGENTS.md`;
- `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`;
- `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`;
- `CURRENT_MILESTONE.md`.

After the remote-verified documentation checkpoint, only the explicitly authorized preservation, worktree retirement, canonical branch promotion, and runtime verification steps may proceed.

---

## Current Prohibited Scope

Do not:

- enter M4;
- enter M5;
- modify accepted M1 / M2 / M3 capability code;
- modify V5 / V4 / V3 architecture or ownership;
- rewrite accepted UI-R1 application code;
- create a second Creator UI;
- create a new normal-development worktree;
- treat `file://` as final UI evidence;
- delete preserved user content;
- use `git reset --hard` or `git clean`.

---

## Promotion Completion Gate

Canonical Workspace Promotion may be reported PASS only after:

1. the four control documents are reconciled;
2. semantic-loss review reports `LOST = NONE` except explicit Project Lead supersession;
3. the docs-only commit is pushed and local SHA equals remote SHA;
4. preservation is re-verified;
5. the original workspace is cleaned without data loss;
6. the accepted UI-R1 branch is promoted into the canonical workspace;
7. all four control documents are tracked in the canonical workspace;
8. the Creator Server runs from the canonical workspace over HTTP;
9. Dashboard, AI Director, Projects, Story, and Script smoke checks pass;
10. the canonical worktree is clean.

Even after promotion PASS:

- M4 remains `PAUSED / NOT STARTED`;
- M5 remains `NOT STARTED`;
- Execution Wave M4 → M5 remains `PLANNED`;
- Project Lead authorization is required before any milestone transition.

---

## Stop Rule

STOP if:

- control documents still conflict;
- semantic content would be lost without explicit supersession;
- docs push or remote SHA verification fails;
- preservation verification fails;
- unique uncommitted or ignored runtime data cannot be protected;
- canonical branch promotion is not clean and reversible;
- the runtime is not served from the canonical workspace;
- any step would enter M4 or M5.

Do not resolve these blockers by silently changing architecture, product scope, or Git history.
