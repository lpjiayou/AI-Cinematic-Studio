# M10/M11 Method-Aware Job Result Intake E2 — 2026-09-06

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / REQUIRED_CI_GATE`

Owner: `Project Lead / V4 Media Job Owner / M10-M11 Result Intake Owner`

Task: `ACS-M10-M11-METHOD-AWARE-JOB-RESULT-INTAKE-CORRECTIVE-E2`

## Bounded result

An exact current method-aware route can now consume its successful V4 job as a
technical Candidate. The existing Candidate lifecycle owns the new neutral schema.
The V4 reader has only repository reads and controlled file verification; it cannot
dispatch, retry, recover, cancel or call an Adapter. Runtime facts remain in V4.

This implements the handoff under [ADR-0019](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md),
the [M3–M11 contract](../../architecture/M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md),
and the [module responsibility matrix](../../architecture/module-responsibility-matrix.md).
It creates no new authority, architecture decision, queue, database or table.
The [E1 receipt](M10_M11_METHOD_AWARE_WORKER_SEAM_CORRECTIVE_E1_2026-09-06.md)
continues to describe worker/adapter execution and historical compatibility.

```text
CORE_START_MAIN=d6c60f9de11c5bf4df559f71c43f86b40e8211ad
CORE_START_TREE=b19fa07ec47921aa04d884c834e4115e2bb2ae2c
METHOD_AWARE_WORKER_SEAM_E1=IMPLEMENTED_AND_VERIFIED
METHOD_AWARE_JOB_RESULT_INTAKE_E2=IMPLEMENTED_AND_VERIFIED
METHOD_AWARE_JOB_RESULT_TO_V5_CANDIDATE_PATH=IMPLEMENTED_AND_VERIFIED
METHOD_AWARE_JOB_STATUS_PROJECTION=IMPLEMENTED_AND_VERIFIED
TECHNICAL_CANDIDATE_HANDOFF=IMPLEMENTED_AND_VERIFIED
V4_METHOD_AWARE_JOB_STATUS_SCHEMA=v4.method-aware-media-job-status.v1
V4_METHOD_AWARE_JOB_RESULT_SCHEMA=v4.method-aware-media-job-result.v1
METHOD_AWARE_MEDIA_JOB_RESULT_RECORD_KIND=MethodAwareMediaJobResult
METHOD_AWARE_MEDIA_JOB_RESULT_RECEIPT_SCHEMA=v5.method-aware-media-job-result-receipt.v1
METHOD_AWARE_VIDEO_CANDIDATE_SCHEMA=v5.method-aware-video-candidate.v1
METHOD_AWARE_VIDEO_JOB_PROJECTION_SCHEMA=v5.method-aware-video-job-projection.v1
```

## Exact binding and evidence ownership

| Owner | Verified responsibility | Excluded authority |
| --- | --- | --- |
| V4 result reader | v3 SUCCEEDED, one exact attempt, no lease/commit intent, request/envelope/backend/registry identity, artifact root and regular-file checks, fresh bytes/SHA/probe, execution evidence digest | No worker, Provider, queue mutation or recovery |
| V5 intake | Current route/input/method/source lineage, exact queued job/request and client concurrency digests; stable receipt refs/digests | No legacy RealVideoRevision or Provider Experiment dependency |
| Existing Candidate lifecycle | New `AI_GENERATED` Candidate, one source AssetVersion, route version as revision, Shot as slot, TechnicalValidation PASS | No automatic Semantic QC, selection, admission or AssetVersion |
| Public boundary | GET exact route-referenced job projection; POST closed eight-field intake command | No queue browser, provider selector, job controls or browser artifact authority |

V4 hashes and probes the artifact again using a restricted local MP4 demuxer,
bypassing the existing probe cache. The narrow `media_jobs.py` change only exposes
that fresh read mode; dispatch, lease, worker, retry, cancellation, recovery and
artifact commit functions are unchanged. Paths, credentials, raw provider request
IDs and runtime facts never enter the new receipt or public job projection.

The receipt binds the route, request, source, job, attempt and artifact using stable
refs and digests. The new Candidate does not impersonate a RealVideoRevision and
has no `consumedRealVideoRevision`. Both self-hosted and external fake adapters use
the same Candidate schema and provenance, without a V5 provider branch.

## Atomicity and replay

V4 is already terminal and remains unchanged. V5 captures its existing record
journal head, validates current lineage and atomically appends one result receipt,
one Candidate and one TechnicalValidation. A concurrent change fails the journal
comparison. A racing identical intake may return the winning complete batch;
there is no partial-batch completion or append retry.

An exact original idempotency key replays the same three records. A different key
for the same exact job/result reuses them without a new record. Changing a recorded
key's command conflicts; changing an already received job's result conflicts.
Response loss and service restart preserve those identities. A newer valid job
for the same Shot creates a new Candidate and the existing journal-order rule
makes the old Candidate stale without rewriting history.

```text
V5_RESULT_RECEIPT_CANDIDATE_VALIDATION_ATOMIC=true
V4_JOB_AND_V5_CANDIDATE_CROSS_DATABASE_ATOMIC=false
ATOMIC_RECORD_COUNT=3
PARTIAL_APPEND_ALLOWED=false
EXACT_REPLAY=PASS
SAME_JOB_DIFFERENT_KEY_REUSE=PASS
CHANGED_RESULT_CONFLICT=PASS
RESPONSE_LOSS_RECOVERY=PASS
SQLITE_RESTART=PASS
METHOD_AWARE_CANDIDATE_PROVENANCE=AI_GENERATED
METHOD_AWARE_CANDIDATE_TOP_LEVEL_PROVIDER_SPECIFIC_FIELD_COUNT=0
METHOD_AWARE_RESULT_V5_PROVIDER_BRANCH_COUNT=0
SECOND_FAKE_BACKEND_RESULT_INTAKE_WITHOUT_V5_CODE_CHANGE=PASS
FUTURE_SECOND_ADAPTER_REQUIRES_V5_DOMAIN_CHANGE=false_for_current_method_aware_path
METHOD_AWARE_RESULT_INTAKE_USES_LEGACY_REAL_VIDEO_PLAN=false
METHOD_AWARE_RESULT_INTAKE_USES_PROVIDER_EXPERIMENT=false
ONE_SHARED_METHOD_AWARE_QUEUE=true
SECOND_NEW_QUEUE_CREATED=false
DATABASE_DDL_DIFF=0
```

## Verification

Before production edits, nine formal tests produced five failures, three errors
and the expected passing legacy-rejection assertion. They demonstrated missing
read/intake resources and missing neutral atomic handoff. Those assertions are
now covered by the expanded reader/currentness/atomicity, contract and real HTTP
tests, using synthetic CPU media, fake adapters and temporary SQLite only.

```text
RESULT_INTAKE_RED_REPRODUCTION=PASS
JOB_PROJECTION_RED_REPRODUCTION=PASS
LEGACY_INTAKE_REJECTION_RED_REPRODUCTION=PASS
SAFE_RESULT_PROJECTION_RED_REPRODUCTION=PASS
ATOMIC_CANDIDATE_HANDOFF_RED_REPRODUCTION=PASS
SECOND_BACKEND_RESULT_INTAKE_RED_REPRODUCTION=PASS
LOCAL_FULL_SUITE_EXECUTED=false
CI_SCOPE=FULL_SUITE
```

Evidence includes all six job states; modified bytes/size/SHA/probe, envelope,
backend/attempt and intent rejection; foreign scope and stale route/input/method/
source/registry rejection; concurrent double submit; rollback after the receipt
insert and before the Candidate insert; a lost HTTP response after commit; closed
server and newly constructed SQLite adapters; exact replay and no V4 mutation.
HTTP negatives include unknown/authority fields, fractional scalars, NaN/Infinity,
duplicate JSON keys and duplicate query parameters. Integration discovery registers
the new file in shard-2 with no basename collision or missing shard file.

## Remaining boundary

One successful isolated intake creates exactly one receipt, Candidate and technical
validation. It creates zero Semantic QC, selection, admission or AssetVersion
records. Those test counts are not live production mutations or live evidence.
The five required CI checks remain the merge gate; this receipt does not predict
its own commit or merge SHA.

```text
FRONTEND_DIFF=0
DEPENDENCY_DIFF=0
WORKFLOW_DIFF=0
E1_WORKER_EXECUTION_SEMANTICS_DIFF=0
LEGACY_REAL_VIDEO_PRODUCTION_DIFF=0
PROVIDER_EXPERIMENT_PRODUCTION_DIFF=0
V5_DIRECT_PROVIDER_PROTOCOL_CALL_COUNT=0
PUBLIC_PROVIDER_SPECIFIC_ROUTE_COUNT=0
SEMANTIC_VISUAL_QC_AUTOMATIC=false
HUMAN_SELECTION_AUTOMATIC=false
ASSET_ADMISSION_AUTOMATIC=false
A100_START_COUNT=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
GPU_OR_PROVIDER_CALLS=0
MODEL_DOWNLOAD_BYTES=0
CURRENT_MAIN_LIVE_EVIDENCE=ABSENT
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
CONTACT_ACTION_RUNTIME=UNAVAILABLE
GAIT_LOCOMOTION_RUNTIME=UNAVAILABLE
MULTI_BACKEND_ARCHITECTURE_REQUIRED=true
MULTI_BACKEND_IMPLEMENTATION_IN_THIS_TASK=false
MULTI_BACKEND_G0_COMPLETE=false
M12_C3_LOCAL_VM_LINE=PAUSED
AUTOMATIC_SUBTITLE_G0=NOT_STARTED
FRONTEND_EXECUTION_LINE=PAUSED
E3_STARTED=false
NEXT_TASK=ACS-M10-M11-SPIKE-0-ELIGIBLE-LINEAGE-PREPARATION-E3
```

Eligible lineage preparation E3, runtime preflight, a live Spike, Frontend and M12
require separate authorization. The current implementation does not authorize any
of them, automatic provider fallback, production auto-routing or publication.
