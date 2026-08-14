# AI Cinematic Studio — Codex Agent Rules

> Status: LONG-TERM AGENT CONSTITUTION
>
> Scope: AI Cinematic Studio 全项目 Codex / Automation 长期执行规则
>
> This file defines HOW Codex works.
>
> It does not define temporary task details.
> Current execution scope is defined by CURRENT_MILESTONE.md.

---

# 1. Role

You are the implementation agent for AI Cinematic Studio.

You execute the approved product roadmap.

You do not redefine the product.

You do not independently change:

- product direction;
- Production Spine;
- milestone roadmap;
- architecture layers;
- domain ownership;
- UI information architecture;
- accepted contracts;
- accepted Git baselines.

The Project Lead controls:

- final product direction;
- final milestone acceptance;
- architecture decisions;
- domain ownership changes;
- Production Spine changes;
- roadmap rebaselining;
- destructive migration approval;
- milestone / execution-wave authorization.

Codex may implement, test, commit, push and automatically transition
between milestones only when CURRENT_MILESTONE.md explicitly authorizes
an AUTO-SEQUENTIAL execution wave.

Codex must never issue final:

FEATURE ACCEPTED

Only the Project Lead may issue final acceptance.

Codex may report:

FEATURE ACCEPTED CANDIDATE
READY FOR PROJECT LEAD ACCEPTANCE

or an explicitly defined technical checkpoint state.

---

# 2. Source-of-Truth Hierarchy

Before any work, Codex MUST discover and read every applicable instruction source.
The following authority order is frozen verbatim for this repository:

1. 适用的 `AGENTS.override.md`
2. 最近层级的嵌套 `AGENTS.md`
3. 根目录 `AGENTS.md`
4. Accepted ADR 与强制治理规则
5. `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`
6. `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`，仅在 UI、UX、Frontend 范围内生效
7. `CURRENT_MILESTONE.md`，仅控制当前任务、门禁和执行状态
8. Accepted/remote-verified Git evidence，仅证明实现事实，不得自行改变架构
9. Historical、superseded、archived evidence

Temporary conversation instructions must not silently override
higher-level project baselines.

If a genuine conflict exists:

STOP.

Report the exact conflict.

Do not guess which source should win.

---

# 3. Product Definition

AI Cinematic Studio is not a collection of isolated AI tools.

It is a Project-first AI film production system.

The long-term objective is:

real content demand
→ structured production
→ traceable audiovisual assets
→ deterministic composition
→ final works
→ release
→ real performance feedback
→ next creative cycle

The product must evolve as one connected production system.

---

# 4. Project First

Project is the formal production root.

Formal production facts must eventually belong to:

Workspace
→ Content Profile
→ Project

For Series projects:

Project
→ Series
→ Episode

Project answers:

What production are we making?

Series answers:

What long-running narrative / production context does it belong to?

Episode answers:

What specific production unit are we producing?

Never collapse these identities.

Never use:

episodeRef == projectRef

Never use:

episodeRef == canonicalProjectId

unless an explicitly accepted V5 contract defines such a relationship.

---

# 5. Long-Term Production Spine

The fixed long-term Production Spine is:

Workspace
→ Content Profile
→ Project
→ AI Director
→ Series
→ Series Planning
→ Series IP Bible / Character Intelligence
→ Episode
→ Episode CreativePlan
→ Story Projection
→ Script / ScriptVersion
→ Consistency Validation
→ Storyboard
→ Creative Shot
→ Asset Requirement
→ Asset / AssetVersion
→ Image / Video / Audio Production
→ Timeline
→ V3 Composition / Render
→ Preview / QC / Approval
→ Episode Master
→ Series Release & Management
→ Performance Data
→ AI Director / Content Profile Feedback

All major implementation must strengthen this spine.

Do not create capabilities that function independently
but are disconnected from this production chain.

---

# 6. Core Integration Principle

A feature is not complete simply because:

- the page works;
- the API returns 200;
- unit tests pass;
- a model generates output.

Before implementing a capability, identify:

1. upstream authoritative object;
2. stable input contract;
3. output contract;
4. direct downstream consumer;
5. Ref / Version lineage;
6. final traceability path.

If these cannot be identified:

STOP.

A module that works alone but cannot participate in the Production Spine
is NOT complete.

---

# 7. Data Lineage Rule

Connections must use stable references and version lineage.

Do NOT use the following as authoritative integration:

- copied text;
- duplicated JSON;
- display names;
- titles;
- episode numbers;
- character names;
- UI labels;
- route strings.

Preferred relationships include:

workspaceRef
→ contentProfileRef
→ projectRef
→ seriesRef
→ episodeRef
→ creativePlanRef / creativePlanVersion
→ seriesPlanRef / seriesPlanVersionRef
→ seriesBibleRef / seriesBibleVersionRef
→ characterRef / characterStateRef
→ scriptRef / scriptVersionRef
→ consistencyValidationRef
→ storyboardRef / storyboardVersionRef
→ shotRef / shotVersionRef
→ assetRequirementRef
→ assetRef / assetVersionRef
→ generationRequestRef / generationResultRef
→ videoAssetVersionRef / audioAssetVersionRef
→ timelineRef / timelineVersionRef / timelineClipRef
→ previewCandidateRef
→ episodeMasterRef
→ releasePackageRef
→ performanceRecordRef

Not every Ref exists yet.

Future implementation must not create conflicting identity systems.

Every downstream object should eventually identify the upstream object
and version that produced it.

---

# 8. Vertical Closure

Vertical closure first.

Series architecture early.

Batch capability later.

Execution scale:

1 Episode
→ 3 Episodes
→ 10 Episodes
→ 30 Episodes
→ 100 Episodes

Do not build industrial batch orchestration before a real single-Episode
production chain is proven.

Do not build platform infrastructure merely because it may be useful later.

Real production first.

Scale second.

---

# 9. Current Roadmap

Accepted historical/product milestones:

M1 — AI Director Core
ACCEPTED

M2 — Series + Episode Foundation
ACCEPTED

M3 — Script Studio
ACCEPTED

M3-H — Script Candidate Robustness
ACCEPTED

Story Projection Integration
ACCEPTED

UI-R1 — Enterprise Cinematic UI Rebaseline
ACCEPTED

M4 — Project Context Foundation
ACCEPTED

M5 — Series Planning + Series Director
ACCEPTED

Future roadmap begins with M6:

M6 — Series IP Bible + Character Intelligence

M7 — Narrative Closed Loop

M8 — Storyboard + Creative Shot Domain

M9 — Asset Requirement + Asset Intelligence

M10 — Image Generation

M11 — Video Production

M12 — Audio Production

M13 — V3 Timeline + Composition + Render

M14 — Preview / QC / Approval / Local Regeneration

M15 — Episode Master + Works

M16 — V4 Batch Production Orchestration

M17 — Series Release & Management

M18 — Performance Feedback

M19 — Commercial SaaS / Enterprise Hardening

The roadmap may only be changed by the Project Lead
through an explicit system-level rebaseline.

The PRE-M6 route is fixed as:

`PRE-M6-RB1.1 Source-of-Truth Rebaseline`
→ `PRE-M6-RB1.2 Legacy UI Decommission`
→ `PRE-M6-RB1.3 Full Core Current-State Audit`
→ `Architecture Review`
→ `M6 Preconditions`
→ `M6-P1`

The current phase is `M6-P3-B1-R1 Owner Acceptance Closeout`.

Current governance state:

- PRE-M6-RB1.3-R2-P1: `ACCEPTED`;
- PRE-M6-RB1.3-R2-P2: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
  0aa14b4e426a3d968ec314029d60a47ea30cbc4d`;
- PRE-M6-RB1.3: `REMEDIATION COMPLETE / FORMALLY CLOSED BY PROJECT LEAD OWNER REVIEW`;
- PRE-M6-RB1.3-IR1: `COMPLETED`;
- Full Core Audit Report v1.2 acceptance label: `PRESERVED`; repository-resident
  report provenance: `OPEN / NON-BLOCKING UNDER R-CORE-GOV-002 / NOT AN
  IMPLEMENTATION AUTHORITY`;
- PRE-M6-RB1.3-R1-RV1: `INDEPENDENTLY ACCEPTED`;
- RB13-F001: `R1 IMPLEMENTED / INDEPENDENTLY ACCEPTED / CLOSED`;
- RB13-F002: `REMEDIATED / CLOSED IN CURRENT TESTED CORE BASELINE`;
- Architecture Review: `SATISFIED FOR BOUNDED M6-P0/P1 AND M6-P2 LOCAL SQLITE ONLY`;
- M6 Preconditions: `SATISFIED FOR BOUNDED M6-P0/P1 AND M6-P2 LOCAL SQLITE ONLY`;
- ACS-M6-P0-P1-R2: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
  e38c75aa4ff26bdea80c82d8a24096f799dad860`;
- current task: `ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER`;
- legacy repository capability provenance: `MEDIUM / OPEN / NON-BLOCKING`,
  Owner Gate `P3-RV1-003`;
- M6-P0: `CONTRACT ACCEPTED / COMPLETE`;
- M6-P1: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
  e38c75aa4ff26bdea80c82d8a24096f799dad860`;
- M6-P2-G0: `ADR-0004 AND SQLITE CONTRACT ACCEPTED / COMPLETE`;
- M6-P2-G1: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
  8227c6c616140824fd70de920dc6fcf459bb734d`;
- M6-P3-G0: `OWNER ACCEPTED / COMPLETE AS GOVERNANCE-ARCHITECTURE / NO
  IMPLEMENTATION AUTHORITY`;
- ADR-0005 and M6 consumer contract: `ACCEPTED AS ARCHITECTURE / B1 OWNER
  ACCEPTED THROUGH B1-R1 / G1 BOUNDED IMPLEMENTATION AUTHORIZED`;
- M6-P3-B1 binding prerequisite: `ORIGINAL CANDIDATE REMOTE-VERIFIED AT
  8449b521c96bb8340806ecda8649698f4771914a / REVISION REQUIRED / CORRECTED
  THROUGH B1-R1 / OWNER ACCEPTED AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`;
- M6-P3-B1 authorized base:
  `6bb9d165a693057f38e5789c408293ff0eaf5bcc`;
- M6-P3-B1 affected Domain Owners: `M2 / M4 / M5 / M6 APPROVED`;
- M6-P3-B1 frozen scope: `8 GOVERNANCE / 6 PRODUCTION / 9 TEST PATHS`;
- M6-P3-B1 implementation candidate: `REMOTE-VERIFIED AT
  8449b521c96bb8340806ecda8649698f4771914a / OWNER REVIEW REVISION REQUIRED /
  NOT OWNER ACCEPTED`;
- M6-P3-B1-F001: `CLOSED BY OWNER-ACCEPTED B1-R1 — SQLITE SAME-PROJECT
  CROSS-SERIES FALSE dependent_series_plan_binding_exists`;
- M6-P3-B1-R1: `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
  5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`;
- M6-P3-B1-R1 authorized base:
  `8449b521c96bb8340806ecda8649698f4771914a`;
- M6-P3-B1-R1 evidence: `PRE-FIX SQLITE REGRESSION REPRODUCED 409 / POST-FIX
  SQLITE MODULE 30/30 / ORIGINAL B1 SUITE 174/174 / FULL CORE 449/449 /
  NON-TEST PYTHON AST 63/63`;
- M6-P3-G1: `BOUNDED CORE-ONLY IMPLEMENTATION AUTHORIZED ON 2026-08-14 /
  GOVERNANCE REMOTE VERIFICATION REQUIRED BEFORE CODE / NOT OWNER ACCEPTED`;
- M6-P3 after G1 / M6-P4+: `NOT AUTHORIZED / NOT STARTED`;
- R-CORE-ARCH-001: `CONFIRMED / HIGH / MONITORING — APPLICATION DIRECT V4
  DEPENDENCY REMEDIATED AT OWNER-ACCEPTED G1-R1`;
- ADR-0006 V5 Text Generation Capability Boundary: `ACCEPTED FOR BOUNDED G1
  REMEDIATION`;
- ACS-ARCH-R1-V5-TEXT-GENERATION-G0: `COMPLETE / REMOTE-VERIFIED AT
  92d1f3ac9e08c71458af04514baa659555fc55a7`;
- ACS-ARCH-R1-V5-TEXT-GENERATION-G1: `REMOTE-VERIFIED CANDIDATE AT
  0c283eb653e74784301620bdaf64bf451bb687dd / REVISION REQUIRED / NOT OWNER
  ACCEPTED / SUPERSEDED BY G1-R1`;
- ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1: `OWNER ACCEPTED / COMPLETE /
  REMOTE-VERIFIED AT d44f471c644e319bb4a5bf73707c3274ecbaa426`;
- R-CORE-GOV-002 audit-report provenance: `OPEN / NON-BLOCKING`;
- M7-M19: `NOT STARTED / NOT AUTHORIZED`;
- Formal 8765 Deployment: `UNTOUCHED / NOT DEPLOYED`;
- Frontend: `FROZEN / UNTOUCHED`;
- Production Ready: `NO`.

Legacy repository implementation must not be counted as current Core production
capability. RB13-F001 and RB13-F002 are closed in the accepted current tested Core
baseline. M6-P0/P1 and M6-P2 are Owner Accepted. The remote-verified G3/P3-G0
revision at `c524486c05c21b270a7dd75e89fae4312430736a` has now been accepted as
architecture only; its consumer behavior remains unimplemented and the architecture
acceptance alone granted no implementation authority. The later
explicit Owner decision authorizes only bounded B1 after governance remote
verification. The Project Lead accepted the corrected G1-R1
checkpoint at `d44f471c644e319bb4a5bf73707c3274ecbaa426`, closing Architecture
Remediation R1. The original G1 remains historical `REVISION REQUIRED / NOT OWNER
ACCEPTED` and is superseded by G1-R1. B1 is remote-verified at
`8449b521c96bb8340806ecda8649698f4771914a` but failed Owner Review because its SQLite
dependency scan crosses legitimate Series histories inside one Project. The B1-R1
governance checkpoint is remote-verified at
`716b4d298173f8123cafd93114dfc67339943ff3`; its exact one-production/one-test
correction is remote-verified at
`5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`. Independent Owner Review reproduced
the original false `409`, confirmed the correction, reran the complete `449/449`
regression and accepted B1-R1 on `2026-08-14`. M6-P3-G1 received its separate bounded
authorization later that day; its governance checkpoint must be remote-verified first.

The M6 gate order is:

1. R1 implementation completes and passes independent review;
2. R2 deletion lifecycle remediation completes;
3. InMemory/SQLite consistency, concurrency and TOCTOU validation pass;
4. the RB1.3 full regression passes;
5. RB1.3 is formally closed;
6. Architecture Review passes;
7. all M6 Preconditions are satisfied;
8. the Project Lead separately authorizes M6-P1.

All eight gates are satisfied for the bounded M6-P0/P1 scope recorded by the Project
Lead on `2026-08-13`. M6-P0/P1 is owner accepted and remote-verified at
`e38c75aa4ff26bdea80c82d8a24096f799dad860`.

The M6-P2 gate order is:

1. M6-P0/P1 owner acceptance and remote verification pass;
2. ADR-0004 and the M6 durable SQLite contract are accepted;
3. only temporary file SQLite is used for migration and persistence evidence;
4. InMemory/SQLite contract parity, restart, atomicity, lifecycle and concurrency pass;
5. the complete M1-M6/P1 and R2 regression passes;
6. the M6-P2 checkpoint is committed, pushed and remote-verified;
7. execution stops for Project Lead owner review.

The Project Lead accepted M6-P2-G1 at
`8227c6c616140824fd70de920dc6fcf459bb734d`. The Project Lead and Architecture
Owner have now accepted ADR-0005 and its contract as the target M6 consumer
architecture only. The accepted Core has no shared stable key between M2
`episodeRef` and M5 `episodePlanItemRef`; number/title/index inference is forbidden.
ADR-0005 therefore requires an immutable M5 EpisodePlanItemBinding in a new exact
SeriesPlanVersion. The Project Lead, Architecture Owner, Repository Governance Owner
and affected M2/M4/M5/M6 Domain Owners now authorize bounded M6-P3-B1 after its
governance checkpoint is remote-verified. M2 retains Series/Episode identity and
membership; M4 retains Project identity and Project-to-Series context.

Initial plan creation remains v1. B1 permits v1→v1, explicit v1→v2 and v2→v2,
forbids v2→v1 and requires an explicit new v2 version for unbinding. The only new
operation is Core-only `create_episode_plan_item_binding_version`; no HTTP route,
handler or external DTO source file may be added or changed. By explicit Owner
clarification, the existing HTTP workspace versions projection passes through
`episodePlanItemBindings` for v2 responses. v1 responses remain unchanged, and no
other HTTP contract expansion is authorized.

This does not establish a general Architecture Review, Production Ready status,
formal database deployment, M3/M6 consumer authority or M6-P3-G1 authority.

M6 Character Intelligence must cover at least:

- background;
- motivation;
- belief;
- conflict;
- goal;
- personality;
- behavior rules;
- dialogue rules;
- forbidden behavior;
- visual identity rules;
- `CharacterState`;
- `RelationshipContext`;
- timeline and continuity.

`M6 ≠ V5 Identity Lock`. M6 does not implement M7, GPU Render, ComfyUI,
Worker execution or cross-repository UI. M6-P0/P1 is `OWNER ACCEPTED / COMPLETE /
REMOTE-VERIFIED`; ADR-0004 and the M6-P2 SQLite contract are accepted;
M6-P2-G1 is `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
8227c6c616140824fd70de920dc6fcf459bb734d`; M6-P3-G0 is `OWNER ACCEPTED /
COMPLETE AS GOVERNANCE-ARCHITECTURE`; M6-P3-B1 is `OWNER ACCEPTED THROUGH B1-R1 AT
5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`; M6-P3-G1 is separately authorized
only by `governance/ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER.md`. All work after G1
remains `NOT AUTHORIZED / NOT STARTED`.

The accepted architecture-remediation sequence is:

1. G0 records ADR-0006, the normative
   `architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md`, risks and exact G1
   authority in one governance-only checkpoint;
2. G0 is committed, pushed and remote-verified with no production or test diff;
3. G1 introduces the V5-owned public Text Generation capability and migrates the
   existing M1 AI Director, M3 Script Studio, M5 Series Director and Creator Server
   composition from direct V4 imports to that V5 boundary;
4. V5 alone consumes the existing public V4 `TextGenerationPort`; V4 retains Provider
   execution and Adapter ownership and no second Provider stack is created;
5. G1 preserves existing public HTTP/API, Domain, candidate validation and product
   error semantics, adds an executable no-Application-to-V4 guard, passes the complete
   Core regression, and is committed, pushed and remote-verified;
6. after G1 remote verification: `STOP` for Project Lead owner review;
7. independent review marks the G1 candidate `REVISION REQUIRED` because the guard
   misses aliased `importlib.import_module` / `__import__` access while the production
   migration remains valid;
8. G1-R1 first creates a governance-only authorization checkpoint, then changes only
   `tests/contract/test_creator_series_planning_contract.py` to add binding-aware AST
   analysis and positive/negative regression cases;
9. after G1-R1 commit, push and remote verification: `STOP` for Project Lead owner
   review;
10. the Project Lead accepts G1-R1 at
    `d44f471c644e319bb4a5bf73707c3274ecbaa426`, closes the remediation wave and
    historically authorizes governance closeout plus read-only M6-P3-G0 Owner Review;
11. the Project Lead and Architecture Owner accept ADR-0005 and the M6 Consumer
    Contract as architecture only;
12. the Project Lead, Architecture Owner, Repository Governance Owner and affected
    M2/M4/M5/M6 Domain Owners authorize exact B1: first an eight-path governance
    checkpoint and remote verification, then the frozen six-production/nine-test
    implementation, remote verification and STOP for B1 Owner Review.
13. B1 Owner Review marks candidate
    `8449b521c96bb8340806ecda8649698f4771914a` `REVISION REQUIRED`; the Project Lead,
    Architecture Owner, Repository Governance Owner and affected M2/M5 Domain Owners
    authorize only `ACS-M6-P3-B1-R1-SQLITE-SERIES-ISOLATION`: the same eight governance
    paths, then `services/v5_core_os/series_planning/foundation.py` and
    `tests/integration/test_creator_lifecycle_sqlite_p2.py`, remote verification and
    STOP for B1-R1 Owner Review;
14. B1-R1 Owner Review independently reproduces the original false `409`, verifies
    the corrected exact/suspicious-scope selection, reruns `449/449` and accepts the
    remote technical checkpoint at `5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`.

The G1 authorization requires its exact eight-path governance checkpoint to be
remote-verified before production or test edits. It then permits only the seven
production and three new test paths frozen in
`governance/ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER.md`, followed by complete gates,
non-force publication, remote verification and STOP for Project Lead Owner Review.
It authorizes no Schema/Migration, formal port-8765 database access, HTTP route,
handler or external DTO source-file change, Auth/RBAC, Frontend, M7+, V3, GPU, Worker
or ComfyUI work.

Legacy Phase 0 provenance debt remains `OPEN / NON-BLOCKING` under Owner Gate
`P3-RV1-003`. This acknowledgement does not silently close the debt or import
old-repository capabilities into current Core.

---

# 10. Architecture Direction — V2.3

The accepted dependency direction is:

Creator Application
↓
V5 Core OS
↓
V4 Platform
↓
V3 Render Core
↓
Compute
↓
Foundation

Cross-cutting concerns include:

- Content Safety;
- Rights;
- Security;
- Audit;
- Observability;
- Logging;
- Tenant / Workspace isolation;
- Resource isolation;
- Provenance.

Rules:

- No reverse dependency.
- No cross-layer private imports.
- No duplicate authoritative owner.
- Browser must not access persistence directly.
- Application must not execute SQL directly.
- Application must not access private infrastructure adapters directly.
- V4 must not own V5 domain facts.
- V3 must not redefine V5 creative domain authority.
- Compute must not own business state.
- External AI providers must not control production lifecycle.

If implementation violates this direction:

STOP.

---

# 11. V5 Core OS Ownership

V5 Core OS is the long-term owner of authoritative production facts,
including where applicable:

- Identity;
- Content Profile references;
- Project;
- Series;
- Episode;
- Series Planning;
- Series Bible;
- Character;
- Character State;
- Script;
- Storyboard / Creative Shot Specification;
- Asset Registry;
- Asset Version;
- Rights;
- Provenance;
- production version lineage;
- approvals;
- Master metadata;
- Audit / Outbox;
- durable production semantics.

V5 also owns the public Text Generation Capability boundary consumed by Creator
Application. That capability owns provider-neutral Application-facing request,
response and error semantics plus closed purpose-to-execution-policy mapping. Creator
Application retains prompts, candidate schema parsing, local validation and the
accepted maximum-one-repair orchestration. V5 does not own V4 Provider execution or
Provider adapters.

Do not duplicate these facts in Creator Application.

---

# 12. V4 Platform Ownership

V4 is the execution and AI platform boundary.

Early V4 may provide:

TextGenerationPort
→ Provider Adapter

The accepted V5 Text Generation Capability is the only production consumer of this
V4 port in the current Core path. Creator Application must not import, configure or
call V4 directly.

Later V4 may provide:

- Provider Registry;
- Model Router;
- Image Provider;
- Video Provider;
- Audio Provider;
- Generation execution;
- Queue;
- DAG;
- Worker;
- Retry;
- Recovery;
- Compute Router;
- GPU scheduling.

V4 does not own:

Project
Series
Episode
Script
Character
Asset identity
approval state
publication state

V4 executes work.

V5 owns production facts.

---

# 13. V3 Render Ownership

V3 Render Core owns deterministic audiovisual composition and render execution.

Examples:

- executable render representation;
- composition;
- tracks;
- subtitles;
- transitions;
- virtual camera;
- audio composition;
- preview render;
- final render;
- encoding.

V5 Creative Shot Specification is not the same thing as a V3 render node.

Expected relationship:

V5 Creative Shot Specification
↓ stable contract
V3 Executable Render Representation

Do not create two authoritative Shot domains.

---

# 14. Provider Rule

External AI providers are replaceable adapters.

Providers may generate candidates.

Providers do NOT own:

- project identity;
- series identity;
- episode identity;
- character identity;
- Script identity;
- Storyboard identity;
- Asset identity;
- lifecycle state;
- approvals;
- rights;
- publication state.

Provider output must pass local validation
before it becomes usable application/domain input.

Provider-specific implementation must remain behind accepted boundaries.

---

# 15. DeepSeek Rule

DeepSeek is currently an accepted initial text intelligence provider.

Approved path:

Creator/Application
→ V5 Text Generation Capability
→ V4 TextGenerationPort
→ DeepSeek Adapter
→ DeepSeek API

Never:

Browser
→ DeepSeek API

Never expose or commit the DeepSeek API key.

Never create a second DeepSeek/provider stack
if an accepted V4 TextGenerationPort already exists.

DeepSeek may generate:

candidate semantic content.

The local system must create authoritative structural Refs such as:

scriptRef
scriptVersionRef
scriptSceneRef
seriesPlanRef
seriesPlanVersionRef

where those identities belong to the platform.

---

# 16. Candidate vs Domain Fact

AI output is candidate output.

The general pattern is:

AI Candidate
↓
Local Schema Validation
↓
Optional controlled repair
↓
Human Confirmation where required
↓
Authoritative / confirmed domain version

Never interpret:

AI generation success

as:

human confirmation.

Never interpret:

Schema PASS

as:

creative approval.

Never interpret:

technical PASS

as:

rights approval.

Never interpret:

consistency PASS

as:

publication approval.

---

# 17. Versioning Rule

Production artifacts requiring history must use immutable versions.

Pattern:

Object
├─ Version 1
├─ Version 2
├─ Version 3
└─ current / confirmed reference

Manual edits create new versions when traceability is required.

AI rewrites create new versions.

Historical versions are not overwritten.

Confirmation updates a reference to an immutable version.

Apply this pattern to domains such as:

- SeriesPlanVersion;
- SeriesBibleVersion;
- ScriptVersion;
- StoryboardVersion;
- ShotVersion;
- AssetVersion;
- TimelineVersion;
- MasterVersion.

---

# 18. Validation Staleness

Validation is bound to the exact versions it validated.

Example:

ConsistencyValidation
=
ScriptVersion
+
SeriesBibleVersion
+
CharacterStateRefs

If any authoritative input changes:

old validation becomes:

STALE

A stale validation must not authorize downstream readiness.

---

# 19. UI Architecture Authority

Customer-facing UI implementation MUST follow:

AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md

The Enterprise Cinematic UI baseline is accepted.

Accepted ADR-0001 and the remote-verified PRE-M6-RB1.1 baseline place the
customer-facing Commercial SaaS experience layer in the separate
`AI-Cinematic-Studio-Frontend` repository.

This Core repository continues to own the
Creator Server Runtime, public HTTP/API boundaries, Creator Application
orchestration and lower platform layers, while not owning the customer-facing
Commercial SaaS UI source.

Do not redesign the entire product during ordinary capability work.

Future milestones should activate existing UI architecture,
not invent new global structure.

---

# 20. One Creator UI Rule

There is ONE Creator product UI.

ADR-0001 is accepted and PRE-M6-RB1.1 is a remote-verified checkpoint. This means:

ONE CREATOR UI
=
the customer-facing Commercial Frontend in the separate
`AI-Cinematic-Studio-Frontend` repository.

Do not create:

Legacy UI
+
New UI

as two parallel products.

Core agents MUST NOT implement or recreate customer-facing Commercial SaaS
pages in this repository.

The Core repository may contain:

- Creator Server Runtime and public HTTP/API handlers;
- Creator Application commands, queries, DTOs and services;
- technical non-product utilities required to operate or diagnose Core.

It must not contain a second Commercial SaaS experience layer.

The accepted cross-repository dependency chain is:

`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

The Frontend Experience Adapter belongs to the Frontend repository and may
consume only Creator Public HTTP/API. The Frontend must not import Core source,
access Creator Application, Domain, SQL or persistence directly, call providers,
or connect to private V5, worker, GPU or ComfyUI adapters. The repositories do
not share customer UI source code.

The historical browser UI under `apps/creator-workspace-mvp` was classified and
decommissioned through the remote-verified PRE-M6-RB1.2 checkpoint. Core retains
Server/API/Application/Domain/Persistence/Test responsibilities and must not
recreate a customer-facing Commercial SaaS UI.

Final customer UI evidence belongs to the Frontend Experience Gate in the
separate Frontend repository and must use its real HTTP runtime.

Core HTTP runtime evidence validates APIs and application behavior, not
customer-facing visual parity.

The current local Core HTTP runtime may continue to use endpoints such as
`http://127.0.0.1:8765/` during the controlled migration.

`file://` may be used only for temporary local debugging.

`file://` is NOT acceptable final Browser / Visual evidence.

---

# 21. Global UI Navigation Freeze

Global navigation is:

首页
AI导演
项目
资产库
创作中心
作品

Do not add:

Series
Episode
Script
Storyboard
Timeline
Release

as new global top-level navigation.

Those capabilities belong inside Project Workspace.

This navigation remains a product/experience contract for the separate
Frontend repository. Core must expose stable public contracts for it and must
not recreate the navigation as a second customer UI.

---

# 22. Project Workspace IA Freeze

Project Workspace is organized by production lifecycle.

Top-level sections:

概览

策划

内容

制作

后期

交付

Detailed structure:

策划
- AI导演
- 系列规划
- IP圣经
- 角色
- 世界与连续性

内容
- 分集
- 故事
- 剧本
- 一致性

制作
- 分镜
- 镜头
- 场景
- 项目资产
- 生成任务

后期
- 时间线
- 预览
- 质检
- 审批

交付
- Master
- 导出
- 系列管理
- 发布
- 数据

Future milestones activate these areas.

Do not redesign this IA without Project Lead authorization.

---

# 23. UI Shell vs Real Capability

Future capability UI Shells may exist before backend/domain capability.

But UI must not fabricate facts.

Allowed:

- Empty State;
- Capability State;
- Editor Shell;
- disabled action;
- context explanation.

Forbidden:

- fake Project;
- fake Bible;
- fake CharacterState;
- fake Storyboard;
- fake Shot;
- fake Asset;
- fake Timeline;
- fake Master;
- fake analytics;
- fake PASS status.

Already accepted capabilities must remain REAL.

Current real capabilities include:

- AI Director;
- Series / Episode;
- Story Projection;
- Script Studio.

Never downgrade an accepted capability to:

“即将上线”.

---

# 24. Chinese-First UI Rule

User-facing UI is Chinese-first.

Allowed exceptions include:

AI Cinematic Studio
WANLIGHT
and necessary industry abbreviations such as:
AI / QC / BGM / SFX / API

Do not expose ordinary users to:

schema names
repository
adapter
port
raw Ref
provider exception names
stack traces

Engineering details belong in advanced diagnostics / Inspector only.

---

# 25. Persistence Rule

Application depends on public repository / service boundaries.

Application must not execute SQL directly.

Local SQLite is:

LOCAL DEVELOPMENT DURABLE ADAPTER

It is not:

PRODUCTION DATABASE

Repository contracts must allow future production persistence
such as PostgreSQL without rewriting domain/application contracts.

Persistence implementations must support where relevant:

- transactions;
- rollback;
- restart roundtrip;
- repository contract tests;
- version semantics;
- integrity constraints.

---

# 26. Deletion / Lifecycle Safety

Deletion must preserve production lineage.

A front-end visual removal is not deletion.

Deletion must pass through the authoritative application/V5 boundary.

If an object already has protected downstream production facts,
ordinary destructive deletion should be blocked or follow
an explicitly accepted lifecycle policy.

Examples:

unproduced test object
→ deletable where contract permits

object with ScriptVersion / Assets / Master
→ protect, archive, retire, or require explicit policy

Never create orphan production facts.

---

# 27. Human Confirmation

Human confirmation gates remain separate.

Examples:

Creative Confirmation
Script Confirmation
Consistency
Rights
Technical QC
Final Approval
Publication Eligibility

Do not collapse all semantics into:

approved = true

---

# 28. Integration Gate

Every formally completed capability must report:

UPSTREAM CONNECTION

INPUT CONTRACT

OUTPUT CONTRACT

DOWNSTREAM CONNECTION

REF / VERSION LINEAGE

TRACEABILITY

If any is missing:

INTEGRATION PASS must not be reported.

---

# 29. Production Spine Integrity Gate

Every milestone must prove that its real implementation
connects to the current accepted Production Spine.

Fixtures may support tests.

Fixtures alone are insufficient for final acceptance.

Where real upstream accepted data exists,
the milestone must perform a real integration smoke using it.

---

# 30. Scope Control

Do not expand scope simply because another feature looks useful.

Do not implement future milestones early.

Do not create unnecessary governance documents.

Do not turn implementation into an endless audit/document loop.

Use targeted design/audit only when required to resolve
a real architecture or integration question.

---

# 31. Audit Rule

Targeted repository audits are appropriate before major boundary work.

Typical audit-worthy areas include:

- Project;
- Series Planning;
- IP Bible / Character;
- Asset ownership;
- V3 integration;
- V4 orchestration;
- enterprise boundaries.

An audit must lead directly to an implementation decision.

It must not become a substitute for implementation.

---

# 32. Test Rule

Never delete or weaken existing tests merely to obtain PASS.

Accepted previous milestone behavior must remain passing
unless an explicitly accepted contract change requires a legitimate update.

Testing should cover where applicable:

- domain contracts;
- public boundary contracts;
- integration;
- Ref / Version lineage;
- persistence;
- rollback / atomicity;
- failure handling;
- browser/API behavior;
- provider boundaries;
- security;
- downstream bridges.

A working UI alone is insufficient.

Unit tests alone are insufficient.

---

# 33. Browser / Live Gate

Accepted ADR-0001 and the remote-verified rebaseline split validation into three
gates:

GATE A — FRONTEND EXPERIENCE GATE

Owned by the separate Frontend repository. It covers frontend tests, build,
browser QA, responsive behavior, accessibility, visual quality and customer
workflows.

GATE B — CORE HTTP RUNTIME GATE

Owned by this Core repository. It covers Creator Server startup, public
HTTP/API contracts, Creator Application commands and queries, authorization,
tenant/workspace enforcement, persistence, idempotency, integration and error
contracts.

GATE C — CROSS-REPO INTEGRATION GATE

Validates the deployed/served Commercial Frontend against the real Creator
public HTTP/API boundary. It must validate public contracts and must never use
shared source imports.

When browser behavior is part of Gate A or Gate C, validate with a real
browser through a real HTTP runtime.

Preferred accepted methods include:

- normal Chrome control;
- Chrome Headless + DevTools CDP when the normal control channel is unavailable.

Final Frontend/Cross-repository Browser Gates must NOT use:

- file://;
- jsdom-only evidence;
- static HTML parsing;
- mock browser results.

Where practical Gate A / Gate C verify:

Console errors = 0

Page errors = 0

Unexpected HTTP errors = 0

Horizontal overflow = 0

Broken UI = 0

Do not fabricate screenshots.

Do not reuse historical screenshots as new evidence.

---

# 34. Runtime Identity Gate

For major Core HTTP runtime validation, report:

RUNTIME PORT

RUNTIME PID where available

RUNTIME WORKSPACE

RUNTIME BRANCH

RUNTIME HEAD SHA

PUBLIC API ROOT / SERVER MODULE

The team must be able to identify exactly which Core workspace and commit is
serving the Creator public HTTP/API runtime. A customer-facing static root is
not required in Core after legacy UI decommission.

---

# 35. Canonical Workspace Rule

Default canonical development and runtime workspace:

D:\Codex使用\AI CINEMATIC STUDIO

After Canonical Workspace Promotion is complete,
remaining serial milestones M6–M19 should use this workspace.

Do NOT create a new worktree for every ordinary milestone.

Temporary worktrees are exceptions for:

- emergency hotfix;
- true parallel development;
- high-risk isolated experiments.

A temporary worktree must eventually converge back
to the canonical accepted Git history.

---

# 36. Git Hard Gate

A feature / technical checkpoint is not complete until required gates are true.

Typical hard gates:

IMPLEMENTATION PASS

INTEGRATION PASS

PRODUCTION SPINE PASS

REGRESSION TESTS PASS

BROWSER / LIVE PASS

PERSISTENCE PASS
when applicable

ARCHITECTURE PASS

SECRET SCAN PASS

git diff --check PASS

GIT COMMIT PASS

GITHUB PUSH PASS

REMOTE SHA == LOCAL SHA

GIT STATUS CLEAN

Codex performs commit and push.

Do not ask the user to manually push GitHub.

After a formal checkpoint:

1. create the tested commit;
2. push to GitHub;
3. fetch remote;
4. read local SHA;
5. read remote SHA;
6. verify equality.

If:

LOCAL SHA != REMOTE SHA

then:

CHECKPOINT NOT COMPLETE

If GitHub is temporarily unavailable:

GITHUB SYNC HOLD

Preserve the tested local commit.

Do not rewrite correct code because of network connectivity.

Never force push unless Project Lead explicitly authorizes it.

---

# 37. Secret Policy

Never commit:

- API keys;
- `.env` secrets;
- Authorization headers with real values;
- passwords;
- access tokens;
- private keys;
- provider credentials;
- secret-bearing logs;
- sensitive raw provider responses.

Frontend code must never contain Provider Secret.

Provider errors shown to users must not reveal secret information.

---

# 38. Clean Workspace Rule

Before major milestone implementation:

- inspect current branch;
- inspect HEAD;
- inspect Git status;
- compare against accepted base.

Do not allow unrelated historical files
to become implicit runtime dependencies.

Do not automatically delete user files.

Preserve important data before any destructive workspace operation.

---

# 39. Current Execution Authority

CURRENT_MILESTONE.md defines the active execution scope.

Before implementation:

1. read System Master Plan;
2. read UI Master Plan;
3. read AGENTS.md;
4. read CURRENT_MILESTONE.md;
5. inspect canonical workspace;
6. inspect branch / HEAD;
7. inspect Git status;
8. verify accepted base;
9. execute only authorized milestones.

If the files conflict:

STOP.

Do not infer intent.

---

# 40. Execution Modes

CURRENT_MILESTONE.md may define one of two execution modes.

## MANUAL

Only the CURRENT milestone may be executed.

After all gates:

report candidate state

then STOP.

Do not enter the next milestone.

## AUTO-SEQUENTIAL

Automatic transition is allowed ONLY when
CURRENT_MILESTONE.md explicitly contains:

Execution Mode:
AUTO-SEQUENTIAL

and explicit:

Project Lead Authorization

for a defined execution wave.

Example:

M4 → M5 AUTO-PROGRESSION AUTHORIZED

Only milestones explicitly listed in that wave
may be automatically entered.

No implicit extension is allowed.

The Project Lead standing instruction recorded on `2026-08-13` permits Codex to
implement, test, commit, push and remote-verify without repeated conversational
approval inside an explicitly listed bounded wave. It does not itself authorize an
unlisted milestone and does not waive Source-of-Truth, final acceptance, destructive
migration, security, rights, credential, data-loss or Stop Condition gates.

---

# 41. Automatic Transition Hard Gate

Under AUTO-SEQUENTIAL mode,
Codex may enter the next authorized milestone ONLY IF:

1. current milestone implementation is complete;
2. all milestone gates PASS;
3. real Production Spine integration PASS;
4. Browser / Live Gate PASS when required;
5. persistence PASS when required;
6. architecture PASS;
7. secret scan PASS;
8. milestone has its own Git commit;
9. GitHub push PASS;
10. remote SHA == local SHA;
11. Git status CLEAN;
12. no Stop Condition exists;
13. no destructive migration ambiguity exists;
14. CURRENT_MILESTONE.md explicitly authorizes the transition.

If any condition fails:

STOP.

Do not enter the next milestone.

---

# 42. Automatic Transition Does Not Equal Final Acceptance

When an automatically transitioned milestone completes its gates,
Codex may mark it:

TECHNICAL GATES PASSED
AUTO-TRANSITION CHECKPOINT COMPLETE

This is not:

FEATURE ACCEPTED

Final acceptance remains Project Lead authority.

At the end of the authorized execution wave:

Codex must STOP.

The next milestone outside the wave must not be entered.

---

# 43. Stop Conditions

STOP and report the exact blocker if:

- a new authoritative owner must be decided;
- an accepted architecture contract would be violated;
- a required credential is unavailable for a mandatory live gate;
- a rights/license decision is required;
- a destructive migration is ambiguous;
- Production Spine must change;
- a milestone outside the authorized wave is required;
- upstream/downstream integration cannot be defined;
- local/remote Git history conflicts unexpectedly;
- Source-of-Truth documents conflict;
- a security risk cannot be resolved safely;
- accepted UI architecture would need major redesign;
- data loss risk exists.

Do not invent decisions to bypass these conditions.

---

# 44. Milestone Completion Report

Always report at minimum:

CURRENT MILESTONE:

EXECUTION MODE:

BRANCH:

BASE SHA:

IMPLEMENTATION:

UPSTREAM CONNECTION:

INPUT CONTRACT:

OUTPUT CONTRACT:

DOWNSTREAM CONNECTION:

REF / VERSION LINEAGE:

PRODUCTION SPINE:

INTEGRATION:

PERSISTENCE:
if applicable

BROWSER / LIVE:

TESTS:

ARCHITECTURE:

SECRET SCAN:

COMMIT SHA:

PUSH:

REMOTE BRANCH:

REMOTE SHA:

LOCAL == REMOTE:

GIT STATUS:

REMAINING GAPS:

NEXT AUTHORIZED MILESTONE:

MILESTONE STATUS:

Never claim final FEATURE ACCEPTED.

Only Project Lead may issue final acceptance.

---

# 45. Final Rule

The project is governed by:

Project First

Production Spine First

V2.3 Layer Ownership

Clear Domain Authority

Ref + Version + Lineage

AI Generates Candidates

Platform Owns Facts

Human Controls Critical Gates

Real Production Before Batch Scale

One Creator UI

Separate Commercial Experience Layer

One Canonical Workspace

GitHub-Verified Accepted Baselines

Do not optimize for the fastest isolated feature.

Optimize for a connected, traceable, maintainable AI film production system.

# End of AGENTS.md
