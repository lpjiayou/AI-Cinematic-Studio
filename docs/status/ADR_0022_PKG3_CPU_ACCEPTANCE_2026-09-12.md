# ADR-0022 Package 3 CPU Closed-Loop Acceptance

Document class: `IMPLEMENTATION_EVIDENCE`
Status: `RECORDED`
Owner: Project Lead / Package 3 Owner / Repository Governance Owner
Record date: `2026-09-12`
Current-state claims allowed: `false`
`HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true`

## Human decision and accepted scope

The Owner decision
`ACS-ADR-0022-PKG3-OWNER-ACCEPTANCE-20260912` accepts the exact Package 3
CPU-isolated candidate identified below. Publication is not yet merged at this
document's authoring point; final PR, CI and merge identities belong only in
the external publication receipt.

```text
PACKAGE_3_OWNER_ACCEPTANCE=ACCEPTED_WITHIN_SCOPE_CPU_ISOLATED
PACKAGE_3_CPU_CLOSED_LOOP=PASS_FOR_EXACT_CPU_ISOLATED_CANDIDATE
PACKAGE_3_PUBLICATION=NOT_YET_MERGED_AT_DOCUMENT_AUTHORING
ADR_FULL_ACCEPTANCE=ACCEPTED_ARCHITECTURE_ONLY
FULL_DISPATCH_MECHANISM_READY=false
SPIKE_0_READINESS=BLOCKED
```

The accepted scope comprises one Grant-bound Job and Attempt, L1 consumption,
the unique `CONSUMPTION_COMMITTED` Terminal, a process-local one-shot
SendCapability, L2 currentness verification, a staged CPU fake transport and
strict result/recovery binding. It is limited to the evidence-backed
CPU-isolated implementation and does not authorize live execution.

[ADR-0022 v1.2](../../governance/ADR-0022-generation-dispatch-grant.md) remains
accepted architecture only. Its normative text, Package 1 and Package 2
acceptance histories are unchanged.

## Exact accepted candidate

| Identity | Accepted value |
| --- | --- |
| Base commit | `ccb8cd2649a00ed9e16382b8ce3d95e09b065642` |
| Base tree | `5816a07c78bb6587e893ee2d052c569d2ef543fd` |
| Candidate branch | `feature/adr-0022-pkg3-consume-send-result-r1` |
| Candidate manifest digest | `7197e2a7f82ee25b3a3b38af9f15904be32b7e622dcb3b02ce90e2d301676994` |
| Complete patch SHA-256 | `8a675df8492920ba00b9caa2f70d4e65d1b23a919dc2e9300f4621ee9ad531b7` |
| Handoff archive SHA-256 | `9cadd22e00302974f6f42202f54d1dbf70765ef75f99a45063bc5a3a45556ef8` |
| Candidate paths | 15: 5 modifications and 10 additions |
| New production modules | 3 |

Acceptance binds the manifest's fifteen paths byte for byte with their
`100644` modes. The five publication-registration documents are a separate
authorized documentation delta. The handoff archive, complete patch, raw logs
and generated evidence remain outside Git and are not runtime credentials,
approval bundles or execution configuration.

## Closed-loop behavior

The accepted implementation uses the existing V4 SQLite queue, revision CAS,
Attempt and lease authority. Concurrent claims produce at most one Attempt for
the Grant-bound Job. L1 re-reads the formal Grant, source, approval, config,
runtime, cost, Job, Attempt and lease facts before atomically appending the one
Terminal shared with revoke.

Consume replay returns the original receipt with `continuation=null`. Unknown
commit recovery is read-only and returns no sending authority. A newly
committed consume can return only an in-process SendCapability bound to its
process, thread, Job, Attempt, lease, envelope, workflow and read-set state.
Copy, deepcopy, pickle, JSON, cross-thread, cross-process, reconstruction and
second use are rejected.

L2 rechecks source, approval, config, runtime, cost, selectors, validity,
budget, Job, Attempt and lease immediately before transport. A legitimate
heartbeat revision is accepted only for the same Attempt, worker and lease;
replacement or cancellation fails closed. The capability is spent before the
initial transport write begins.

The staged fake transport records request-byte commitment as zero or one.
Connection failure before commitment is not retried. Receipt loss, response
failure, cancellation or unknown outcome after commitment never causes a
second submission. Result persistence failure leaves recovery read-only and
bound to the original Grant, Job, Attempt, request, envelope, workflow and
transport submission. Existing Job v1/v2/v3 and worker behavior remains under
its original contracts; the legacy worker rejects Job v4 before claim.

## CPU-isolated evidence

The frozen candidate completed its final bounded regression with `168/168`
tests passing in `409.212` seconds, with zero failures and zero errors. The raw
log SHA-256 is
`31543cec158b2db0bd6a3e18d209f074967ec3ab6b58f6355c1bf736bba49fb2`.
The selection includes all 28 new Package 3 unit, contract and integration
tests plus direct Package 1/2, V4 queue, CAS, Attempt, lease, heartbeat,
cancel, result recovery and sharding regressions.

The independent review disposition is
`RECOMMEND_PACKAGE3_ACCEPTANCE_WITHIN_SCOPE`. It is evidence for the supplied
Owner decision, not an independent grant of execution authority.

During development, one existing in-process test exercised a mock route named
`/prompt`. Its classification is
`TEST_ONLY_IN_PROCESS_MOCK_NO_LIVE_SUBMISSION`: it contacted no real Provider
or ComfyUI instance, used no GPU and incurred no cost. The final bounded run
excluded that legacy mock route. This disclosure is part of the accepted
history and is not removed or represented as a live submission.

```text
FORMAL_DATABASE_ACCESSES=0
REAL_NETWORK_TRANSPORT_CALLS=0
COMFYUI_CONNECTIONS=0
GPU_CALLS=0
PROMPT_SUBMISSION_COUNT=0
NEW_PAID_OPERATIONS_STARTED=0
```

Temporary SQLite databases, deterministic synthetic files and the preinstalled
local FFmpeg were used only by CPU-isolated tests.

## Excluded authority and later work

This record does not add a real Provider or ComfyUI transport, activate runtime
or execution configuration, access a formal database, authorize GPU execution,
submit a real `/prompt`, admit an output AssetVersion, create a Master/Export,
add a Frontend entrypoint or authorize any paid operation. It does not declare
multi-Provider, multi-GPU, batch dispatch, automatic retry or Spike-0 ready.

Code publication does not authorize live Grant issuance or consumption. Real
transport implementation, deployment, GPU/runtime acceptance and any future
generation request require separate Project Lead authorization.
