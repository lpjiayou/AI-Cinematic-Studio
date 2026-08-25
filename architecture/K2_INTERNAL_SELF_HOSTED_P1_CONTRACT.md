# K2 Internal Self-hosted P1 Contract

> Historical/closed as of 2026-08-25: this exception is bound to the original
> exact K2-001 workspace/run. It does not govern or authorize K2-002.

## 1. Scope

This contract governs one K2 Internal Content Lab, single-episode, video-only P1
smoke execution.  It reuses the existing Creator Public API, V5 Episode Production,
V4 MediaJob and ComfyUI/Wan2.2 boundaries.

It does not govern commercial provider onboarding, rights clearance, budget approval,
asset admission, Master creation, export or publication.

## 2. Invariants

1. The execution grant is process configuration, not a browser claim.
2. The grant is exact-scoped to one `workspaceRef + productionRunRef`.
3. The source must be one existing current G4 video GenerationRequest.
4. The source GenerationRequest, AssetRequirement, CreativeShotVersion and current
   AssetResolutionManifest digests must be preserved in the derived request/candidate.
5. V5 may orchestrate but may not execute the provider workflow.
6. V4 owns MediaJob/Attempt and artifact containment.
7. A candidate is not an AssetVersion and cannot advance publication state.
8. `publicationAllowed=false` at every layer.

## 3. Server configuration

Internal mode is enabled only when all three exact values are present:

```text
K2_P1_EXECUTION_AUTHORITY=GRANTED_INTERNAL
K2_P1_INTERNAL_WORKSPACE_REF=<exact current workspaceRef>
K2_P1_INTERNAL_PRODUCTION_RUN_REF=<exact current productionRunRef>
```

The existing complete `COMFYUI_*` configuration remains required.  Provider/model,
endpoint, runtime-attestation, cost and timeout facts are copied from the already
validated V4 adapter configuration.  Partial configuration fails process assembly.

The grant digest is deterministic over:

- mode and P1 scope;
- exact workspace/run;
- provider/model/region/endpoint technical identity;
- runtime-attestation ref/digest;
- operational cost ceiling and timeout;
- `publicationAllowed=false`.

No token, credential value, base URL or host path enters the grant or its public
projection.

## 4. Public API command

For the exact internal run:

```http
POST /creator/api/v1/episode-production-runs/{runRef}/provider-experiments
Authorization: Bearer <server credential>
Content-Type: application/json

{
  "idempotencyKey": "<opaque replay key>",
  "sourceGenerationRequestRef": "<existing current video request ref>"
}
```

The authenticated server injects `workspaceRef` and path-derived
`productionRunRef`.  No other field is accepted.  In particular, the client must not
supply `providerCapabilityRef`, policy, rights, credential, usage-terms, budget,
runtime-attestation or publication fields.

Outside the exact internal grant scope, the legacy external command and policy checks
remain unchanged.

## 5. Derived V5 request

The internal request carries:

- exact upstream lineage refs/digests;
- `executionMode=INTERNAL_SELF_HOSTED`;
- exact execution-grant ref/digest;
- `adapterCapability=comfyui-wan22-ti2v-v1`;
- server-derived provider/model/region/endpoint technical facts;
- exact runtime-attestation ref/digest;
- bounded operational cost and timeout;
- one deterministic 49-frame smoke profile;
- `requestedProvenance=LIVE_PROVIDER` at the V4 transport boundary;
- `experimentOnly=true` and `publicationAllowed=false`.

The request must not carry:

- `productionPolicyBundleRef` or `productionPolicyRef`;
- `rightsManifestRef`;
- `providerExecutionPolicyRef`;
- `providerCapabilityRef`;
- `credentialSourceRef`;
- `usageTermsRef`;
- `budgetAuthorityRef`.

`LIVE_PROVIDER` at V4 means a live adapter execution with returned execution facts;
it does not imply external Provider Authority.  The V5 candidate provenance is
`SELF_HOSTED_AI_GENERATED`.

## 6. Smoke profile

The profile is derived from the existing source request and is fixed as:

| Field | Rule |
|---|---|
| frames | `49` |
| frame rate | exact source frame rate |
| width | source width capped at `640`, aligned to 32 |
| height | source aspect ratio, aligned to 32 |
| steps | `20` |
| cfg | `5.0` |
| sampler | `uni_pc` |
| scheduler | `simple` |
| model shift | `8.0` |
| seed | deterministic from the source payload digest |

## 7. Verification

Success requires all of the following:

- V4 job state `SUCCEEDED`;
- one successful final Attempt;
- ComfyUI adapter identity exact match;
- returned provider/model/region/endpoint match the bound technical profile;
- runtime-attestation ref/digest exact match;
- runtime facts digest exact match;
- `deviceType=cuda`, non-empty CUDA device and `gpuUsed=true`;
- cost and latency within the configured operational limits;
- artifact remains inside the configured run artifact root;
- artifact byte size and SHA-256 match independently read bytes;
- V4 and V5 media probes match the exact request;
- no publication permission is returned.

Any mismatch rejects the candidate.  It cannot be downgraded to a warning.

## 8. Candidate and readiness

The successful candidate has:

```text
state=UNSELECTED_INTERNAL_CANDIDATE
validationState=TECHNICALLY_VERIFIED
selectionState=UNSELECTED
admissionState=NOT_ADMITTED
rightsState=NOT_REQUIRED_INTERNAL
provenance=SELF_HOSTED_AI_GENERATED
experimentOnly=true
publicationAllowed=false
```

Before execution, internal readiness is:

```text
state=READY_INTERNAL_EXECUTION
blockers=[internal_video_execution_missing]
```

After one verified video candidate:

```text
state=PASSED_INTERNAL_VIDEO_EXECUTION
verifiedVideoExperiments>=1
blockers=[]
nextActions=[candidate_selection_not_started,p2_full_shot_production_not_started]
publicationAllowed=false
```

Image/audio provider evidence, Rights Authority, Provider Policy Authority and Budget
Authority are not blockers for this P1 exit.

## 9. Regression obligations

The implementation must prove:

1. exact internal scope becomes ready without an external production-policy bundle;
2. the Public API internal command contains no provider selection field;
3. the request and candidate contain no external rights/provider/budget authority refs;
4. one same-lineage GPU video smoke passes internal P1;
5. runtime-attestation mismatch still fails closed;
6. wrong-run scope falls back to the unchanged legacy external gate;
7. browser-supplied `providerCapabilityRef` is rejected in internal mode;
8. the existing legacy external policy tests remain green;
9. the full Core regression remains green.
