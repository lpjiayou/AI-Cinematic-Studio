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

The proposed PRE-M6 route is fixed as:

`PRE-M6-RB1.1 Source-of-Truth Rebaseline`
→ `PRE-M6-RB1.2 Legacy UI Decommission`
→ `PRE-M6-RB1.3 Full Core Current-State Audit`
→ `Architecture Review`
→ `M6 Preconditions`
→ `M6-P1`

The current work is limited to the `PRE-M6-RB1.1` revision and review stage.
No later stage is implied or authorized.

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
Worker execution or cross-repository UI. M6 remains `NOT STARTED / NOT AUTHORIZED`.

Legacy Phase 0 governance drift is `OPEN / DEFERRED TO PRE-M6-RB1.3`.
This acknowledgement does not silently amend those governance files.

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

Do not duplicate these facts in Creator Application.

---

# 12. V4 Platform Ownership

V4 is the execution and AI platform boundary.

Early V4 may provide:

TextGenerationPort
→ Provider Adapter

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
→ capability service
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

The PRE-M6-RB1.1 proposal, subject to ADR-0001 acceptance, places the
customer-facing Commercial SaaS experience layer in the separate
`AI-Cinematic-Studio-Frontend` repository.

Under that conditional proposal, this Core repository continues to own the
Creator Server Runtime, public HTTP/API boundaries, Creator Application
orchestration and lower platform layers, while not owning the customer-facing
Commercial SaaS UI source.

Do not redesign the entire product during ordinary capability work.

Future milestones should activate existing UI architecture,
not invent new global structure.

---

# 20. One Creator UI Rule

There is ONE Creator product UI.

If ADR-0001 is later accepted and the rebaseline becomes a remote-verified
checkpoint, this means:

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

The only proposed cross-repository dependency chain is:

`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

The Frontend Experience Adapter belongs to the Frontend repository and may
consume only Creator Public HTTP/API. The Frontend must not import Core source,
access Creator Application, Domain, SQL or persistence directly, call providers,
or connect to private V5, worker, GPU or ComfyUI adapters. The repositories do
not share customer UI source code.

The historical browser UI under `apps/creator-workspace-mvp` remains a controlled
`DECOMMISSION CANDIDATE`. Do not delete the whole directory blindly. Every file
must be classified; mixed files remain `AMBIGUOUS_SHARED_FILE`. Preserve
Server/API/Application/Domain/Persistence/Test responsibilities. Actual removal
requires separate `PRE-M6-RB1.2` authorization and may remove only files proven
UI-only.

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

Subject to ADR-0001 acceptance and the remote-verified rebaseline checkpoint,
validation is proposed to split into three gates:

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
