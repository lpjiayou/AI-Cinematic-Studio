# Cross-Repository Behavior Baseline

Status: `CURRENT / IMMUTABLE BEHAVIOR BASELINE`

Reviewed: `2026-09-02`

## 1. Frozen values

```text
CORE_MAIN=a455c8e76427d53d75bb7f15259b9875d9768914
CORE_TREE=d92159d5c3c5d3896d1fe9e56b896413277fe4e8
M13_BASE_TAG=m13-base-backend-v1
M13_BASE_TAG_OBJECT=b2d086b622bdb5456f6af325e458aa3771e43e80
M13_BASE_TAG_TARGET=a455c8e76427d53d75bb7f15259b9875d9768914
FRONTEND_MAIN=a0be9edc91437bf0e7c5dd14883e656e750b3aee
FRONTEND_TREE=c25b9e3744d561c93fed26d0a07e59a1915a6071
```

`CORE_MAIN` and `FRONTEND_MAIN` above name the frozen behavior snapshots, not a promise
that documentation-only governance merges leave the branch refs at those commits.

## 2. Tag semantics

`m13-base-backend-v1` is an annotated tag object. Its object and peeled commit must
remain exactly as shown above.

```text
M13_BASE_TAG_IMMUTABLE=true
M13_BASE_BACKEND_COMPLETE=true
M13_BASE_CLOSEOUT_ACCEPTED=true
M13_PRODUCT_CAPABILITY_COMPLETE=false
```

Documentation work may advance `main`; it must not move, recreate or replace the tag.
The tag proves the accepted M13 base backend behavior only. It does not prove Frontend
product-surface completion, M14 QC/Approval, M15 Master/Export or publication.

## 3. Frontend pin semantics

The Frontend baseline pins a tested Core behavior commit/tree for cross-repository CI.
A pin-only Frontend change means compatibility was revalidated against that Core
behavior. It does not implement a Timeline Studio, Effect Inspector, RenderCandidate
review product, M12 audio UI, M14/M15 integration or publication.

The governance wave must not modify `CORE_PIN_SHA` or `CORE_PIN_TREE`. A later pin move
requires its own authorized compatibility task and evidence.

## 4. Closed execution boundaries

```text
M12_RUNTIME_G0=NOT_COMPLETE
M12_C3_READY_TO_START=false
M13_EXTENSION_G0_AUTHORIZED=false
A100_START_AUTHORIZED=false
GPU_CALLS_ALLOWED=false
PROVIDER_CALLS_ALLOWED=false
PUBLICATION_ALLOWED=false
```

The next legal project boundary after documentation governance is
`LOCAL_WSL2_HANDOFF_AND_M12_C3_PREFLIGHT`; it is not C3 execution authority.
