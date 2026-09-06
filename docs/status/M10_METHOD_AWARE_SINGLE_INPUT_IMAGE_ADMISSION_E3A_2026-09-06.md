# M10 Current Single-Input Image Admission E3A — 2026-09-06

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / REQUIRED_CI_GATE`

Owner: `Project Lead / M10 Input Asset Owner / Candidate Lifecycle Owner`

Task: `ACS-M10-M11-CURRENT-SINGLE-INPUT-IMAGE-ADMISSION-CORRECTIVE-E3A`

## Bounded result

The current MICRO_MOTION / SINGLE_ANCHOR_I2V requirement has a sanctioned source
for one imported ACTION_READY_ANCHOR image. It reuses the existing Candidate
lifecycle, canonical AssetVersion authority and Episode Production evidence journal.
The old real-image exact-four, image successor and Static Resource FONT paths retain
their semantics. There is no new table, queue, upload API or provider execution.

This bounded implementation follows [ADR-0019](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md),
the [module responsibility matrix](../../architecture/module-responsibility-matrix.md)
and the [public HTTP contract](../04-interface-contract/creator-public-http-v1.md).
[E1 worker execution](M10_M11_METHOD_AWARE_WORKER_SEAM_CORRECTIVE_E1_2026-09-06.md)
and [E2 result intake](M10_M11_METHOD_AWARE_JOB_RESULT_INTAKE_CORRECTIVE_E2_2026-09-06.md)
remain independently owned and unchanged.

```text
CORE_START_MAIN=ccb624eb222fba703573018a433acdebc645bbfd
CORE_START_TREE=4db53bbc1a06dae4a8051b181629b7f717c026aa
CURRENT_SINGLE_INPUT_IMAGE_ADMISSION_E3A=IMPLEMENTED_AND_VERIFIED
CURRENT_SINGLE_INPUT_IMAGE_CANDIDATE_INTAKE=IMPLEMENTED_AND_VERIFIED
CURRENT_SINGLE_INPUT_IMAGE_ASSET_ADMISSION=IMPLEMENTED_AND_VERIFIED
E3_CURRENT_SINGLE_ANCHOR_ADMISSION_PATH=AVAILABLE
ONE_CANDIDATE_LIFECYCLE=true
ONE_ASSET_VERSION_AUTHORITY=true
ONE_EVIDENCE_JOURNAL=true
DATABASE_DDL_DIFF=0
PUBLIC_METHOD_AWARE_RESOURCE_COUNT=8
EPISODE_PRODUCTION_SUBRESOURCE_COUNT=34
```

## Ownership and configuration

| Boundary | Responsibility | Authority retained elsewhere |
| --- | --- | --- |
| V4 digest-pinned artifact evidence | Strict closed bundle, exact scope/lineage, regular-file path containment, size/SHA, single PNG/JPEG image, repeated probe and hash | No production facts, QC, human decision, publication or provider permission |
| Operator bundle script | Explicit existing refs; local image verification, content-addressed no-replace staging and bundle SHA output | No Core database writes, Candidate or AssetVersion creation |
| V5 input intake | Current plan/requirement/Shot plus fresh artifact evidence; atomic receipt, existing Candidate and TechnicalValidation | No automatic QC, selection or admission |
| Existing review | Semantic QC and exact digest-pinned external human decision | Browser credentials cannot claim external actor or decision authority |
| V5 input admission | Rebuild current selection chain, reverify artifact, atomically append one admission and AssetVersion | No successor, rights upgrade, route or job |
| Existing input planning | Canonical current asset plus exact role/key/requirement/plan bindings | No provider selection or execution |

Configure all three values together:

```text
CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH
CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_SHA256
CREATOR_METHOD_AWARE_SOURCE_ROOT
```

All absent selects a rejecting port and valid new commands return stable 503.
Partial configuration fails composition before database creation. Bundle bytes are
independently pinned and reloaded at startup and each use. Duplicate JSON keys,
unknown fields, invalid numeric values, duplicate staged refs or duplicate exact
scope/lineage/role entries fail closed. The operator tool takes all existing scope,
plan, requirement, Shot and evidence references explicitly; `--help` lists arguments.
No production lineage is invented by the tool.

Single PNG/JPEG inputs are bounded at 100 MiB, positive integer dimensions up to
16384, one stream and one frame. Symlink files/parents, unsafe keys, animation,
wrong codec, changed bytes or changed manifest are rejected. Local ffprobe reads
only supplied bytes through the pipe protocol. Reader operations never copy or
modify source bytes. Staging refuses to replace an existing different file.

## Lifecycle, atomicity and replay

```text
V4_INPUT_ARTIFACT_BUNDLE_SCHEMA=v4.method-aware-input-artifact-authority-bundle.v1
V4_INPUT_ARTIFACT_SAFE_PROJECTION_SCHEMA=v4.method-aware-input-artifact.v1
V5_INPUT_ARTIFACT_RECEIPT_SCHEMA=v5.method-aware-input-artifact-receipt.v1
CANDIDATE_SCHEMA=v5.k2-media-candidate.v1
CANDIDATE_PROVENANCE=IMPORTED
TECHNICAL_VALIDATION_SCHEMA=v5.k2-technical-validation.v1
CANDIDATE_INTAKE_ATOMIC_RECORD_COUNT=3
METHOD_AWARE_INPUT_ADMISSION_SCHEMA=v5.method-aware-input-asset-admission.v1
METHOD_AWARE_INPUT_ASSET_VERSION_SCHEMA=v5.method-aware-input-image-asset-version.v1
ADMISSION_ATOMIC_RECORD_COUNT=2
INPUT_ASSET_AUTHORITY_STATE=TECHNICAL_EVIDENCE_ONLY
INPUT_ASSET_PROVIDER_PROCESSING_AUTHORIZED=false
INPUT_ASSET_PUBLICATION_ALLOWED=false
```

Server-generated intake references bind exact scope, plan, requirement and staged
artifact digest. Journal CAS and atomic append prevent partial batches and concurrent
duplicates. Request conflicts fail without writes; exact replay revalidates current
lineage and fresh bytes. Response loss and process restart reuse the same records.

Standalone SELECTED is permitted only for this exact current input receipt chain,
using the existing digest-pinned external selection authority. Legacy SELECTED still
requires its original atomic admission path. QC version supersession remains intact.
Admission validates the complete prepared pair before atomic persistence and the
canonical authority validates the closed persisted schema and exact linked chain.
One initial asset exists per workspace/run/requirement/role. The same exact selection
under another key reuses it; another candidate receives the explicit unsupported
successor conflict. Admission grants neither provider processing nor publication.

## Validation and stop boundary

Before production changes, nine baseline cases produced five expected missing-path
failures and four preserved-boundary passes, without errors. Final isolated tests
exercise real synthetic bytes, authenticated HTTP, digest-pinned external approval,
SQLite rollback on record two/three, concurrent requests, socket response loss,
restart replay, stale lineage, strict DTOs and one READY Micro Motion input.
Legacy exact-four, FONT, E1/E2, review and state-projection regressions remain gates.
Only focused local sets run; the one PR tree requires the five full-suite CI checks.
No actual E3 lineage, SH09 bytes, GPU or provider operation was performed.

```text
SINGLE_INPUT_CANDIDATE_RED_REPRODUCTION=PASS
SINGLE_INPUT_ADMISSION_RED_REPRODUCTION=PASS
LEGACY_EXACT_FOUR_BOUNDARY_RED_REPRODUCTION=PASS
STATIC_FONT_BOUNDARY_RED_REPRODUCTION=PASS
DIRECT_FIXTURE_BYPASS_REQUIRED_BEFORE_FIX=true
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
ANCHOR_BYTES_VERIFIED=false
VIDEO_METHOD_ROUTE_CREATED=false
MEDIA_JOB_CREATED=false
A100_RUNTIME_VERIFIED=false
EXECUTION_COST_CEILING_RESOLVED=false
CONTACT_ACTION_RUNTIME=UNAVAILABLE
GAIT_LOCOMOTION_RUNTIME=UNAVAILABLE
NEXT_TASK=ACS-M10-M11-SPIKE-0-ELIGIBLE-LINEAGE-PREPARATION-E3-RESUME-R1
```

E3 resume requires separate authorization after merge and branch cleanup. This
receipt does not authorize live execution, Frontend, M12-C3 or automatic subtitles.
