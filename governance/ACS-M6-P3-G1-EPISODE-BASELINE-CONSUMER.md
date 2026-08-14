# ACS-M6-P3-G1 Episode Baseline Consumer Authorization

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER` |
| Date | `2026-08-14` |
| Decision | `AUTHORIZED AFTER GOVERNANCE REMOTE VERIFICATION / NOT YET IMPLEMENTED OR OWNER ACCEPTED` |
| Execution mode | `AUTO-SEQUENTIAL / BOUNDED / FAIL-CLOSED` |
| Authorized base | `c5485b70b17f9154ff17246f6329a99113a5eaa9` |
| Accepted technical prerequisite | `M6-P3-B1-R1 OWNER ACCEPTED AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` |
| Frontend sequence evidence | `main b4997ec6fdaaf9d2874141571163056ba19950ef / TREE 90a4c663ea8fcda5556e4ca3d107ce48d6147bf7 / POST-MERGE CI 31759310779 SUCCESS` |
| Governance checkpoint | `EIGHT GOVERNANCE PATHS / PRODUCTION AND TEST DIFF ZERO` |
| Technical allowlist | `SEVEN PRODUCTION PATHS + THREE NEW TEST PATHS` |
| Final stop | `REMOTE-VERIFIED G1 CHECKPOINT CANDIDATE / PROJECT LEAD OWNER REVIEW REQUIRED` |

The Project Lead, Architecture Owner, Repository Governance Owner and affected M2,
M3, M4, M5 and M6 Domain Owners authorize the bounded Core-only implementation
defined here. ADR-0005 and the M6 Consumer Contract remain the normative architecture.
This decision does not pre-accept the implementation and does not authorize any work
after G1.

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
