# ACS-M6-P3-G1 Episode Baseline Consumer Authorization

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER` |
| Date | `2026-08-14` |
| Decision | `ORIGINAL G1 REVISION REQUIRED / G1-R1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED` |
| Execution mode | `AUTO-SEQUENTIAL / BOUNDED / FAIL-CLOSED` |
| Authorized base | `c5485b70b17f9154ff17246f6329a99113a5eaa9` |
| Accepted technical prerequisite | `M6-P3-B1-R1 OWNER ACCEPTED AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` |
| Frontend sequence evidence | `main b4997ec6fdaaf9d2874141571163056ba19950ef / TREE 90a4c663ea8fcda5556e4ca3d107ce48d6147bf7 / POST-MERGE CI 31759310779 SUCCESS` |
| Governance checkpoint | `EIGHT GOVERNANCE PATHS / PRODUCTION AND TEST DIFF ZERO` |
| Technical allowlist | `SEVEN PRODUCTION PATHS + THREE NEW TEST PATHS` |
| Original G1 checkpoint | `3696d6af12222d30eb99b65d67e6db18897eb42f / TREE 37cf9a4154ee27c53c4671c1b677ff0eada21a0c / REVISION REQUIRED` |
| Accepted G1-R1 checkpoint | `e172cc7c9bfca04066153d9edad70d9074bb37e5 / TREE be7447c3d60510262e428b86cd1a6a83972f64c0 / 464/464 / OWNER ACCEPTED` |
| Converged main | `5976263f92f7f9cbe9c091719eccb036ee8c0c2d / SAME TREE / PR #2 REBASE AND MERGE / MAIN CI PASS` |

The Project Lead, Architecture Owner, Repository Governance Owner and affected M2,
M3, M4, M5 and M6 Domain Owners authorize the bounded Core-only implementation
defined here. ADR-0005 and the M6 Consumer Contract remain the normative architecture.
The original G1 implementation was not accepted and is superseded by the bounded
G1-R1 error-semantics correction. Owner Acceptance of G1-R1 does not authorize any
work after G1.

## 2. Authorized outcome

G1 may introduce one internal, read-only and persistence-neutral
`ActiveM6BaselineReader` and exactly one new M3 read surface:

```text
ScriptStudioPublicBoundary.get_m6_episode_baseline(
  workspaceRef,
  projectRef,
  seriesRef,
  episodeRef
) -> v5.m6-episode-baseline-input.v1
```

The reader composes trusted M4 Project-to-Series context, trusted M2
Series-to-Episode membership, the accepted exact M5 v2 EpisodePlanItem binding and the
current active M6 baseline. It returns only one coherent `CURRENT` immutable DTO or a
stable fail-closed error. It performs no write, emits no event and records no consumer
checkpoint or operation.

The exact stable errors are:

```text
m6_baseline_not_available
m6_baseline_stale
m6_lineage_mismatch
m6_consumer_authority_unavailable
m6_episode_mapping_unavailable
```

`m6_reconciliation_required` remains reserved and must not be returned by G1.

## 3. Authorized automatic sequence

```text
G1 GOVERNANCE-ONLY AUTHORIZATION CHECKPOINT
→ COMMIT / NON-FORCE PUBLISH / REMOTE VERIFY
→ BOUNDED G1 CORE IMPLEMENTATION AND THREE NEW TEST FILES
→ COMPLETE TEST / AST / ARCHITECTURE / SECRET / DIFF GATES
→ COMMIT / NON-FORCE PUBLISH / REMOTE VERIFY
→ STOP FOR PROJECT LEAD G1 OWNER REVIEW
```

Production and test paths may not change before the governance checkpoint is
remote-verified. A remote-verified technical candidate is not Owner Acceptance.

## 4. Governance checkpoint allowlist

The authorization checkpoint may change exactly these eight paths:

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md
governance/ADR-0005-m6-series-intelligence-consumer-boundary.md
governance/ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER.md
```

Production and test source diff must be zero at this checkpoint.

## 5. Technical implementation allowlist

After governance remote verification, G1 may change exactly these seven production
paths:

```text
services/v5_core_os/series_intelligence/contracts.py
services/v5_core_os/series_intelligence/errors.py
services/v5_core_os/series_intelligence/foundation.py
services/v5_core_os/series_intelligence/public.py
services/v5_core_os/series_intelligence/composition.py
services/v5_core_os/script_studio/public.py
services/v5_core_os/lifecycle_integrity/composition.py
```

and may add exactly these three test paths:

```text
tests/unit/test_series_intelligence_consumer_m6_p3.py
tests/contract/test_creator_series_intelligence_consumer_contract.py
tests/integration/test_creator_series_intelligence_consumer.py
```

The technical checkpoint may synchronize the same eight governance paths with
factual candidate and gate results. Any other path is a hard stop.

## 6. Required exact behavior

The result is closed-world and contains exactly the fields and `applicableFacts`
collections frozen by sections 6 and 13.2 of the M6 Consumer Contract. The bound
EpisodePlanItem comes from the exact locked M5 v2 source. All eight Bible collections
remain in canonical stable-ref order; characters sort by `characterRef`; applicable
state intervals and relationships use start-inclusive/end-exclusive plan-item
positions and sort by their stable refs. Empty arrays remain present. IdentityBinding
is excluded.

An unbound v1 source, missing exact Episode binding, unavailable trusted context,
absent baseline, stale source or inconsistent Ref/Digest lineage fails closed. Number,
title, name, index, copied content and route text are never identity. Repeated reads
are deterministic and write-neutral. A subsequent read after a valid M6 baseline
replacement returns the new current DTO while a previously returned DTO remains
unchanged.

InMemory, temporary-file SQLite and SQLite restart semantics must agree within one
coherent lifecycle read snapshot. Existing ScriptVersion bytes and fields,
`get_workspace`, Script create/confirm/rewrite/storyboard behavior and all existing
M1–M6-P2 plus B1-R1 behavior remain unchanged.

## 7. Explicit exclusions

G1 authorizes no `__init__` export, schema, migration, DDL, M6 SQLite adapter change,
ScriptVersion persistence/binding, create/confirm/rewrite behavior, public HTTP/API or
DTO, route, handler, Auth/RBAC, Frontend or Experience Adapter change, event consumer,
dispatcher, checkpoint, broker, formal port-8765 access, M7/M9 behavior, M6-P4+,
V4/V3, Provider, GPU, Worker, ComfyUI or Production Ready claim. No
`projectRef`, `seriesRef` or `episodeRef` may be inferred or fabricated.

## 8. Acceptance and stop gates

The candidate must pass all gates in Consumer Contract section 13.2, the focused unit,
contract and integration modules, full Core regression, Markdown/local-link checks,
non-test Python AST, architecture/import guards, secret scan, allowlist review and
`git diff --check`. It must be non-force published and prove Local SHA = Remote SHA,
ahead/behind `0/0` and clean worktree. Then execution stops:

```text
M6-P3-G1 REMOTE-VERIFIED CHECKPOINT CANDIDATE
PROJECT LEAD OWNER REVIEW REQUIRED
M6-P3 AFTER G1 / M6-P4+ / M7 / M9 NOT AUTHORIZED
```

## 9. Technical candidate evidence

The bounded implementation changes exactly the seven production paths and adds
exactly the three test paths in section 5. It adds no other production or test path.
The local candidate proves:

```text
FOCUSED G1: 14/14 PASS — UNIT 5 / CONTRACT 4 / INTEGRATION 5
FULL CORE: 463/463 PASS — UNIT 252 / CONTRACT 88 / INTEGRATION 123
NON-TEST PYTHON AST: 63/63 PASS
MARKDOWN: 88/88 PASS
LOCAL DOCUMENTATION LINKS: 323/323 PASS
APPLICATION-TO-V4 ARCHITECTURE GUARD: PASS
SECRET / __init__ / HTTP / MIGRATION / DDL / DIFF CHECKS: PASS
```

The evidence includes trusted M4/M2 exact Scope, M5 v2 binding without inference,
closed-world current input, all five returned G1 error codes, stable fact filtering,
same-name and real cross-Scope rejection, BusinessDomain/Tenant isolation, read
determinism and write neutrality, existing Script workspace stability, baseline
replacement, InMemory/SQLite parity, SQLite restart and coherent-read blocking against
an M5 write. Remote publication and equality verification remain pending at this
documented local-candidate timepoint.

The later remote technical checkpoint is
`3696d6af12222d30eb99b65d67e6db18897eb42f`; Owner Review marked it
`REVISION REQUIRED / NOT OWNER ACCEPTED` because its unknown-exception fallback
incorrectly returned the specific `m6_lineage_mismatch / 409` business semantic.

## 10. G1-R1 correction and Owner Acceptance

The separately authorized G1-R1 correction changes only:

```text
services/v5_core_os/script_studio/public.py
tests/unit/test_m6_p3_g1_r1_error_semantics.py
```

It maps an unknown consumer exception to neutral
`m6_consumer_internal_error / 500`, preserves `from None`, leaves all five ADR-0005
business failure mappings unchanged and adds the exact unknown-exception regression.
The accepted result is:

```text
M6-P3-G1-R1 OWNER ACCEPTED / COMPLETE
REMOTE-VERIFIED AT e172cc7c9bfca04066153d9edad70d9074bb37e5
TREE be7447c3d60510262e428b86cd1a6a83972f64c0
FULL CORE 464/464 PASS
```

Core `main` was later converged through PR `#2` using `Rebase and merge`. The resulting
`main` SHA is `5976263f92f7f9cbe9c091719eccb036ee8c0c2d` and has the exact accepted
G1-R1 tree. This closeout does not authorize M6-P4+, M7-M19, HTTP/API, Frontend,
Schema/Migration, GPU, Worker or ComfyUI work.
