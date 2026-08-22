# K2 Internal Self-hosted P1 Runbook

## Purpose

Execute one real Wan2.2 video smoke through the existing K2 Public API → V5 → V4 →
ComfyUI chain.  This runbook does not create a Master, export or publication record.

## Entry facts

Do not begin unless read-only verification shows:

- the expected Core revision and a clean tracked worktree before deployment;
- the exact canonical K2 workspace and production-run refs;
- G2 Identity Lock, G3 Shot Graph and G4 asset plan are current;
- at least one G4 video GenerationRequest exists;
- the configured ComfyUI runtime is reachable;
- the current runtime-attestation ref/digest and all three Wan2.2 model digests match
  the runtime being started;
- no existing successful internal P1 candidate already satisfies the same command.

Names, titles, shot labels and copied test refs are not authority.  Read the opaque
refs from the current authenticated API projection.

## 1. Repository validation

Apply the accepted implementation to the exact reviewed Core base, then run the
focused and complete repository test suites.  Stop if the base revision, patch
digest, worktree state or any test differs from the accepted checkpoint.

This step must not open a Creator process against canonical data until repository
validation passes.

## 2. Exact internal scope

Configure the existing Creator deployment with:

```text
K2_P1_EXECUTION_AUTHORITY=GRANTED_INTERNAL
K2_P1_INTERNAL_WORKSPACE_REF=<exact authenticated K2 workspaceRef>
K2_P1_INTERNAL_PRODUCTION_RUN_REF=<exact current K2 productionRunRef>
```

Keep the complete existing `COMFYUI_*`, canonical database and artifact-root
configuration.  Do not add Rights, Provider Policy, credential-source,
usage-terms or Budget Authority bundles for this internal checkpoint.

Keep V4 job/artifact persistence under the existing K2 runtime root. The default
internal provider paths are derived from `CREATOR_MEDIA_JOB_DATA_PATH` and
`CREATOR_MEDIA_ARTIFACT_ROOT`, not from the canonical Core database path. If explicit
`CREATOR_PROVIDER_EXPERIMENT_*` overrides are used, they must also resolve inside the
K2 runtime root and must be recorded in the deployment evidence.

Restart Creator using the deployment's existing process boundary.  Do not introduce
a second server, database or artifact root solely for P1.

## 3. Readiness preflight

Use authenticated GET on:

```text
/creator/api/v1/episode-production-runs/{runRef}/production-readiness
```

Require:

```text
state=READY_INTERNAL_EXECUTION
executionMode=INTERNAL_SELF_HOSTED
rightsState=NOT_REQUIRED_INTERNAL
providerPolicyState=NOT_REQUIRED_SELF_HOSTED
budgetAuthorityState=NOT_REQUIRED_INTERNAL
publicationAllowed=false
```

If the response is legacy `BLOCKED_POLICY`, the exact grant was not activated for
that workspace/run.  Do not forge a policy bundle.

## 4. Select the current source

GET the current asset plan:

```text
/creator/api/v1/episode-production-runs/{runRef}/assets
```

Select exactly one returned item where `mediaKind=video`.  Preserve its opaque
`generationRequestRef`; do not construct a ref from the shot name.

For the first smoke, use the first current video request in the canonical ordering.
Record its source request digest and CreativeShotVersion ref/digest in the operator
evidence before dispatch.

## 5. Dispatch one smoke

POST exactly:

```json
{
  "idempotencyKey": "k2-p1-internal-video-smoke-v1",
  "sourceGenerationRequestRef": "<exact current video GenerationRequest ref>"
}
```

to:

```text
/creator/api/v1/episode-production-runs/{runRef}/provider-experiments
```

Do not include provider, policy, rights, credential, usage, budget, attestation or
publication fields.  Reuse the same idempotency key only for byte-equivalent current
lineage.

## 6. Verify the result

Require all of:

```text
candidate.state=UNSELECTED_INTERNAL_CANDIDATE
candidate.validationState=TECHNICALLY_VERIFIED
candidate.selectionState=UNSELECTED
candidate.admissionState=NOT_ADMITTED
candidate.provenance=SELF_HOSTED_AI_GENERATED
candidate.gpuUsed=true
candidate.publicationAllowed=false
readiness.state=PASSED_INTERNAL_VIDEO_EXECUTION
readiness.blockers=[]
```

Independently verify:

- source request and CreativeShot lineage match the preflight values;
- request/candidate execution-grant digests match the process readiness projection;
- runtime-attestation ref/digest and model facts match the current runtime record;
- stored artifact SHA-256, byte size and probe match the response/evidence record;
- no forbidden external-authority ref is present;
- no AssetVersion, Master, export, approval or publication record was created by the
  experiment.

GET `/provider-experiments` again and require the same persisted candidate and P1
readiness.

## 7. Stop boundary and next work

Stop after P1 evidence is recorded.  Do not auto-admit the smoke.

The next authorized design checkpoint is P2: select/admit the appropriate real-video
candidate path and execute the four canonical shot videos at their exact full frame
counts (`168 / 168 / 192 / 192`) through the same V5/V4 lineage.  P2 requires its own
contract and tests before host execution.

G7/frontend, Master/export and publication remain out of this P1 runbook.
