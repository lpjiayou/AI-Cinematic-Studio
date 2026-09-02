# AI Cinematic Studio — Current Execution State

Status: `CURRENT / EVIDENCE-BACKED / FAIL-CLOSED`

Last reviewed: `2026-09-02`

## 1. Current baselines

The behavior baselines are frozen even though documentation-only merges may advance
the repositories' `main` refs:

```text
CORE_BEHAVIOR_BASELINE=a455c8e76427d53d75bb7f15259b9875d9768914
CORE_BEHAVIOR_TREE=d92159d5c3c5d3896d1fe9e56b896413277fe4e8
CORE_BEHAVIOR_TAG=m13-base-backend-v1
CORE_TAG_OBJECT=b2d086b622bdb5456f6af325e458aa3771e43e80
CORE_TAG_TARGET=a455c8e76427d53d75bb7f15259b9875d9768914
FRONTEND_BEHAVIOR_BASELINE=a0be9edc91437bf0e7c5dd14883e656e750b3aee
FRONTEND_BEHAVIOR_TREE=c25b9e3744d561c93fed26d0a07e59a1915a6071
M13_BASE_TAG_IMMUTABLE=true
```

The Frontend pin is a tested Core behavior baseline. It does not prove that every
Frontend M12/M13 product surface exists. See
[`docs/status/CROSS_REPOSITORY_BASELINE.md`](docs/status/CROSS_REPOSITORY_BASELINE.md).

## 2. Current capability projection

The six-dimensional, evidence-linked source is
[`docs/status/M1-M19-CAPABILITY-STATUS.md`](docs/status/M1-M19-CAPABILITY-STATUS.md).

| Range | Current high-level state |
| --- | --- |
| M1–M2, M4–M5 | Bounded Core and connected Frontend capabilities exist; live production readiness remains unverified. |
| M3 | Historical ScriptVersion v1 remains readable; the additive v2 successor now stores one exact server-resolved M6 consumer binding. |
| M6 | The bounded Series Intelligence reader now supplies the immutable M3 binding and M7 currentness input; missing authority still fails closed. |
| M7 | Generic immutable narrative validation, structured Findings, PASS/WARN/BLOCK, staleness and fail-closed M8 readiness are implemented on the existing evidence journal. |
| M8 | Additive Storyboard/CreativeShot v2 and five-class ActionExecutionBeat planning are implemented behind the current M7 READY gate on the existing evidence journal. |
| M9 | Independent Visual/Audio/Postprocess requirements and closed dispositions are implemented as planning facts; they create no provider or media job. |
| M10 | Generic method-aware input requirements now resolve only current admitted AssetVersions through the existing candidate/QC/selection/admission chain; historical K2 exact-four behavior is unchanged. |
| M11 | A closed method registry queues only MICRO_MOTION/SINGLE_ANCHOR_I2V on the existing coordinator; Contact/Gait are capability-unavailable, static media bypasses video and deterministic events remain on the M13 path. |
| M12 | Domain contracts and runtime protocols are merged; runtimes are not installed, Runtime G0 is not complete, and C3/C4 have not started. |
| M13 | Base architecture, backend and deterministic CPU slice are complete and closeout is accepted; product capability is incomplete. |
| M14–M19 | Implementation is not authorized; production and publication remain closed. |

The decisive M12/M13 state is:

```text
M12_DOMAIN_CONTRACT=MERGED
M12_RUNTIME_PROTOCOL=MERGED
M12_RUNTIME_INSTALLED=false
M12_RUNTIME_G0=NOT_COMPLETE
M12_G0_3_STATE=ENVIRONMENT_HOLD
M12_FRONTEND=UNVERIFIED
M12_PRODUCT=NOT_COMPLETE
M12_PRODUCTION=NOT_AUTHORIZED
M12_C3_READY_TO_START=false

M13_BASE_ARCHITECTURE=ACCEPTED
M13_BASE_BACKEND=COMPLETE
M13_BASE_RUNTIME_CPU=VERIFIED
M13_BASE_CLOSEOUT=ACCEPTED
M13_FRONTEND_PRODUCT_SURFACE=INCOMPLETE
M13_EXTENSION_CATALOG=NOT_AUTHORIZED
M13_M14_M15_INTEGRATION=NOT_AUTHORIZED
M13_PUBLICATION=NOT_AUTHORIZED
M13_PRODUCT_CAPABILITY_COMPLETE=false
```

## 3. Current authorization and execution wave

The documentation-governance wave is complete and its required-check fast path is
available. The active Project Lead authorization is the upstream execution-method
closure accepted in
[`ADR-0019`](governance/ADR-0019-upstream-execution-method-and-requirement-routing.md)
and specified by
[`M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md`](architecture/M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md):

```text
ACTIVE_TASK=ACS-M3-M11-UPSTREAM-METHOD-CLOSURE
EXECUTION_MODE=AUTO-SEQUENTIAL_BOUNDED_SERIAL
GPU_REQUIRED=false
PROVIDER_CALLS_ALLOWED=false
A100_START_AUTHORIZED=false

ARCHITECTURE_CHECKPOINT=ADR_0019_ACCEPTED_AND_MERGED
AUTHORIZED_SEQUENCE=PR-B→PR-C→PR-D→PR-E→PR-F→FRONTEND_PIN
COMPLETED_SEQUENCE=PR-A→PR-B→PR-C→PR-D
AUTHORIZED_REMAINING_SEQUENCE=PR-E→PR-F→FRONTEND_PIN

M3_M6_CONSUMER_BINDING=IMPLEMENTED_BOUNDED
M7_NARRATIVE_VALIDATION=IMPLEMENTED_BOUNDED
M8_ACTION_EXECUTION_BEATS=IMPLEMENTED_BOUNDED
M9_THREE_AXIS_REQUIREMENTS=IMPLEMENTED_BOUNDED
M10_METHOD_AWARE_PLANNING=IMPLEMENTED_BOUNDED
M11_METHOD_CAPABILITY_BOUNDARY=IMPLEMENTED_FAIL_CLOSED
M9_M12_AUDIO_BRIDGE=AUTHORIZED_NOT_IMPLEMENTED
NEXT_SERIAL_PR=PR-E_M9_M12_EXPLICIT_AUDIO_REQUIREMENT_BRIDGE
```

The following merged governance facts remain true and continue to protect every PR
in this wave:

```text
DOCUMENT_GOVERNANCE_VALIDATION=IMPLEMENTED
DOCS_ONLY_CI_FAST_PATH=IMPLEMENTED
REQUIRED_CHECK_CONTEXTS=5_UNCHANGED
PROTECTED_CHANGE_FULL_SUITE=ENFORCED
POST_MERGE_DUPLICATE_FULL_CI=REMOVED
```

The PRs are strictly serial. A later PR may start only after the prior PR is merged,
all five required checks succeed, `origin/main` is re-fetched, the worktree is clean
and no concurrent scope conflict exists. PR-F may modify tests/fixtures only.

The M12 runtime remains incomplete. The future C3/C4 target host decision is recorded,
but no host or GPU action is authorized in this wave:

```text
M12_C3_C4_TARGET_HOST=A100_CODE_SERVER_BUILD_HOST
M12_RUNTIME_G0=NOT_COMPLETE
M12_C3_READY_TO_START=false
A100_START_AUTHORIZED=false
A100_GPU_EXECUTION_AUTHORIZED=false
```

After the full upstream wave and final read-only closeout, the next legal task is:

```text
NEXT_TASK=ACS-M12-C3-C4-A100-BUILD-HOST-PREFLIGHT
```

That identifier is a preflight boundary, not authorization to start the host, install
a runtime, use a GPU or execute M12-C3/C4.

The previous governance validator token is retained only for compatibility with the
already-merged docs-only fast-path checker; it is superseded by the active and next
task fields above and grants no execution authority:

```text
SUPERSEDED_VALIDATOR_NEXT_TASK=LOCAL_WSL2_HANDOFF_AND_M12_C3_PREFLIGHT
SUPERSEDED_VALIDATOR_TOKEN_GRANTS_AUTHORITY=false
```

## 4. Explicit prohibitions

```text
M12_C3_READY_TO_START=false
M12_C4_AUTHORIZED=false
M13_EXTENSION_G0_AUTHORIZED=false
M13_EXTENSION_IMPLEMENTATION_AUTHORIZED=false
A100_START_AUTHORIZED=false
GPU_CALLS_ALLOWED=false
PROVIDER_CALLS_ALLOWED=false
ASSET_ADMISSION_ALLOWED=false
PUBLICATION_ALLOWED=false
M14_M15_IMPLEMENTATION=NOT_AUTHORIZED
EPISODE_MASTER_CREATED=0
EXPORT_ARTIFACT_CREATED=0

GPU_OR_PROVIDER_CALLS=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
ASSET_ADMISSION=0
LIVE_CANONICAL_MUTATIONS=0
```

Additional architecture guards for this wave are:

```text
SECOND_SCRIPT_AUTHORITY_CREATED=false
SECOND_M6_AUTHORITY_CREATED=false
SECOND_IDENTITY_AUTHORITY_CREATED=false
SECOND_SHOT_AUTHORITY_CREATED=false
SECOND_ASSET_AUTHORITY_CREATED=false
SECOND_MEDIA_QUEUE_CREATED=false
SIDECAR_DATABASE_CREATED=false
K2_HARDCODED_PRODUCTION_BRANCHES=0
```

`RenderCandidate` is non-publishing and is not `EpisodeMaster` or `ExportArtifact`.
Machine QC is not human Approval. Historical K2 evidence does not authorize a new live
write.

## 5. Immutable history

The former section `## 0A.` through EOF is preserved byte-for-byte in
[`CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md`](CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md).

```text
HISTORICAL_SECTION_SHA256=5e05b68e83ed55f90b342aee627001a7bbf66cf59f92e5106270175b07f61f6a
HISTORICAL_DOCUMENT_GRANTS_CURRENT_AUTHORITY=false
HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true
```

Historical uses of “current”, “next”, “authorized” or local paths retain their original
checkpoint meaning and do not override this projection, an Accepted ADR or a current
Project Lead authorization.
