# ADR-0022 Package 1 CPU Foundation Acceptance

Document class: `IMPLEMENTATION_EVIDENCE`
Status: `RECORDED`
Owner: Project Lead / Core Architecture Owner / Repository Governance Owner
Record date: `2026-09-10`
Current-state claims allowed: `false`
`HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true`

## Human decision and accepted scope

The Project Lead's instruction “验收通过 开始下一步” accepts the exact
Package 1 CPU-isolated candidate identified below. This records the Owner
decision supplied in task
`ACS-ADR-0022-PKG1-ACCEPTED-CODE-PUBLICATION-20260910`, based on the cited
`ACS-ADR-0022-PKG1-F01-CORRECTIVE-R1-INDEPENDENT-REVIEW-20260910`.
No precise approval time is asserted.

```text
ACCEPTANCE_REF=ACS-ADR-0022-PKG1-CPU-FOUNDATION-ACCEPTANCE-20260910
PACKAGE_1_OWNER_ACCEPTANCE=ACCEPTED_WITHIN_SCOPE_CPU_ISOLATED
PKG1_R1_F01=OWNER_CLOSED_FOR_ACCEPTED_CANDIDATE
ADR_FULL_ACCEPTANCE=ACCEPTED_ARCHITECTURE_ONLY
```

The accepted scope is immutable permission records, independent approval
material validation, issue/inspect/revoke foundations and CPU-isolated tests
using the existing evidence journal and synthetic temporary SQLite databases.
[ADR-0022 v1.2](../../governance/ADR-0022-generation-dispatch-grant.md) retains
architecture-only acceptance; its
[architecture acceptance record](ADR_0022_V1_2_ARCHITECTURE_ACCEPTANCE_2026-09-10.md)
and normative body are unchanged.

## Exact candidate

| Identity | Accepted value |
| --- | --- |
| Base commit | `521439dad61bad49c415059f8503727d2d95d233` |
| Base tree | `4694e8443b8272ea49b0bec4bb58bc940ab8bce6` |
| Candidate manifest | `CANDIDATE_FILES.json` |
| Manifest SHA-256 | `f486168a5f16780978cd4018f0b458c93bf4e90b34a61cef57dc8fa3b73ce873` |
| Complete patch | `PKG1_COMPLETE_UNCOMMITTED.patch` |
| Patch SHA-256 | `5756b47584495aa39ac2c7dcc9afb7dd2c803fb92eef7f031edd9171382711bc` |
| Handoff archive | `PKG1_F01_CORRECTIVE_R1_UNCOMMITTED_HANDOFF_20260910.zip` |
| Archive bytes | `354803` |
| Archive SHA-256 | `1f0e770559f9e5948dbacc1c30c7705461198e06732b79b50c0196897065fd68` |

Acceptance binds the manifest's twelve source/test/script files byte for byte,
including their `100644` modes: ten additions and two modifications relative to
the base. The five publication-registration documents are a separate authorized
documentation delta. The handoff, raw logs and synthetic database exports remain
outside Git and are referenced by digest; this document is not an approval bundle
for issuing a live Grant.

## F01 closure for this candidate

The accepted correction adds a trusted first-issue validity decision inside the
actual SQLite write transaction, after required insert/read/decode work and
immediately before commit. An expired or otherwise invalid final clock reading
rejects the first append; confirmed rollback reports zero committed writes.
Uncertain rollback, commit or receipt ownership retains the unknown-outcome
contract. The corresponding InMemory decision occurs inside its held lock.

The original sealed `createdAt`, Ref, digest and approval remain immutable.
Expired historical issue replay returns the original record with separate
eligibility, and legal revocation of an expired Grant remains supported. This
application decision point does not assert physical atomicity between a clock
reading and durable database commit, or redefine `createdAt` as physical commit
time. Owner closure is limited to `PKG1-R1-F01` in the exact accepted candidate.

## Existing CPU evidence

The frozen candidate's `TEST_RESULTS.json` has SHA-256
`0ede4b86edadda4c392f4d2e20e653afe4ed19e9e723bc0d1d9ade26bbb2fb71`.
Its final batches bind the same accepted twelve-file manifest.

| Batch | Existing result | Raw log SHA-256 | Observed receipt SHA-256 |
| --- | --- | --- | --- |
| `final_A` | 54/54 passed | `a6fdd928c29e07401362ee2c1e60cf446c454409308ff40af7151402e6b1a17e` | `2f4160579b0fe1f0b146da4bb9e736ca0cd6275d1e198d906a7a987c2c055114` |
| `final_B` | 70/70 passed | `dbb5cc836e3ee36dd821e3d3aa6842f85bcd512808c77abd2a92c923b5df26d0` | `72ea20aebe2ae81e17c83846c4ad60218893c6ab0c495e0fd6ca994e98ff7832` |

These are 124 distinct executed test IDs, with no overlap between the final
batches. `final_A` covers the five Package 1 modules and F01 regressions;
`final_B` reuses the exact prior C-group regression selection. Transaction-stage,
clock, rollback, reopen and snapshot-token observations are in
`F01_TRANSACTION_VALIDITY_EVIDENCE.json`, SHA-256
`52ad2f7e3489349ad13c7b7e192fead6ba1994460e03a22c5f9e51a7a032dca0`.
The corrective executor receipt has SHA-256
`a85d5c168b379ee33e4c8cd9f7158e24e0f5adf392f97de50708a3f5fea2077d`.

The red F01 witness remains a failed defect reproduction; its later green
result does not rewrite it. The original B01 failure, old 45/45 and 94/94
receipts retain their historical candidate identities. They are not added to
124 as further distinct tests. These reused local logs do not claim that a
GitHub CI run for this publication has passed. Actual PR, run, checkout,
merge and document hashes belong in the external publication receipt.

## Unchanged execution boundaries

The [historical dispatch audit](M10_M11_GENERATION_DISPATCH_AUTHORITY_AUDIT_2026-09-09.md)
still describes the missing mechanism at audited commit
`f007ab3e93c3fb7f5e8b3b7f81c34fec28858176`. Package 1 acceptance does not
rewrite that historical finding or move the E4 execution pin, Frontend pin or
any existing tag. The current state is projected only by
[CURRENT_MILESTONE](../../CURRENT_MILESTONE.md).

Full dispatch readiness remains false and Spike-0 remains blocked. Packages 2
and 3 are not authorized. Consumption, send wiring, Job/Attempt,
SendCapability, L1/L2, live application assembly and transport are outside this
acceptance. Default trusted dependencies remain unconfigured and fail closed.
O01 is not corrected by this publication; L01 remains later-package scope.

No live Grant issuance/consumption, generation authorization application,
Provider processing, prompt submission, formal database access, A100 or ComfyUI
operation, deployment/config activation or Frontend change is authorized by
this evidence record. CPU fixtures and a preloaded consumed Terminal are not
evidence of real consumption or generation. Code publication does not clear
these execution gates or authorize a next task.
