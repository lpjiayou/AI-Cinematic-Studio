# M10/M11 Method-Aware Worker Seam E1 — 2026-09-06

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / REQUIRED_CI_GATE`

Owner: `Project Lead / V4 Media Job Owner / M10-M11 Method-Aware Owner`

Task: `ACS-M10-M11-METHOD-AWARE-COMFYUI-WORKER-SEAM-CORRECTIVE-E1`

## Bounded result

The existing shared MediaJob repository now reserves new method-aware work with a
server-selected backend binding. The exact worker builds a neutral execution
envelope, persists the attempt binding before execution and produces only a V4
technical artifact. Focused tests use fake adapters, ephemeral loopback HTTP and
synthetic CPU media. They do not establish live GPU capability or production cost.

The controlling boundaries remain [ADR-0019](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md),
the [M3–M11 contract](../../architecture/M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md)
and the [module responsibility matrix](../../architecture/module-responsibility-matrix.md).
This receipt records an implementation checkpoint; it creates no architecture or
execution authority and does not predict its own merge SHA.

```text
CORE_START_MAIN=35d48ab2a00e8c0580b798b0d4fea8890cda24f8
CORE_START_TREE=6f544d4232576ab01547054ba8304167d87c0f26
METHOD_AWARE_WORKER_SEAM_E1=IMPLEMENTED_AND_VERIFIED
METHOD_AWARE_COMPOSITION_I2V_SEAM=IMPLEMENTED
METHOD_AWARE_WORKER_ENTRYPOINT=IMPLEMENTED
METHOD_AWARE_REQUEST_WORKER_CONTRACT=COMPATIBLE
ONE_MEDIA_JOB_AUTHORITY=true
ONE_SHARED_METHOD_AWARE_QUEUE=true
METHOD_AWARE_QUEUE_STORE_COUNT=1
SECOND_NEW_QUEUE_CREATED=false
PROVIDER_EXPERIMENT_QUEUE_REUSED=false
ATTEMPT_LEVEL_PROVIDER_BINDING=COMPLETE_FOR_NEW_METHOD_AWARE_JOBS
BACKEND_BINDING_PERSISTED_BEFORE_ADAPTER=true
BACKEND_BINDING_IMMUTABLE=true
CREDENTIAL_SECRET_PERSISTED=false
JOB_SCHEMA_HARD_CODES_SINGLE_GPU=false
JOB_SCHEMA_HARD_CODES_A100=false
```

## Ownership and compatibility

| Component | Responsibility | Evidence |
| --- | --- | --- |
| V5 method-aware route | Current scope, Shot/beat, admitted AssetVersion refs/digests, camera/action and existing run output constraints | Existing HTTP/currentness/replay tests and second external fake backend injection |
| V4 backend registry | Operator-pinned backend, profile, credentials **reference**, runtime/model digests, cost ceiling and resource shape | Closed registry, stable digest, method rejection and changed-binding conflict tests |
| V4 envelope builder | Canonical closed JSON; strict integers; source bytes/probe; exact semantic/profile/binding agreement | Missing/changed source, malformed output, fractional/non-finite values and digest/extra-field negatives |
| Shared coordinator | One exact claim, fenced immutable attempt, artifact commit intent, terminal failure/recovery | Real SQLite restart, no unrelated queue mutation, commit recovery and pre-call durable binding |
| I2V adapter | ComfyUI protocol/nodes, model parameters, exact runtime checks, source staging and normalized technical evidence | Production CLI against fake loopback with LoadImage and exact output frames |

Public route/resource sets and the public method-aware v1 schemas are unchanged.
Existing adapter capability/identity fields now come from the injected resolver.
`wanFallbackUsed=false` remains a legacy-compatible display field and never an
execution input. Historical v1/v2 jobs remain readable and are not rewritten.
New method-aware jobs use JSON v3 in the existing SQLite DDL. Legacy Provider
Experiment execution/store and Candidate/AssetVersion/Admission authorities are
unchanged. An unavailable backend cannot reserve a fake CPU/T2V job.

```text
BACKEND_RESOLVER_SCHEMA=v4.video-execution-backend-registry.v1
BACKEND_ROUTE_DECISION_SCHEMA=v4.video-execution-backend-route-decision.v1
EXECUTION_ENVELOPE_SCHEMA=v4.method-aware-media-execution-envelope.v1
MEDIA_JOB_SCHEMA_VERSION=v4.media-job.v3
ATTEMPT_BACKEND_BINDING_SCHEMA=v4.execution-attempt-backend-binding.v1
SECOND_FAKE_ADAPTER_WITHOUT_V5_CODE_CHANGE=PASS
FUTURE_SECOND_ADAPTER_REQUIRES_V5_DOMAIN_CHANGE=false_for_current_method_aware_path
MULTI_BACKEND_PRODUCTION_AUTO_ROUTING=false
MULTI_BACKEND_G0_COMPLETE=false
```

The schema can describe CPU, a self-hosted single GPU, independent GPU worker
pools, cloud workers and external APIs. Resource minima are expressed in bytes. Only the configured ComfyUI I2V production
factory is installed in E1. A future second adapter is registered in V4; this does
not require changing the current V5 semantic path. Distributed inference and
provider webhook orchestration remain unimplemented, and adding a second real
backend or automatic routing requires the separately authorized multi-backend G0.

## Worker and server configuration

The production entrypoint is `services.v4_platform.method_aware_worker`. This is
an operator reference, not permission to run a real backend:

```sh
python -m services.v4_platform.method_aware_worker run-one \
  --job-ref "$TASK_JOB_REF" --workspace-ref "$TASK_WORKSPACE_REF" \
  --production-run-ref "$TASK_RUN_REF" --worker-ref "$TASK_WORKER_REF" \
  --queue-db "$TASK_QUEUE_DB" --artifact-root "$TASK_ARTIFACT_ROOT" \
  --backend-registry-manifest "$TASK_BACKEND_MANIFEST" \
  --backend-registry-sha256 "$TASK_BACKEND_MANIFEST_SHA256" --max-attempts 1
```

| Server setting | Meaning |
| --- | --- |
| `CREATOR_METHOD_AWARE_BACKEND_REGISTRY` / `_SHA256` | Exact server manifest file and byte digest; also supplied by worker CLI |
| `CREATOR_METHOD_AWARE_SOURCE_ROOT` | Digest-addressed source bytes, never a source of AssetVersion identity |
| `METHOD_AWARE_COMFYUI_BASE_URL` | Server-held endpoint, kept outside V5 and job payloads |
| `METHOD_AWARE_COMFYUI_INPUT_ROOT` / `_MODEL_ROOT` | Adapter-owned staging and model locations |
| `METHOD_AWARE_COMFYUI_RUNTIME_ATTESTATION` | Complete exact v2 I2V attestation file |
| `METHOD_AWARE_COMFYUI_COST_MINOR_PER_ATTEMPT` | Explicit nonnegative integer, bounded by the pinned attempt ceiling |
| `credentialSourceRef=env:<name>` | Resolve a credential from server environment; persist only its reference |

The application passes its existing `CREATOR_MEDIA_JOB_DATA_PATH` repository into
the V4 factory. No method-aware database is created by that factory. Worker CLI
requires the existing queue and validates its schema with initialization disabled.
Exit codes are 0 (SUCCEEDED), 1 (FAILED), 2 (rejected/unclaimable/configuration),
3 (CANCELLED). Safe output contains the job ref, state and attempt count only.

```text
WORKER_EXECUTION_MODE=EXACT_SINGLE_JOB_ONE_ATTEMPT
EXACT_SINGLE_JOB_CLAIM=true
WHOLE_QUEUE_EXECUTION_ALLOWED=false
PRE_EXECUTION_VALIDATION_BEFORE_RUNNING=true
INVALID_ENVELOPE_PROVIDER_CALL_COUNT=0
INVALID_ENVELOPE_RUNNING_ORPHAN_COUNT=0
REMOTE_SUBMISSION_RESPONSE_LOSS_AUTO_RETRY=false
UNKNOWN_SUBMISSION_SECOND_POST_COUNT=0
AUTOMATIC_FAILOVER_ALLOWED=false
METHOD_AWARE_COMFYUI_ADAPTER_CLASS=ComfyUIWan22ImageToVideoAdapter
METHOD_AWARE_BASE_T2V_ADAPTER_USED=false
SILENT_T2V_SUBSTITUTION_COUNT=0
```

Preflight errors persist `FAILED / PRE_EXECUTION_VALIDATION_FAILED` with no adapter
call. A lost submit response persists `FAILED / REMOTE_SUBMISSION_INDETERMINATE`,
non-retryable. SIGTERM during execution closes as a non-retryable failure. A hard
process death leaves the durable lease/attempt; an exact restart before expiry
rejects the claim, and after expiry fails an unknown submission without resending.
A verifiable durable artifact commit intent can recover its artifact without a
second provider call. Existing heartbeat, fencing and quarantine rules remain.

## Versioned attestation and archive

Legacy exact `v4.comfyui-runtime-attestation.v1` T2V remains readable unchanged.
Version 2 requires `capabilityMode=TEXT_TO_VIDEO|IMAGE_TO_VIDEO`; I2V requires all
11 nodes including `LoadImage`, plus the exact `startImageCapability` fact. The
shared V4 validator rejects missing/extra fields, altered digests and mode
mismatch. Archive cross-file checks also require `LoadImage.image` and the Wan
`start_image` port. Original attestation bytes and complete facts are retained in
the archive and covered by its manifest digest. No field stripping is permitted.

```text
I2V_ATTESTATION_SCHEMA=v4.comfyui-runtime-attestation.v2
I2V_ARCHIVE_VALIDATION=PASS
LEGACY_T2V_ARCHIVE_COMPATIBILITY=PASS
I2V_LOAD_IMAGE_REQUIRED=true
I2V_START_IMAGE_CAPABILITY_REQUIRED=true
ATTESTATION_FIELD_STRIPPING_ALLOWED=false
```

## Verification and remaining boundary

The first nine regressions ran against unchanged production code and returned
seven failures and two errors. They exposed the missing worker/bridge/composition
ports, absent attempt binding, second-adapter rejection, I2V archive rejection
and the actual `KeyError('mediaKind')` after persisting RUNNING. The safety
assertions now pass and are expanded into exact worker, registry, envelope,
archive, real SQLite/CLI and loopback tests.

```text
WORKER_SEAM_RED_REPRODUCTION=PASS
REQUEST_BRIDGE_RED_REPRODUCTION=PASS
RUNNING_ORPHAN_VECTOR_RED_REPRODUCTION=PASS
I2V_ARCHIVE_RED_REPRODUCTION=PASS
SECOND_ADAPTER_V5_LOCK_IN_RED_REPRODUCTION=PASS
LOCAL_BACKEND_RESOLVER_TESTS=PASS
LOCAL_EXECUTION_ENVELOPE_TESTS=PASS
LOCAL_ATTEMPT_BINDING_TESTS=PASS
LOCAL_EXACT_WORKER_TESTS=PASS
LOCAL_NO_RETRY_TESTS=PASS
LOCAL_METHOD_AWARE_COMPOSITION_TESTS=PASS
LOCAL_I2V_ATTESTATION_ARCHIVE_TESTS=PASS
LOCAL_MEDIA_JOB_REGRESSION=PASS
LOCAL_PROVIDER_EXPERIMENT_REGRESSION=PASS
LOCAL_METHOD_AWARE_REGRESSION=PASS
LOCAL_INTEGRATION_SHARD_AUDIT=PASS
LOCAL_DOC_GOVERNANCE=PASS
LOCAL_COMPILE=PASS
GIT_DIFF_CHECK=PASS
LOCAL_FULL_SUITE_EXECUTED=false
PUBLIC_ROUTE_SET_DIFF=0
PUBLIC_RESOURCE_SET_DIFF=0
FRONTEND_DIFF=0
DEPENDENCY_DIFF=0
WORKFLOW_DIFF=0
DATABASE_DDL_DIFF=0
CANDIDATE_AUTHORITY_DIFF=0
ASSET_VERSION_AUTHORITY_DIFF=0
ADMISSION_AUTHORITY_DIFF=0
CANONICAL_REGISTRATION_DIFF=0
PROVIDER_EXPERIMENT_PRODUCTION_DIFF=0
V5_DIRECT_PROVIDER_PROTOCOL_CALL_COUNT=0
PROVIDER_SPECIFIC_PUBLIC_ROUTE_COUNT=0
METHOD_AWARE_JOB_RESULT_TO_V5_CANDIDATE_PATH=ABSENT_NOT_IN_E1
CANDIDATE_MUTATION_COUNT=0
ASSET_VERSION_CREATED=false
ASSET_ADMISSION_COUNT=0
CANONICAL_MUTATION_COUNT=0
A100_START_COUNT=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
GPU_OR_PROVIDER_CALLS=0
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
CONTACT_ACTION_RUNTIME=UNAVAILABLE
GAIT_LOCOMOTION_RUNTIME=UNAVAILABLE
NEXT_TASK=ACS-M10-M11-METHOD-AWARE-JOB-RESULT-INTAKE-CORRECTIVE-E2
```

Counts above concern real runtime/domain work; isolated test fixtures intentionally
create synthetic domain lineage and fake HTTP requests. E1 makes no current
Candidate, AssetVersion, Selection, Admission, Master or Export. Result intake,
eligible Spike lineage, A100/runtime verification and execution cost authority
remain blockers. E2, GPU preflight, live Spike, Frontend, M12-C3 and subtitles are
separate tasks and are not started by this checkpoint.
