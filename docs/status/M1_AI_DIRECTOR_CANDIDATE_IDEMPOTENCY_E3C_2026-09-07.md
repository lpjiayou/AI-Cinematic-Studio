# M1 AI Director Candidate Idempotency E3C — 2026-09-07

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / REQUIRED_CI_GATE`

Owner: `Project Lead / Creator Application Owner / M1 AI Director Owner`

Task: `ACS-M1-AI-DIRECTOR-CANDIDATE-IDEMPOTENCY-AND-ISSUANCE-RECEIPT-CORRECTIVE-E3C`

## Reproduced gap and correction

The quarantined E3 R4 check returned two random candidate refs for identical keyed
requests. A formal authenticated HTTP/SQLite module was created in the working
tree before production edits: seven assertions failed (identity drift, duplicate
generation, missing durable receipt, unknown fields, duplicate JSON keys, restart
drift and unissued-source confirmation); the unkeyed compatibility control passed.
The original red log SHA-256 is
`3d2c1635d172dfaca0d104ed9b141cb756c834976a943297098fbcbb35ea74ea`.

Creator Application now owns the non-authoritative command/issuance service.
Its optional storage adapter lives under Series/Episode infrastructure without
becoming confirmed-plan domain authority. It uses the existing Creator SQLite file.
The existing AI Director prompt, V5 Text Generation boundary, validation and
repair-once algorithm are unchanged. Public confirmation resolves the exact issued
candidate before entering the unchanged E3B confirmation method.

```text
CORE_START_MAIN=7c14b0da0146e00dfdebfb94b53b069051032def
CORE_START_TREE=e68e2a5f7beb82deba07fd981c9e9641263d9405
AI_DIRECTOR_CANDIDATE_IDEMPOTENCY_E3C=IMPLEMENTED_AND_VERIFIED
AI_DIRECTOR_CANDIDATE_REPLAY_RED_REPRODUCTION=PASS
AI_DIRECTOR_DUPLICATE_GENERATION_RED_REPRODUCTION=PASS
AI_DIRECTOR_UNKNOWN_FIELD_RED_REPRODUCTION=PASS
AI_DIRECTOR_ISSUANCE_BINDING_RED_REPRODUCTION=PASS
PUBLIC_ENDPOINT=/creator/api/v1/ai-director/candidates
AI_DIRECTOR_CANDIDATE_COMMAND_IDENTITY_SCHEMA=creator.ai-director-candidate-command-identity.v1
AI_DIRECTOR_CANDIDATE_COMMAND_SCHEMA=creator.ai-director-candidate-command.v1
AI_DIRECTOR_CANDIDATE_RECEIPT_SCHEMA=creator.ai-director-candidate-receipt.v1
KEYED_REQUEST_FIELDS=brief,idempotencyKey
UNKEYED_REQUEST_FIELDS=brief
KEYED_FIRST_HTTP_STATUS=200
KEYED_REPLAY_HTTP_STATUS=200
KEYED_CHANGED_REPLAY_HTTP_STATUS=409
KEYED_EXACT_REPLAY_SOURCE_PLAN_REF_EQUAL=true
KEYED_EXACT_REPLAY_CANDIDATE_DIGEST_EQUAL=true
KEYED_EXACT_REPLAY_PLAN_EQUAL=true
FULL_HTTP_ENVELOPE_DIGEST_EQUALITY_REQUIRED=false
STABLE_CANDIDATE_PAYLOAD_DIGEST_EQUALITY_REQUIRED=true
REPLAY_ADDITIONAL_PROVIDER_CALL_COUNT=0
RESPONSE_LOSS_RECOVERY=PASS
PROCESS_RESTART_EXACT_REPLAY=PASS
PENDING_AUTO_RETRY=false
FAILED_AUTO_RETRY=false
PUBLIC_CONFIRMATION_REQUIRES_ISSUED_RECEIPT=true
CURRENT_FRONTEND_BODY_COMPATIBILITY=PASS
UNKEYED_CANDIDATE_MODE=NEW_CANDIDATE_PER_EXPLICIT_REQUEST
```

## Identity, storage and confirmation

The [public contract](../04-interface-contract/creator-public-http-v1.md) freezes
closed request shapes and the versioned canonical identity/digest inputs. Keyed
command and source refs use independent namespaces and full 256-bit digests.
Only request/brief digests persist; raw key and raw brief do not. A canonical
candidate contains the issued source/version, brief digest, plan digest and plan.

The store reserves `PENDING` in a committed transaction before generation. Provider
work runs outside that transaction. It atomically finishes the same row as
`COMPLETED` before success, or `FAILED` with a stable failure code only. Existing
pending/failed commands never automatically re-enter generation. Same-key changed
requests return 409 without mutation; exact completed replay returns the original
candidate and adds zero calls. The no-key Frontend flow independently receipts each
new generation and keeps its original six-field response.

The optional exact schema has a workspace/command primary key and unique
workspace/identity and workspace/source indexes. All-or-absent allowlisting adds no
wildcards. DDL, columns, marker, indexes, timestamps, state-dependent nullable fields,
row checksum and candidate/plan digests are revalidated for every durable row.
`recordDigest` is a corruption checksum, not proof against an actor able to rewrite
the database and recompute checksums. SQL remains in infrastructure, outside the app.

Confirmation requires a completed receipt bound to authenticated workspace, source
ref/version, normalized brief and validated plan. Unknown/foreign/uncompleted sources
return 404; valid-but-different version or content returns 409; unavailable/corrupt
storage returns 503. Strict malformed-version validation remains 400. The server
passes its stored canonical plan into E3B. Another legitimately issued candidate
with an already-used confirmation key still exercises E3B's original 409 conflict.
Historical random-ref confirmed rows remain readable and bindable without backfill.

## Verification and unchanged scope

Formal tests cover frozen UTF-8 identity vectors, all seven changed brief fields,
closed JSON/key validation, failed replay and repair-once, response loss before
reading the body, process death after reservation, fresh Python process restart,
simultaneous requests in separate processes, and a blocked provider with another
SQLite connection proving that generation holds no database write transaction.
Startup tests reject partial/altered schema, duplicate identities/sources, corrupt
request digests/candidate JSON, invalid timestamps and unknown states. Integrity and
foreign-key checks pass. Temporary test databases create no E3 lineage facts.

Focused regressions include E3B unit/domain and public confirmation, Project
Foundation, clean-state public E2E, M5 receipts, M6/Lifecycle migration, E1/E2/E3A and
strict JSON/numeric integrity. Related HTTP fixtures now obtain genuine candidate
receipts before testing downstream behavior. The new integration module is assigned
exactly once to shard-2; all three new basenames differ. Local full-suite execution
is prohibited; the single PR tree requires normal full-suite CI before merge.

```text
APPLICATION_COMPONENT_DDL_DIFF=ADDITIVE_OPTIONAL_AI_DIRECTOR_CANDIDATE_COMMAND_COMPONENT
DATABASE_SCHEMA_DIFF=ADDITIVE_OPTIONAL_APPLICATION_COMPONENT_ONLY
GLOBAL_LIFECYCLE_SCHEMA_VERSION_DIFF=0
SERIES_INTELLIGENCE_SCHEMA_VERSION_DIFF=0
CONFIRMED_CREATIVE_PLAN_SCHEMA_VERSION_DIFF=0
DOMAIN_TABLE_DDL_DIFF=0
HISTORICAL_ROW_REWRITE_COUNT=0
SECOND_CREATOR_DATABASE_CREATED=false
PUBLIC_ROUTE_SET_DIFF=0
PUBLIC_RESOURCE_SET_DIFF=0
CONFIRMED_CREATIVE_PLAN_PRODUCTION_DIFF=0
PROJECT_FOUNDATION_PRODUCTION_DIFF=0
SERIES_PLANNING_PRODUCTION_DIFF=0
SCRIPT_STUDIO_PRODUCTION_DIFF=0
EPISODE_PRODUCTION_PRODUCTION_DIFF=0
E1_WORKER_SEMANTICS_DIFF=0
E2_RESULT_INTAKE_SEMANTICS_DIFF=0
E3A_INPUT_ADMISSION_SEMANTICS_DIFF=0
E3B_CONFIRMATION_IDEMPOTENCY_SEMANTICS_DIFF=0
FRONTEND_DIFF=0
FRONTEND_PIN_DIFF=0
DEPENDENCY_DIFF=0
LOCKFILE_DIFF=0
WORKFLOW_DIFF=0
LOCAL_FULL_SUITE_EXECUTED=false
```

## Quarantine and next gate

The seven historical evidence files retain the digests recorded in the
[E3B receipt](M1_CREATIVE_PLAN_CONFIRMATION_IDEMPOTENCY_E3B_2026-09-06.md).
R4's diagnostic runner and replay check are root-cause evidence, not acceptance
authority or a substitute for formal tests. Its staging/database, workspace refs
and token remain quarantined; neither R3 nor R4 may seed R5.

| Immutable R4 evidence | SHA-256 |
| --- | --- |
| `E3_R4_BLOCKED_RECEIPT.json` | `f0705052a2e73cc684fdf82e180d8c5422c84e28ef467da9ec3f68a3100567ad` |
| `E3_R4_UPSTREAM_CANDIDATE_REPLAY_CHECK.json` | `5a5f67bde391f02b35164a053b0b58262bb40d5d55307bcc80a8fbde8406bb30` |

```text
E3_R4_BUSINESS_FACT_CREATION_COUNT=0
E3_R4_STAGING_REUSABLE=false
E3_R5_FRESH_STAGING_ROOT_REQUIRED=true
R0_VISUAL_INSPECTION_RESULT=FAIL
R1_VISUAL_INSPECTION_RESULT=FAIL
R2_OBSERVABLE_TARGET_VISUAL_INSPECTION_RESULT=PASS
R4_ANCHOR_BYTES_VERIFIED=true
R5_VISUAL_REINSPECTION_REQUIRED=false
R4_VISUAL_REINSPECTION_COUNT=0
METHOD_AWARE_WORKER_SEAM_E1=IMPLEMENTED_AND_VERIFIED
METHOD_AWARE_JOB_RESULT_INTAKE_E2=IMPLEMENTED_AND_VERIFIED
CURRENT_SINGLE_INPUT_IMAGE_ADMISSION_E3A=IMPLEMENTED_AND_VERIFIED
CREATIVE_PLAN_CONFIRMATION_IDEMPOTENCY_E3B=IMPLEMENTED_AND_VERIFIED
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
E3_RESUME_R5_STARTED=false
A100_START_COUNT=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
GPU_OR_PROVIDER_CALLS=0
MODEL_DOWNLOAD_BYTES=0
NEXT_TASK=ACS-M10-M11-SPIKE-0-ELIGIBLE-LINEAGE-PREPARATION-E3-RESUME-R5
```

R5 requires separate authorization, fresh staging/database/token and the same exact
anchor bytes. Compare stable candidate fields, not the replay flag's HTTP envelope.
E3C ends after its authorized PR/CI/merge and automatic branch deletion. It does not
start E3, Spike-0/1, E4, a VideoMethodRoute, a MediaJob, live provider execution,
Frontend work, M12 or publication.
