# ADR-0021 — Manifest v2 Technical Input Append Authority

## Document metadata

| Field | Value |
| --- | --- |
| ADR ID | `ADR-0021` |
| Title | Manifest v2 Technical Input Append Authority |
| Status | `Accepted` |
| Created | `2026-09-08` |
| Last updated | `2026-09-08` |
| Decision owners | Project Lead / Core Architecture Owner / Manifest v2 Contract Owner / M10 Canonical Input Append Owner / Candidate Review and Admission Owner |
| Decision ref | `ACS-M10-MANIFEST-V2-TECHNICAL-INPUT-APPEND-AUTHORITY-E3H` |
| Extends | `ADR-0019`; adds one bounded M10 input-append authority |
| Amends scope | `ADR-0014` decision 8 and the dynamic-preflight blanket M10/M11 mutation rejection only for the exact lifecycle below |
| Supersedes | None |
| Superseded by | None |

## Status

`Accepted`

The named owners accept this decision and its normative
[M10 contract](../architecture/M10_MANIFEST_V2_TECHNICAL_INPUT_APPEND_AUTHORITY_CONTRACT.md).
Acceptance authorizes the bounded Core implementation and isolated tests. It does
not issue a production grant, resume the preserved R6 prefix, start a provider,
authorize GPU work or permit publication.

## Context

ADR-0014 correctly made the K2-002 manifest v2 ShotPlan a local structural
representation and kept camera, dispatch and publication unavailable. The public
dynamic-media preflight contract therefore rejected all legacy M10/M11 Candidate,
review and admission mutations. It also stated that a future canonical M10 append
required a separate accepted contract.

ADR-0019 later established the canonical M6-bound Script → M7 → M8/M9 → M10/M11
lineage and the single Candidate/QC/selection/admission/AssetVersion authorities. It
did not itself decide how a preflight-only manifest v2 run could append an externally
staged technical input without acquiring media-execution authority.

The observed E3 R6 input request reached that deliberate guard and returned
`execution_not_authorized` with zero writes. Deleting the guard would silently turn
transport access or technical-evidence labels into execution authority. Keeping an
unqualified blanket rejection would prevent a current, exact staged IMAGE input from
entering the already accepted canonical lifecycle.

## Decision

1. Manifest v2 remains rejecting by default. The shared review service retains its
   ordinary v2 `execution_not_authorized` guard.
2. A separately configured, operator-managed, absolute-path and independently
   SHA-256-pinned closed JSON authority may permit only the exact current technical
   IMAGE subject defined by the normative contract.
3. The subject binds run and manifest digests, current Script/M6/M7/M8/M9 facts,
   exact requirement/shot/beat/source facts and independently verified staged-image
   evidence. There are no wildcard grants.
4. The closed allowed operations are intake, semantic visual QC, HumanSelection,
   admission and corresponding MethodAwareInputPlan consumption. External
   HumanSelection approval remains independent.
5. Provider processing, media generation, video result/output intake, dispatch,
   Master/Export and publication are explicit exclusions. A manifest v2 video route
   remains forbidden even with READY inputs and a working backend.
6. The authority decision, versioned receipt, Candidate and TechnicalValidation are
   appended as one four-record transaction in the existing evidence journal.
   Admission and canonical AssetVersion remain one two-record transaction.
7. Exactly one new record kind is accepted:
   `MethodAwareInputAppendAuthority`. The receipt gains an additive v2 schema rather
   than mutating the v1 schema. No table, database, queue or asset authority is added.
8. Every write and legal replay rederives currentness and revalidates the pinned
   bundle. A fresh process without valid authority configuration rejects new writes;
   immutable historical reads remain available.
9. The four manifest safety facts remain
   `LOCAL_STRUCTURAL_REPRESENTATION_ONLY`, `NOT_VERIFIED`, `NOT_READY` and
   `dispatchAllowed=false`. Input READY is not run, camera, execution or publication
   readiness.
10. This decision does not migrate or authorize an existing v2 run. Applying it to a
    preserved production prefix requires a later exact-subject issuance and resume
    authorization.

## Scope relationship

ADR-0014 and ADR-0019 remain Accepted. This ADR narrowly qualifies only the statement
that every M10/M11 Candidate/review/admission mutation for a manifest v2 run is
forbidden: the precise M10 technical-input lifecycle in this ADR is now permitted
when its exact authority is present. All legacy writes, M11 execution, ShotPlan/camera
approval, Provider/GPU and publication restrictions remain controlling.

## Consequences

- The configuration owner must generate and pin an exact subject; ordinary clients
  cannot self-assert permission.
- A persisted authority record is audit evidence, not a reusable live grant.
- v1 E3A/E3G input semantics and historical receipts remain compatible.
- Tests must prove full input completion and zero execution escalation, rather than
  treating one successful Candidate POST as acceptance.
- The preserved R6 staging root, database, authority, token and failed request remain
  unchanged during E3H.

## Verification and rollback

The implementation is accepted only with focused unit, contract and authenticated
HTTP/SQLite integration tests, full pull-request CI, one verified squash merge and
branch cleanup. Removing both E3H configuration values at process composition
restores default rejection for new writes without deleting immutable evidence. A
future broader M10/M11 or Provider permission requires another Accepted decision.

## Change log

| Date | Owner | Change | Decision ref |
| --- | --- | --- | --- |
| `2026-09-08` | Project Lead / Core Architecture Owner / M10 Owner | Accepted the exact technical-input append exception while preserving default v2 and all execution/publication blocks | `ACS-M10-MANIFEST-V2-TECHNICAL-INPUT-APPEND-AUTHORITY-E3H` |
