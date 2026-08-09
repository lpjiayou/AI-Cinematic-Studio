# AI Cinematic Studio — Current Execution Wave

> Document: `CURRENT_MILESTONE.md`
>
> Status: `EXECUTION WAVE ACTIVE`
>
> Execution Wave: `Wave 1`
>
> Scope: `M4 → M5`
>
> Execution Mode: `AUTO-SEQUENTIAL`
>
> Project Lead Authorization:
> `M4 → M5 AUTO-PROGRESSION AUTHORIZED`
>
> M6 Authorization:
> `NOT AUTHORIZED`

---

# 0. Canonical Execution Baseline

## Canonical Workspace Promotion

Status:

`PASS`

Canonical Workspace:

`D:\Codex使用\AI CINEMATIC STUDIO`

Promotion / Control-Baseline SHA:

`59946b6bb67f30a7f978b447850cbd83e8e1d1a6`

Promotion Remote Verification:

`LOCAL SHA == REMOTE SHA — PASS`

Canonical Runtime:

`http://127.0.0.1:8765/`

Canonical Workspace Rule:

Normal serial development for M4–M19 must use:

`D:\Codex使用\AI CINEMATIC STUDIO`

Do not create a new normal milestone worktree for M4 or M5.

Temporary worktrees are allowed only for:

- emergency hotfix;
- true parallel development;
- high-risk isolated experiment.

---

# 1. Wave Authorization Checkpoint

This file is the Project Lead approved execution authorization
for Wave 1.

Before any M4 implementation begins, Codex must ensure that the
approved current versions of:

- `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`
- `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`
- `AGENTS.md`
- `CURRENT_MILESTONE.md`

are tracked in Git and remotely verified.

If replacing this file created a Git working-tree modification,
Codex is authorized to create ONE docs-only authorization checkpoint
before M4 implementation.

Allowed commit message:

`docs(project): authorize execution wave m4 m5`

This checkpoint may contain ONLY approved project-control-document
changes.

After the checkpoint:

- push GitHub;
- fetch remote;
- verify local SHA == remote SHA;
- verify Git status CLEAN.

The resulting Remote-Verified HEAD becomes:

`WAVE_1_BASE_SHA`

and therefore:

`M4_BASE_SHA`

Do not begin M4 from a dirty working tree.

If no control-document change exists because the approved version is
already tracked and Remote Verified:

`WAVE_1_BASE_SHA = current Remote-Verified Canonical HEAD`

Record the exact SHA before implementation.

---

# 2. Mandatory Startup Read Order

Before implementation Codex MUST read, in this order:

1. `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`
2. `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`
3. `AGENTS.md`
4. `CURRENT_MILESTONE.md`

Then inspect:

- canonical workspace;
- current branch;
- HEAD;
- Git status;
- remote tracking state;
- accepted baseline;
- Creator runtime identity;
- existing V5 Project-related code and public boundaries.

If any Source-of-Truth conflict exists:

`STOP`

Do not infer which source should win.

---

# 3. Accepted Historical Capabilities

The following are already accepted.

They MUST NOT be rebuilt.

## M1 — AI Director Core

Status:

`FEATURE ACCEPTED`

## M2 — Series + Episode Foundation

Status:

`FEATURE ACCEPTED`

## M3 — Script Studio

Status:

`FEATURE ACCEPTED`

## M3-H — Script Candidate Robustness

Status:

`FEATURE ACCEPTED`

## Story Projection Integration

Status:

`ACCEPTED`

## UI-R1 — Enterprise Cinematic UI Rebaseline

Status:

`FEATURE ACCEPTED`

Accepted UI-R1 Code SHA:

`c9536fc0c745d0bf9e9c3eb543f4ab6c0566798a`

Canonical control baseline after promotion:

`59946b6bb67f30a7f978b447850cbd83e8e1d1a6`

Existing real production chain:

AI Director
→ Confirmed CreativePlan
→ Series
→ Episode
→ Story Projection
→ Script Studio
→ ScriptVersion

M4 and M5 must extend this chain.

They must not replace it.

---

# 4. Execution Wave 1

Authorized sequence:

M4 — Project Context Foundation
↓
M4 Technical Checkpoint
↓
M5 — Series Planning + Series Director
↓
Wave Stop
↓
Project Lead Review

M6 is outside this execution wave.

Codex MUST NOT enter M6.

---

# 5. M4 — Project Context Foundation

Status:

`CURRENT`

Base:

`M4_BASE_SHA = WAVE_1_BASE_SHA`

Preferred Branch:

`codex/creator-capability-phase4-project-context`

Workspace:

`D:\Codex使用\AI CINEMATIC STUDIO`

Do not create:

`AI CINEMATIC STUDIO-m4`

unless a genuine isolation Stop Condition requires it.

---

# 6. M4 Purpose

M4 establishes Project as the authoritative production root.

Target hierarchy:

Workspace
→ Content Profile
→ Project
→ Series
→ Episode
→ Story
→ Script

M4 does NOT rebuild:

- AI Director;
- Series;
- Episode;
- Story Projection;
- Script Studio.

M4 adds the missing Project production context above the accepted
Series / Episode chain.

---

# 7. M4 Product Semantics

Project answers:

`What production are we making?`

Series answers:

`What series narrative / production context does it belong to?`

Episode answers:

`What concrete production unit are we producing?`

For Series projects:

Workspace
→ Content Profile
→ Project
→ Series
→ Episode

Rules:

- Project != Series
- Project != Episode
- Series != Episode
- Episode != Canonical Project
- `episodeRef != projectRef`
- Browser must not fabricate `projectRef`

M4 must not create ambiguous identity shortcuts.

---

# 8. M4 Existing Project-Domain Convergence Gate

Before creating any new Project implementation:

inspect all existing V5 Project-related code, contracts, repositories,
adapters and services.

Goal:

reuse / extend / converge on ONE authoritative V5 Project boundary.

Do not create:

- a second Project Domain;
- a Creator-owned Project authority;
- a Browser-only Project;
- a second persistence truth.

If an existing Project concept has incompatible semantics
and authoritative ownership cannot be resolved safely:

`STOP`

Report the exact architecture conflict.

Do not silently create another Project model.

---

# 9. M4 Content Profile Scope

M4 does NOT implement a complete Content Profile Intelligence system.

Where accepted existing flows already provide a stable:

`contentProfileRef`

M4 may consume and preserve it as Project context.

Target relationship:

workspaceRef
→ contentProfileRef
→ projectRef

Do not overbuild Content Profile during M4.

---

# 10. M4 Core Domain Scope

M4 establishes at minimum:

- authoritative V5 Project boundary;
- stable `projectRef`;
- Project type;
- minimal Project lifecycle foundation;
- workspace relationship;
- Content Profile reference relationship;
- Project → Series relationship;
- Series → Episode context resolution;
- Project create command;
- Project read/query contract;
- Project list/query;
- Project context projection;
- existing Series/Episode compatibility strategy;
- Project-aware Story navigation;
- Project-aware Script navigation.

All authoritative writes go through accepted V5 public boundaries.

---

# 11. M4 Existing Identity Preservation

M4 must preserve existing accepted identities and facts:

- `seriesRef`
- `episodeRef`
- `ConfirmedCreativePlanBinding`
- `sourcePlanRef`
- `sourcePlanVersion`
- Story lineage
- `scriptRef`
- `scriptVersionRef`
- `confirmedScriptVersionRef`

Existing accepted facts must not be rewritten merely because
Project Context is introduced.

No name-based authority.

No copied-text authority.

No copied-JSON authority.

---

# 12. M4 Existing Data Compatibility

Existing accepted Series / Episode data must not be discarded.

If an existing Series requires attachment to a Project:

use an explicit deterministic compatibility strategy.

Requirements:

- preserve `seriesRef`;
- preserve `episodeRef`;
- preserve CreativePlan lineage;
- preserve Script lineage;
- no Browser-generated IDs;
- no name-based matching as authoritative identity;
- no silent destructive migration;
- no orphan Series;
- no orphan Episode.

If destructive migration semantics are ambiguous:

`STOP`

Do not proceed to M5.

---

# 13. M4 Input Contract

M4 must explicitly define the accepted Project input boundaries.

At minimum:

Project Create Input

Project Query Input

Project → Series association input

Episode Project Context resolution input

Relevant upstream references may include:

- `workspaceRef`
- `contentProfileRef`
- existing `seriesRef`
- existing `episodeRef`

depending on the operation.

UI input is not authoritative until accepted by the Application/V5
boundary.

---

# 14. M4 Output Contract

M4 must produce stable Project-context outputs.

Required core lineage:

workspaceRef
→ contentProfileRef
→ projectRef
→ seriesRef
→ episodeRef

Existing production lineage must continue:

projectRef
→ seriesRef
→ episodeRef
→ sourcePlanRef
→ Story Projection
→ scriptRef
→ scriptVersionRef

Downstream M5 must consume real:

`projectRef`
+
`seriesRef`

not copied Project names.

---

# 15. M4 Project Creation Flow

The accepted UI-R1 New Project Wizard becomes functional.

For a Series Project:

User Input
↓
Application Command
↓
V5 Project
↓
projectRef
↓
Series association / creation through accepted V5 boundary
↓
Project Workspace

Do not auto-create all planned Episodes.

Example:

plannedEpisodeCount = 100

means:

planning intent

not:

100 Episode records.

M4 must not create:

- 100 Episodes;
- 100 Scripts;
- 100 jobs;
- Batch orchestration.

---

# 16. M4 UI Activation

Use the already accepted Enterprise UI-R1 shell.

Do NOT redesign:

- Global Navigation;
- Project Workspace IA;
- visual language;
- Editor Shell;
- Inspector pattern;
- Workflow Action Bar.

Activate real UI capability for:

Global:
- 项目
- 新建项目

Project Workspace:
- 项目概览
- Project Context Bar

Existing accepted:
- AI导演
- Series / Episode
- 故事
- 剧本

must remain real.

---

# 17. M4 Context Bar Gate

Inside a real Project the Enterprise UI must display real context:

项目
→ Project

系列
→ Series

单集
→ Episode

阶段
→ current production stage

当前对象
→ current production object

版本
→ applicable real version

The Context Bar must use real Refs internally.

No fake Project.

No browser-generated Project.

---

# 18. M4 Production Spine Gate

A real browser flow must prove:

Create Project
→ Series
→ Episode
→ Story
→ Script

and preserve:

projectRef
→ seriesRef
→ episodeRef
→ sourcePlanRef
→ scriptRef
→ scriptVersionRef

Fixtures may support tests.

Fixtures alone are NOT sufficient for the final M4 integration gate.

---

# 19. M4 Persistence / Atomicity Gate

M4 must survive:

- Browser refresh;
- Creator Server restart;
- Project query roundtrip;
- Project → Series relationship;
- Series → Episode relationship;
- Story lineage;
- Script lineage.

Where an operation writes multiple authoritative facts,
transaction / rollback semantics must be explicit.

Failed Project/Series association must not create partial orphan state.

---

# 20. M4 Lifecycle / Deletion Safety

Project lifecycle behavior must respect existing production lineage.

Do not allow ordinary deletion to destroy downstream protected facts.

If Project contains protected:

- Episode;
- ScriptVersion;
- Asset;
- future Master;

follow accepted lifecycle protection.

Do not create orphan production facts.

---

# 21. M4 Regression Gate

M4 must preserve accepted behavior for:

## M1

- AI Director
- DeepSeek path
- candidate validation
- Human Confirmation

## M2

- Series
- Episode
- parent-child identity
- ConfirmedCreativePlanBinding
- persistence

## Story

- real Story Projection
- same Episode lineage
- Provider calls = 0

## M3

- Script Generate
- controlled repair
- ScriptVersion
- manual edit
- scene rewrite
- confirmation
- version history
- persistence
- deletion protection

No accepted capability may be downgraded to a placeholder.

---

# 22. M4 Browser / Runtime Gate

Final M4 Browser Gate must use:

Creator HTTP Runtime

Expected:

`http://127.0.0.1:8765/`

Runtime must report:

- Runtime Workspace
- Runtime Branch
- Runtime HEAD
- Static Root

Browser method may use:

- normal Chrome control;
- Chrome Headless + DevTools CDP.

Do NOT use `file://` as final evidence.

Where applicable:

Console errors = 0

Page errors = 0

Unexpected HTTP errors = 0

Horizontal overflow = 0

---

# 23. M4 Required Gates

ALL must PASS before M5 may start:

IMPLEMENTATION

UPSTREAM CONNECTION

INPUT CONTRACT

OUTPUT CONTRACT

DOWNSTREAM CONNECTION

REF / VERSION LINEAGE

PRODUCTION SPINE

INTEGRATION

V5 OWNERSHIP

PROJECT DOMAIN CONVERGENCE

PROJECT IDENTITY

CONTENT PROFILE RELATIONSHIP

PERSISTENCE

ATOMICITY / ROLLBACK

MIGRATION / COMPATIBILITY

LIFECYCLE / DELETION SAFETY

M1 REGRESSION

M2 REGRESSION

STORY REGRESSION

M3 REGRESSION

BROWSER / LIVE

RESPONSIVE

ARCHITECTURE

SECRET SCAN

git diff --check

GIT COMMIT

GITHUB PUSH

REMOTE SHA == LOCAL SHA

GIT STATUS CLEAN

---

# 24. M4 Git Checkpoint

M4 must have its own independent Git checkpoint.

Suggested commit:

`feat(creator): establish project production context`

After M4 passes every gate:

record:

`M4_FINAL_SHA`

Push M4 branch to GitHub.

Fetch remote.

Verify:

`LOCAL SHA == REMOTE SHA`

Verify:

`git status CLEAN`

Do not combine M4 and M5 in one commit.

---

# 25. Automatic M4 → M5 Transition

Project Lead explicitly pre-authorizes:

`M4 → M5`

only if every M4 Required Gate passes.

If all M4 gates PASS:

treat M4 execution state as:

`TECHNICAL GATES PASSED`
`AUTO-TRANSITION CHECKPOINT COMPLETE`

This does NOT mean:

`FEATURE ACCEPTED`

Final Feature Acceptance remains Project Lead authority.

Then treat:

M5 Status:

`CURRENT`

M5 Base:

`M4_FINAL_SHA`

Continue automatically.

IMPORTANT:

Do NOT modify `CURRENT_MILESTONE.md` merely to record the M4 → M5
automatic transition.

The transition state is execution state and belongs in:

- Codex runtime execution context;
- M4 technical checkpoint;
- final Wave report.

The worktree MUST remain CLEAN at the M4 → M5 boundary.

If ANY M4 gate fails:

`STOP`

Do not enter M5.

---

# 26. M5 — Series Planning + Series Director

Initial Status:

`QUEUED / AUTO-NEXT`

Automatic Status after successful M4 transition:

`CURRENT`

Base:

`M5_BASE_SHA = M4_FINAL_SHA`

Preferred Branch:

`codex/creator-capability-phase5-series-planning`

Workspace:

`D:\Codex使用\AI CINEMATIC STUDIO`

After M4:

create / switch to M5 branch from the exact Remote-Verified
`M4_FINAL_SHA`.

Do not create a separate `-m5` worktree for normal serial development.

---

# 27. M5 Purpose

M5 turns a real Project / Series concept into an authoritative,
versioned Series Production Plan.

Example:

Project:
穿越大唐

Series:
穿越大唐

Planned Episodes:
100

ARC 1
EP01–20
求生

ARC 2
EP21–50
建立势力

ARC 3
EP51–80
权力冲突

ARC 4
EP81–100
最终选择

M5 creates planning facts.

M5 does NOT create:

- 100 production Episodes;
- 100 Scripts;
- 100 Storyboards;
- 100 GPU jobs;
- Batch production.

---

# 28. M5 Upstream

Authoritative upstream:

- `workspaceRef`
- `contentProfileRef`
- `projectRef`
- `seriesRef`
- Project creative context
- existing AI Director capability where applicable

M5 must consume real M4 Project Context.

No name-based Project lookup as authoritative integration.

---

# 29. M5 Series Planning Ownership

Authoritative Series Planning belongs to:

`V5 Core OS`

Creator Application:

orchestrates command / query.

V4:

executes AI generation.

Provider:

generates candidate content.

Browser:

presentation / interaction only.

Do not create a Creator-owned Series Plan authority.

---

# 30. M5 Series Planning Identity

Required direction:

projectRef
→ seriesRef
→ seriesPlanRef
→ seriesPlanVersionRef

Episode Plan Items are planning facts.

They must have deterministic/stable identity within the accepted
Series Plan contract.

They must NOT reuse:

`episodeRef`

unless an actual Episode has been created.

A planned Episode is not the same thing as a production Episode.

---

# 31. M5 Minimal Series Plan Contract

Series Plan must support enough structure for real downstream production.

At minimum:

- Series concept;
- premise / logline;
- main narrative direction;
- main arcs;
- sub-arcs;
- Character Arc Intent;
- Episode Plan Items;
- narrative rhythm;
- world intent;
- continuity intent;
- foreshadowing-compatible planning context;
- production assumptions.

Do not overbuild a full industrial writers-room platform in M5.

Build the minimum authoritative plan required by M6 and future Episodes.

---

# 32. M5 Series Director

AI Director gains Project / Series context mode.

Expected flow:

Project Context
+
Series Context
+
Creative Input
↓
V4 TextGenerationPort
↓
Text Provider
↓
Series Plan Candidate
↓
Local Schema Validation
↓
Optional Controlled Repair
↓
Human Confirmation
↓
SeriesPlanVersion

Provider remains replaceable.

Provider must not own:

- projectRef;
- seriesRef;
- seriesPlanRef;
- seriesPlanVersionRef;
- Episode identity;
- Character identity;
- approval state.

---

# 33. M5 Candidate / Repair Rule

Provider output is candidate output.

Pattern:

Generate
→ Validate
→ at most controlled repair when required
→ Validate
→ Human Confirmation

No infinite retry.

Malformed candidate:

must not become authoritative `SeriesPlanVersion`.

System-owned structural identity must be created locally.

---

# 34. M5 Planned Episode vs Created Episode

This distinction is a hard gate.

## Episode Plan Item

Planning fact.

Represents:

what a future Episode should contain.

## Episode

Production Domain Object.

Represents:

an actual production unit.

Therefore:

plannedEpisodeCount = 100

may result in:

100 Episode Plan Items

but must NOT automatically create:

100 Episode records.

UI must visibly distinguish:

`计划分集`

from:

`已创建单集`

---

# 35. M5 Series Planning UI Activation

Activate existing accepted UI-R1 areas:

策划
→ AI导演
→ 系列规划

Use existing Enterprise Shell.

Do NOT redesign:

- Global Navigation;
- Project Workspace IA;
- Inspector architecture;
- visual baseline.

Expected patterns:

- Arc Navigator;
- Series Planning Board;
- Episode Plan Table;
- Inspector;
- Version History;
- Source / Lineage;
- Workflow Next Action.

Large Series should use:

Dense Table / List

not:

100 giant cards.

---

# 36. M5 Versioning

Series Plan uses immutable versions.

Example:

SeriesPlan v1
→ AI candidate confirmed

SeriesPlan v2
→ manual revision

SeriesPlan v3
→ later controlled revision

Historical versions remain immutable.

Current confirmed plan is represented by an explicit
confirmed/current version reference.

Do not overwrite previous plan versions.

---

# 37. M5 Production Spine Gate

Must prove:

Project
→ Series
→ SeriesPlanVersion
→ Episode Plan Item

and for a real created Episode:

Project
→ Series
→ SeriesPlanVersion
→ Episode
→ Story
→ Script

M5 must strengthen the accepted production chain.

It must not create a separate planning island.

---

# 38. M5 M6 Downstream Bridge

M5 must expose a deterministic downstream input contract
for:

M6 — Series IP Bible + Character Intelligence.

Target bridge must preserve:

- `projectRef`
- `seriesRef`
- `seriesPlanRef`
- `seriesPlanVersionRef`
- main arcs
- Episode plan
- Character Arc Intent
- world intent
- continuity intent
- foreshadowing-compatible planning context

Deterministic projection Provider calls:

`0`

M6 must not need:

- copied UI text;
- duplicated random JSON;
- display-name lookup.

The M6 bridge may be prepared and tested.

M6 implementation must NOT begin.

---

# 39. M5 Persistence / Atomicity

Must survive:

- Browser refresh;
- Creator Server restart;
- Series Plan version history;
- confirmed/current SeriesPlan version reference;
- Project relationship;
- Series relationship;
- Episode Plan Items;
- existing Episode production lineage.

Failed writes must not create partial authoritative state.

---

# 40. M5 Regression Gate

M5 must preserve:

## M4

Project Context

Project → Series

Series → Episode

## M1

AI Director

## M2

Series / Episode

## Story

Story Projection

## M3

Script Studio

No accepted real capability may become a placeholder.

---

# 41. M5 Browser / Live Gate

Real browser flow must demonstrate:

Project
→ Series
→ Series Planning
→ Series Director Candidate
→ Validation
→ Human Confirmation
→ SeriesPlanVersion

Then prove existing production context remains connected.

If M5 requires real provider generation,
the mandatory live provider gate must be real.

Do not report a historical provider call as the new M5 Live Gate.

If required Provider credential is unavailable:

`STOP`

Do not fake PASS.

---

# 42. M5 Required Gates

ALL must PASS before Wave 1 may complete:

SERIES PLAN DOMAIN

V5 OWNERSHIP

PROJECT / SERIES LINEAGE

SERIES PLAN IDENTITY

AI SERIES DIRECTOR

V4 PROVIDER BOUNDARY

SCHEMA VALIDATION

CONTROLLED FAILURE HANDLING

VERSIONING

HUMAN CONFIRMATION

PLANNED VS CREATED EPISODE SEPARATION

M6 DOWNSTREAM BRIDGE

M4 REGRESSION

M1 REGRESSION

M2 REGRESSION

STORY REGRESSION

M3 REGRESSION

PERSISTENCE

ATOMICITY / ROLLBACK

PRODUCTION SPINE

BROWSER / LIVE

RESPONSIVE

ARCHITECTURE

SECRET SCAN

git diff --check

GIT COMMIT

GITHUB PUSH

REMOTE SHA == LOCAL SHA

GIT STATUS CLEAN

---

# 43. M5 Git Checkpoint

M5 must have its own independent Git checkpoint.

Suggested commit:

`feat(creator): add series planning and series director`

After every M5 gate passes:

record:

`M5_FINAL_SHA`

Push M5 branch to GitHub.

Fetch remote.

Verify:

`LOCAL SHA == REMOTE SHA`

Verify:

`git status CLEAN`

---

# 44. Execution Wave Stop Rule

After M5 all gates PASS:

report M5 execution state as:

`FEATURE ACCEPTED CANDIDATE`
`AWAITING PROJECT LEAD ACCEPTANCE`

report M4 execution state as:

`TECHNICAL GATES PASSED`
`AUTO-TRANSITION CHECKPOINT COMPLETE`

Do NOT enter M6.

Do NOT implement:

- Series IP Bible;
- Character Intelligence;
- Narrative Closed Loop;
- Storyboard.

Do NOT modify `CURRENT_MILESTONE.md` merely to record the final
Wave status unless explicitly instructed by the Project Lead.

STOP.

Project Lead reviews M4 + M5 together.

---

# 45. Global Stop Conditions

Immediately STOP if any of the following occurs:

- Source-of-Truth documents conflict;
- Canonical Workspace is not clean before milestone implementation;
- accepted V2.3 dependency direction would be violated;
- Project authoritative ownership is ambiguous;
- duplicate Project Domain would be created;
- Series ownership changes unexpectedly;
- destructive migration semantics are ambiguous;
- existing Series / Episode identity cannot be preserved safely;
- M1 / M2 / Story / M3 production lineage would break;
- required Provider credential is unavailable for a mandatory Live Gate;
- GitHub push fails at a milestone checkpoint;
- remote SHA != local SHA;
- Browser Gate fails because of a real product defect;
- security issue cannot be safely resolved inside scope;
- data-loss risk appears;
- accepted Enterprise UI architecture would require major redesign;
- M6 implementation would be required to make M5 pass.

Do not bypass a Stop Condition to keep automation moving.

---

# 46. Execution Branch Rule

Wave 1 uses one Canonical Workspace but separate milestone branches.

Expected:

Wave Base
↓
M4 Branch
↓
M4_FINAL_SHA
↓
M5 Branch created from M4_FINAL_SHA
↓
M5_FINAL_SHA

Do not create a new filesystem worktree for ordinary M4/M5 execution.

Do not combine M4 and M5 into one branch checkpoint without preserving
the independent M4 Remote-Verified commit.

---

# 47. Git / Runtime Clean Boundary

At each milestone transition:

Git status must be:

`CLEAN`

Remote SHA must equal:

Local SHA

Creator runtime validation must report:

- Runtime Workspace
- Runtime Branch
- Runtime HEAD
- HTTP URL

Do not run M5 against stale M4 runtime code.

---

# 48. Final Wave Report

After M5 completes, output:

EXECUTION MODE:

CANONICAL WORKSPACE:

WAVE_1_BASE_SHA:

CANONICAL START SHA:


M4 BASE SHA:

M4 BRANCH:

M4 FINAL SHA:

M4 IMPLEMENTATION:

M4 PROJECT DOMAIN:

M4 DOMAIN CONVERGENCE:

M4 V5 OWNERSHIP:

M4 CONTENT PROFILE RELATIONSHIP:

M4 PROJECT → SERIES:

M4 SERIES → EPISODE:

M4 MIGRATION / COMPATIBILITY:

M4 STORY:

M4 SCRIPT:

M4 PRODUCTION SPINE:

M4 PERSISTENCE:

M4 ATOMICITY:

M4 TESTS:

M4 BROWSER / LIVE:

M4 RESPONSIVE:

M4 ARCHITECTURE:

M4 SECRET SCAN:

M4 DIFF CHECK:

M4 PUSH:

M4 REMOTE SHA:

M4 LOCAL == REMOTE:

M4 GIT STATUS:


M5 BASE SHA:

M5 BRANCH:

M5 FINAL SHA:

M5 SERIES PLAN:

M5 SERIES PLAN IDENTITY:

M5 SERIES DIRECTOR:

M5 PROVIDER BOUNDARY:

M5 SCHEMA VALIDATION:

M5 REPAIR:

M5 HUMAN CONFIRMATION:

M5 PLAN VERSIONING:

M5 PLANNED VS CREATED EPISODE:

M5 M6 BRIDGE:

M5 PRODUCTION SPINE:

M5 PERSISTENCE:

M5 ATOMICITY:

M5 TESTS:

M5 BROWSER / LIVE:

M5 RESPONSIVE:

M5 ARCHITECTURE:

M5 SECRET SCAN:

M5 DIFF CHECK:

M5 PUSH:

M5 REMOTE SHA:

M5 LOCAL == REMOTE:

M5 GIT STATUS:


M1 REGRESSION:

M2 REGRESSION:

STORY REGRESSION:

M3 REGRESSION:


M6 ENTERED:

NO


EXECUTION WAVE 1 STATUS:

FEATURE ACCEPTED CANDIDATE
/
AWAITING PROJECT LEAD ACCEPTANCE

STOP.

# End of CURRENT_MILESTONE.md