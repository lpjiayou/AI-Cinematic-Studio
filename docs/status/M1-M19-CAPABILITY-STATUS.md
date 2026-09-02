# M1–M19 Capability Status

Status: `CURRENT / SIX-DIMENSIONAL / FAIL-CLOSED`

Reviewed: `2026-09-02`

## 1. Reading rules

This matrix deliberately avoids a single `COMPLETE` flag. Architecture, backend,
runtime, Frontend, product and production can advance independently. `UNVERIFIED`
means the frozen repositories do not contain enough auditable evidence for a stronger
claim; it must not be inferred from roadmap prose.

Repository implementation evidence does not establish a live provider, GPU, human
Approval or publication fact. Project-specific K2 evidence does not prove a general
milestone product. The immutable M13 behavior tag applies only to the accepted M13 base
backend.

## 2. Six-dimensional matrix

| Milestone | ARCHITECTURE_STATUS | BACKEND_STATUS | RUNTIME_STATUS | FRONTEND_STATUS | PRODUCT_STATUS | PRODUCTION_STATUS |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | `BASELINE_DEFINED` | `IMPLEMENTED` | `REPOSITORY_VERIFIED` | `CONNECTED_BASELINE` | `IMPLEMENTED_BOUNDED` | `UNVERIFIED` |
| M2 | `BASELINE_DEFINED` | `IMPLEMENTED` | `REPOSITORY_VERIFIED` | `CONNECTED_BASELINE` | `IMPLEMENTED_BOUNDED` | `UNVERIFIED` |
| M3 | `BASELINE_DEFINED_ADR_0019_BINDING_ACCEPTED` | `IMPLEMENTED_M6_BOUND_V2` | `LOCAL_SQLITE_RESTART_VERIFIED` | `CONNECTED_V1_BASELINE_V2_PIN_PENDING` | `IMPLEMENTED_BOUNDED` | `UNVERIFIED` |
| M4 | `BASELINE_DEFINED` | `IMPLEMENTED` | `REPOSITORY_VERIFIED` | `CONNECTED_BASELINE` | `IMPLEMENTED_BOUNDED` | `UNVERIFIED` |
| M5 | `BASELINE_DEFINED` | `IMPLEMENTED` | `REPOSITORY_VERIFIED` | `CONNECTED_BASELINE` | `IMPLEMENTED_BOUNDED` | `UNVERIFIED` |
| M6 | `ACCEPTED_ADR_0019_BINDING_INPUT` | `IMPLEMENTED_BOUNDED_CONSUMER_BOUND` | `LOCAL_SQLITE_VERIFIED` | `ACCEPTED_FAIL_CLOSED_BOUNDARY` | `BOUNDED_ACCEPTED` | `NOT_AUTHORIZED` |
| M7 | `ADR_0019_ACCEPTED` | `IMPLEMENTED_NARRATIVE_CURRENTNESS` | `LOCAL_SQLITE_RESTART_VERIFIED` | `NO_DEDICATED_SURFACE_PIN_PENDING` | `IMPLEMENTED_BOUNDED` | `NOT_AUTHORIZED` |
| M8 | `ADR_0019_ACCEPTED` | `IMPLEMENTED_ACTION_EXECUTION_BEATS_V2` | `LOCAL_SQLITE_RESTART_VERIFIED` | `CONNECTED_V1_BASELINE_V2_PIN_PENDING` | `IMPLEMENTED_BOUNDED` | `NOT_AUTHORIZED` |
| M9 | `ADR_0019_ACCEPTED` | `IMPLEMENTED_THREE_AXIS_REQUIREMENTS` | `LOCAL_SQLITE_RESTART_VERIFIED` | `CONNECTED_V1_BASELINE_V2_PIN_PENDING` | `IMPLEMENTED_BOUNDED` | `NOT_AUTHORIZED` |
| M10 | `ADR_0019_ACCEPTED` | `IMPLEMENTED_METHOD_AWARE_INPUT_PLANNING` | `LOCAL_SQLITE_RESTART_VERIFIED_NO_MODEL_CALL` | `MAPPING_ONLY` | `IMPLEMENTED_BOUNDED` | `NOT_AUTHORIZED` |
| M11 | `ADR_0019_ACCEPTED_FAIL_CLOSED_METHOD_BOUNDARY` | `IMPLEMENTED_CLOSED_METHOD_ROUTING` | `WAN_MICRO_QUEUE_ONLY_CONTACT_GAIT_UNAVAILABLE` | `MAPPING_ONLY` | `IMPLEMENTED_BOUNDED_HISTORICAL_QC_FAILURE_PRESERVED` | `NOT_AUTHORIZED` |
| M12 | `ACCEPTED_ADR_0019_AUDIO_BRIDGE` | `EXPLICIT_M9_REQUIREMENT_BRIDGE_IMPLEMENTED` | `NOT_INSTALLED_G0_NOT_COMPLETE` | `V1_ADAPTER_SCHEMA_COMPATIBLE_PIN_PENDING` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |
| M13 | `BASE_ACCEPTED` | `BASE_BACKEND_COMPLETE_RENDER_CANDIDATE_PROJECTED` | `DETERMINISTIC_CPU_VERIFIED` | `PIN_ONLY_PRODUCT_SURFACE_INCOMPLETE` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |
| M14 | `PLANNED_AND_BOUNDARY_CONSTRAINED` | `NOT_AUTHORIZED` | `NOT_STARTED` | `UNVERIFIED` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |
| M15 | `PLANNED_AND_BOUNDARY_CONSTRAINED` | `NOT_AUTHORIZED` | `NOT_STARTED` | `UNVERIFIED` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |
| M16 | `PLANNED_MASTER_ONLY` | `NOT_AUTHORIZED` | `NOT_STARTED` | `UNVERIFIED` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |
| M17 | `PLANNED_MASTER_ONLY` | `NOT_AUTHORIZED` | `NOT_STARTED` | `UNVERIFIED` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |
| M18 | `PLANNED_MASTER_ONLY` | `NOT_AUTHORIZED` | `NOT_STARTED` | `UNVERIFIED` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |
| M19 | `PLANNED_MASTER_ONLY` | `NOT_AUTHORIZED` | `NOT_STARTED` | `UNVERIFIED` | `NOT_COMPLETE` | `NOT_AUTHORIZED` |

## 3. Evidence, blockers and next legal task

`PR=UNVERIFIED` below is intentional where early repository history records a commit
but not a uniquely provable pull-request number.

| M | Accepted ADR / architecture source | Implementation PR | Merge commit | Behavior tag | Test / acceptance evidence | Current blocker | Next legal task |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | [`ADR-0002`](../../governance/ADR-0002-v5-lifecycle-integrity-boundary.md) for lifecycle; milestone-specific ADR `UNVERIFIED` | `PR=UNVERIFIED` | `8bf3dc42323007202b083663125e0c31f8e93802` AI Director | none dedicated | `4191a379c77339d4735018f68c600db238f3cba7` repository UI verification | live production evidence absent | separately authorize production-readiness proof if required |
| M2 | [`ADR-0002`](../../governance/ADR-0002-v5-lifecycle-integrity-boundary.md); milestone-specific ADR `UNVERIFIED` | `PR=UNVERIFIED` | `f0fd38ab22a41e00bac3e1e39e9667625b62de15` Series/Episode | none dedicated | current required suite plus immutable repository history; dedicated acceptance `UNVERIFIED` | live production evidence absent | separately authorize production-readiness proof if required |
| M3 | [`ADR-0002`](../../governance/ADR-0002-v5-lifecycle-integrity-boundary.md); [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | `#55` | existing v1 history plus the M6-bound v2 implementation tree tested by `#55` | none dedicated | `test_narrative_currentness_m7.py`; `test_creator_narrative_currentness_m7.py` SQLite restart | Frontend behavior pin remains later in this wave | PR-F generic acceptance, then Frontend pin |
| M4 | System Master Plan; milestone-specific Accepted ADR `UNVERIFIED` | `PR=UNVERIFIED` | `4ec5de7273076d3b4f66272b6a4f0e3eecd89073` | none dedicated | current required suite; milestone-specific acceptance `UNVERIFIED` | live production evidence absent | separately authorize production-readiness proof if required |
| M5 | System Master Plan; milestone-specific Accepted ADR `UNVERIFIED` | `PR=UNVERIFIED` | `8c3e4271662e1e02e963618ade3c29d6e9f91e89` | none dedicated | current required suite; milestone-specific acceptance `UNVERIFIED` | live production evidence absent | separately authorize production-readiness proof if required |
| M6 | [`ADR-0003`](../../governance/ADR-0003-m6-series-intelligence-baseline.md), [`ADR-0004`](../../governance/ADR-0004-m6-series-intelligence-durable-sqlite-boundary.md), [`ADR-0005`](../../governance/ADR-0005-m6-series-intelligence-consumer-boundary.md), [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | early history `PR=UNVERIFIED`; `#55` for M3/M7 consumer closure | `5976263f92f7f9cbe9c091719eccb036ee8c0c2d` plus the consumer-binding tree tested by `#55` | none dedicated | exact server-resolved binding and stale-baseline tests | external production authority remains unavailable by default | PR-F generic acceptance, then Frontend pin |
| M7 | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md); [`ADR-0008`](../../governance/ADR-0008-k2-single-episode-production-closure.md) remains exact K2 history | `#55` | generic M7 implementation tree tested by `#55`; historical K2 root remains unchanged | none dedicated | all Finding categories, PASS/WARN/BLOCK, staleness, replay, cross-scope and SQLite restart tests | Frontend behavior pin remains later in this wave | PR-F generic acceptance, then Frontend pin |
| M8 | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | `#56` | additive v2 implementation tree tested by `#56`; historical `885245146cb497710fbaa616e0b16b1413f119dd` K2 graph remains readable | none dedicated | five classes, multi-beat coverage, overlap/key rejection, M7 staleness, exact replay and SQLite restart | generic non-K2 vertical acceptance remains pending | PR-F tests/fixtures only after `#58` merge |
| M9 | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | `#56`, `#58` downstream bridge | generic three-axis planning tree tested by `#56`; the explicit audio consumer tree is tested by `#58`; historical `2841526a7d505b2fca7722a24392dc48d0558283` K2 requirements remain readable | none dedicated | explicit Visual/Audio/Postprocess arrays, every audio type, SILENCE zero-request, exact source-span/currentness and SQLite replay | generic non-K2 vertical acceptance remains pending | PR-F tests/fixtures only after `#58` merge |
| M10 | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md); K2 history remains under ADR-0011/0012 | `#57` | generic method-aware input-plan tree tested by `#57`; historical `448be50d1c9341f4f21a57def0257dd80d082684` K2 admission remains unchanged | none dedicated | per-method static/anchor/contact/gait/event-free requirements, exact current AssetVersion/admission-chain binding, replay/stale and SQLite restart tests | live generic image generation/admission is not authorized; Contact/Gait inputs remain requirements only | PR-F generic acceptance after `#58`; no runtime expansion |
| M11 | [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md); historical K2 failure remains immutable | `#57` | queue-only closed router tree tested by `#57`; historical `f93f9d3b5e9ae181b09120b9bc219f2df16c3b54` K2 candidates remain readable | none dedicated | Wan Micro positive reservation; Contact/Gait unavailable; static bypass; deterministic rejection; neutral SH12 mechanism regression; zero adapter/GPU/Provider/ComfyUI/prompt calls | Contact/Gait runtimes are not installed; `9efc5b93657f89c34d84a8e34a65227a36d1942d` historical visual-QC failure remains immutable | PR-F generic acceptance after `#58`; no runtime expansion |
| M12 | [`ADR-0015`](../../governance/ADR-0015-m12-isolated-audio-runtime-and-acyclic-voice-clone-lineage.md), [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | `#20`, `#21`, `#24`–`#27`, `#30`, `#32`, `#34`, `#58` | `0386cd6da5fd434a0d525c7ec004ceb98d824b3e` runtime protocols plus the additive explicit-M9 bridge tree tested by `#58` | none dedicated | every AudioRequirement type, exact speech source/speaker/timing, clone lineage, stale M9/VoiceLock/Consent, DTO redaction, no legacy write and SQLite restart | runtimes remain uninstalled; Runtime G0 and C3/C4 are not complete/authorized | PR-F acceptance, then Frontend pin; C3/C4 remain unauthorized |
| M13 | [`ADR-0016`](../../governance/ADR-0016-m13-timeline-render-candidate-and-deterministic-post-boundary.md), [`ADR-0017`](../../governance/ADR-0017-canonical-static-resource-assets-and-font-license-boundary.md), [`ADR-0018`](../../governance/ADR-0018-canonical-identity-reference-version-projection-and-runtime-currentness-boundary.md) | `#23`, `#29`, `#31`, `#33`, `#35`, `#36`, `#41`, `#42`, `#48`, projection correction `#58` | `a455c8e76427d53d75bb7f15259b9875d9768914` closeout; existing RenderCandidate is now present in the v1 capability projection | `m13-base-backend-v1` object `b2d086b622bdb5456f6af325e458aa3771e43e80` | `783b981b9c0e0ee3e400692fe556b00867b45f41` CPU vertical slice, `#48` acceptance and `#58` closed-state projection test | Frontend product surface, extension catalog, M14/M15 and publication incomplete/not authorized | finish PR-F and Frontend behavior pin; no Extension G0 implicit start |
| M14 | System Master Plan plus M13 endpoint constraints in [`ADR-0016`](../../governance/ADR-0016-m13-timeline-render-candidate-and-deterministic-post-boundary.md) | none | none | none | none | implementation not authorized; human Approval boundary absent | Project Lead architecture/work-package authorization |
| M15 | System Master Plan plus exclusive Master/Export boundary in [`ADR-0016`](../../governance/ADR-0016-m13-timeline-render-candidate-and-deterministic-post-boundary.md) | none | none | none | none | implementation not authorized; M14 acceptance absent | Project Lead architecture/work-package authorization after M14 |
| M16 | System Master Plan; Accepted ADR `UNVERIFIED` | none | none | none | none | M15/P9 and Gate A/B/C prerequisites absent | no legal implementation task currently authorized |
| M17 | System Master Plan; Accepted ADR `UNVERIFIED` | none | none | none | none | earlier milestone and authority prerequisites absent | no legal implementation task currently authorized |
| M18 | System Master Plan; Accepted ADR `UNVERIFIED` | none | none | none | none | earlier milestone and authority prerequisites absent | no legal implementation task currently authorized |
| M19 | System Master Plan; Accepted ADR `UNVERIFIED` | none | none | none | none | earlier milestone and authority prerequisites absent | no legal implementation task currently authorized |

## 4. Required M12 projection

```text
M12_DOMAIN_CONTRACT=MERGED
M12_RUNTIME_PROTOCOL=MERGED
M9_M12_EXPLICIT_AUDIO_BRIDGE=IMPLEMENTED_BOUNDED_FAIL_CLOSED
M12_AUDIO_REQUEST_RUNTIME_DISPATCH=NOT_AUTHORIZED
M12_RUNTIME_INSTALLED=false
M12_RUNTIME_G0=NOT_COMPLETE
M12_FRONTEND=UNVERIFIED
CREATOR_CAPABILITY_ADAPTER_SCHEMA=V1_COMPATIBLE
M12_PRODUCT=NOT_COMPLETE
M12_PRODUCTION=NOT_AUTHORIZED
M12_G0_3_STATE=ENVIRONMENT_HOLD
M12_C3_READY_TO_START=false
A100_START_AUTHORIZED=false
```

## 5. Required M13 projection

```text
M13_BASE_ARCHITECTURE=ACCEPTED
M13_BASE_BACKEND=COMPLETE
M13_BASE_RUNTIME_CPU=VERIFIED
M13_BASE_CLOSEOUT=ACCEPTED
M13_RENDER_CANDIDATE_RESOURCE_PROJECTED=true
M13_FRONTEND_PRODUCT_SURFACE=INCOMPLETE
M13_EXTENSION_CATALOG=NOT_AUTHORIZED
M13_M14_M15_INTEGRATION=NOT_AUTHORIZED
M13_PUBLICATION=NOT_AUTHORIZED
M13_PRODUCT_CAPABILITY_COMPLETE=false
```
