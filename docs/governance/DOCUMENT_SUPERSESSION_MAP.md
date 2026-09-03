# Document Supersession Map

Status: `GENERATED_REFERENCE / REVIEWED 2026-09-03`

This map makes existing replacement and amendment relationships discoverable. It does
not rewrite predecessor content or create architecture authority. Machine-readable
edges remain in [`DOCUMENT_REGISTRY.json`](DOCUMENT_REGISTRY.json).

## 1. Relationship rules

- `SUPERSEDES` means the named predecessor is no longer current authority in the
  successor's declared scope.
- `AMENDS_SCOPE` preserves the earlier Accepted ADR and changes only the explicitly
  stated current application.
- `EXTENDS_SCOPE` preserves the earlier Accepted ADR and adds a compatible,
  explicitly bounded downstream contract.
- `REINFORCES_SCOPE` records a later decision that restates an existing boundary
  without replacing or amending it.
- `ARCHIVES` preserves evidence and closes it for further current execution.
- A predecessor remains readable and must never be rewritten to match its successor.

## 2. Accepted ADR scope relationships

| Predecessor | Relationship | Successor | Current interpretation |
| --- | --- | --- | --- |
| [`ADR-0009`](../../governance/ADR-0009-k2-publishable-media-production.md) | `AMENDS_SCOPE` | [`ADR-0011`](../../governance/ADR-0011-k2-internal-self-hosted-p1.md) | ADR-0011 controls the exact internal self-hosted P1 execution scope. |
| [`ADR-0009`](../../governance/ADR-0009-k2-publishable-media-production.md) | `ARCHIVES` | [`ADR-0014`](../../governance/ADR-0014-k2-001-archive-k2-002-changan-start.md) | K2-001 is historical; K2-002 begins as a separate non-GPU project scope. |
| [`ADR-0012`](../../governance/ADR-0012-k2-internal-image-first-real-media-revision.md) | `AMENDS_SCOPE` | [`ADR-0013`](../../governance/ADR-0013-k2-control-plane-convergence.md) | ADR-0013 governs the accepted control-plane convergence corrections. |
| [`ADR-0005`](../../governance/ADR-0005-m6-series-intelligence-consumer-boundary.md) | `EXTENDS_SCOPE` | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | ADR-0019 adds the explicit M3-owned binding and M7 consumer-readiness contract without replacing the existing M6 read boundary. |
| [`ADR-0015`](../../governance/ADR-0015-m12-isolated-audio-runtime-and-acyclic-voice-clone-lineage.md) | `EXTENDS_SCOPE` | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | ADR-0019 adds the M9-to-M12 `AudioRequirement` routing bridge, but its A100 build-host clause conflicts with ADR-0015's non-A100 C3 requirement; neither ADR supersedes the other, so C3 is held for architecture correction. |
| [`ADR-0016`](../../governance/ADR-0016-m13-timeline-render-candidate-and-deterministic-post-boundary.md) | `REINFORCES_SCOPE` | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | ADR-0019 keeps deterministic events and effects in M13 and does not move them into M11 generation planning. |

All referenced ADRs remain `ACCEPTED_DECISION`; a relationship does not delete an
Accepted ADR or turn it into ordinary historical prose.

## 3. Total document replacements

| Superseded document | Successor |
| --- | --- |
| [`K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md`](../../architecture/K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md) | [`K2_INTERNAL_SELF_HOSTED_P1_CONTRACT.md`](../../architecture/K2_INTERNAL_SELF_HOSTED_P1_CONTRACT.md) and ADR-0014 for the later project boundary |
| [`K2-001-PREPRODUCTION-CANDIDATE.md`](../16-k2-production/K2-001-PREPRODUCTION-CANDIDATE.md) | [`K2-001-HISTORICAL-VALIDATION-ARCHIVE.md`](../16-k2-production/K2-001-HISTORICAL-VALIDATION-ARCHIVE.md) |
| [`K2-P1-PREBOOT-TO-LIVE-RUNBOOK.md`](../16-k2-production/K2-P1-PREBOOT-TO-LIVE-RUNBOOK.md) | [`K2-INTERNAL-SELF-HOSTED-P1-RUNBOOK.md`](../16-k2-production/K2-INTERNAL-SELF-HOSTED-P1-RUNBOOK.md) |
| [`K2-002 ... v1.3`](../16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.3.md) | [`K2-002 ... v1.4`](../16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md) |
| [`K2-002 source v1.2`](../16-k2-production/k2-002-changan/source/K2-002-CHANGAN-SOURCE-v1.2.md) | [`K2-002 repository-reviewed v1.4`](../16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md) |
| [`K2-002 uploaded owner revision v1.4`](../16-k2-production/k2-002-changan/source/K2-002-CHANGAN-UPLOADED-OWNER-REVISION-v1.4.md) | [`K2-002 repository-reviewed v1.4`](../16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md) for repository execution; the upload remains immutable source evidence |
| [`K2_P1_PREBOOT_OFFLINE_PACKAGE.md`](../../governance/K2_P1_PREBOOT_OFFLINE_PACKAGE.md) | [`ADR-0011`](../../governance/ADR-0011-k2-internal-self-hosted-p1.md) |
| [`K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md`](../../governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md) | [`ADR-0011`](../../governance/ADR-0011-k2-internal-self-hosted-p1.md) |
| [`K2_PUBLISHABLE_PRODUCTION_EXECUTION_PACKAGE.md`](../../governance/K2_PUBLISHABLE_PRODUCTION_EXECUTION_PACKAGE.md) | [`ADR-0014`](../../governance/ADR-0014-k2-001-archive-k2-002-changan-start.md) |
| [`M12_A100_BUILD_HOST_PREFLIGHT_2026-09-03.md`](../status/M12_A100_BUILD_HOST_PREFLIGHT_2026-09-03.md) | [`M12_A100_BUILD_HOST_REFLIGHT_2026-09-03.md`](../status/M12_A100_BUILD_HOST_REFLIGHT_2026-09-03.md) as the current host-status checkpoint; the preflight remains immutable historical evidence |

## 4. Current-state history separation

[`CURRENT_MILESTONE.md`](../../CURRENT_MILESTONE.md) is the only concise current-state
projection. The former `## 0A.` through EOF is preserved byte-for-byte in
[`CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md`](../../CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md).
The archive does not grant current authority and is not a competing current document.

## 5. Cross-repository relationships

Frontend `FRONTEND_GLOBAL_SHELL_REMEDIATION_CONTRACT_REV3.md` supersedes Rev2.
Frontend `FE-G0-R1_FRONTEND_GLOBAL_SHELL_ROUTE_GOVERNANCE.md` supersedes the original
FE-G0 document for implementation. Frontend PR-C records those edges in its own
registry; Core does not pretend to own their semantics.

## 6. Unclassified relationships

```text
UNCLASSIFIED_SUPERSESSION_COUNT=0
```

Version-family similarity without an explicit replacement statement is not silently
treated as supersession.
