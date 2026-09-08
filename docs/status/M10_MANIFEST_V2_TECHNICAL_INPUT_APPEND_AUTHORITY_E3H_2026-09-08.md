# M10 Manifest v2 Technical-Input Append Authority — E3H

Status: `BOUNDED IMPLEMENTATION / LOCAL VALIDATION / REQUIRED CI GATE`

Owner: Project Lead / Core Architecture Owner / Manifest v2 Contract Owner /
M10 Canonical Input Append Owner / Candidate Review and Admission Owner

Task: `ACS-M10-MANIFEST-V2-TECHNICAL-INPUT-APPEND-AUTHORITY-E3H`

## Baseline, decision and preserved incident

```text
CORE_START_MAIN=1ce0c7a32624d8899e70c192d72755aeef600f2c
CORE_START_TREE=d002c60315fcacbd9a323886d21989903103d0fc
PREVIOUS_BLOCK_REASON=INPUT_SUFFIX_PUBLIC_PATH_GAP
PREVIOUS_FAILED_STAGE=INPUT_CANDIDATE
PREVIOUS_HTTP_STATUS=409
PREVIOUS_ERROR_CODE=execution_not_authorized
ACTUAL_BLOCKED_RECEIPT_SHA256=ec5b1312514d6e10a963bed3e6afabfc15d66b5b69fd0c68f9530d25e0228dcb
OFFLINE_SNAPSHOT_MANIFEST_SHA256=d8aebfd9abe251e6023925d29a6c8f16e58a542a96e7110f6a7e9a75255112d0
FAILED_REQUEST_DATABASE_LOGICAL_DIGEST=fc4272468ff91fd426d798c9b337230a8aa03a27f3aed75b1d0168a563fab39e
FROZEN_PREFIX_AND_SNAPSHOT_UNCHANGED=true
R6_LIVE_MUTATION_COUNT=0
R6_INPUT_APPEND_AUTHORITY_ISSUED=false
R6_RESUMED=false
CI_SCOPE=FULL_SUITE
```

The actual blocked receipt and offline snapshot index were read and hashed without
starting the preserved service or opening the target for mutation. Their 48-record
valid prefix, failed request, database, authority, token and prediction-invalidated
matrix remain quarantined evidence. No R6 database was copied into a test fixture.
This receipt does not predict its own commit, pull request, CI run or merge identity.

[ADR-0021](../../governance/ADR-0021-manifest-v2-technical-input-append-authority.md)
and the [normative contract](../../architecture/M10_MANIFEST_V2_TECHNICAL_INPUT_APPEND_AUTHORITY_CONTRACT.md)
narrowly amend the earlier blanket manifest-v2 mutation rejection. The prior
`execution_not_authorized` result was correct under the then-current configuration;
it is not rewritten as a product defect or successful live run.

## Exact bounded authority

The environment factory loads a dedicated rejecting-by-default boundary before any
database or method-aware execution factory. A production grant requires both exact
settings:

```text
CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_PATH
CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_SHA256
```

The operator-managed bundle path is absolute. Core safely reads a regular file
through a no-symlink parent chain, verifies stable bytes and the independent SHA-256,
then validates strict closed JSON. It reopens and revalidates those bytes for every
new write and legal replay. Missing or partial configuration, unknown fields or
operations, duplicate keys, non-canonical numbers, excessive nesting, a pin mismatch,
symlink, replaced file, malformed grant or wrong subject fails closed.

```text
INPUT_APPEND_AUTHORITY_BUNDLE_SCHEMA=v5.m10-input-append-authority-bundle.v1
INPUT_APPEND_AUTHORITY_GRANT_SCHEMA=v5.m10-input-append-authority-grant.v1
INPUT_APPEND_AUTHORITY_SUBJECT_SCHEMA=v5.m10-input-append-authority-subject.v1
INPUT_APPEND_AUTHORITY_EVIDENCE_SCHEMA=v5.method-aware-input-append-authority-decision.v1
INPUT_APPEND_AUTHORITY_RECORD_KIND=MethodAwareInputAppendAuthority
```

The closed subject binds exact Workspace/Project/Series/Episode/Run; ProductionRun,
manifest and upstream digests; confirmed ScriptVersion and M6 binding; current M7;
current M8/M9 plan; one VisualExecutionRequirement, CreativeShot, ActionExecutionBeat
and source span/text digest; and one freshly verified staged IMAGE /
ACTION_READY_ANCHOR. It also freezes the technical-only authority state, input key,
media facts and all execution/publication safety values. There is no wildcard Run,
requirement, beat, artifact or record-kind scope.

The allowed operation set is exactly intake, semantic visual QC, HumanSelection,
admission and corresponding MethodAwareInputPlan consumption. Provider processing,
media generation, video result intake, output selection/admission, dispatch,
Master/Export and publication are explicit exclusions. An authenticated token, a
request field, IMAGE provenance, `TECHNICAL_EVIDENCE_ONLY` or persisted audit record
is not a live grant. External HumanSelection approval remains independently required.

## Persistence, compatibility and currentness

The existing shared Candidate lifecycle and Episode Production journal remain the
only owners. Authorized manifest-v2 intake atomically appends exactly:

```text
1 MethodAwareInputAppendAuthority
1 MethodAwareInputArtifact receipt v2
1 IMAGE Candidate
1 TechnicalValidation
V2_INTAKE_ATOMIC_RECORD_COUNT=4
```

Receipt `v5.method-aware-input-artifact-receipt.v2` adds only the exact authority
record ref and digest. Candidate binds that receipt, and canonical AssetVersion binds
the receipt, making the exact subject and decision reachable from the final asset.
Manifest-v1 receipt schema and its existing three-record intake remain unchanged and
readable without backfill. Admission and AssetVersion remain one two-record atomic
append through the existing canonical AssetVersion authority.

Before QC, selection, admission and input-plan consumption, the input service reads
the actual persisted chain, current upstream and fresh staged bytes, rederives the
subject, and revalidates the configured grant for the exact operation. The shared
review service's ordinary manifest-v2 guard still rejects calls without its internal
verified context. No client `allowV2`, bypass header or generic append surface exists.

Same key and request replay only after fresh authority/currentness verification;
changed content conflicts. SQLite fault injection leaves all four intake records
absent, and concurrent identical intake has one complete four-record winner. A new
process can read and replay the complete chain with exact configuration and zero
writes. Recomposition after removing the two settings preserves immutable reads but
rejects Candidate replay and every new write.

## Full isolated input path and anti-escalation evidence

An isolated fixture creates a real `k2.golden-episode.manifest.v2` ProductionRun with
explicit `shotBudgets`, confirmed M6-bound Script v2, current M7 PASS and current
M8/M9 plan through the current public boundary. The production environment factory
then serves authenticated public HTTP with internal routes disabled. No target
authority record, receipt, Candidate, Admission or InputPlan is preseeded.

The authenticated path completes intake, TechnicalValidation, semantic QC, external
HumanSelection, Admission/AssetVersion and a CURRENT MethodAwareInputPlan. Candidate,
Admission and InputPlan replay return the same immutable digests without appends. A
real child interpreter reopens the SQLite and configured authorities, repeats those
replays, reads CURRENT, verifies the route stop, removes authority configuration,
recomposes, and observes fail-closed zero-write rejection.

```text
V1_INPUT_LIFECYCLE_REGRESSION=PASS
V2_WITHOUT_AUTHORITY_REJECTION=PASS
V2_EXACT_AUTHORITY_INPUT_LIFECYCLE=PASS
V2_REAL_MANIFEST_ASSERTED=true
V2_INTAKE_ATOMICITY=PASS
ADMISSION_ATOMICITY=PASS_2_RECORDS
QC_AND_SELECTION_AUTHORITY_SEPARATION=PASS
INPUT_PLAN_CURRENTNESS=PASS
CHANGED_SOURCE_AND_FOREIGN_REJECTION=PASS
EXACT_REPLAY_AND_CONCURRENCY=PASS
REAL_PROCESS_RESTART=PASS
AUTHORITY_REMOVAL_REASSEMBLY_REJECTION=PASS
```

The complete input path leaves the ProductionRun manifest byte-for-value unchanged:

```text
shotPlanAuthorityState=LOCAL_STRUCTURAL_REPRESENTATION_ONLY
shotPlanApprovalState=NOT_VERIFIED
cameraContractState=NOT_READY
dispatchAllowed=false
providerProcessingAuthorized=false
publicationAllowed=false
```

Manifest-v2 video routing rejects at the V5 safety boundary before appending a route
record or invoking queue, backend, adapter or provider behavior. This remains true
with a working mock backend. Generic Candidate, legacy image/video revision and
video-result paths cannot borrow the input permission. Dynamic preflight remains
read-only.

```text
CONFIGURED_BACKEND_CANNOT_ESCALATE_INPUT_PERMISSION=PASS
LEGACY_AND_VIDEO_PATHS_STILL_BLOCKED=PASS
PUBLIC_ROUTE_SET_DIFF=0
QUEUED_JOB_COUNT=0
EXECUTION_ATTEMPT_COUNT=0
ADAPTER_GENERATE_COUNT=0
REAL_PROVIDER_CALL_COUNT=0
MASTER_EXPORT_COUNT=0
PUBLICATION_COUNT=0
```

## Change and verification boundary

```text
INTERNAL_SCHEMA_DIFF=ADDITIVE_RECEIPT_V2_AND_ONE_AUTHORITY_RECORD_KIND
DATABASE_DDL_DIFF=0
EXISTING_MANIFEST_REWRITE_COUNT=0
FRONTEND_DIFF=0
WORKFLOW_DIFF=0
DEPENDENCY_DIFF=0
LOCAL_FULL_SUITE_EXECUTED=false
```

Focused unit, contract and authenticated HTTP/SQLite integration modules cover
authority parsing, subject closure, currentness, default rejection, full lifecycle,
selection separation, atomic fault/concurrency, process restart, revocation and
execution isolation. Existing E3A/E3G, Candidate lifecycle, input planning, dynamic
preflight, module namespace and exact integration-shard coverage remain required
gates. Five documentation validators, changed-file compilation, diff check and secret
scan precede the one full-suite pull-request CI run.

```text
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
E4_STARTED=false
A100_START_COUNT=0
COMFYUI_START_COUNT=0
```

After verified merge and cleanup, the only named next task is
`E3_R6_V2_INPUT_AUTHORITY_ISSUANCE_AND_PRESERVED_PREFIX_RESUME`. It requires a
separate authorization, preserved-prefix compatibility recheck and exact live subject
issuance; E3H itself grants no live-lineage write or execution authority.
