# M10/M11 Spike-0 Eligible Input Lineage — E3 R6 Post-E3H

Status: `PREPARED_AND_VERIFIED / EXECUTION_BLOCKED`

Owner: Project Lead / Core Architecture Owner / Manifest v2 Technical Input
Authority Owner / M10 Input Admission Owner / Spike-0 Evidence Custody Owner

Task: `E3_R6_V2_INPUT_AUTHORITY_ISSUANCE_AND_PRESERVED_PREFIX_RESUME`

Authorization revision: `POST_E3H_EXACT_INPUT_GRANT_RESUME_R1`

## Baseline and preserved-prefix custody

```text
UPSTREAM_CREATED_UNDER=9c367c476b0486639444435f296407caf1b01bf8
PREVIOUS_REJECTION_UNDER=1ce0c7a32624d8899e70c192d72755aeef600f2c
INPUT_SUFFIX_CREATED_UNDER=7081f9dbfbda2664f539a59e20b30f079d039dc4
INPUT_SUFFIX_CREATED_UNDER_TREE=4eee7d27348a6b6bd655a4cfe07a900df340a083
LATEST_BLOCKED_RECEIPT_SHA256=ec5b1312514d6e10a963bed3e6afabfc15d66b5b69fd0c68f9530d25e0228dcb
OFFLINE_SNAPSHOT_MANIFEST_SHA256=d8aebfd9abe251e6023925d29a6c8f16e58a542a96e7110f6a7e9a75255112d0
PREFIX_COMPATIBILITY_REPORT_SHA256=f9db524395d829db980a47ee0e7a1315dcdd92fff967fa70f246792253b792d7
PREFIX_COMPATIBILITY=PASS
UPSTREAM_CURRENTNESS=PASS
```

The exact double-character R6 prefix was located from its real blocked receipt,
not reconstructed from a path or manifest. Its stopped offline snapshot, seven
SQLite databases, 48-record upstream logical projection, authority material and
anchor were verified before any grant or input POST. A separate validation copy
passed integrity and foreign-key checks and seven authenticated public reads under
the current code. Those reads preserved the old response bodies and the original
logical digest; the copy received no business writes and did not become authority.

The existing failure remains evidence: under the pre-E3H contract, the input
Candidate request correctly returned `409 execution_not_authorized` and wrote
nothing. This task neither edits that receipt nor relabels the old request as a
success. The E3H implementation receipt remains historically correct that E3H
itself issued no R6 grant; the grant below was issued only by this later, exact
Project Lead authorization.

## Frozen technical target and source separation

```text
TECHNICAL_TARGET_ID=SPIKE0-E3-SH09-VISIBLE-UPPER-BODY-HEAD-TURN-LOCKED-V2
SCENE_CHARACTER_NAMES=沈知微,裴昀
VISIBLE_CHARACTER_NAMES=沈知微
ACTION_EXECUTION_SUBJECT_REF=character-shen-zhiwei
TARGET_SHOT_COUNT=1
TARGET_VISUAL_EXECUTION_REQUIREMENT_COUNT=1
TARGET_INPUT_ANCHOR_COUNT=1
TARGET_EXECUTION_CLASS=MICRO_MOTION
TARGET_EXECUTION_METHOD=SINGLE_ANCHOR_I2V
TARGET_CAMERA_MOVEMENT=LOCKED
ANCHOR_SHA256=3b4f871ab59332625f0d343bde0ca1686477a135a3a2f9d6373f474f22e252ea
ANCHOR_BYTE_SIZE=998335
ANCHOR_DIMENSIONS=704x1280
ANCHOR_MEDIA_TYPE=image/png
VISUAL_REINSPECTION_COUNT=0
```

The current Script scene and M6 facts resolve two distinct characters. 沈知微 is
the sole visible and active execution subject. 裴昀 remains off camera with zero
dialogue, action beat, visual requirement and input asset. The single anchor passed
regular-file, no-symlink parent, exact bytes, PNG chunk/CRC, no-APNG, single-stream,
single-frame and stable pre/post-probe checks. The earlier R2 evidence was rebound
by digest to the new Candidate and TechnicalValidation without a new visual
judgment. It proves only the same image, visible subject and observable target; it
does not prove the off-camera character.

The upstream Script, M6, ProductionRun, M7 and M8/M9 facts were created under the
earlier baseline and were only read and revalidated here. This task sent no M1–M9
POST and made no upstream object, version, update or delete.

## One exact input authority

[ADR-0021](../../governance/ADR-0021-manifest-v2-technical-input-append-authority.md)
and the [M10 authority contract](../../architecture/M10_MANIFEST_V2_TECHNICAL_INPUT_APPEND_AUTHORITY_CONTRACT.md)
control this exception. A source map derived one closed subject from authenticated
public reads, the production V4 artifact reader and the production sealing rules.
No test helper, private authority method, SQL-built grant subject, preseeded journal
authority or client bypass field was used.

```text
SUBJECT_SCHEMA=v5.m10-input-append-authority-subject.v1
SUBJECT_PAYLOAD_DIGEST=8fb9f0ae0986199025296fecdad34c7479b36d5d02c9162c39f8cf495c642788
INPUT_APPEND_AUTHORITY_REF=e3-r6-post-e3h-sh09-input-append-authority
AUTHORITY_DECISION_REF=e3-r6-post-e3h-project-lead-input-append-decision
AUTHORITY_DECISION_DIGEST=89150f4c9adf243f4575234eef7535e37982b1aa2f34124c547d63e0cb4f9db4
AUTHORITY_BUNDLE_SCHEMA=v5.m10-input-append-authority-bundle.v1
AUTHORITY_BUNDLE_SHA256=ccb03d5930cd39c31f752e165c9df3dee8f4942612860b61c776da3a26242612
AUTHORITY_GRANT_COUNT=1
AUTHORITY_DECISION=APPROVED
LIVE_CORE_SUBJECT_MATCH=PASS_INTAKE_201_EXACT_GRANT_ACCEPTED
```

The production CLI built and independently validated one pinned grant. Its exact
allowed operation set is:

```text
TECHNICAL_INPUT_INTAKE
SEMANTIC_VISUAL_QC
HUMAN_SELECTION
INPUT_ADMISSION
METHOD_AWARE_INPUT_PLAN
```

The grant explicitly excludes `PROVIDER_PROCESSING`, `MEDIA_GENERATION`,
`VIDEO_RESULT_INTAKE`, `OUTPUT_SELECTION`, `OUTPUT_ADMISSION`,
`EXECUTION_DISPATCH`, `MASTER_OR_EXPORT` and `PUBLICATION`. Transport
authentication, M10 append permission and the independent external
HumanSelection approval remained separate controls. The same Workspace and
credential identity were retained while a new random transport token was used;
the raw token was destroyed and is absent from evidence and transfer artifacts.

One pre-grant CLI preparation attempt used a non-canonical `+00:00` timestamp and
was rejected before bundle creation or business POST. Its failure receipt is
preserved with SHA-256
`7cf802ba0509eaa836a0fc9680d51f7df92d2a02afb4b2de890f3e050a0c7617`.
The timestamp was corrected to canonical `Z` before the only grant was signed and
consumed; no authority identity, pinned bundle or accepted request was replaced.

## Authenticated public input lifecycle

The input-only production environment factory bound to loopback with internal
routes disabled and no backend registry, execution credential, ComfyUI endpoint,
runtime attestation or model directory. The approved public HTTP chain produced:

| Step | First / replay | Persistent result |
| --- | --- | --- |
| manifest-v2 input intake | `201 / 200` | one authority record, receipt v2, IMAGE Candidate and TechnicalValidation atomically |
| semantic visual QC | `201 / 200` | one digest-verified R2 evidence binding; no reinspection |
| external HumanSelection | `201 / 200` | one independently approved exact Candidate/QC decision |
| input admission | `201 / 200` | one AssetAdmission and one immutable AssetVersion atomically |
| MethodAwareInputPlan | `201 / 200` | one CURRENT plan with one resolved READY binding |

```text
INPUT_ARTIFACT_RECEIPT_SCHEMA=v5.method-aware-input-artifact-receipt.v2
INPUT_INTAKE_ATOMIC_RECORD_COUNT=4
INPUT_ADMISSION_ATOMIC_RECORD_COUNT=2
INPUT_ARTIFACT_RECEIPT_REF=input-artifact-33c49a51c2c3f5bcc66c4ab6809d252c4269d69b
INPUT_CANDIDATE_REF=input-candidate-33c49a51c2c3f5bcc66c4ab6809d252c4269d69b
INPUT_ASSET_VERSION_REF=input-image-version-7bcfd25263f533af53f2af090fdbcc0f5e74f902
METHOD_AWARE_INPUT_PLAN_REF=method-aware-input-plan-version-f0a4eaa090294059b515e08e641bb69d
METHOD_AWARE_INPUT_PLAN_CURRENTNESS=CURRENT
TARGET_RESOLVED_ASSET_BINDING_COUNT=1
TARGET_READY_MICRO_MOTION_COUNT=1
```

The AssetVersion remains `image / ACTION_READY_ANCHOR / IMPORTED /
TECHNICAL_EVIDENCE_ONLY`, with provider processing and publication false. Exact
replays reused the original keys and bodies and created zero additional records.
The five public operations did not send a VideoMethodRoute probe and did not create
a MediaJob, Attempt, adapter call or provider call.

## Restart, data invariants and transfer

A fresh Python process reloaded authentication, M6, artifact, input and selection
authority bytes, read the current lineage, and replayed all five supported commands.
Every ref, version and stable digest matched; the replay added zero records. All
task servers then stopped successfully.

```text
DATABASE_COUNT=7
BEFORE_INPUT_LOGICAL_DIGEST=fc4272468ff91fd426d798c9b337230a8aa03a27f3aed75b1d0168a563fab39e
AFTER_INPUT_LOGICAL_DIGEST=dd63311fa609fc83a820fff19ac15d94e954580318fe59f7e673b1ef70fbec65
INPUT_SUFFIX_EVIDENCE_ROWS_ADDED=9
UPSTREAM_NEW_OBJECT_OR_VERSION_COUNT=0
EXISTING_UPSTREAM_UPDATE_OR_DELETE_COUNT=0
UPSTREAM_POST_REQUEST_COUNT=0
UPSTREAM_CAPABILITY_CALL_COUNT=0
REPLAY_ADDITIONAL_RECORD_COUNT=0
SQLITE_INTEGRITY_AND_FOREIGN_KEYS=PASS
```

After all write connections closed, a consistent stopped snapshot was packaged as
`SPIKE_0_E3_R6_POST_E3H_ELIGIBLE_INPUT_LINEAGE_BUNDLE.tar.gz`.

```text
BUNDLE_SHA256=ab4399d2ad769a8f8a9fc8ca0368a2e6d8f721ab76d6499a077d0a1a586dcfc2
BUNDLE_BYTE_SIZE=1428336
BUNDLE_FILE_COUNT=111
SHA256SUMS_ENTRY_COUNT=110
BUNDLE_SECRET_SCAN=PASS
BUNDLE_ROUNDTRIP=PASS
```

The archive safety audit found no symlink, special file or traversal member. The
secret scan found no raw token, authorization header, cookie, private key or
provider credential. An independent extraction verified every listed digest,
seven database integrity/foreign-key results, the unchanged logical digest,
authority and selection loads, the exact anchor, eight authenticated GETs and the
single CURRENT InputPlan with zero POST. Migration may only rebind external config
paths; grant, artifact and selection authority bytes remain immutable.

## Execution boundary and next gate

The prepared lineage does not make the ProductionRun executable. Its manifest
safety values remain unchanged:

```text
manifestSchemaVersion=k2.golden-episode.manifest.v2
shotPlanAuthorityState=LOCAL_STRUCTURAL_REPRESENTATION_ONLY
shotPlanApprovalState=NOT_VERIFIED
cameraContractState=NOT_READY
dispatchAllowed=false
providerProcessingAuthorized=false
publicationAllowed=false
VIDEO_METHOD_ROUTE_COUNT=0
MEDIA_JOB_COUNT=0
EXECUTION_ATTEMPT_COUNT=0
REAL_PROVIDER_CALL_COUNT=0
MASTER_COUNT=0
EXPORT_COUNT=0
```

No production source, test, database schema definition, Frontend, workflow or
dependency changed in this task. The repository change is documentation-only and
does not commit the database, image, authority bundle, selection bundle or operator
scripts. This receipt records external evidence and does not predict its own commit,
pull request, CI run or merge identity.

```text
SPIKE_0_ELIGIBLE_LINEAGE_E3=PREPARED_AND_VERIFIED
LINEAGE_READINESS=READY_FOR_A100_RUNTIME_AND_COST_PREFLIGHT
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
E4_STARTED=false
M5_CONFIRM_VERSION_HISTORICAL_RECEIPT=UNPROVEN_CONTRACT_DECISION_PENDING
```

The only named next task is
`ACS-M10-M11-SPIKE-0-A100-READ-ONLY-RUNTIME-AND-COST-PREFLIGHT-E4`.
It is read-only preflight authority, not A100 start, provider processing, video
routing, media execution or publication authority. Any later runtime or cost result
cannot by itself change the manifest-v2 dispatch contract.
