# ADR-0022 Package 2 CPU Binding Acceptance

Document class: `IMPLEMENTATION_EVIDENCE`
Status: `RECORDED`
Owner: Project Lead / Core Architecture Owner / Repository Governance Owner
Record date: `2026-09-11`
Current-state claims allowed: `false`
`HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true`

## Human decision and accepted scope

The Owner decision
`ACS-ADR-0022-PKG2-OWNER-ACCEPTANCE-20260911` accepts the exact Package 2
CPU-isolated candidate identified below, with the bounded residual evidence risk
recorded in this document.

```text
PACKAGE_2_OWNER_ACCEPTANCE=ACCEPTED_WITHIN_SCOPE_CPU_ISOLATED_WITH_RESIDUAL_EVIDENCE_RISK
PKG2_FINAL_R1_01_OWNER_CLOSURE=CLOSED_FOR_ACCEPTED_CANDIDATE
PKG2_R1_F01_OWNER_CLOSURE=CLOSED_FOR_ACCEPTED_CANDIDATE
ADR_FULL_ACCEPTANCE=ACCEPTED_ARCHITECTURE_ONLY
PACKAGE_2_PUBLICATION=NOT_YET_MERGED_AT_DOCUMENT_AUTHORING
```

The accepted scope is exact upstream fact reading and complete read-set proof
binding for runtime attestation, every cost source-evidence item and continuing
charges evidence; PREPARE/ISSUE currentness; coordination and normal in-flight
access takeover; GenerationDispatchGrant validation; request, envelope and
route v2; one durable unclaimed Job v4; same-Grant replay to the same Job; and
fail-closed handling of unknown commits and lost commit receipts. Acceptance is
limited to the cited CPU-isolated evidence.

[ADR-0022 v1.2](../../governance/ADR-0022-generation-dispatch-grant.md) remains
accepted architecture only. This registration neither changes its normative
text nor creates live execution authority.

## Exact accepted candidate

| Identity | Accepted value |
| --- | --- |
| Base commit | `230bde8ac53a4d7d02ef02f8eea85efe6f1afc13` |
| Base tree | `dcae160a286b10d10ebf795cb26b58339a14214f` |
| Candidate manifest SHA-256 | `7527ad1d5a44e35e8a2609951c3509e554c640f418af2c4d333a8ecb5dff6f7b` |
| Complete patch SHA-256 | `b0d296a7734d82c4a146bec759e18f86f2d1db7cb13a00ccf66c7ecb066e7f0f` |
| Candidate paths | 41: 14 additions and 27 modifications |

Acceptance binds all 41 manifest paths to their recorded bytes, modes and Git
blob identities. The five publication-registration documents are a separate
authorized documentation delta. External evidence archives and raw logs remain
outside Git and are referenced by digest; they are not runtime credentials or
live approval material.

## Candidate-specific finding closure

`PKG2-FINAL-R1-01` is closed for this accepted candidate by the completed
read-set proof chain: referenced runtime attestation, all cost source evidence
and continuing-charges evidence are read from trusted ports, validated and
included in the PREPARE/ISSUE objects. Missing, substituted or mismatched proof
objects fail closed before a Grant can be appended.

`PKG2-R1-F01` is closed for this accepted candidate by the final coordination,
takeover and unknown-outcome handling. Normal storage access is registered for
its real lifetime; activation requires safe drain; source-commit uncertainty
and Job-receipt loss preserve the primary failure and poison or refuse unsafe
continuation rather than creating a replacement Job.

These closures are candidate-specific technical dispositions. They do not
resolve the separate historical causes listed below and do not constitute
Package 3 implementation.

## CPU-isolated evidence

The current candidate completed A with 110/110 tests passing. The exact prior A
completion and process receipts have SHA-256 values
`c31a8647699e314cc852ba5bdc00bd3d2ef1ec8075912e2af81a91ff691520aa` and
`cb9cf310d25941df33f722349c0f66ec6375e766ec394a7ef77b6e3a9bd4b7c6`.
The single clean R4 B execution completed 38/38 tests passing; its handoff
archive has SHA-256
`564156a8a1d55e2c58506c63795abf69c7a193dc34b7136fa80c947d1cdad0f1`.

B25 passed in that clean B execution, so the current result is
`NOT_REPRODUCED_ON_SINGLE_CLEAN_B_RERUN`; its historical cause remains
`UNDETERMINED`. This result is not represented as a repair of that historical
event.

## Accepted residual evidence risk

The R4 streaming lifetime JSONL lacks 18 intermediate event bodies. The same
run still records 38 complete method boundaries, zero group-end controlled
registrations, no active accesses or additional threads, restored hooks and an
empty error collection. Those facts support the accepted bounded decision but
do not reconstruct the missing event bodies or establish why their duplicate
streaming export was incomplete.

A separate earlier B38 run with the same selection and resource gate retained
all 116 lifetime events. It is cross-run residual evidence only: none of its
events is presented as an event from R4, and it does not make the R4 JSONL
complete. The Owner accepted this limited risk without authorizing another B38
run.

The following historical causes remain undetermined: B25 CAS mismatch, human
selection, QC, read-one-to-zero, the original timeout and index binary drift.
The current green evidence does not rewrite those histories.

## Excluded authority and later work

Package 2 acceptance does not include Grant consumption,
`CONSUMPTION_COMMITTED`, Attempt claim, SendCapability, transport or ComfyUI
sending, GPU result collection, live Provider/runtime/cost-owner installation,
Package 3 or real generation. It does not authorize live Grant issuance or
consumption, a generation authorization application, prompt submission, GPU or
A100 access, formal database access, deployment/configuration activation or new
paid operations.

Spike-0 remains blocked and the full dispatch mechanism is not ready. Final PR,
CI, merge and publication identities are deliberately recorded only in the
external publication receipt after they actually occur; this pre-merge evidence
document does not predict them or create execution authority.
