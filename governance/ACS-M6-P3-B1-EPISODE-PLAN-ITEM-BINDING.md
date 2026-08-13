# ACS-M6-P3-B1 EpisodePlanItemBinding Authorization

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING` |
| Date | `2026-08-13` |
| Decision | `GOVERNANCE CHECKPOINT REMOTE-VERIFIED AT ae82ea27b39c44a8b77941f2b43abf7544492765 / BOUNDED IMPLEMENTATION CANDIDATE` |
| Execution mode | `AUTO-SEQUENTIAL / BOUNDED / FAIL-CLOSED` |
| Authorized base | `6bb9d165a693057f38e5789c408293ff0eaf5bcc` |
| Governance checkpoint | `EIGHT DOCUMENT PATHS / PRODUCTION AND TEST DIFF ZERO` |
| Technical implementation | `SIX PRODUCTION PATHS + NINE TEST PATHS` |
| Owner HTTP clarification | `EXISTING CANONICAL V2 PROJECTION RETURNED BY WORKSPACE VERSIONS PASSES THROUGH episodePlanItemBindings / MANUAL AND BOOTSTRAP V1 BEHAVIOR UNCHANGED / NO ROUTE-HANDLER-EXTERNAL-DTO SOURCE CHANGE / NO OTHER HTTP EXPANSION` |
| M6-P3-G1 | `NOT AUTHORIZED / NOT STARTED / BLOCKED UNTIL B1 OWNER ACCEPTANCE` |
| Final stop | `B1 REMOTE-VERIFIED CANDIDATE / PROJECT LEAD OWNER REVIEW REQUIRED` |

The Project Lead, Architecture Owner, Repository Governance Owner and the affected
M2, M4, M5 and M6 Domain Owners approve the bounded M6-P3-B1 implementation review.
This record authorizes the exact automatic sequence in section 3. It does not accept
an implementation in advance and does not authorize M6-P3-G1.

## 2. Authorized outcome

B1 may implement only the accepted M5-owned immutable
`EpisodePlanItemBinding { episodeRef, episodePlanItemRef }` prerequisite inside a new
exact SeriesPlanVersion. The implementation shall add the Core-only operation:

```text
create_episode_plan_item_binding_version
```

The operation creates a new immutable M5 version. It is not an HTTP route, handler or
external DTO. Owner clarification permits only the existing HTTP workspace versions
projection to pass through `episodePlanItemBindings` when it returns a canonical v2
version, without modifying any route, handler or external DTO source file. This is not
general Public HTTP/API expansion and does not authorize a v2 manual-version response.

Its command and result contracts are closed-world and exact:

```text
create_episode_plan_item_binding_version({
  workspaceRef,
  projectRef,
  seriesRef,
  seriesPlanRef,
  expectedPlanVersion,
  episodePlanItemBindings
}) -> {plan, version}
```

No `humanConfirmed`, `content` or other field is accepted. The binding array is the
complete desired replacement set for the new exact version; `[]` is an explicit
unbind. The operation creates a draft and human-gated `confirm_version` remains a
separate transition.

The accepted version-transition policy is exact:

| Current exact version | Authorized new version | Rule |
| --- | --- | --- |
| initial plan | `v1` | Initial plan creation remains v1 |
| `v1` | `v1` | Existing non-binding version behavior remains valid |
| `v1` | `v2` | Allowed only through the explicit binding-version operation |
| `v2` | `v2` | Allowed only through the explicit binding-version operation |
| `v2` | `v1` | `FORBIDDEN` — downgrade is rejected |

Unbinding is never an in-place mutation and never a downgrade. It requires an
explicit new v2 version whose normalized binding set omits the removed association.
Existing v1 and v2 history remains immutable; no inference, backfill or silent
rebinding is allowed.

`confirm_candidate` always creates v1. Existing `create_manual_version` remains the
v1→v1 non-binding edit path and rejects a current v2 version, so it cannot create,
replace, remove, remap or return bindings. Only the dedicated Core operation may
create v1→v2 or v2→v2 versions and change a binding set, including explicit unbinding.
Every v2 durable write validates trusted M2/M4 context, and human-gated confirmation
revalidates the stored v2 binding set before updating the confirmed reference.

The v2 write and v2 confirmation paths are available only through the accepted,
lifecycle-bound `LifecycleAssembly`. A standalone or independently composed Series
Planning compatibility boundary fails closed with `lifecycle_unavailable / 503`.
The dedicated write reuses existing
`LifecycleOperation.APPEND_SERIES_PLAN_VERSION`; B1 adds no lifecycle enum value.

All other accepted binding semantics remain controlled by ADR-0005 and the M6
Consumer Contract, including trusted M2 Episode membership and M4 Project-to-Series
validation, confirmation-time revalidation, closed-world payloads, deterministic
ordering and digest, lifecycle dependency enforcement, cross-Scope isolation and
InMemory/SQLite parity without DDL.

## 3. Authorized automatic sequence

The only authorized automatic sequence is:

```text
B1 governance authorization checkpoint
→ commit / non-force push / remote verification
→ bounded B1 technical implementation
→ complete required tests and gates
→ implementation commit / non-force push / remote verification
→ STOP FOR B1 PROJECT LEAD OWNER REVIEW
```

Remote verification of the governance checkpoint is a hard prerequisite to editing
any production or test path. Remote verification of the implementation candidate does
not constitute Owner Acceptance. No next milestone is entered automatically.

## 4. Governance checkpoint allowlist

The governance-only authorization checkpoint may change exactly these eight paths:

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md
governance/ADR-0005-m6-series-intelligence-consumer-boundary.md
governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md
```

Production and test source diff must be zero in this first checkpoint. Historical
governance records, including the G0 proposal, review-open and Owner Acceptance
records, remain immutable timepoint evidence.

## 5. Technical implementation allowlist

After governance remote verification, B1 may change exactly these six production
paths:

```text
services/v5_core_os/series_planning/foundation.py
services/v5_core_os/series_planning/public.py
services/v5_core_os/series_episode/foundation.py
services/v5_core_os/series_intelligence/record_integrity.py
services/v5_core_os/lifecycle_integrity/composition.py
services/v5_core_os/lifecycle_integrity/coordinator.py
```

and exactly these nine test paths:

```text
tests/unit/test_series_planning_m5.py
tests/unit/test_deletion_lifecycle_integrity.py
tests/contract/test_creator_series_episode_contract.py
tests/contract/test_creator_series_planning_contract.py
tests/contract/test_creator_series_intelligence_sqlite_contract.py
tests/integration/test_creator_series_planning.py
tests/integration/test_creator_series_intelligence.py
tests/integration/test_creator_series_intelligence_sqlite_p2.py
tests/integration/test_creator_lifecycle_sqlite_p2.py
```

The implementation checkpoint may also synchronize the same eight governance paths
listed in section 4 with factual test and candidate status. No other path is allowed.

The M6 integrity path is limited to validating or recomputing the accepted M5 v2
source projection and digest for existing durable M6 facts; it may not add consumer
behavior. The Series/Episode foundation path is limited to the stable
`dependent_series_plan_binding_exists` lifecycle dependency error; it may not change
M2 identity or write-model ownership.

Episode deletion scans every historical v2 version in the exact Workspace and Series,
including draft, current and confirmed versions. A matching binding blocks deletion;
malformed, unknown or unreadable relevant-scope version data may not return false and
is conservatively treated as a dependency with stable
`dependent_series_plan_binding_exists / 409`. Other Workspace or Series data is
isolated. A later explicit unbind changes only the new current mapping and never
removes the deletion protection created by a historical binding.

Schema dispatch uses the immutable `SeriesPlanVersionRecord.schemaVersion` / SQLite
`schema_version` value and never infers a version from field presence. Existing v1
content bytes, fields, source projection and digest are not rewritten. The v2 internal
M5 source snapshot adds the normalized binding set to its digest. SQLite uses only the
existing `content_json` column, with strict Python JSON validation and no JSON1, DDL,
marker or migration. M6 `record_integrity` may only validate/recompute the corresponding
v1/v2 M5 source digest and adds no consumer behavior.

The existing HTTP workspace versions projection passes through stored canonical
versions. Its v2 version objects therefore include `episodePlanItemBindings`; its v1
shape remains unchanged. Existing manual-version behavior remains v1-only and
`build_m6_bootstrap` remains its exact v1 DTO without bindings. No route, handler or
external DTO source file may change, and no other HTTP contract expansion is allowed.

## 6. Required behavior and gates

The B1 implementation must prove all binding prerequisite gates in section 13.1 of
the M6 Consumer Contract, including:

1. v2 binding creation occurs only in a new immutable M5 version through
   `create_episode_plan_item_binding_version`;
2. initial creation stays v1; v1→v1, explicit v1→v2 and v2→v2 are supported;
   v2→v1 is rejected and unbinding requires a new explicit v2 version;
3. M2 Episode membership and M4 Project-to-Series context are validated before the
   first durable write and revalidated at human-gated confirmation;
4. binding objects are closed-world, identities are unique and input order
   normalizes deterministically to plan-item position then `episodeRef`;
5. v1 history remains byte/field stable and unbound, and all v2 history remains
   immutable without backfill;
6. the normalized binding set participates in the v2 source projection and digest;
7. any historical binding blocks Episode deletion with the accepted error precedence,
   race, rollback and commit-uncertainty behavior;
8. InMemory/SQLite behavior and restart agree using the existing `content_json`, with
   no table, column, marker, DDL or migration;
9. `create_manual_version` rejects a current v2 version without a durable write; only
   the dedicated Core method creates v2→v2;
10. the canonical v2 projection returned by HTTP workspace versions passes through
   `episodePlanItemBindings` without route, handler or external DTO source-file
   changes; v1 projections, manual-version behavior and the v1 bootstrap remain
   unchanged;
11. focused tests, full Core regression, AST/architecture checks, secret scan and
   `git diff --check` pass;
12. the implementation is committed once, non-force pushed and remote-verified with
    Local SHA equal to Remote SHA, ahead/behind `0/0` and a clean worktree.

Existing tests may not be deleted, skipped or weakened.

## 7. Explicit exclusions and stop conditions

B1 does not authorize:

- any route, handler or external DTO source-file change, or Creator Public HTTP/API
  contract expansion beyond the Owner-approved existing canonical v2 pass-through in
  workspace versions; the exact Core-only `SeriesPlanningPublicBoundary` operation
  authorized in section 2 is the sole allowed boundary addition;
- any table, column, marker, DDL, migration, PostgreSQL or formal port-8765 work;
- an M3 or M6 consumer, `ActiveM6BaselineReader`, ScriptVersion binding or any part of
  M6-P3-G1;
- M2 identity/write-model changes or a reassignment of M2/M4/M5/M6 ownership;
- Frontend or cross-repository work;
- M7/M9 behavior, M6-P4+, M7-M19, V4/V3, Provider, GPU, Worker or ComfyUI work;
- Production Ready or release authority.

Execution stops immediately before an out-of-scope edit if implementation needs:

- any path outside the frozen 6 production, 9 test and 8 governance paths;
- any DDL/migration or persistence shape beyond existing SQLite `content_json`;
- any route/handler/external DTO source-file change or HTTP expansion beyond the
  approved existing canonical v2 pass-through in workspace versions;
- any M3/M6 consumer, G1, Frontend or M7+ behavior;
- a changed architecture decision, widened Domain ownership or force push.

The blocker must be reported to the Project Lead; the implementation may not silently
expand its allowlist.

## 8. Approval record

| Role | Owner | Decision | Date | Scope |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `AUTHORIZED` | `2026-08-13` | Exact auto-sequential governance checkpoint and bounded B1 implementation |
| Architecture Owner | `蔺鹏` | `APPROVED` | `2026-08-13` | Version policy, Core-only operation and accepted ADR-0005 boundary |
| Repository Governance Owner | `蔺鹏` | `AUTHORIZED` | `2026-08-13` | 8 governance, 6 production and 9 test paths; non-force remote verification |
| M2 Domain Owner | `蔺鹏` | `APPROVED FOR B1` | `2026-08-13` | Episode identity, membership and deletion dependency boundary |
| M4 Domain Owner | `蔺鹏` | `APPROVED FOR B1` | `2026-08-13` | Trusted Project-to-Series validation boundary |
| M5 Domain Owner | `蔺鹏` | `APPROVED FOR B1` | `2026-08-13` | Immutable binding version, projection and digest ownership |
| M6 Domain Owner | `蔺鹏` | `APPROVED FOR B1` | `2026-08-13` | Existing M6 source/digest compatibility only; no consumer |

No approval is inferred for M3, M7, M9 or any other future implementation.

## 9. Final stop rule

After the bounded B1 implementation is committed, non-force pushed and
remote-verified:

```text
STOP — M6-P3-B1 REMOTE-VERIFIED IMPLEMENTATION CANDIDATE
PROJECT LEAD B1 OWNER REVIEW REQUIRED
M6-P3-G1 NOT AUTHORIZED / NOT STARTED
NEXT AUTHORIZED MILESTONE: NONE
```

Only a new explicit Project Lead decision may Owner Accept B1 or authorize G1.
