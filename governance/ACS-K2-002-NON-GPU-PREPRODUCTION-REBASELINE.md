# ACS-K2-002 Non-GPU Preproduction Governance Rebaseline

| Field | Decision |
| --- | --- |
| Record ID | `ACS-K2-002-GOV-RB1` |
| Record Type | Project priority, exact-scope Phase applicability, and execution authorization decision |
| Decision Date | `2026-08-25` |
| Status | `OWNER ACCEPTED / EXACT-SCOPE IMPLEMENTATION AUTHORIZED / PR #11 MAIN-MERGED AND MAIN-VERIFIED / ACTIVE` |
| Decision Owner | Project Lead / Architecture Owner / Repository Governance Owner `蔺鹏` |
| Architecture Baseline | AI Cinematic Studio V2.3; unchanged |
| Governing ADR | [ADR-0014](ADR-0014-k2-001-archive-k2-002-changan-start.md) |
| Preserved Control Plane | [ADR-0013](ADR-0013-k2-control-plane-convergence.md) |
| Core Accepted Base | `main@6d28a53f3a077f032e341a87412b19b37c00bb1e` |
| Active Work Package | `ACS-K2-002-CHANGAN-ONBOARDING-AND-EP01-CHAIN` |
| Active Episode Set | `EP01` only |
| Execution Boundary | Repository implementation, isolated verification, and zero-write preflight; non-GPU only |
| Technical Candidate Acceptance | `NO SEPARATE FINAL FEATURE ACCEPTANCE CLAIM; PR #11 MAIN-MERGED AFTER REQUIRED INDEPENDENT REVIEW` |
| Live Production Authorization | `NOT GRANTED` |
| Provider / GPU Dispatch | `NOT GRANTED` |
| Release / Publication | `NOT GRANTED / publicationAllowed=false` |
| Production Ready | `NO` |

> Current additive overlay — `2026-08-26`: [ACS-K2-002-SCRIPT-RB2](ACS-K2-002-SCRIPT-V1-4-EXACT-DIGEST-REBASELINE.md)
> preserves the uploaded v1.4 exact source, rebases the six directed logic changes onto
> the Core-reviewed v1.3 predecessor, and establishes the versioned v2 EP01 mapping.
> Its script/version/asset facts supersede this record's v1.3-only current projection;
> all live mutation, ShotPlan, asset, Provider/GPU and publication limits below remain
> unchanged.

## 1. Purpose

This record closes one exact governance conflict without reopening the general ACS
Engineering Phase 1 or adopting an unverifiable Generation 2 charter.

The dated [Phase 1 Scope Approval](../docs/12-release/phase-1-scope-approval.md)
and [Phase 1 Execution Authorization](../docs/12-release/phase-1-execution-authorization.md)
recorded an X2-first review envelope and kept K2 implementation blocked. Both records
also explicitly allow K2 to enter after an independent priority decision and a separate,
frozen K2 authorization. ADR-0014 later selected K2-002-CHANGAN as the active project
and authorized non-GPU preproduction, but it did not enumerate how that decision applies
to the older Phase records.

This record is that required independent priority decision and exact work-package
authorization. It does not rewrite the historical records, make a phase-wide `PASS`
claim, or accept the implementation candidate.

## 2. Authority and applicability

The Decision Owner acts for this exact decision as:

- Project Lead, selecting the active Internal Content Lab project and resource priority;
- Architecture Owner, confirming that the work remains inside V2.3, ADR-0013 and
  ADR-0014;
- Repository Governance Owner, authorizing one bounded repository work package and its
  review/merge conditions.

The decision has the following authority effect:

```text
INDEPENDENT_PRIORITY_DECISION=COMPLETE
X2_STATUS=DEFERRED_NOT_CANCELLED
K2_002_PRIORITY=ACTIVE_BOUNDED
ONE_ACTIVE_IMPLEMENTATION_PACKAGE=true

GENERAL_PHASE_1_IMPLEMENTATION=NOT_REBASELINED
K2_002_EXACT_REPOSITORY_IMPLEMENTATION=GRANTED
TECHNICAL_CANDIDATE=NOT_ACCEPTED_INDEPENDENT_REVIEW_REQUIRED

GEN2_CHARTER=DEFERRED_NOT_ADOPTED
V2_3_ARCHITECTURE=UNCHANGED
```

X2 is not rejected, cancelled, completed or transferred into K2. It is deferred while
K2-002 is the sole active Internal Content Lab implementation package. Starting a second
active content implementation package requires a new Project Lead decision.

The untracked Generation 2 Charter and its integration record remain
`DEFER / NOT INCLUDED IN CURRENT BASELINE` as recorded by the
[Baseline Asset Acceptance Decision Record](../docs/12-release/baseline-asset-acceptance-decision-record.md).
This rebaseline neither accepts those assets nor creates a Gen2-to-V2.3 layer mapping.

## 3. Exact authorized outcome

The authorized outcome is limited to a reviewable repository candidate that makes the
K2-002 EP01 non-GPU preproduction chain truthful and fail-closed.

The candidate may establish contracts and implementation for:

1. preserving the K2-002 v1.2 source and its recorded source/normalized digests;
2. preserving v1.3 only as a reviewed correction candidate with separate Script Owner
   acceptance;
3. defining distinct K2-002 Project, Series, Episode, package and production-run lineage;
4. idempotent, package-digest-pinned registration behavior through existing public
   application and V5 boundaries;
5. an explicit EP01 twelve-shot editorial draft representation that preserves supplied
   timing, visible-identity, dialogue-sync and deterministic-postprocess constraints;
6. an additive vertical output profile that does not call `704×1280` strict 9:16;
7. authenticated, authority-reading, zero-write dynamic-media preflight through the
   existing Creator Public API boundary;
8. fail-closed validation of missing references, approvals, rights, policies, runtime
   capabilities and immutable inputs;
9. isolated unit, contract and integration evidence for those behaviors; and
10. K2-001 historical archiving and guards against K2-001 authority inheritance.

Registration implementation may be exercised only in isolated tests or non-production
verification stores under this authorization. Applying registration to a live canonical
host, creating a live production run, or appending live canonical production evidence is
not authorized by this record.

## 4. ShotPlan and ShotGraph authority boundary

The EP01 twelve-shot representation is editorial input, not an approved ShotPlan and not
an executable graph. The implementation must preserve this distinction in stored facts,
public projections, state transitions and tests.

```text
SOURCE_PACKAGE=V1.3_REVIEWED_CORRECTION_CANDIDATE
SCRIPT_OWNER_ACCEPTANCE=PENDING
EDITORIAL_SHOT_PLAN=DRAFT_ONLY
SHOT_PLAN_APPROVAL=NOT_GRANTED
EXECUTABLE_SHOT_GRAPH=NOT_COMPILED
CAMERA_CONTRACT=NOT_READY
```

Before a trusted ShotPlan approval resolves an exact ShotPlan ref, version, digest and
approval lineage, the implementation must not:

- create or project a canonical fact named `ExecutableShotGraph`;
- advance a canonical production state to `SHOTS_COMPILED`;
- present synthetic test cameras as production authority;
- treat editorial duration, camera or framing text as approved production facts; or
- use the draft to authorize M10/M11 append or V4 dispatch.

Tests may use synthetic examples only as explicitly labelled fixtures. Passing tests do
not promote those fixtures into K2-002 canonical facts.

## 5. Required production spine

All authorized implementation must remain on the existing chain:

```text
Creator Public HTTP/API
→ Creator Application
→ V5 Core OS
→ V4 Platform
→ Compute
```

V5 remains the sole authority for production facts and admission decisions. V4 may own
runtime job/attempt facts only. Compute and providers may never own Project, Script,
ShotPlan, AssetVersion, selection, admission, approval or publication state.

This authorization does not permit:

- a K2-002-specific database or durable authority;
- a second Asset Registry or AssetVersion owner;
- direct Application-to-V4 or V5-to-provider access;
- a detached provider experiment as a canonical generation path;
- a new renderer, queue, worker, scheduler or provider-routing authority; or
- reuse of K2-001 refs, databases, receipts, manifests, package IDs, media assets or
  exact-scope exceptions.

## 6. Explicitly forbidden scope

The following remain `NOT GRANTED`:

1. accepting v1.3 as the Canonical Script or asserting Script Owner approval;
2. approving the editorial shot draft or compiling an `ExecutableShotGraph`;
3. mutating a live canonical host or applying K2-002 registration to production data;
4. appending canonical M10/M11 media facts;
5. creating, selecting, admitting or promoting an image, video or audio AssetVersion;
6. calling a media Provider, dispatching a V4 media job or using a GPU;
7. fabricating missing character references, scene masters, glyph masks, rights evidence,
   provider policy, budget authority or runtime attestations;
8. creating a Master, ExportArtifact, release package or external delivery;
9. enabling batch execution, M16 orchestration or EP02–EP30 generation;
10. setting or deriving `publicationAllowed=true`;
11. claiming `Production Ready`, `Release Ready`, Production Proof or Commercial Proof;
12. weakening authentication, workspace isolation, append-only evidence, selection,
    admission, review or publication controls; and
13. interpreting this decision as general M7–M15, Phase 1, Gen2 or K2 production
    authorization.

The fixed terminal state for this work package remains:

```text
LIVE_CANONICAL_HOST_MUTATION=NOT_GRANTED
MEDIA_GENERATION=NOT_STARTED
PROVIDER_DISPATCH=NOT_GRANTED
GPU_DISPATCH=NOT_GRANTED
PRODUCTION_ASSETS=NOT_ADMITTED
BULK_GENERATION_ALLOWED=false
RELEASE_AUTHORIZATION=NOT_GRANTED
PUBLICATION_ALLOWED=false
PRODUCTION_READY=NO
```

## 7. Existing Phase gate application

This record creates no parallel Phase gate. It applies the existing `P1-PV-G01` and
`P1-PV-G02` semantics only to entry of this exact package:

| Gate / State | Exact-package result | Limits |
| --- | --- | --- |
| `P1-PV-G01` scope and authority | `PASS — EXACT PACKAGE ENTRY ONLY` | Project, architecture and repository decision roles are recorded here; not a phase-wide authorization or exit claim |
| `P1-PV-G02` track definition | `PASS — EXACT PACKAGE ENTRY ONLY` | K2-002/EP01 is active and X2 is deferred; no second package or broad K2 production route |
| `P1-PV-G03` architecture | `CANDIDATE REVIEW REQUIRED` | Independent review must confirm V2.3, ADR-0013 and ADR-0014 compliance |
| `P1-PV-G04` contract | `CANDIDATE REVIEW REQUIRED` | Exact public, V5, V4, draft-state and zero-write contracts must pass review/tests |
| `P1-PV-G05`–`G09` | `NO PHASE-WIDE PASS CLAIM` | Repository evidence may support the candidate only; it is not live production evidence |
| `P1-PV-G10`–`G12` | `NOT AUTHORIZED / NOT RUN` | No release, production validation or Phase 1 exit decision |

`PASS — EXACT PACKAGE ENTRY ONLY` means that the corresponding entry prerequisite no
longer vetoes this work package. It does not turn an unrun downstream gate into `PASS`,
does not authorize live execution, and does not establish ACS Engineering Phase 1 exit.

## 8. Supersession and preserved applicability

The older Phase records remain immutable, dated evidence. Their bodies must not be
silently rewritten to make the earlier decision appear different.

For only `ACS-K2-002-CHANGAN-ONBOARDING-AND-EP01-CHAIN`, this record supersedes the
older current-state clauses that:

- make X2 the only implementation-eligible content track;
- prohibit all K2 repository implementation;
- leave the K2 independent-priority decision unresolved;
- leave the exact K2 decision and execution owner unassigned; or
- treat the absence of a versioned Gen2 Charter as a veto of this bounded V2.3 work.

In particular, it supplies the independent priority review and separate K2 authorization
contemplated by:

- Phase 1 Scope Approval, sections 5 and 9.1; and
- Phase 1 Execution Authorization, sections 4 and 10.1.

All other restrictions in those records remain applicable, including no silent layer
mapping, one active package, no duplicate authority, no unapproved live production, no
proof inflation and no release/publication without separate authority.

The [Phase 1 Production Validation Plan](../docs/12-release/phase-1-production-validation-plan.md)
and [Phase 1 Vertical Slice Authorization](../docs/12-release/phase-1-vertical-slice-authorization.md)
remain general historical/planning records. They do not independently grant work and
their dated K2/X2 status snapshots do not override this exact later decision.

## 9. Review and merge conditions

This governance decision authorizes correction and review. It does not accept the
technical candidate and does not by itself make PR #11 mergeable.

Merge into Core `main` is conditionally authorized only after all of the following are
true for one exact candidate SHA and tree:

1. the ShotPlan draft/ShotGraph authority defect is corrected;
2. the complete changed-file set is reviewed against this record and ADR-0014;
3. focused unit, contract and integration tests pass;
4. the complete Core regression and all required GitHub Actions checks pass;
5. an independent technical review reports no unresolved blocker, authority leak,
   hidden write, provider dispatch or proof inflation;
6. Core ruleset `20544466` remains active with `0 approvals` under the Owner-approved
   [single-operator zero-approval exception](GIT_WORKFLOW.md#4b-core-单人运营零批准精确例外当前2026-08-25),
   approval-dependent dismiss-stale/latest-push/extra-approval options disabled,
   conversation resolution, strict up-to-date, linear/deletion/non-fast-forward
   protection, five required checks and no bypass;
7. the zero-approval decision is represented as `NOT REQUIRED`, not as `0/0`, author
   self-approval or fabricated review; the independent technical review in item 5
   remains mandatory evidence and is not a GitHub approval;
8. PR #11 remains based on the accepted Core `main` lineage without unrelated history;
9. the merge uses the repository specification's `Squash and merge`, with no force
   push, ordinary merge commit or rebase merge; and
10. post-merge `main` SHA/tree, Actions result and clean repository state are verified.

Automated or independent technical review is mandatory evidence, not Project Lead final
feature acceptance and not a platform approval. `0 approvals` does not mean no review.

The decision-time pre-merge remote configuration and PR state were:

```text
CORE_RULESET_ID=20544466
CORE_RULESET_STATE=active
CORE_CONFIGURATION=CONFORMING_UNDER_OWNER_APPROVED_SINGLE_OPERATOR_ZERO_APPROVAL_SCOPE
CORE_VERIFICATION=PARTIAL_REMOTE_SETTINGS_REREAD; POST_CHANGE_API_IDS_NOT_REREAD
REQUIRED_APPROVALS=0
DISMISS_STALE_APPROVALS=false
REQUIRE_LAST_PUSH_APPROVAL=false
REQUIRE_EXTRA_APPROVAL_FOR_UNATTRIBUTED_CHANGES=false
REQUIRE_CONVERSATION_RESOLUTION=true
ALLOWED_MERGE_METHODS=[squash]
STRICT_REQUIRED_CHECKS=true
DO_NOT_ENFORCE_ON_CREATE=false
REQUIRED_CHECKS=Markdown,Documentation Links,Unit Tests,Contract Tests,Integration Tests
REQUIRED_CHECKS_PRIOR_API_INTEGRATION_ID=15368; POST_CHANGE_API_IDS_NOT_REREAD
LINEAR_HISTORY=true
DELETION_PROTECTION=true
NON_FAST_FORWARD_PROTECTION=true
BYPASS_ACTORS=[]

REPOSITORY_GENERAL_MERGE_SETTINGS=merge,squash,rebase
EFFECTIVE_MAIN_MERGE_METHOD=squash

PR_11_AUTHOR=lpjiayou
PR_11_REVIEWS=[]
PR_11_PLATFORM_APPROVAL=NOT_REQUIRED_BY_CURRENT_CORE_RULESET
PR_11_REQUIRED_APPROVALS=0
PR_11_MERGE=PENDING_EXACT_CANDIDATE_REVALIDATION
```

At that decision-time snapshot, the configuration was
`CONFIGURATION-CONFORMING / PARTIALLY VERIFIED`, not end-to-end behavior verified. The
effective `main` ruleset was squash-only; the whole repository could not be described
as squash-only while General settings still advertised all three methods. PR #11 had
no platform approval-count blocker but remained pending until the exact candidate
satisfied every non-approval condition above. No bypass was authorized.

The current post-merge lifecycle overlay is:

```text
CORE_RULESET_ID=20544466
CORE_RULESET_STATE=active
REQUIRED_APPROVALS=0
REQUIRED_CHECKS=Markdown,Documentation Links,Unit Tests,Contract Tests,Integration Tests
REQUIRED_CHECKS_API_INTEGRATION_ID=15368
ALLOWED_MERGE_METHODS=[squash]
BYPASS_ACTORS=[]

PR_11_EXACT_CANDIDATE_SHA=59588351d69ac5bef1a4c18a2c210b62388d986b
PR_11_EXACT_CANDIDATE_TREE=51d25529f4781cd276f43c726a21c3046a28f74c
PR_11_INDEPENDENT_TECHNICAL_REVIEW=PASS
PR_11_REQUIRED_ACTIONS=5/5_SUCCESS
PR_11_MERGE=SQUASH_MERGED
PR_11_MAIN_SHA=af7f50a8dc7cdccdb7dd47cd425d33a288961cc9
PR_11_MAIN_TREE=51d25529f4781cd276f43c726a21c3046a28f74c
PR_11_CURSOR_SUITE=QUEUED_ZERO_CHECKS_NOT_REQUIRED_NOT_COMPLETE

CONTROLLED_NEGATIVE_BEHAVIOR_VERIFICATION=PENDING
FINAL_FEATURE_ACCEPTANCE=NOT_DECLARED_BY_TECHNICAL_REVIEW_OR_THIS_OVERLAY
```

This overlay closes PR #11's exact repository merge gate and records its positive
protected-PR control. It does not reuse that exact-tree evidence for a later candidate,
does not close the remaining controlled negative ruleset verification, and does not
grant Script acceptance, ShotPlan approval, live canonical mutation, Provider/GPU
dispatch, media selection/admission, production readiness, release or publication.

Failure of any merge condition leaves the state:

```text
TECHNICAL_CANDIDATE=BLOCKED
MAIN_MERGE=NOT_PERMITTED
PRODUCTION_AUTHORIZATION=NOT_GRANTED
```

## 10. Roles and non-acceptance boundary

| Role | Assignment / State | Authority limit |
| --- | --- | --- |
| Project Lead | `蔺鹏 / DECISION RECORDED` | Selects project priority and final owner decisions; this record does not imply Script acceptance |
| Architecture Owner | `蔺鹏 / DECISION RECORDED` | Confirms exact V2.3/ADR boundary; cannot turn tests into production evidence |
| Repository Governance Owner | `蔺鹏 / DECISION RECORDED` | Authorizes exact repository package and conditional merge path; cannot bypass active rules |
| Implementation / Evidence Producer | Codex automation / bounded work package | May implement and test; cannot issue final feature, Script, media or publication acceptance |
| Independent Technical Reviewer | Required before merge | Reviews exact candidate; is mandatory evidence, not a platform approval, and does not replace Project Lead or any separately required specialized authority |
| Script Owner Acceptance | `PENDING` | Separate Project Lead content decision |
| ShotPlan / Camera Approval | `UNASSIGNED / NOT GRANTED` | Required before graph compilation or dispatch |
| Rights / Provider / Budget / Runtime Authorities | `NOT CURRENT / NOT GRANTED` | Required independently before any Provider/GPU dispatch |
| Selection / Admission / Publication Authorities | `NOT GRANTED` | Required independently for exact candidate, AssetVersion and destination scope |

Owner acceptance of this governance record means only that the exact scope and controls
are accepted. It does not mean:

- v1.3 Script accepted;
- ShotPlan or camera approved;
- implementation candidate accepted;
- media generated, selected or admitted;
- live registration completed;
- Gate C or production validation passed; or
- release/publication authorized.

## 11. Change control and stop conditions

A new decision is required before any of the following:

- activating X2 or a second content implementation package in parallel;
- expanding beyond EP01 or enabling batch generation;
- changing the V2.3 dependency direction or authoritative owner;
- creating a new public mutation, database, queue, worker, renderer or provider route
  outside ADR-0014's accepted boundary;
- applying registration to a live canonical host;
- compiling an approved ShotPlan into an executable graph;
- invoking a Provider or GPU;
- selecting/admitting media; or
- creating a Master, export, release or publication eligibility decision.

Implementation must stop and report the exact blocker if the candidate cannot preserve
draft-versus-authoritative semantics, the single production spine, workspace isolation,
append-only evidence, or fail-closed publication.

## 12. Final decision

The following block is the decision-time state before independent technical review:

```text
GOVERNANCE_REBASELINE=OWNER_ACCEPTED
INDEPENDENT_PRIORITY_DECISION=COMPLETE
K2_002_NON_GPU_PREPRODUCTION_REPOSITORY_WORK=AUTHORIZED
ONE_ACTIVE_IMPLEMENTATION_PACKAGE=true

SCRIPT_OWNER_ACCEPTANCE=PENDING
SHOT_PLAN_APPROVAL=NOT_GRANTED
EXECUTABLE_SHOT_GRAPH=NOT_COMPILED
LIVE_CANONICAL_MUTATION=NOT_GRANTED
PROVIDER_OR_GPU_DISPATCH=NOT_GRANTED
MEDIA_SELECTION_OR_ADMISSION=NOT_GRANTED
BULK_GENERATION_ALLOWED=false
PUBLICATION_ALLOWED=false
PRODUCTION_READY=NO

TECHNICAL_CANDIDATE_ACCEPTANCE=PENDING_EXACT_CANDIDATE_REVALIDATION
MAIN_MERGE=PENDING_EXACT_CANDIDATE_REVALIDATION
```

The highest truthful state after this decision and before independent technical review
is:

`GOVERNANCE REBASELINED / EXACT NON-GPU REPOSITORY CORRECTION AUTHORIZED /
TECHNICAL CANDIDATE NOT ACCEPTED / LIVE PRODUCTION AND PUBLICATION CLOSED`.

### 12.1 Post-merge verification overlay (`2026-08-26`)

```text
PR_11_REPOSITORY_MERGE_CONDITIONS=SATISFIED
PR_11_MAIN_MERGE=SQUASH_MERGED
PR_11_MAIN_SHA=af7f50a8dc7cdccdb7dd47cd425d33a288961cc9
PR_11_MAIN_TREE=51d25529f4781cd276f43c726a21c3046a28f74c
PR_11_MAIN_ACTIONS=5/5_SUCCESS
PR_11_REPOSITORY_LIFECYCLE=MAIN_VERIFIED

FINAL_FEATURE_ACCEPTANCE=NOT_DECLARED_BY_TECHNICAL_REVIEW_OR_THIS_OVERLAY
SHOT_PLAN_APPROVAL=NOT_GRANTED
EXECUTABLE_SHOT_GRAPH=NOT_COMPILED
LIVE_CANONICAL_MUTATION=NOT_GRANTED
PROVIDER_OR_GPU_DISPATCH=NOT_GRANTED
MEDIA_SELECTION_OR_ADMISSION=NOT_GRANTED
PUBLICATION_ALLOWED=false
PRODUCTION_READY=NO
```

This is a repository lifecycle update only. The decision-time authority boundaries,
future exact-candidate revalidation requirement and all non-GPU/non-publishing stop
conditions remain unchanged.
