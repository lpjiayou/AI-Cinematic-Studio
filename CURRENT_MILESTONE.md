# AI Cinematic Studio — Current Execution State

Status: `CURRENT / EVIDENCE-BACKED / FAIL-CLOSED`; reviewed: `2026-09-15`

## 1. Active task and boundaries

Only the block below is the machine-checked current execution projection.
Dated receipts retain their original checkpoint meaning; they are not additional
current-task overrides. This update records progress and existing authorization,
not a new Grant, feature acceptance or production-readiness decision.

<!-- CURRENT_STATE:BEGIN -->
```text
CURRENT_TASK=ACS-D1-PRE-SEND-FAILURE-RECOVERY
CURRENT_ACTION=SAME_SERVICE_RESTART_AND_UNSELECTED_MODEL_INVENTORY_RECOVERY
NEXT_TASK=D1_PUBLISHED_FIX_AND_ONE_APPROVED_SH09
REVIEWED_MAIN=20aca1d669214cd9ce6c8dcd2ef4aece0a4e4f43
REVIEWED_TREE=23a3e80f567ceebc70b1a43f2eec8ad574aadeec
ADR_0022_ACCEPTED_VERSION=1.8_SAME_SERVICE_RESTART_AND_UNSELECTED_MODEL_ADDITIONS
R2_F01_ENGINEERING=ACCEPTED_WITHIN_CPU_FIXTURE_SCOPE_AND_MERGED
R3_F01_ENGINEERING=MERGED
D1_OPERATOR_CODE=MERGED
D1_SEVEN_STORE_BINDING_FIX=MERGED
ORIGINAL_EVIDENCE_AVAILABILITY=RESOLVED
D1_BOUNDED_DEPLOYMENT=OWNER_AUTHORIZED
D1_EXISTING_DATA_BINDING=ORIGINAL_CUSTODY_WORKSET_BOUNDED_AUTHORIZATION
D1_SELECTED_SSH_FORWARD_TARGET=127.0.0.1:8188
D1_RUNTIME_OBSERVATION=DATED_READ_ONLY_METADATA_ONLY
D1_EXACT_RUN_REQUEST=ORIGINAL_APPROVED_PLAN_REQUIRES_PUBLISHED_FIX_REBINDING
D1_COMPLETE=false
SYSTEM_RUNTIME_BOUND=false
PROMPT_SUBMISSION_AUTHORIZED=false
SPIKE_0_EXECUTED=false
SPIKE_0_READINESS=BLOCKED_PENDING_EXACT_RUN_GATES
FORMAL_DATABASE_WRITES_AUTHORIZED=false
LIVE_GRANT_ISSUED=true
LIVE_GRANT_CONSUMED=false
OUTPUT_ASSET_ADMISSION_ALLOWED=false
PUBLICATION_ALLOWED=false
D2_D3=QUEUED_NOT_AUTHORIZED
FRONTEND_IMPLEMENTATION_IN_THIS_TASK=NOT_AUTHORIZED
PRODUCTION_READY=false
M12_RUNTIME_INSTALLED=false
M12_RUNTIME_G0=NOT_COMPLETE
M12_G0_3_STATE=DEDICATED_CPU_VM_SELECTION_HOLD
M12_C3_READY_TO_START=false
M12_C3_AUTHORIZED=false
M12_C4_AUTHORIZED=false
M12_NEXT_TASK=ACS-M12-C3-DEDICATED-LINUX-CPU-VM-PROVIDER-SELECTION-AND-PREFLIGHT
M13_BASE_BACKEND=COMPLETE
M13_BASE_CLOSEOUT=ACCEPTED
M13_PRODUCT_CAPABILITY_COMPLETE=false
M13_EXTENSION_G0_AUTHORIZED=false
M13_EXTENSION_IMPLEMENTATION_AUTHORIZED=false
A100_START_AUTHORIZED=false
DOCUMENT_GOVERNANCE_VALIDATION=IMPLEMENTED
DOCS_ONLY_CI_FAST_PATH=IMPLEMENTED
REQUIRED_CHECK_CONTEXTS=5_UNCHANGED
PROTECTED_CHANGE_FULL_SUITE=ENFORCED
ISOLATED_TEST_CI_FAST_PATH=MERGED
INTEGRATION_SHARDS=6
POST_MERGE_DUPLICATE_FULL_CI=REMOVED
```
<!-- CURRENT_STATE:END -->

The original exact SH09 plan was approved and one Grant/Attempt was created, but
the pre-consumption failure produced no confirmed send or video. Preserve the
original records. The Owner authorized failure-only cleanup and the ADR-0022
section 8.5 single-replacement exception; consumed/UNKNOWN cases remain excluded.
The replacement must bind the published repair and current runtime through the
original Operator. Its send permission is not active until those gates pass.
The old approved window expired. The Owner explicitly confirmed one new five-hour
window after publication and current preparation, with the two-hour execution and
RMB 1,000 cap unchanged. Its exact times must be recorded, not silently extended.
Leave the GPU on; storage remains billed. No formal 8765 database access is allowed.
The Owner explicitly authorized one consolidated correction and publication before
continuing the original SH09: proven unrelated media/model-list additions and a
freshly approved same-service restart binding under ADR-0022 section 8.7. Selected
model bytes, input, launch/configuration, scope, budget and the one-send limit remain
unchanged. Old records remain immutable; consumed/UNKNOWN cases cannot be retried.
Current runtime evidence must match the new exact binding before permission becomes
active. No new live send is recorded by this implementation checkpoint.

The Owner authorized bounded CI optimization after PR #95 passed all five required
checks and merged. Only an exact isolated-test allowlist may use affected selection;
production and CI changes still run full suites. Six workers rebalance full
Integration coverage without removing tests. D1 host/input wiring is merged at
`c4c30eb785a5c342e92ae359e50bd8e482048350`; this is not a live result.

Current work is the bounded D1 repair, direct CPU validation and protected
publication, followed by the already authorized exact-run gates. It does not open
another implementation wave or authorize the separate M12 A100 wave.

## 2. Merged engineering evidence — do not redo

| Scope | Published checkpoint | What it proves / what it does not prove |
| --- | --- | --- |
| R2/F01, PR #89 | `3e5b8d08d3eef26506a69be99c42c90f38826cc0` | Accepted CPU/fixture-owned loopback engineering; not a live SH09 result |
| R3/F01, PR #90 | `0b3a0653794656658abac8a7455eeed5801802fe` | Exact offline binding/runtime seam and bounded correction; not current GPU binding |
| D1, PR #91 | `2c42645a173840d6e17e2eb3541f00f47b2881b5` | Original live Operator and bounded recovery path; not execution approval |
| D1 binding fix, PR #92 | `1e62786ea75823869c97934b18e22d722b7949f9` | Seven existing-store reader binding; not a real Grant or generated result |
| D1 zero-send replacement, PR #97 | `f481180264a360fe18aa2cfb13e2c20ca1c75244` | Original Attempt closed FAILED/zero-send; replacement not issued; no video |

These are observed merged commits, not predicted SHAs for this maintenance change.
Use the [R2 record](docs/status/A14B_STAGED_TRANSPORT_IMPLEMENTATION_2026-09-12.md),
[R3 record](docs/status/SH09_EXACT_OFFLINE_BINDING_R3_2026-09-13.md) and
[ADR-0022](governance/ADR-0022-generation-dispatch-grant.md) for exact scope.
Package 1/2/3 and their candidate-specific failures/closures remain historical
evidence. No new implementation or acceptance of those packages is required.

## 3. Runtime observation versus remaining D1 gates

The 2026-09-13 deployment/read-only receipts record service/input/model/node
metadata, the bounded SSH forwarding correction and HTTP GET connectivity.
At 11:27:59 UTC the observed queue contained one running item and zero pending
items; its origin was not established. This is a timestamped observation, not a
current empty-queue guarantee or permission to interrupt somebody else's job.

The earlier D1 statement that the service and anchor were absent is superseded as
a current observation, not erased from its original evidence. Metadata and SSH
reachability do not establish `SYSTEM_RUNTIME_BOUND`, exact Camera/plan approval,
complete cost/window enforcement, a live Grant, SH09 output or Spike-0 PASS.

Next in the same D1: complete the original Operator's read-only prepare and exact
single-run application; resolve any missing approval/configuration field explicitly.
Do not rebuild transport, invent a parallel worker, repeat frozen-package searches
or use synthetic tests as live-generation evidence.

## 4. Audit debt disposition

The 2026-09-13 full-project audit is retained as dated evidence. This table records
disposition, not new implementation authority or final Owner acceptance.

| Finding | Present disposition | Bounded follow-up |
| --- | --- | --- |
| AUD-001: dispatch consumer gap | Code connected in PR #91/#92; live proof still open | Finish D1's original Operator prepare/run gates, not a new dispatch stack |
| AUD-002: Frontend method-aware islands | Open; eight adapter functions were unused at audit time | One separately authorized real product consumer slice |
| AUD-003: Project foundation multi-POST | Core recoverable command exists; Frontend cutover open | Consume existing command; no second Project domain |
| AUD-004: experimental patches | Preserved, not blanket-approved or merged | Reuse only a demonstrated dependency; defer VACE/Phantom expansion |
| AUD-005: old engines/tombstone | Not evidence of a second active production authority | No broad deletion/refactor before the real vertical slice |
| AUD-006: redirected UI remnants | Open Frontend-only cleanup debt | Remove only after checking consumers/tests; preserve compatibility redirects |
| AUD-007: stale task/substring validator | Corrected in this working candidate | Exact current records, duplicate rejection and regression tests |
| AUD-008: dated receipts treated as current | Corrected in this working candidate | Registry classifications; generated index/map; one active task block |
| AUD-009: cold documentation in default reading | Hot-path navigation corrected; history retained | Read only applicable authority and required evidence, not every archived receipt |
| AUD-010: oversized domain modules | Deferred maintenance; not a proven SH09 blocker | Extract only while changing a demonstrated defect |
| AUD-011: Frontend build/CI duplication | Unmeasured optimization debt; no CI weakened | Measure separately before altering build or required checks |
| AUD-012: code/live/approval conflation | Current status wording corrected | Repository PASS, runtime observation and approved result remain distinct |
| AUD-013: commercial security/operations | Open product-readiness work | Existing bearer/workspace guards are not complete SaaS security; no public-production claim |

Nearest sequence: finish this small maintenance candidate; resume the existing D1
read-only prepare and exact run request; after the authorized real result, seek one
Frontend script-to-shot consumer slice. M12 audio, M14/M15 approval/master and
commercial operations remain explicit gaps, not prerequisites invented for the
bounded silent SH09 technical experiment and not silently declared implemented.

## 5. Scoped baselines and immutable history

The [capability matrix](docs/status/M1-M19-CAPABILITY-STATUS.md) separates architecture,
backend, runtime, Frontend, product and production. The
[cross-repository baseline](docs/status/CROSS_REPOSITORY_BASELINE.md) preserves the
closed K2 compatibility pin and immutable M13 behavior tag; neither is advertised
as today's Core or Frontend branch HEAD. No Frontend pin is changed here.

Earlier current-state projections remain recoverable in
[the pre-maintenance Git revision](https://github.com/lpjiayou/AI-Cinematic-Studio/blob/1e62786ea75823869c97934b18e22d722b7949f9/CURRENT_MILESTONE.md).
The [original history](CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md) remains
byte-for-byte unchanged, including its failures and checkpoint-scoped permissions.

```text
HISTORICAL_SECTION_SHA256=5e05b68e83ed55f90b342aee627001a7bbf66cf59f92e5106270175b07f61f6a
HISTORICAL_DOCUMENT_GRANTS_CURRENT_AUTHORITY=false
HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true
```

Repository checks and scoped testing follow [AGENTS.md](AGENTS.md). This mixed
documentation/validator change is not the docs-only CI fast path; required contexts
and fail-closed safety checks remain unchanged.
