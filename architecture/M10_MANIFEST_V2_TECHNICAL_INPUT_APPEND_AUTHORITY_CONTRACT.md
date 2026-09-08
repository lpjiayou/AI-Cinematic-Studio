# M10 Manifest v2 Technical Input Append Authority Contract

> Status: `ACCEPTED NORMATIVE CONTRACT`
>
> Authority: [ADR-0021](../governance/ADR-0021-manifest-v2-technical-input-append-authority.md)
>
> Work package: `ACS-M10-MANIFEST-V2-TECHNICAL-INPUT-APPEND-AUTHORITY-E3H`

## 1. Decision and boundary

A current `k2.golden-episode.manifest.v2` ProductionRun remains preflight-only by
default. Without the exact authority defined here, every M10/M11 candidate, review,
selection and admission mutation continues to fail with `execution_not_authorized`
before a business record is appended.

One current manifest v2 run may enter only this bounded technical-input lifecycle
when Core freshly verifies an operator-managed, digest-pinned M10 input-append
authority for the exact current subject:

```text
MethodAwareInputAppendAuthority
+ MethodAwareInputArtifact receipt v2
+ IMAGE Candidate
+ TechnicalValidation
→ SemanticVisualQCDecision
→ HumanSelectionDecision
→ AssetAdmission + canonical AssetVersion
→ MethodAwareInputPlanVersion consumption
```

The first four records are one atomic intake batch. `AssetAdmission` and
`AssetVersion` remain a separate two-record atomic batch. The existing Episode
Production evidence journal and canonical AssetVersion authority remain the only
persistence owners; this contract adds no table, database, queue or asset authority.

This permission does not authorize image generation, video generation, provider
processing, video-result intake, output selection or admission, execution dispatch,
`VideoMethodRouteVersion`, `MediaJob`, `Attempt`, M12/M13 execution, Master, Export or
publication.

## 2. Run safety invariants

The accepted exception applies only while all four manifest facts remain exact:

```text
shotPlanAuthorityState=LOCAL_STRUCTURAL_REPRESENTATION_ONLY
shotPlanApprovalState=NOT_VERIFIED
cameraContractState=NOT_READY
dispatchAllowed=false
```

Input-plan `READY` means only that the method-specific input bindings are current.
It cannot elevate the ProductionRun, ShotPlan, camera, provider, dispatch or
publication state. `TECHNICAL_EVIDENCE_ONLY` is a required safety value, never a
standalone bypass.

## 3. Configuration and bundle

The only production configuration is:

```text
CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_PATH
CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_SHA256
```

Both values are required together. The path is absolute and the expected digest is
64 lowercase hexadecimal characters. No configuration selects the rejecting
implementation. Partial configuration, a non-regular file, a symlink in the file or
parent chain, changed bytes during a read, digest mismatch, duplicate JSON keys,
non-canonical numbers, excessive nesting, unknown fields, unknown operations or an
unsupported schema fail closed. Bundle bytes are re-read and revalidated for every
new write and legal replay; a newly composed process without both exact settings
cannot use a previously persisted receipt to authorize another write.

The bundle is a closed object:

```text
schemaVersion = v5.m10-input-append-authority-bundle.v1
authorityRef
grants[]
```

Each grant is a closed
`v5.m10-input-append-authority-grant.v1` object containing exactly:

```text
schemaVersion
inputAppendAuthorityRef
version
subject
subjectDigest
allowedOperations
excludedOperations
decision
authorityDecisionRef
authorityDecisionDigest
decidedAt
payloadDigest
```

`version` is `1`, `decision` is `APPROVED`, and no authority or decision identity may
be duplicated. `subjectDigest` is the SHA-256 of canonical JSON for `subject`.
`authorityDecisionDigest` seals `authorityRef`, `inputAppendAuthorityRef`, `version`,
`subjectDigest`, both operation lists, `decision`, `authorityDecisionRef` and
`decidedAt`. `payloadDigest` seals every grant field except itself. All digests use
UTF-8 JSON with sorted object keys, compact separators and no NaN or infinity.

The only allowed-operation list, in this order, is:

```text
TECHNICAL_INPUT_INTAKE
SEMANTIC_VISUAL_QC
HUMAN_SELECTION
INPUT_ADMISSION
METHOD_AWARE_INPUT_PLAN
```

The required exclusion list, in this order, is:

```text
PROVIDER_PROCESSING
MEDIA_GENERATION
VIDEO_RESULT_INTAKE
OUTPUT_SELECTION
OUTPUT_ADMISSION
EXECUTION_DISPATCH
MASTER_OR_EXPORT
PUBLICATION
```

An input-append authority is not a HumanSelection approval and is not implied by an
authenticated transport credential. A public request cannot submit the bundle, its
subject, an actor, an authority, a header or an `allowV2` flag.

## 4. Exact authority subject

`subject` is a closed `v5.m10-input-append-authority-subject.v1` object. It contains
exactly the following fields:

```text
schemaVersion
workspaceRef
projectRef
seriesRef
episodeRef
productionRunRef
productionRunPayloadDigest
manifestSchemaVersion
manifestDigest
upstreamDigest
scriptVersionRef
scriptVersionDigest
m6ConsumerBindingDigest
m6BaselineSnapshotRef
m6BaselineCanonicalDigest
activationRevision
seriesPlanVersionRef
seriesPlanVersionDigest
seriesBibleVersionRef
seriesBibleVersionDigest
characterContinuityVersionRef
characterContinuityVersionDigest
consistencyValidationVersionRef
consistencyValidationDigest
executionMethodPlanVersionRef
executionMethodPlanDigest
visualExecutionRequirementRef
visualExecutionRequirementDigest
creativeShotVersionRef
creativeShotVersionDigest
actionExecutionBeatRef
actionExecutionBeatDigest
sourceSpan
sourceTextDigest
executionClass
executionMethod
inputRequirementKey
stagedArtifactRef
stagedArtifactDigest
artifactContentDigest
artifactMediaType
artifactByteSize
mediaKind
inputRole
authorityState
shotPlanAuthorityState
shotPlanApprovalState
cameraContractState
dispatchAllowed
providerProcessingAuthorized
publicationAllowed
payloadDigest
```

`sourceSpan` is the existing closed M8 source-span object. The fixed values are
`manifestSchemaVersion=k2.golden-episode.manifest.v2`,
`executionClass=MICRO_MOTION`, `executionMethod=SINGLE_ANCHOR_I2V`,
`mediaKind=IMAGE`, `inputRole=ACTION_READY_ANCHOR`,
`authorityState=TECHNICAL_EVIDENCE_ONLY`, and all three permission booleans are
false. `inputRequirementKey` is
`action-ready-anchor:<visualExecutionRequirementRef>`. The staged-artifact digest
binds the operator entry; the content digest, media type and byte size bind the
independently remeasured image projection.

Core derives this subject from fresh current reads of the ProductionRun, confirmed
M6-bound ScriptVersion, current M6 binding, latest current M7 PASS, current M8/M9
plan, exact VisualExecutionRequirement, CreativeShot/ActionExecutionBeat and the
freshly probed staged image. Wildcard scope and authority over a different run,
requirement, plan, beat or artifact are invalid.

## 5. Persistent authority evidence and receipt versioning

The one new journal record kind is `MethodAwareInputAppendAuthority`. Its closed
payload schema is `v5.method-aware-input-append-authority-decision.v1` and contains:

```text
schemaVersion
workspaceRef
projectRef
seriesRef
episodeRef
productionRunRef
inputAppendAuthorityRef
version
authorityRef
subject
subjectDigest
allowedOperations
excludedOperations
decision
authorityDecisionRef
authorityDecisionDigest
decidedAt
providerProcessingAuthorized
publicationAllowed
createdAt
payloadDigest
```

The persisted decision is a byte-independent canonical projection of the verified
grant, not a copy of the bundle path. It is appended in the intake transaction and
cannot authorize later writes by itself.

Manifest v1 intake continues to write
`v5.method-aware-input-artifact-receipt.v1` with record version `1`. Authorized
manifest v2 intake writes the additive
`v5.method-aware-input-artifact-receipt.v2` with record version `2` and two additional
closed fields:

```text
inputAppendAuthorityRef
inputAppendAuthorityDigest
```

Those fields identify the exact persisted authority record. Candidate lineage binds
the receipt as its `revisionRef`; the final AssetVersion binds the receipt by
`sourceArtifactReceiptRef` and `sourceArtifactReceiptDigest`. Thus the existing
AssetVersion chain reaches the exact authority subject and decision without a new
sidecar or silent v1 schema expansion. Historical v1 records remain readable and
are not backfilled.

## 6. Operation, replay and currentness rules

Only the MethodAwareInputArtifact service may create the verified internal context
used by the shared Candidate review service. That service's ordinary manifest v2
guard remains rejecting. Before intake, QC, selection, admission and input-plan
consumption, Core must re-read the persisted receipt chain, rederive the current
subject, re-read and verify the pinned authority bundle, and require the exact
operation member. The intake context may prepare only its not-yet-persisted IMAGE
Candidate and TechnicalValidation for the same atomic batch.

The Candidate, technical validation, QC, external HumanSelection approval,
admission, canonical AssetVersion and input-plan currentness rules remain unchanged.
QC FAIL, missing or changed external selection approval, stale currentness, a changed
artifact, foreign scope, different plan or requirement, an unsupported media kind,
and a malformed or removed authority all reject without partial writes.

Same-key/same-request replay returns the immutable result only after the authority
and current source are verified again. Changed content conflicts. Concurrent intake
has one atomic winner. Existing immutable records remain readable after authority
removal, but removal or replacement followed by process composition rejects every
new lifecycle write and input-plan append.

## 7. Execution anti-escalation

Every manifest v2 `VideoMethodRoute` request remains forbidden, including when all
technical inputs are READY and a working backend is configured. The rejection occurs
at the V5 run-safety boundary before a route record, job, attempt, adapter or provider
work.
Generic Candidate registration, legacy image/video revisions, video Candidate/result
intake, output admission and all G4/G5 legacy write routes cannot consume this input
authority. Dynamic media preflight remains zero-write.

## 8. Acceptance evidence

Acceptance requires isolated SQLite and authenticated public HTTP coverage for a
real manifest v2 run with explicit `shotBudgets`, current M6-bound Script v2, current
M7 PASS and current M8/M9 facts. The complete input lifecycle, exact replay,
concurrency and a real fresh-process readback/replay must pass. Negative coverage
must prove default rejection, tamper/foreign/stale rejection, external selection
separation, authority-removal reassembly rejection, legacy/video isolation and zero
route/job/attempt/provider work even with a working mock backend.

This contract does not issue authority for, mutate or resume any preserved R6
staging root, database, token, run or evidence prefix. Such issuance and resume
require a later explicit task.
