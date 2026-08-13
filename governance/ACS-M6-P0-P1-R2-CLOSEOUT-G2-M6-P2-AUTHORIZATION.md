# ACS-M6-P0/P1 R2 Closeout G2 and Bounded M6-P2 Authorization

> Status: `ACCEPTED GOVERNANCE AND ARCHITECTURE RECORD`
>
> Decision Date: `2026-08-13`
>
> Accepted Technical Baseline: `e38c75aa4ff26bdea80c82d8a24096f799dad860`
>
> Decision Authority: Project Lead / Architecture Owner / Repository Governance Owner `蔺鹏`

## Decision

The Project Lead accepts `ACS-M6-P0-P1-R2` at the technical baseline above as:

`OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`.

This closes the bounded M6-P0/P1 wave:

- M6-P0: `CONTRACT ACCEPTED / COMPLETE`;
- M6-P1: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`;
- M6-P0/P1 full Core regression: `332/332 PASS`;
- M6 targeted tests: `44/44 PASS`;
- R2 lifecycle regression: `30/30 PASS`;
- Python AST: `54/54 PASS`;
- Markdown structure: `74/74 PASS`;
- local documentation links: `310/310 PASS`;
- secret scan and `git diff --check`: `PASS`;
- SQLite schema/migration change in P0/P1: `NONE`;
- Formal 8765 database: `UNTOUCHED / NOT DEPLOYED`;
- Frontend: `FROZEN / UNTOUCHED`;
- Production Ready: `NO`.

The accepted implementation remains the exact M6 Series Intelligence InMemory slice
defined by ADR-0003. This record does not reinterpret P0/P1 as a durable or production
database implementation.

## G2 Validation

This checkpoint changes exactly nine governance, architecture and repository-orientation
Markdown files. Production code, tests, SQLite schema/migration, formal database and
Frontend diffs are zero.

- full Core regression re-run: `332/332 PASS`;
- Python AST: `54/54 PASS`;
- current tracked Markdown structure: `77/77 PASS`;
- current tracked local documentation links: `297/297 PASS`;
- secret scan and `git diff --check`: `PASS`.

## Standing Bounded Automation Instruction

The Project Lead instruction `以后始终授权无需再问` is recorded as standing
operational authority to implement, test, commit, push and remote-verify without
repeated conversational approval only inside a work package or AUTO-SEQUENTIAL wave
explicitly listed in `CURRENT_MILESTONE.md`.

It does not waive or override:

- Source-of-Truth hierarchy;
- final Project Lead acceptance authority;
- destructive migration approval;
- rights, security, credential and data-loss gates;
- Production Spine or domain ownership;
- Stop Conditions;
- the requirement to define each future milestone and execution wave explicitly.

## Accepted M6-P2 Architecture Decision

ADR-0004 is accepted for one bounded M6-P2 implementation:

`M6 SERIES INTELLIGENCE DURABLE SQLITE SLICE`.

M6-P2 is limited to:

- local-development SQLite persistence for the accepted M6 domain;
- atomic fresh/upgrade/idempotent migration on temporary SQLite files;
- complete M6 Scope keys and composite integrity constraints;
- M5 confirmed source re-read within the shared SQLite transaction;
- durable idempotency operation records;
- durable ordered Outbox records;
- deletion/lifecycle integrity and stable domain-error mapping;
- restart, rollback, commit-uncertainty and cross-connection validation.

The normative contract is
[`M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md`](../architecture/M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md).

## Authorized Automatic Execution Wave

Execution Mode is `AUTO-SEQUENTIAL` only for:

```text
ACS-M6-P0-P1-R2-CLOSEOUT-G2 / M6-P2-G0
→ ACS-M6-P2-G1
```

`ACS-M6-P2-G1` may implement, test, commit, push and remote-verify the accepted bounded
SQLite slice without another conversational approval. At the end of G1, Codex must
report a checkpoint candidate and stop for Project Lead acceptance.

## Explicit Exclusions

This record does not authorize:

- access to, migration of or deployment against the formal port-8765 database;
- PostgreSQL or Production database work;
- Public HTTP/API endpoints or public DTO changes;
- Auth, RBAC, Permission, Billing or enterprise identity work;
- Frontend changes or cross-repository UI implementation;
- M3, M4, M7 or M9 consumer/reconciliation implementation;
- Identity, Asset or Rights Registry implementation;
- Outbox dispatcher, delivery acknowledgement or external message-bus integration;
- V4, V3, Provider, GPU, Worker or ComfyUI work;
- M6-P3+, M7-M19 or Production Ready status.

## Preserved Governance Facts

- `P3-RV1-003`: `OPEN / NON-BLOCKING`;
- PRE-M6-RB1.3: remains formally closed;
- RB13-F001 and RB13-F002: remain closed;
- the immutable PRE-M6 G1 historical snapshot remains unchanged;
- M7-M19: `NOT STARTED / NOT AUTHORIZED`.
