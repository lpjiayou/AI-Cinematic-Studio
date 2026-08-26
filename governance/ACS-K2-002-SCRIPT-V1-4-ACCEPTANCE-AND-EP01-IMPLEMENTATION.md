# ACS-K2-002 Script v1.4 Acceptance and EP01 Implementation Authorization

| Field | Decision |
| --- | --- |
| Record ID | `ACS-K2-002-SCRIPT-ACC3` |
| Record Type | Script content acceptance and ordered non-GPU implementation authorization |
| Decision Date | `2026-08-26` |
| Status | `OWNER ACCEPTED / STEPS 2-7 AUTHORIZED CONDITIONALLY / NON-GPU ONLY` |
| Decision Owner | Project Lead / Architecture Owner / Repository Governance Owner `蔺鹏` |
| Parent Authority | [ADR-0014](ADR-0014-k2-001-archive-k2-002-changan-start.md), [ACS-K2-002-GOV-RB1](ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md), and [ACS-K2-002-SCRIPT-RB2](ACS-K2-002-SCRIPT-V1-4-EXACT-DIGEST-REBASELINE.md) |
| Active Project / Episode | `K2-002-CHANGAN / EP01 ONLY` |
| Accepted Script | repository-reviewed v1.4 at SHA-256 `a954cc970c71f73028ecf5a6f5fe5d2603776cf49d21fb33da676bedf4093faf` |
| Preserved Owner Source | uploaded v1.4 at SHA-256 `33067592eb3c0c632d10f2fea3ef20b77ab319ee5aec9990ad0b285bfb548580` |
| Machine Mapping | `k2-002-changan-preproduction.v2.json` at SHA-256 `aa65a1e8eb5749aaad5188bcc1bf6448d802c4b0ebd34db6f73a75e99cf9db7e` |
| External Asset Package | `final-assets-v1.2.zip` at SHA-256 `532765d91b56692e611cabb9fcbd3d8ecc916f169f5c4e2b3b9e82a56bbe99c6` |
| Provider / GPU | `NOT AUTHORIZED / MUST BE REQUESTED SEPARATELY AFTER ALL PREREQUISITES PASS` |
| Publication | `publicationAllowed=false` |

## 1. Script acceptance

The Decision Owner explicitly accepted the content of the repository-reviewed v1.4
and directed EP01 to enter implementation. This decision closes the prior
`PENDING_EXPLICIT_CONTENT_ACCEPTANCE` state for exactly the reviewed document digest
above. It does not accept a different byte stream, the uploaded source document in
place of the reviewed rebase, the historical v1.3 document, or any later revision.

The accepted narrative and production boundary remains:

```text
PROJECT=K2-002-CHANGAN
ACTIVE_EPISODE_SET=EP01_ONLY
SCRIPT_OWNER_ACCEPTANCE=ACCEPTED_EXACT_DIGEST
EP01_SHOT_COUNT=12
EP01_TOTAL_FRAMES=720
FRAME_RATE=24
BULK_GENERATION_ALLOWED=false
PUBLICATION_ALLOWED=false
```

Acceptance of content is not itself a live `ScriptVersion`, an approved ShotPlan, an
AssetVersion, an `ExecutableShotGraph`, or a Provider/GPU grant. Those remain distinct
facts and must be created in the ordered chain below.

## 2. Authorized order

The Decision Owner directed the implementation to proceed automatically and in this
exact order:

1. persist a trusted, digest-bound Script acceptance record;
2. perform durable, idempotent EP01 canonical registration through the existing V5
   ownership boundaries and publish a verifiable receipt;
3. create and confirm the M5 v2 `EpisodePlanItem` binding to the exact accepted
   `ScriptVersion`;
4. remap the external asset package to v1.4 requirements, independently verify its
   bytes and visuals, resolve rights and human selection, and admit only eligible
   exact assets;
5. freeze and approve an exact ShotPlan and Camera Contract;
6. compile the `ExecutableShotGraph` from those current approved facts;
7. run a final currentness and prerequisite audit, then stop and request a separate
   Provider/GPU execution authorization.

No later fact may be applied before the preceding fact is current. Repository work may
implement and test the accepted capability, but tests, temporary databases and fixture
refs do not count as live canonical completion.

## 3. Trusted acceptance semantics

The trusted acceptance record must be V5-owned, durable and immutable. It must bind:

- project, series and episode scope;
- exact uploaded source, normalized source, reviewed document and canonical Script
  content digests;
- exact `scriptRef` and `scriptVersionRef`;
- this decision record ID and repository revision;
- decision owner reference, decision date and `ACCEPTED` outcome;
- `publicationAllowed=false`.

The resolver must verify the closed-world decision before confirmation. A client-provided
actor, role, boolean or approval string is not authority. Exact replay returns the same
record; changed scope, digest, decision or lineage conflicts and fails closed. The
generic generated-script confirmation path remains unchanged.

## 4. Canonical and M5 boundaries

K2-002 must use the existing Creator Public API / V5 lifecycle and Episode Production
repositories. The implementation must not create a K2-002-specific database, duplicate
AssetVersion registry or bypass route. Durable apply is allowed only against an explicit
canonical target, with private staging, restart verification, idempotent replay and a
secret-free receipt. K2-001 refs, databases and receipts are historical and forbidden.

The M5 binding is a new v2 `SeriesPlanVersion` whose exact `EpisodePlanItem` binds EP01
to the accepted Script lineage. It must be confirmed through the existing M5 boundary
before an `EpisodeProductionRun` can become canonical.

### 4.1 Script acceptance capability checkpoint

The implementation candidate adds one generic V5 Script Studio operation for exact
reviewed-import acceptance. It uses the existing Creator Public API, Lifecycle lease,
Script repository and transaction; no K2-specific endpoint or database is introduced.
The immutable record schema is `v5.script-acceptance.v1`. SQLite persistence is an
additive `script_acceptance@1` component in the accepted Lifecycle V2 database, with
strict schema/row validation and atomic migration. The external resolver is a
separately SHA-256-pinned, closed-world authority bundle and defaults to rejection.

This repository capability is not itself the live K2-002 acceptance record. Completion
of ordered step 1 still requires importing the exact reviewed v1.4 content into the
explicit canonical target and applying `ACS-K2-002-SCRIPT-ACC3` through this operation.
Temporary test stores and local fixture refs remain non-canonical evidence only.

### 4.2 Durable canonical registration capability checkpoint

The implementation candidate adds one generic V5 canonical-registration boundary and
two authenticated Creator Public API resources: deterministic zero-write preflight and
durable apply. A non-client `CREATOR_CANONICAL_TARGET_REF` is mandatory. Preflight
derives stable server-owned refs and the exact Script acceptance subject without a
canonical mutation, allowing the separately digest-pinned closed-world authority
bundle to bind the eventual Script/ScriptVersion identities before apply.
The target digest also binds the resolved physical SQLite storage identity. Once a
receipt exists, copying that database to another path under the same target label is
rejected during restart validation and cannot silently establish a second canonical
authority.

Apply uses one shared Lifecycle SQLite lease and transaction for Series, Project,
confirmed creative plan, EP01, reviewed-import ScriptVersion, trusted Script
acceptance and immutable `v5.canonical-registration.v1` receipt. The additive
`canonical_registration@1` table is foreign-keyed to the existing V5 parents. Exact
and concurrent replay returns the original receipt after restart; changed target,
scope, package, content, approval or lineage conflicts; a fault at any intermediate
point rolls every domain row back. Restart validation re-derives all server-owned refs
from the complete request digest and verifies the immutable registered parent facts
remain exact without blocking a later valid Project lifecycle transition. The receipt
is secret-free and keeps `publicationAllowed=false`.

This is still a repository capability candidate. No explicit K2-002 canonical target
or matching live authority bundle was available in this workspace, so no live roots,
Script acceptance or registration receipt were applied. M5 remains the next ordered
implementation gate after an independently verified canonical apply.

## 5. Asset-package boundary

The package digest above is authorized as candidate evidence for v1.4 remapping and
review. This decision does **not** invent missing provenance or rights. The package
currently declares user references as `USER_SUPPLIED_UNKNOWN`, commercial-use evidence
as not provided or pending, human selection as pending, and production admission as
not admitted. Consequently:

```text
TECHNICAL_AND_VISUAL_AUDIT=AUTHORIZED
V1_4_REQUIREMENT_REMAP=AUTHORIZED
RIGHTS_ASSERTION=NOT_INFERRED
ASSET_ADMISSION=CONDITIONAL_ON_EXACT_RIGHTS_AND_SELECTION_EVIDENCE
```

Only EP01-required assets that pass byte verification, v1.4 semantic mapping, visual
QC, exact human selection and rights clearance may become immutable AssetVersions.
EP02-EP03-only assets remain deferred. The package's v1.3
`EP01_executable_shotgraph.json` is historical candidate metadata and cannot be admitted
or used as the canonical graph.

## 6. ShotPlan, Camera and graph boundary

The approved ShotPlan must preserve the accepted twelve-shot, 720-frame editorial
structure. Camera facts must be explicitly authored and reviewed; `editorialShotSize`
alone must not be expanded into invented lens, angle, placement or motion facts. Freeze,
approval and compilation each bind exact refs, versions and digests in the V5 append-only
evidence chain. The compiler must reject stale Script, M5, asset, ShotPlan, Camera,
identity, continuity or output-profile inputs.

## 7. Explicit stop before execution

This record authorizes no Provider call, GPU reservation, host power-on for media work,
V4 dispatch, candidate generation, master/export or publication. After every precondition
is independently current, the implementation must emit a fail-closed preflight receipt
and request one separate Provider/GPU decision from the Project Lead. Silence, prior
credentials or this record must not be interpreted as that decision.
