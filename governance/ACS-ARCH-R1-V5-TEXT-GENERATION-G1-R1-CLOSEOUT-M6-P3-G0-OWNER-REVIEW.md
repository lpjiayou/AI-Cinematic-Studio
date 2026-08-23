# ACS-ARCH-R1 G1-R1 Closeout / M6-P3-G0 Owner Review Start

> Status: `GOVERNANCE-ONLY CLOSEOUT / G1-R1 OWNER ACCEPTED / M6-P3-G0 OWNER REVIEW OPENED`
>
> Decision date: `2026-08-13`
>
> Project Lead / Architecture Owner / Repository Governance Owner: `蔺鹏`
>
> Owner-accepted technical checkpoint: `d44f471c644e319bb4a5bf73707c3274ecbaa426`
>
> Review input checkpoint: `c524486c05c21b270a7dd75e89fae4312430736a`

## 1. Decision

The Project Lead accepts the corrected G1-R1 technical checkpoint at
`d44f471c644e319bb4a5bf73707c3274ecbaa426` and authorizes this governance-only
closeout. The accepted result preserves the production migration completed by the
original G1 while replacing its defective continuing guard with the alias-aware guard
verified in G1-R1.

This decision records:

- G1-R1 is `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`;
- the Architecture Remediation R1 wave is closed at the accepted G1-R1 checkpoint;
- the original G1 checkpoint `0c283eb653e74784301620bdaf64bf451bb687dd`
  remains historical `REVISION REQUIRED / NOT OWNER ACCEPTED` and is superseded by
  G1-R1;
- ADR-0006 and the accepted `Application → V5 → V4` direction remain unchanged;
- `R-CORE-ARCH-001` moves from `MITIGATING` to `MONITORING`, not `CLOSED`;
- the Project Lead opens a read-only Owner Review of the existing M6-P3-G0 proposal,
  ADR-0005 and the M6 consumer contract;
- this checkpoint does not accept ADR-0005 or the consumer contract and does not
  authorize M6-P3-B1, M6-P3-G1 or any implementation.

## 2. Accepted G1-R1 evidence

The accepted technical checkpoint has the following reviewed evidence:

| Gate | Result |
| --- | --- |
| Targeted V5/Application regression | `124/124 PASS` |
| Full Core discovery | `404/404 PASS` |
| Unit / Contract / Integration | `226 / 81 / 97 PASS` |
| M6-P2 strict regression | `52/52 PASS` |
| Deletion/lifecycle regression | `31/31 PASS` |
| Non-test Python AST parse | `63/63 PASS` |
| Application static/programmatic V4 access | `0` |
| V5 text-generation V4 importer | `public.py` only |
| Independent final reviews | `PASS / no remaining contract blocker` |
| Production diff in G1-R1 | `0` |
| Remote verification | Local SHA = Remote SHA; ahead/behind `0/0`; clean |

The accepted guard covers the bounded Python programmatic-import forms defined by the
G1-R1 authorization. It remains a lightweight architecture gate rather than a Python
sandbox. That documented limitation is residual monitored risk, not permission to
weaken the guard.

## 3. Governance-only closeout scope

This checkpoint may change exactly these seven paths:

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
governance/RISK_REGISTER.md
governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-CLOSEOUT-M6-P3-G0-OWNER-REVIEW.md
```

Production and test diffs must be zero. The historical G0, original G1, G1-R1
authorization and M6-P3-G0 proposal records must not be rewritten.

## 4. M6-P3-G0 Owner Review scope

The read-only review evaluates the existing remote-verified proposal at
`c524486c05c21b270a7dd75e89fae4312430736a`, specifically:

- `governance/ADR-0005-m6-series-intelligence-consumer-boundary.md`;
- `architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md`;
- current M2/M3/M4/M5/M6 ownership and implementation facts needed to judge the
  proposal's feasibility and safety.

The review must decide whether the proposed boundary is acceptable, requires
revision or must be rejected. It must test at least:

1. exact Scope, identity, Ref/Digest and lineage ownership;
2. absence of number, title, list-position or display-name inference;
3. M5 v1 historical compatibility and proposed v2 immutability;
4. InMemory/SQLite feasibility without schema or migration authority;
5. Episode deletion dependency, atomicity, concurrency and rollback safety;
6. B1-before-G1 sequencing and M7/M9 ownership exclusions;
7. no accidental HTTP, Frontend, event-consumer or Production Ready expansion.

Review activity is read-only. ADR-0005 and the consumer contract remain
`PROPOSED / UNDER OWNER REVIEW / NO IMPLEMENTATION AUTHORITY` until the Project Lead
issues a separate decision.

## 5. Preserved implementation hold

The following remain `NOT AUTHORIZED / NOT STARTED`:

- M6-P3-B1 EpisodePlanItemBinding implementation;
- M6-P3-G1 and all M6-P3-G1+ work;
- M7-M19;
- Schema/Migration or formal port-8765 database work;
- HTTP/Public API/Auth/RBAC expansion;
- Frontend activation;
- V3, GPU, Worker or ComfyUI work.

Production Ready remains `NO`. `R-CORE-GOV-002` and `P3-RV1-003` remain open and
non-blocking; this closeout does not change their evidence meaning.

## 6. Verification and stop rule

This governance checkpoint must pass exact seven-path scope, production/test diff
zero, Markdown structure, local links, secret scan, `git diff --check`, one commit,
non-force push, fetch, Local SHA equals Remote SHA, ahead/behind `0/0` and clean
worktree.

After remote verification, only the authorized read-only M6-P3-G0 Owner Review may
continue. No implementation may begin. After the review result is reported:

```text
STOP — M6-P3-G0 OWNER DECISION REQUIRED
M6-P3-B1 REMAINS NOT AUTHORIZED
```

## 7. Approval record

| Role | Owner | Decision | Date | Scope |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `OWNER ACCEPTED` | `2026-08-13` | G1-R1 at `d44f471…` |
| Architecture Owner | `蔺鹏` | `APPROVED` | `2026-08-13` | Close Architecture Remediation R1 at corrected boundary |
| Repository Governance Owner | `蔺鹏` | `AUTHORIZED` | `2026-08-13` | Seven-path governance closeout checkpoint |
| Project Lead | `蔺鹏` | `REVIEW AUTHORIZED` | `2026-08-13` | Begin read-only M6-P3-G0 Owner Review; no B1 implementation |
