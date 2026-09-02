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
| M1–M5 | Bounded Core and connected Frontend capabilities exist; live production readiness remains unverified. |
| M6 | Accepted and implemented bounded Series Intelligence boundary; missing external authority continues to fail closed. |
| M7–M11 | Repository/K2 evidence exists, including an immutable M11 visual-QC failure; this is not general product or live-production completion. |
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

## 3. Current authorization and blockers

The active authorization is repository-validation governance only:

```text
ACTIVE_TASK=ACS-DOCUMENTATION-GOVERNANCE-PR-D-AND-DOCS-ONLY-CI-FAST-PATH
DOCS_ONLY=true
GPU_REQUIRED=false
A100_START_AUTHORIZED=false

DOCUMENT_GOVERNANCE_VALIDATION=IMPLEMENTED
DOCS_ONLY_CI_FAST_PATH=IMPLEMENTED
REQUIRED_CHECK_CONTEXTS=5_UNCHANGED
PROTECTED_CHANGE_FULL_SUITE=ENFORCED
POST_MERGE_DUPLICATE_FULL_CI=REMOVED
```

The M12 runtime remains blocked by the absent persistent CPU build environment:

```text
PERSISTENT_CPU_BUILD_ROOT=/data/k2-runtime-artifacts/m12/g0
PERSISTENT_CPU_BUILD_ROOT_PRESENT=false
BLOCK_REASON=PERSISTENT_CPU_BUILD_ARTIFACT_ROOT_UNAVAILABLE
```

The next legal product task after this documentation-governance wave is:

```text
NEXT_TASK=LOCAL_WSL2_HANDOFF_AND_M12_C3_PREFLIGHT
```

That identifier is a handoff/preflight boundary, not authorization to execute M12-C3.

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
