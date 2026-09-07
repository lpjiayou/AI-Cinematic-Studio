# M5 / M7 Legal Entrypoint Closure — E3E

Status: `BOUNDED_IMPLEMENTATION / LOCAL_VALIDATION / REQUIRED_CI_GATE`

Owner: Project Lead / M5 Binding Owner / M7 Narrative Validation Owner / Creator Public HTTP Owner

## Authority and baseline

```text
TASK_ID=ACS-M5-M7-LEGAL-ENTRYPOINT-CLOSURE-CORRECTIVE-E3E
CORE_START_MAIN=4755c73330d775591d479966f007e8fa39996d54
CORE_START_TREE=86d3757d82c7b526242e891b6ba84a458ca2851d
BRANCH=fix/m5-m7-legal-entrypoints-e3e
TASK_COMMIT_COUNT_MAX=1
TASK_PR_COUNT_MAX=1
CI_SCOPE=FULL_SUITE
```

The bounded Project Lead authorization connects existing M5 and M7 public domain
capabilities under [ADR-0005](../../governance/ADR-0005-m6-series-intelligence-consumer-boundary.md),
[ADR-0019](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md)
and the [public HTTP contract](../04-interface-contract/creator-public-http-v1.md).
It does not authorize a new domain, storage schema or live R6 execution. One PR-head
CI wait and verified squash merge/automatic branch deletion are required for closure;
this document does not predict its own commit or merge identity.

## Accepted audit is unchanged

The supplied audit report and evidence index were re-hashed against actual bytes:

```text
AUDIT_REPORT_SHA256=56aaa2d3d5312158e4426ffac95b72f6b51196fef12927b30824a9f1cd3671f9
AUDIT_EVIDENCE_INDEX_SHA256=63cd2e484f4fabc81531905fcada135907d8db3fa6c91a9b863b020928e7d183
R6_PREFLIGHT_MATRIX_SHA256=9d6c7b6fcfeaa93c9fe65a2879099346f70cf18e0419870beaf5f889130c3202
AUDIT_ENDPOINT_CLASSIFICATION=28_TOTAL_19_SAFE_8_UNSAFE_1_UNPROVEN
AUDIT_CASE_CLASSIFICATION=53_TOTAL_39_SAFE_12_UNSAFE_2_UNPROVEN
AUDIT_FINDINGS_PRESERVED=true
AUDIT_SWEEP_REEXECUTED=false
```

The original R6 Phase A matrix was available. B1 and B2 describe entrypoint gaps;
they are not themselves idempotency failures. E3E records its additional resource
verification separately and does not recalculate the original 28-endpoint audit.
None of the 105 audit databases or historical R3/R4/R5/R6 inputs were reused.

## M5 controlled operator

`apps/creator_workspace_mvp/episode_plan_binding_operator.py` and
`scripts/episode_plan_item_binding.py` provide a default read-only preflight and
explicit `--apply`. Managed configuration restricts target, scope and authorization
metadata independently of input. Existing regular-file and parent-chain checks,
strict JSON/field checks, exact source content digest, trusted membership and unchanged
CAS are required. Public Lifecycle composition validates the existing database and
does not initialize, migrate or repair it. No SQL/private repository or lease is used
by the application; all writes call `create_episode_plan_item_binding_version`.

Complete explicit pairs are canonically ordered by source item position, not inferred
from episode numbers or titles. One apply appends at most one v2 binding successor;
v1/v2 source content and history are preserved. It never confirms or activates M6.
The first acknowledgement preserves the domain's draft response. Recovery instead
returns actual current public Plan/version reads after proving one exact successor,
parent, change kind, complete pair set, unchanged content and one-step advance.
Later advancement, ambiguity or insufficient evidence fails closed without another
write. It never refreshes CAS or reconstructs a historical confirmation receipt.

`BINDING_VERSION_CREATED`, `BINDING_VERSION_CURRENT` and
`BINDING_VERSION_CONFIRMED` are separate. The existing SQLite adapter can preserve the
root's earlier `confirmed` status while returning draft for a binding command; its
confirmed pointer remains on the old version. This behavior is unchanged and is not
interpreted as confirmation of the new binding. Recovered receipts use the observed
Plan and exact confirmed-version pointer, not a fabricated first response.

## M7 authenticated HTTP

The single new resource is
`/creator/api/v1/episode-production-runs/{runRef}/narrative-validation`, supporting
POST and GET through existing `create_narrative_validation` and
`get_narrative_validation`. The actual record kind remains
`ConsistencyValidationVersion`, with `consistencyValidationVersionRef`. Legacy
shot-graph `ConsistencyValidation` remains separate and unchanged.

POST's exact external fields are `projectRef`, `seriesRef`, `episodeRef`,
`validationProfileRef`, `validationProfileVersion`, `idempotencyKey`; workspace
comes from authentication and run from the path. First success and replay both
return HTTP 200, `{ok, validation}`, with the existing boundary projection intact.
GET requires the three scope query fields and accepts only the optional exact
`consistencyValidationVersionRef`. Duplicate/unknown/empty inputs fail closed.
Unknown profiles retain `409 / upstream_not_confirmed`; valid changed replay retains
`409 / idempotency_conflict`, source drift `409 / stale_input`, and foreign/missing
scope `404 / not_found`. Profile/currentness validation precedes replay lookup.

PASS/WARN/BLOCK, exact source/profile digests, findings/spans and stale behavior are
unchanged. Current PASS is readable through `require_m8_ready_validation`; WARN/BLOCK
or stale input cannot authorize M8. No downstream writes are triggered. The exact
EpisodeProduction resource count is 35 from a base of 34; the eight method-aware
resources are unchanged. M12/M13 adjacent exact-count assertions and the static
integration shard inventory include this one resource/file increment.

## Focused verification

Before implementation, both existing Core capability tests passed while the M5
operator was absent and authenticated M7 POST returned 404. The new tests use fresh
temporary SQLite databases; target binding/validation results are not preseeded.
They are application/domain fixture tests, not R6 clean-state public-chain acceptance.

The new unit/integration cases prove preflight byte/schema/fact stability, strict
configuration/input, explicit v1→v2/v2→v2, immutable history, canonical pairing,
response-loss recovery, real fresh Python processes, concurrency, stale/ambiguous
refusal, HTTP auth/scope/closed inputs, currentness/profile precedence, PASS/WARN/BLOCK,
read-only M8 consumption and preserved real legacy shot-graph output. Child runtimes
use fixed full module/script entries and explicit checkout cwd; their servers stop
and ephemeral credentials are discarded.

Focused regressions include M5 binding/Lifecycle, M7 currentness, directly affected
public/resource contracts, E3D compatibility and integration shard/namespace checks.
All 210 current focused tests passed, including 28 new E3E tests. The old B1 blanket
Application-source assertion now requires exactly the single authorized operator;
the unchanged exact HTTP endpoint set and explicit handler exclusions still prohibit
binding writes over HTTP. The 60 integration files are assigned exactly once, with
zero missing/extra/duplicate files or unit/integration basename collisions.
Markdown, links, registry, current-state, supersession, compile and diff checks passed.
Complete suites run only in the one authorized PR CI.

## Status and limits

```text
M5_BINDING_OPERATOR_ENTRYPOINT=IMPLEMENTED_AND_VERIFIED
M5_NEW_PUBLIC_BINDING_WRITE_ROUTE_COUNT=0
M7_VALIDATION_PUBLIC_HTTP=IMPLEMENTED_AND_VERIFIED
M7_DOMAIN_ALGORITHM_DIFF=0
M5_DOMAIN_SEMANTICS_DIFF=0
DATABASE_DDL_DIFF=0
MIGRATION_DIFF=0
GLOBAL_ALLOWLIST_DIFF=0
SCRIPT_PRODUCTION_DIFF=0
FRONTEND_DIFF=0
WORKFLOW_DIFF=0
DEPENDENCY_DIFF=0
LOCAL_FULL_SUITE_EXECUTED=false
R6_LIVE_BUSINESS_FACT_CREATION_COUNT=0
EXISTING_PRODUCTION_MUTATION_COUNT=0
REAL_PROVIDER_CALL_COUNT=0
A100_START_COUNT=0
COMFYUI_START_COUNT=0
VIDEO_METHOD_ROUTE_COUNT=0
MEDIA_JOB_COUNT=0
EXECUTION_ATTEMPT_COUNT=0
M3_GENERATION_RECOVERY=OBSERVED_DUPLICATE_CALL_PENDING_E3F
M3_CONFIRMATION_STABILITY=OBSERVED_ROOT_VERSION_DRIFT_PENDING_E3F
M5_CONFIRM_VERSION_HISTORICAL_RECEIPT=UNPROVEN_CONTRACT_DECISION_PENDING
SPIKE_0_ELIGIBLE_LINEAGE_E3=BLOCKED_PENDING_RESUME
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
E3F_STARTED=false
R6_LIVE_LINEAGE_STARTED=false
E4_STARTED=false
NEXT_TASK_AFTER_VERIFIED_MERGE=ACS-M3-SCRIPT-GENERATION-AND-CONFIRMATION-RECOVERY-E3F
```

E1–E3D evidence remains valid within its original boundaries. The observed M3
duplicate-generation/root-version-drift modes remain pending E3F; the audit did not
establish a violated declared idempotency contract. M5 CAS historical confirmation
recovery remains UNPROVEN. R5 remains quarantined valid-prefix evidence. Neither
E3F nor R6 starts automatically after this bounded closure.
