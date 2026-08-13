# ACS-M6-P2-G1 Closeout G3 / M6-P3-G0 Governance Record

> Status: `GOVERNANCE / ARCHITECTURE CHECKPOINT CANDIDATE / OWNER REVIEW PENDING`
>
> Decision date: `2026-08-13`
>
> Accepted technical baseline: `8227c6c616140824fd70de920dc6fcf459bb734d`
>
> Scope: governance-only M6-P2 closeout recording and M6-P3 architecture proposal

## Project Lead decision received

The Project Lead explicitly accepts `ACS-M6-P2-G1` commit
`8227c6c616140824fd70de920dc6fcf459bb734d` as:

```text
OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED
```

The Project Lead also authorizes one governance-only work package:

```text
ACS-M6-P2-G1-CLOSEOUT-G3 / M6-P3-G0
```

This authority permits architecture analysis, a Proposed ADR, a Proposed normative
contract, Source-of-Truth synchronization, validation, one Git commit, GitHub push and
remote verification. It does not authorize M6-P3 implementation.

## Accepted M6-P2 evidence

The accepted bounded M6-P2 technical checkpoint records:

- branch: `codex/m6-p2-series-intelligence-sqlite`;
- base: `2b2a9b9e3cd7ca2415932c035c3c98e6fee44a3e`;
- commit and remote SHA: `8227c6c616140824fd70de920dc6fcf459bb734d`;
- Local equals Remote, ahead/behind `0/0`, clean worktree;
- M6-P2 strict tests: `52/52 PASS`;
- Full Core regression: `385/385 PASS`;
- Unit: `210/210`, Contract: `78/78`, Integration: `97/97`;
- Python AST: `58/58 PASS`;
- Markdown: `77/77 PASS`;
- local links: `297/297 PASS`;
- secret scan and committed `git diff --check`: `PASS`;
- formal port-8765 database, Frontend, HTTP/Auth/RBAC and M7+ changes: `0`.

Acceptance is bounded to the local-development SQLite adapter and does not establish
Production Ready or formal database deployment.

## M6-P3-G0 architecture finding

The accepted production spine places M6 Series Intelligence upstream of Episode
CreativePlan, Story and Script. The first proposed direct consumer is therefore M3
Script Studio. M4 owns Project identity and Project-to-Series context; M2 owns
Series/Episode identity and Series-to-Episode membership. The consumer composes those
trusted read boundaries without making either domain an owner or copy of M6 facts.

The proposed integration requires a read-only, persistence-neutral consumer port that
resolves an Episode-scoped input from the exact active M6 baseline and its
M5/Bible/Character Ref-and-Digest lineage. Copied narrative text, display names and
unversioned JSON are not integration.

The current Core has no shared stable key from M2 `episodeRef` to M5
`episodePlanItemRef`; a read-only resolver over the current facts has no valid success
path. ADR-0005 therefore proposes an immutable M5 `EpisodePlanItemBinding` embedded in
an exact SeriesPlanVersion, while M2 retains Episode identity/membership and M4
supplies trusted Project-to-Series context. Existing M5 v1 history remains unbound and
is never inferred or backfilled. No implementation may infer the association from an
episode number, title, list position or display name.

This creates a mandatory two-checkpoint future sequence: first a separately authorized
and accepted `ACS-M6-P3-B1` binding prerequisite, then a separately authorized
`ACS-M6-P3-G1` read-only M6/M3 consumer. Neither implementation is authorized here. If
B1 requires SQLite DDL/migration or wider ownership changes, it must stop for another
ADR and Project Lead decision.

M7 remains the future owner of ConsistencyValidation, PASS/WARN/BLOCK, findings,
staleness and correction readiness. M9 remains the future owner of AssetRequirement
and asset-resolution readiness. M6-P3-G0 does not implement either domain.

Because the proposed boundary changes a cross-domain contract and future ScriptVersion
lineage, [`ADR-0005`](ADR-0005-m6-series-intelligence-consumer-boundary.md) remains
`PROPOSED`. Its associated
[`M6 consumer contract`](../architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md)
is also proposed and carries no implementation authority.

## Preserved authority and proposed binding ownership

Existing domain facts remain owned by their current domains. ADR-0005 proposes only
the following resolver responsibility:

- M5 owns SeriesPlanVersion and its digest;
- M5 would own the proposed immutable EpisodePlanItemBinding and resolver inside an
  exact SeriesPlanVersion; M2 retains Series/Episode identity and membership;
- M6 owns SeriesBible, CharacterContinuity, M6BaselineSnapshot and its Outbox facts;
- M3 owns Script and immutable ScriptVersion;
- M4 owns Project identity and Project-to-Series context;
- M7 will own consistency reports, verdicts and staleness when separately authorized;
- M9 will own AssetRequirement and asset-resolution-readiness facts when separately authorized;
- `P3-RV1-003` remains `OPEN / NON-BLOCKING`;
- the protected PRE-M6 G1 historical snapshot remains unchanged.

This checkpoint does not authorize:

- M6-P3-G1 or any production/test implementation;
- M6-P3-B1 binding implementation;
- Script Studio, Project Context, M7 or M9 code changes;
- a consumer checkpoint table, schema, migration or persistent delivery state;
- Outbox dispatcher, acknowledgement, broker or external message bus;
- formal port-8765 database access, migration or deployment;
- PostgreSQL or Production database work;
- Creator HTTP/Public API, DTO, Auth, RBAC or Permission changes;
- Frontend changes or cross-repository UI activation;
- Identity, Rights, Asset, V4, V3, Provider, GPU, Worker or ComfyUI work;
- M6-P4+, M7-M19 implementation or Production Ready status.

## Candidate state after this checkpoint

```text
ACS-M6-P2-G1
OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
8227c6c616140824fd70de920dc6fcf459bb734d

ACS-M6-P2-G1-CLOSEOUT-G3
OWNER ACCEPTANCE RECORDED / GOVERNANCE CHECKPOINT CANDIDATE

M6-P3-G0
ARCHITECTURE PROPOSAL DEFINED / BINDING PREREQUISITE OPEN
GOVERNANCE-ONLY CHECKPOINT CANDIDATE / OWNER REVIEW PENDING

ADR-0005 / M6 CONSUMER CONTRACT
PROPOSED FOR PROJECT LEAD REVIEW / NO IMPLEMENTATION AUTHORITY

M6-P3-B1 BINDING PREREQUISITE
PROPOSED / NOT AUTHORIZED / NOT STARTED / BLOCKS G1

M6-P3-G1+
NOT AUTHORIZED / NOT STARTED
```

## Acceptance gates and stop rule

This governance checkpoint is complete only when:

1. exactly the authorized governance/architecture files are changed;
2. production, tests, SQLite, migration, HTTP and Frontend diffs are zero;
3. Source-of-Truth files consistently record the accepted P2 SHA and Proposed P3 state;
4. Markdown structure, local links, secret scan and `git diff --check` pass;
5. one governance commit is pushed and Local SHA equals Remote SHA;
6. ahead/behind is `0/0` and the worktree is clean.

After remote verification:

```text
STOP — GOVERNANCE / ARCHITECTURE CHECKPOINT CANDIDATE
OWNER REVIEW PENDING
```

The Project Lead must separately accept ADR-0005 and the consumer contract, then
authorize and accept the B1 binding prerequisite before separately authorizing G1.
No implementation begins from this checkpoint.
