# Documentation Audit Report — 2026-09-02

Status: `AUDIT_COMPLETE / REMEDIATION_TRACKED`

Audit task: `ACS-DOCUMENTATION-GOVERNANCE-FULL-AUDIT-AND-CONSOLIDATION`

## 1. Frozen audit baseline

| Repository | Commit | Tree | Governed documents |
| --- | --- | --- | ---: |
| Core | `a455c8e76427d53d75bb7f15259b9875d9768914` | `d92159d5c3c5d3896d1fe9e56b896413277fe4e8` | 151 |
| Frontend | `a0be9edc91437bf0e7c5dd14883e656e750b3aee` | `c25b9e3744d561c93fed26d0a07e59a1915a6071` | 74 |

Core's annotated tag was independently verified as type `tag`, object
`b2d086b622bdb5456f6af325e458aa3771e43e80`, peeled target
`a455c8e76427d53d75bb7f15259b9875d9768914`.

The inventory includes all tracked Markdown/MDX/RST, documentary TXT, repository
instructions, documentary JSON manifests, governance, architecture, runbooks and
cross-repository capability mappings. Dependencies, build output, caches, generated
media, binaries, models and test output were excluded.

## 2. Read-only audit results

```text
ACCEPTED_ADR_CONFLICTS=0
BROKEN_CORE_LOCAL_LINKS=0
BROKEN_FRONTEND_LOCAL_LINKS=0
CORE_BASELINE_ORPHANS=33
FRONTEND_BASELINE_ORPHANS=66
CORE_EXACT_DUPLICATES=0
FRONTEND_EXACT_DUPLICATES=0
DOCUMENT_CLASS_UNKNOWN=0_AFTER_REGISTRATION
```

The Core baseline passed `scripts/validate_markdown.py` for 143 Markdown files and
`scripts/validate_doc_links.py` for 433 local links. The equivalent Frontend baseline
scan found no broken local links; `CLAUDE.md` was the only Markdown file without an H1.

The historical portion of `CURRENT_MILESTONE.md`, beginning with `## 0A.` and ending at
EOF, is extractable without byte changes:

```text
HISTORICAL_SECTION_SHA256=5e05b68e83ed55f90b342aee627001a7bbf66cf59f92e5106270175b07f61f6a
```

No pair of Accepted ADRs contains an unexplained current-behavior conflict. Apparent
overlaps are explicitly scoped: ADR-0011 and ADR-0014 narrow or replace ADR-0009's K2
execution scope; ADR-0013 amends ADR-0012; ADR-0015 and ADR-0016 govern separate M12 and
M13 boundaries; ADR-0017 and ADR-0018 add explicit prerequisites.

## 3. Findings

### DOC-GOV-001 — HIGH

- `documentPaths`: `CURRENT_MILESTONE.md`
- `conflictType`: `CURRENT_AND_HISTORY_COLOCATED`
- `currentEvidence`: the current projection occupies section 0 while section 0A
  through EOF contains 1,661 lines of immutable execution history with a verified
  extraction digest.
- `recommendedDisposition`: move section 0A through EOF byte-for-byte to
  `CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md`; replace the current file with a
  concise evidence-backed projection and link the archive.

### DOC-GOV-002 — HIGH

- `documentPaths`: `README.md`, `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`,
  `architecture/module-responsibility-matrix.md`
- `conflictType`: `STALE_CURRENT_M12_M13_STATE`
- `currentEvidence`: repository history and Accepted ADR-0015 through ADR-0018 prove
  merged M12 contracts/protocols and the accepted M13 base backend, while these current
  navigation/architecture documents still describe portions as not started or pending.
- `recommendedDisposition`: correct only current status annotations in Core PR-B;
  preserve all historical records and Accepted ADR bodies.

### DOC-GOV-003 — HIGH

- `documentPaths`: Frontend `docs/CREATOR_CORE_INTEGRATION.md`, Frontend governance
  status documents and Frontend `README.md`
- `conflictType`: `CROSS_REPOSITORY_CAPABILITY_DRIFT`
- `currentEvidence`: Frontend is a pin-only consumer at
  `a0be9edc91437bf0e7c5dd14883e656e750b3aee`; M13 base backend acceptance does not
  establish complete Frontend product surfaces, M14/M15 integration or publication.
- `recommendedDisposition`: add a Frontend registry and cross-repository baseline;
  describe pin semantics without changing the pin or product behavior.

### DOC-GOV-004 — MEDIUM

- `documentPaths`: 33 Core and 66 Frontend baseline documents without an inbound
  Markdown index link
- `conflictType`: `ORPHANED_DOCUMENTATION`
- `currentEvidence`: tracked-file/link graph scan at the frozen commits.
- `recommendedDisposition`: create repository-wide indexes with separate current,
  normative, evidence, historical, superseded and draft sections. Do not place
  historical evidence in the current-authority projection.

### DOC-GOV-005 — MEDIUM

- `documentPaths`: Frontend `CLAUDE.md`, Frontend CI
- `conflictType`: `FRONTEND_DOCUMENT_VALIDATION_GAP`
- `currentEvidence`: `CLAUDE.md` lacks an H1 and Frontend has no complete
  registry/Markdown/link governance check comparable to Core.
- `recommendedDisposition`: add the H1 during Frontend alignment and add an independent
  Frontend governance validator only if it can reuse an existing required job.

### DOC-GOV-006 — MEDIUM

- `documentPaths`: versioned K2 documents, K2 authority packages, ADR-0009 through
  ADR-0014 and Frontend global-shell contracts
- `conflictType`: `SUPERSESSION_RELATIONSHIPS_SCATTERED`
- `currentEvidence`: successor relationships exist in prose but have no consolidated
  bidirectional graph.
- `recommendedDisposition`: encode relationships in registries and publish a Core
  supersession map during PR-B; preserve predecessor bytes and semantics.

### DOC-GOV-007 — LOW

- `documentPaths`: K2 source/repository-review versions and interface-contract families
- `conflictType`: `EXPECTED_VERSION_FAMILY_SIMILARITY`
- `currentEvidence`: similarity scan found related templates and explicitly versioned
  lineage, but no exact duplicate files.
- `recommendedDisposition`: retain; record version/supersession relationships rather
  than deduplicating evidence.

### DOC-GOV-008 — INFORMATIONAL

- `documentPaths`: historical runbooks and execution receipts containing historical
  branches, loopback endpoints or machine-local paths
- `conflictType`: `HISTORICAL_PORTABILITY_CONTEXT`
- `currentEvidence`: no current document contains `sandbox:/workspace`, a conversation
  scratch root, `/mnt/c` or a Windows user path. Historical path facts remain useful.
- `recommendedDisposition`: set
  `HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true` in historical registry records; require
  current runbooks to declare configurable roots and loopback defaults.

## 4. Disposition sequence

1. Core PR-A establishes classification, policy, registry and complete index.
2. Core PR-B separates current state from immutable history, publishes M1–M19 and the
   supersession graph, and corrects current normative annotations.
3. Frontend PR-C aligns its registry, index, baseline and pin semantics.
4. Core PR-D adds no-dependency validation in an existing required check.
5. Frontend PR-E is created only if independent automated validation is necessary.

No finding authorizes production-code, Public API, schema, dependency, Frontend pin or
behavior changes. A100, M12-C3/C4, M13 Extension G0 and publication remain unauthorized.
