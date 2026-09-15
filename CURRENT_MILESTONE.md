# AI Cinematic Studio — Current Execution State

Status: `CURRENT / EVIDENCE-BACKED / FAIL-CLOSED`; reviewed: `2026-09-15`

## 1. Active task and boundaries

Only the block below is the machine-checked current execution projection.
Dated receipts retain their original checkpoint meaning; they are not additional
current-task overrides. This update records progress and existing authorization,
not a new Grant, feature acceptance or production-readiness decision.

<!-- CURRENT_STATE:BEGIN -->
```text
CURRENT_TASK=ACS-IMAGE-DESCRIPTION-VIDEO-LOOP
CURRENT_ACTION=IMPLEMENTED_CPU_AND_HTTP_BROWSER_VERIFIED_CANDIDATE
NEXT_TASK=PUBLISH_AND_BIND_BOUNDED_IMAGE_VIDEO_INSTALLATION_WHEN_AUTHORIZED
REVIEWED_MAIN=06a28c8de086a30db2d33b28f1ee34b7890973ac
REVIEWED_TREE=a6cbc9b431c9ff1ff65d5261448e3259721c0eea
ADR_0022_ACCEPTED_VERSION=1.10_BOUNDED_IMAGE_DESCRIPTION_VIDEO
R2_F01_ENGINEERING=ACCEPTED_WITHIN_CPU_FIXTURE_SCOPE_AND_MERGED
R3_F01_ENGINEERING=MERGED
D1_OPERATOR_CODE=MERGED
D1_SEVEN_STORE_BINDING_FIX=MERGED
ORIGINAL_EVIDENCE_AVAILABILITY=RESOLVED
D1_BOUNDED_DEPLOYMENT=OWNER_AUTHORIZED
D1_EXISTING_DATA_BINDING=ORIGINAL_CUSTODY_WORKSET_BOUNDED_AUTHORIZATION
D1_SELECTED_SSH_FORWARD_TARGET=127.0.0.1:8188
D1_RUNTIME_OBSERVATION=DATED_READ_ONLY_METADATA_ONLY
D1_EXACT_RUN_REQUEST=EXECUTED_ONCE_ORIGINAL_JOB_SUCCEEDED
SH09_TECHNICAL_VIDEO=OWNER_ACCEPTED
D1_UI=PUBLISHED_EXISTING_SH09_PLAYBACK_VERIFIED
IMAGE_DESCRIPTION_VIDEO=IMPLEMENTED_CPU_LOOPBACK_AND_BROWSER_VERIFIED_NOT_LIVE_DEPLOYED
IMAGE_VIDEO_OPERATOR=REUSE_ORIGINAL_NO_SECOND_QUEUE
IMAGE_VIDEO_NEW_LIVE_WINDOW=NOT_INSTALLED_OR_ISSUED_BY_THIS_RECORD
IMAGE_VIDEO_FAILURE_AUTO_RETRY=false
ORIGINAL_SH09=IMMUTABLE_NO_REGENERATION
D1_COMPLETE=false
SYSTEM_RUNTIME_BOUND=false
PROMPT_SUBMISSION_AUTHORIZED=false
SPIKE_0_EXECUTED=false
SPIKE_0_READINESS=BLOCKED_PENDING_EXACT_RUN_GATES
FORMAL_DATABASE_WRITES_AUTHORIZED=false
LIVE_GRANT_ISSUED=true
LIVE_GRANT_CONSUMED=true
OUTPUT_ASSET_ADMISSION_ALLOWED=false
PUBLICATION_ALLOWED=false
D2_D3=QUEUED_NOT_AUTHORIZED
FRONTEND_IMPLEMENTATION_IN_THIS_TASK=IMAGE_DESCRIPTION_GENERATE_PLAYBACK_AUTHORIZED
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

The original Operator completed SH09 at `2026-09-15T04:02:33Z`: one successful
Attempt, 49 native frames, and a 704x1280 MP4 containing 48 frames at 24 fps (2 s).
The delivered video digest is
`c2e047eaa5b5936a8f3f2356b49b2a1ef8416ed775c2b89a51fcbb91df7a046f`.
The Owner accepted this technical video and explicitly authorized UI/API wiring
and the minimal ADR-0022 amendment. It is not Asset admission, Master/Export,
publication approval, or permission for another GPU submission. Prior failures,
revocation, replacement and UNKNOWN records remain immutable historical evidence.

Core PR #100 and Frontend PR #33 published the authenticated original-job UI;
the existing SH09 video plays through that chain without another generation.
The Owner now expressly authorizes the minimal ADR-0022/direct-contract amendment
and image + description → independent Job → original Operator → playback slice.
Reuse the original queue, lifecycle, result and cost boundaries; preserve SH09.
Host-installed bounded policy plus an authenticated, exact-input click must still
pass currentness, cost and one-attempt checks. This record creates no paid window
or Grant. Validate with isolated CPU/loopback data; no formal 8765 database access.

The candidate now implements authenticated image upload and description binding,
an independent Job through the original Operator, bounded cost reservation,
one-attempt execution and same-page playback. CPU/fixture-owned loopback and real
HTTP browser checks passed, including refresh and restart recovery; this is not
new GPU output evidence. Failed or uncertain jobs are not automatically resent.
The original SH09 remains unchanged. Publication, deployed installation and a new
paid execution window are not established by these candidate checks.

The Owner authorized bounded CI optimization after PR #95 passed all five required
checks and merged. Only an exact isolated-test allowlist may use affected selection;
production and CI changes still run full suites. Six workers rebalance full
Integration coverage without removing tests. D1 host/input wiring is merged at
`c4c30eb785a5c342e92ae359e50bd8e482048350`; this is not a live result.

The bounded UI adapter does not reopen transport/Operator implementation, open a
new production wave, or authorize the separate M12 A100 wave.

## 2. Merged engineering evidence — do not redo

| Scope | Published checkpoint | What it proves / what it does not prove |
| --- | --- | --- |
| R2/F01, PR #89 | `3e5b8d08d3eef26506a69be99c42c90f38826cc0` | Accepted CPU/fixture-owned loopback engineering; not a live SH09 result |
| R3/F01, PR #90 | `0b3a0653794656658abac8a7455eeed5801802fe` | Exact offline binding/runtime seam and bounded correction; not current GPU binding |
| D1, PR #91 | `2c42645a173840d6e17e2eb3541f00f47b2881b5` | Original live Operator and bounded recovery path; not execution approval |
| D1 binding fix, PR #92 | `1e62786ea75823869c97934b18e22d722b7949f9` | Seven existing-store reader binding; not a real Grant or generated result |
| D1 zero-send replacement, PR #97 | `f481180264a360fe18aa2cfb13e2c20ca1c75244` | Original Attempt closed FAILED/zero-send; replacement not issued; no video |
| D1 restart recovery, PR #99 | `3b49476705f2e9e92ae74c5afca4d6a70ea6392c` | Published correction; subsequent original Operator produced the accepted technical SH09 video |

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

These old observations are not the current SH09 result. The existing video is
already bound to the published UI. Current work creates separate technical inputs
and Jobs, never reuses or regenerates SH09. Do not rebuild transport, repeat frozen
package searches or use synthetic browser tests as live-generation evidence.

## 4. Audit debt disposition

The 2026-09-13 full-project audit is retained as dated evidence. This table records
disposition, not new implementation authority or final Owner acceptance.

| Finding | Present disposition | Bounded follow-up |
| --- | --- | --- |
| AUD-001: dispatch consumer gap | Original Operator connected; one technical live SH09 succeeded | UI adapter candidate and bounded deployment; no new dispatch stack |
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

Nearest sequence: implement and directly validate the authorized image/description
input through the existing Operator and result playback, preserving cost and
duplicate-submit limits. The broader script-to-shot consumer, M12 audio, M14/M15
approval/master and commercial operations remain explicit gaps; they are neither
prerequisites for this bounded technical slice nor silently declared implemented.

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

Repository checks and scoped testing follow [AGENTS.md](AGENTS.md). This runtime/UI
integration is not the docs-only CI fast path; required contexts
and fail-closed safety checks remain unchanged.
