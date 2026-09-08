# M10 Input Artifact / Execution Configuration Decoupling — E3G

Status: `BOUNDED_IMPLEMENTATION / LOCAL_VALIDATION / REQUIRED_CI_GATE`

Owner: Project Lead / Core Architecture Owner / M10 Input Asset Owner / M11 Execution Configuration Owner

Task: `ACS-M10-M11-INPUT-ARTIFACT-EXECUTION-CONFIG-DECOUPLING-CORRECTIVE-E3G`

## Authority, baseline and preserved failure

```text
CORE_START_MAIN=9c367c476b0486639444435f296407caf1b01bf8
CORE_START_TREE=755a36e73f0b37e254c31bc76fc3eae6889e8b43
FAILURE_EVIDENCE_FOUND=true
FAILURE_EVIDENCE_SHA256=cf11c28f59b50eacf82b59dabea00a6279801291f70cd9323cdd5edbd6b32bbb
R6_VALID_PREFIX_PRESERVED=true
R6_LIVE_DATA_MUTATION_COUNT=0
R6_RESUMED=false
CI_SCOPE=FULL_SUITE
```

The frozen R6 valid upstream prefix and its failed ProductionRun request remain
unchanged. E3G does not retry that request, write its databases, reinterpret its
failure as success or authorize R6/E4. The one production correction is limited to
configuration ownership in `create_method_aware_coordinator_from_environment()`.
This receipt does not predict its own commit, pull request or merge identity.

## Root cause and bounded correction

Before the correction, a fresh temporary composition supplied a valid E3A artifact
bundle, real synthetic PNG bytes and exactly the three existing input settings. The
real production environment factory rejected it with
`BackendValidationError: method-aware backend registry is missing`. The input bundle
was complete; no execution setting was supplied. This is the formal red reproduction.

The registry-presence predicate now excludes only these exact existing input names:

```text
CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH
CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_SHA256
CREATOR_METHOD_AWARE_SOURCE_ROOT
```

`CREATOR_METHOD_AWARE_SOURCE_ROOT` remains available to a configured execution
adapter, but is not itself an execution-enablement signal. The E3A evidence loader
still receives the complete environment first and retains all three-value, file,
digest, schema, containment and byte checks. No input prefix wildcard is exempt.
Unknown `CREATOR_METHOD_AWARE_*` or `METHOD_AWARE_COMFYUI_*` names and every nonempty
partial execution configuration still require a registry and fail closed.

No environment variable, mode, registry schema, backend profile, provider fact,
credential, queue, retry, route or database definition was added. With no execution
configuration, the composition retains `UnavailableMethodAdapter` and
`UnavailableBackendResolver`; it does not construct a fake registry, executable
adapter, CPU fallback or provider-experiment bridge. The worker `run-one` CLI still
requires both registry arguments and cannot execute with unavailable configuration.

## Input-only lifecycle and execution stop proof

An isolated integration creates no target input records in advance. It uses the
actual environment factory, real temporary SQLite files, an authenticated public
HTTP server with `allow_internal_routes=false`, a digest-pinned synthetic image
bundle and an explicit test-only external selection authority. Public calls create
the existing Candidate/TechnicalValidation batch, semantic QC, HumanSelection,
Admission/AssetVersion batch and MethodAwareInputPlan. Candidate, Admission and
InputPlan exact replay add no records. AssetVersion retains
`providerProcessingAuthorized=false` and `publicationAllowed=false`; the input plan
reads back `CURRENT` with one READY action anchor.

The READY request then reaches the actual backend resolver and returns the existing
stable `worker_unavailable` response. Evidence records, VideoMethodRoute rows,
MediaJob rows and Attempts have zero delta; `UnavailableMethodAdapter.generate` and
provider transport have zero calls. A fixed fully qualified test-module entrypoint
starts a new Python interpreter against the same temporary data root. It reopens the
real environment composition, replays Candidate/Admission/InputPlan without writes,
reads the plan as CURRENT and again rejects routing with zero queue/attempt/provider
delta. Test HTTP servers stop, the child exits and test token references are cleared.

The configured E1 path remains separate. Its existing registry, credential,
attestation, model, adapter, exact one-attempt job and same-repository checks pass.
A dedicated successful fake-loopback execution uses the expected five simulated
HTTP requests (system facts, object info, prompt, history and artifact read); these
are not real Provider or GPU calls. Invalid model, attestation, profile and probe
cases remain zero-provider-call pre-execution failures.

## Focused verification and unchanged contracts

```text
INPUT_ONLY_FACTORY_RED_REPRODUCTION=PASS
CONFIGURATION_OWNERSHIP_PREDICATE_CORRECTED=true
NEW_ENVIRONMENT_VARIABLE_COUNT=0
INPUT_ONLY_FULL_ENVIRONMENT_FACTORY_STARTUP=PASS
INPUT_ONLY_AUTHENTICATED_CANDIDATE_INTAKE=PASS
INPUT_ONLY_QC_SELECTION_ADMISSION=PASS
INPUT_ONLY_INPUT_PLAN_CURRENTNESS=PASS
INPUT_ONLY_EXACT_REPLAY=PASS
INPUT_ONLY_REAL_PROCESS_RESTART=PASS
INPUT_PARTIAL_CONFIG_REJECTION=PASS
INPUT_TAMPER_AND_SCOPE_REJECTION=PASS
EXECUTION_PARTIAL_CONFIG_REJECTION=PASS
EXECUTION_INVALID_CONFIG_REJECTION=PASS
UNKNOWN_RELATED_CONFIG_REJECTION=PASS
WORKER_REGISTRY_REQUIREMENT_PRESERVED=PASS
UNAVAILABLE_BACKEND_PRESERVED=PASS
READY_INPUT_WITHOUT_BACKEND_ROUTE_REJECTION=PASS
REJECTED_EXECUTION_QUEUE_DELTA=0
REJECTED_EXECUTION_ATTEMPT_DELTA=0
INPUT_ONLY_PROVIDER_HTTP_REQUEST_COUNT=0
REGRESSION_SIMULATED_PROVIDER_REQUEST_COUNT=5
REAL_PROVIDER_CALL_COUNT=0
PUBLIC_ROUTE_SET_DIFF=0
PUBLIC_RESOURCE_SET_DIFF=0
PUBLIC_REQUEST_SCHEMA_DIFF=0
INPUT_AUTHORITY_SCHEMA_DIFF=0
BACKEND_REGISTRY_SCHEMA_DIFF=0
DATABASE_DDL_DIFF=0
QUEUE_COUNT_SEMANTICS_DIFF=0
FRONTEND_DIFF=0
WORKFLOW_DIFF=0
DEPENDENCY_DIFF=0
LOCAL_FULL_SUITE_EXECUTED=false
```

New unit, contract and integration tests cover the corrected partition, exact
exemption, unknown/partial/invalid execution settings, real factory lifecycle,
failure atomicity and new-process replay. Existing E1, E2 and E3A focused modules,
integration-shard exact coverage and cross-level module namespace checks pass. The
five document validators, changed-file compilation, diff check and secret scan are
required before the pull request. The complete suite remains the one pull-request
CI gate.

Only `services/v4_platform/method_aware_worker.py` changes production behavior.
`episode_production/public.py`, the public route/resource/request contracts, input
authority schemas, backend registry validation, MediaJob/Attempt persistence and
method-aware routing algorithms are unchanged.

```text
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
R6_RESUMED=false
E4_STARTED=false
A100_START_COUNT=0
COMFYUI_START_COUNT=0
```

After verified merge and cleanup, the only named next task is
`E3_R6_VALID_PREFIX_COMPATIBILITY_CHECK_AND_EXPLICIT_RESUME`. It requires separate
authorization and must begin with the preserved-prefix compatibility check; E3G
does not grant any live-lineage write or execution authority.
