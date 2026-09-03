# Cross-Repository Behavior Baseline

Status: `CURRENT / METHOD-AWARE PUBLIC CUTOVER VERIFIED`

Reviewed: `2026-09-03`

## 1. Current repository and behavior values

```text
CORE_MAIN=7feca3b2a4cbacdf2d50e4ccacb0d9f357249de0
CORE_TREE=3a8f76dc805c772ab80bd6a33f1a737fb1fb6c31
CORE_BEHAVIOR_MAIN=5c9ea7fe6993eddb7a492b2ae8f6bd8c2d5ae326
CORE_BEHAVIOR_TREE=de6d43a16f97c1e34dc536336d05b0174d9aab39

FRONTEND_MAIN=d9f25165061988a5d7edb101aa881b0bc6f40bed
FRONTEND_TREE=a72d63ff37914096ae6114993c9bed2cfb14cf1c
FRONTEND_PIN_CORE_SHA=5c9ea7fe6993eddb7a492b2ae8f6bd8c2d5ae326
FRONTEND_PIN_CORE_TREE=de6d43a16f97c1e34dc536336d05b0174d9aab39
FRONTEND_PIN_MATCHES_CORE_BEHAVIOR=true

M13_BASE_TAG=m13-base-backend-v1
M13_BASE_TAG_OBJECT=b2d086b622bdb5456f6af325e458aa3771e43e80
M13_BASE_TAG_TARGET=a455c8e76427d53d75bb7f15259b9875d9768914
```

`CORE_MAIN` records the final merged upstream-method implementation baseline.
`CORE_BEHAVIOR_MAIN` is the production-behavior commit pinned by Frontend. Core PR
#59 is tests/fixtures only, so the pin intentionally targets PR #58. Documentation-
only and CI-only merges may advance the branch without moving either behavior pin.

## 2. Closed upstream wave

```text
UPSTREAM_METHOD_CLOSURE=PASS
GENERIC_NON_K2_VERTICAL_SLICE=PASS
M3_M6_CONSUMER_BINDING=IMPLEMENTED
M7_NARRATIVE_VALIDATION=IMPLEMENTED_BOUNDED
M8_ACTION_EXECUTION_BEATS=IMPLEMENTED
M8_EXECUTION_CLASS=IMPLEMENTED
M9_THREE_AXIS_REQUIREMENTS=IMPLEMENTED
M10_METHOD_AWARE_PLANNING=IMPLEMENTED
M11_METHOD_CAPABILITY_BOUNDARY=IMPLEMENTED
M9_M12_AUDIO_BRIDGE=IMPLEMENTED
K2_METHOD_AWARE_PUBLIC_CUTOVER=PASS
LEGACY_G4_NEW_WRITES=DISABLED
LEGACY_G5_NEW_WRITES=DISABLED
LEGACY_G4_G5_READ_REPLAY=SUPPORTED
K2_002_METHOD_AWARE_SUCCESSOR_REQUIRED=true
M11_CONTACT_RUNTIME=NOT_INSTALLED
M11_GAIT_RUNTIME=NOT_INSTALLED
```

Frontend PR #24 validated the unchanged five-state capability adapter and both real
browser gates against the exact Core behavior tree. This pin proves compatibility,
not complete M12/M13 product surfaces or production readiness.

## 3. Immutable M13 tag

`m13-base-backend-v1` is an annotated tag. Its tag object and peeled commit must
remain exactly as recorded above.

```text
M13_BASE_TAG_IMMUTABLE=true
M13_BASE_BACKEND_COMPLETE=true
M13_BASE_CLOSEOUT_ACCEPTED=true
M13_PRODUCT_CAPABILITY_COMPLETE=false
```

The tag proves the accepted M13 base backend only. It does not prove Frontend product
completion, M14 QC/Approval, M15 Master/Export or publication.

## 4. Preserved predecessor snapshots

The following values preserve the earlier M13 closeout and pre-pin Frontend snapshots
for the already-merged documentation validator. They are historical compatibility
facts, not current branch refs:

```text
M13_FROZEN_CORE_MAIN=a455c8e76427d53d75bb7f15259b9875d9768914
M13_FROZEN_CORE_TREE=d92159d5c3c5d3896d1fe9e56b896413277fe4e8
PRE_PIN_FRONTEND_MAIN=a0be9edc91437bf0e7c5dd14883e656e750b3aee
PRE_PIN_FRONTEND_TREE=c25b9e3744d561c93fed26d0a07e59a1915a6071
```

## 5. Closed execution boundaries

```text
M12_RUNTIME_G0=NOT_COMPLETE
M12_C3_PREREQUISITE_UPSTREAM=PASS
M12_A100_BUILD_HOST_PREFLIGHT=FAIL
M12_C3_PREIMPLEMENTATION_BLOCKER=A100_BUILD_HOST_INFRASTRUCTURE_REMEDIATION_PENDING
M12_C3_READY_TO_REQUEST_AUTHORIZATION=false
M12_C3_READY_TO_START=false
M13_EXTENSION_G0_AUTHORIZED=false
A100_START_AUTHORIZED=false
GPU_CALLS_ALLOWED=false
PROVIDER_CALLS_ALLOWED=false
PUBLICATION_ALLOWED=false
```

The next legal boundary is
`ACS-M12-A100-BUILD-HOST-INFRASTRUCTURE-REMEDIATION-AND-REFLIGHT`. Its name does not
authorize starting the host, installing a runtime, using a GPU, calling a Provider or
entering C3/C4 without a separate execution authorization.
