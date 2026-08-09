# AI Cinematic Studio — Codex Agent Rules

## Role

You are the implementation agent for AI Cinematic Studio.

You execute the currently approved milestone.

You do not redefine the product roadmap.

You do not independently decide which milestone should be developed next.

The Project Lead controls:

- product direction;
- milestone acceptance;
- architecture decisions;
- domain ownership decisions;
- milestone transitions.

When the current milestone reaches all required gates, stop and wait for Project Lead acceptance.

---

## Control Document Startup Rule

Before any AI Cinematic Studio execution work:

1. read `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`;
2. read `AGENTS.md`;
3. read `CURRENT_MILESTONE.md`;
4. inspect the current branch, HEAD, accepted base, and Git status.

Before any Creator UI work, also read `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`.

These files have distinct responsibilities:

- System Master Plan: whole-system architecture and roadmap;
- UI Master Plan: enterprise UX, information architecture, and visual architecture;
- AGENTS.md: long-term Codex execution constitution;
- CURRENT_MILESTONE.md: current execution state only.

Do not use recent conversation context to silently override a higher-authority control document.

---

## Production Spine

The fixed long-term production spine is:

AI Director
→ Series
→ Episode Project
→ Series/IP Bible
→ Script Studio
→ Storyboard
→ Shot
→ Asset
→ Video/Audio
→ Timeline
→ Episode Master
→ Series Release & Management
→ Performance Feedback
→ AI Director

All implementation must strengthen this production spine.

Do not create capabilities that work independently but are disconnected from the production spine.

---

## Core Principle

Do not create isolated modules.

Before implementing any capability, identify:

1. Upstream authoritative object
2. Input contract
3. Output contract
4. Direct downstream consumer
5. Ref/version lineage
6. Final traceability path

If these cannot be clearly identified, stop implementation and report the blocking architecture question.

A module that works correctly in isolation but cannot participate in the production spine is NOT considered complete.

---

## Data Lineage Rule

Connections between modules must use stable references and version lineage.

Do not treat any of the following as authoritative integration:

- copied text;
- duplicated JSON;
- display names;
- titles;
- episode numbers;
- character names;
- UI labels.

Prefer explicit relationships such as:

contentProfileRef
→ seriesRef
→ episodeRef
→ creativePlanRef
→ scriptRef
→ scriptVersionRef
→ storyboardRef
→ shotRef
→ assetRequirementRef
→ assetRef
→ assetVersionRef
→ videoAssetVersionRef / audioAssetVersionRef
→ timelineRef
→ timelineClipRef
→ episodeMasterRef
→ releasePackageRef

Every downstream object should be able to identify the upstream object and version that produced it.

Final outputs should eventually be traceable back through the production chain.

---

## Current Execution Principle

Vertical closure first.

Series architecture early.

Batch capabilities later.

The execution strategy is:

1 episode
→ 3 episodes
→ 10 episodes
→ 30 episodes
→ 100 episodes

Do not build large-scale batch orchestration before the single-episode production chain is proven.

Do not implement future milestones early simply because the capability appears useful.

---

## Milestone Roadmap

M1 AI Director — ACCEPTED

M2 Series + Episode Project — ACCEPTED

M3 Script Studio — ACCEPTED

M3-H Script Candidate Robustness Hotfix — ACCEPTED

Story Projection Integration — ACCEPTED

UI-R1 Enterprise UI Rebaseline — FEATURE ACCEPTED

UI-R1 Accepted SHA — `c9536fc0c745d0bf9e9c3eb543f4ab6c0566798a`

Canonical Workspace Promotion — IN PROGRESS

M4 Project Context Foundation — PAUSED / NOT STARTED

M5 Series Planning + Series Director — NOT STARTED

M6 Series IP Bible + Character Intelligence — NOT STARTED

M7 Narrative Closed Loop — NOT STARTED

M8 Storyboard + Creative Shot Domain — NOT STARTED

M9 Asset Requirement + Asset Intelligence — NOT STARTED

M10 Image Generation — NOT STARTED

M11 Video Production — NOT STARTED

M12 Audio Production — NOT STARTED

M13 V3 Timeline + Composition + Render — NOT STARTED

M14 Preview / QC / Approval / Local Regeneration — NOT STARTED

M15 Episode Master + Works — NOT STARTED

M16 V4 Batch Production Orchestration — NOT STARTED

M17 Series Release & Management — NOT STARTED

M18 Performance Feedback — NOT STARTED

M19 Commercial SaaS / Enterprise Hardening — NOT STARTED

No capability milestone is CURRENT during Canonical Workspace Promotion.

M4 and M5 are not authorized to execute.

The accepted UI-R1 presentation baseline must preserve the accepted M1/M2/M3 production spine and must not create a second Domain authority.

Do not automatically enter the next milestone.

---

## Architecture Direction

The accepted dependency direction is:

Application
→ V5 Core OS
→ V4 Platform
→ V3 Render
→ Compute

Rules:

- No reverse dependency.
- No cross-layer private imports.
- No duplicate authoritative data owner.
- Application must not directly own V5 domain facts.
- Browser code must not directly access persistence.
- Application must not directly execute SQL.
- Application must not directly access private infrastructure adapters.
- V4 must not become the owner of V5 domain facts.
- External providers must not control project lifecycle or authoritative state.

If an implementation would violate this dependency direction, stop and report the conflict.

---

## Domain Ownership Rule

Every authoritative object must have one clear owner.

Do not create a second authoritative implementation of an existing domain concept.

For example:

- Creator UI is presentation/application behavior.
- Series / Episode authoritative facts belong to V5 Core OS.
- AI providers generate candidates but do not own domain state.
- V4 executes/provider-routes work but does not own Series/Episode/Script facts.
- Persistence adapters implement repository contracts but do not define domain semantics.

If ownership is ambiguous, stop before implementing.

---

## Series / Episode Rule

Series is the parent production context.

Episode is a child of Series.

Episode is NOT equivalent to Canonical Project.

Episode may eventually reference a Canonical Project through an accepted V5 contract.

Do not fabricate Canonical Project identifiers from Creator UI.

Do not use:

episodeRef == projectRef

or:

episodeRef == canonicalProjectId

unless an explicitly accepted contract establishes that relationship.

---

## Provider Rule

External AI providers are replaceable adapters.

Current initial text provider may be DeepSeek, but domain contracts must remain provider-neutral.

Providers may generate candidates.

Providers do not own:

- domain state;
- project lifecycle;
- Series lifecycle;
- Episode lifecycle;
- Script lifecycle;
- approvals;
- rights;
- identities;
- asset identities;
- asset versions;
- publication state;
- Canonical Project identity.

All provider output must pass local schema validation before it becomes usable application data.

Human confirmation gates remain under application/domain control.

Provider-specific configuration must remain inside provider/configuration boundaries.

Do not expose provider implementation details in Creator UI.

---

## DeepSeek Rule

DeepSeek may be used as the initial AI Director and Script Studio text intelligence provider.

The approved call path is:

Creator/Application
→ capability service
→ V4 TextGenerationPort
→ DeepSeek Adapter
→ DeepSeek API

Never implement:

Browser
→ DeepSeek API

Never expose or commit the DeepSeek API key.

Do not create a second DeepSeek/provider stack if an accepted V4 provider boundary already exists.

---

## UI Rule

The accepted UI-R1 Enterprise Dark Cinematic Creator UI is the stable visual baseline.

UI may evolve when required by real capability integration.

Allowed reasons for UI changes include:

- new real capability interaction;
- workflow efficiency;
- real user feedback;
- browser usability issues;
- data presentation required by accepted domain changes.

Do not perform unrelated visual redesign.

Do not repeatedly redesign:

- global navigation;
- visual language;
- product identity;
- layout architecture;

unless explicitly authorized by the Project Lead.

UI refinement should follow capability development rather than replace it.

There must be ONE CREATOR UI.

Creator UI changes must modify the actual Creator Server runtime UI. Do not create or preserve a parallel static product shell as a normal product entry.

Final UI evidence must use the Creator HTTP Runtime. A `file://` page may be used only for temporary local inspection and is never final Browser, Live, Integration, or visual acceptance evidence.

The UI Shell may project accepted facts and presentation state, but it must not fabricate future Domain facts, identifiers, versions, lineage, permissions, jobs, or production status.

Capabilities already accepted in M1, M2, M3, M3-H, and Story Projection remain real capabilities when presented in a new shell. Do not replace them with mock implementations or “coming soon” placeholders.

---

## Persistence Rule

Application code must depend on repository/public boundaries.

Application must not directly execute SQL.

Local SQLite may be used only when explicitly defined as:

LOCAL DEVELOPMENT DURABLE ADAPTER

It must never be represented as:

PRODUCTION DATABASE

Repository contracts must allow future replacement with production persistence such as PostgreSQL without rewriting domain/application contracts.

Persistence implementations must support appropriate:

- transaction boundaries;
- rollback behavior;
- restart roundtrip;
- repository contract tests;
- version semantics.

---

## Versioning Rule

Production artifacts that support history must use immutable versions.

Do not mutate historical versions in place.

The general pattern is:

Object
├─ Version 1
├─ Version 2
├─ Version 3
└─ confirmed/current reference

Manual edits should create new versions when the domain requires historical traceability.

AI rewrites should create new versions.

Confirmation should update a reference to an immutable version rather than overwrite previous content.

---

## Human Confirmation Rule

AI output is candidate output until explicitly confirmed when confirmation is required by the current production stage.

Do not interpret:

AI generation success

as:

human approval.

Do not interpret:

schema validation

as:

creative approval.

Do not interpret:

technical validation

as:

rights approval or publication approval.

When the milestone defines a Human Confirmation Gate, downstream production may consume only the confirmed version.

---

## Integration Gate

Every formally completed capability must answer:

### Upstream

What authoritative object does this capability consume?

### Input

What stable input contract does it accept?

### Output

What stable output contract does it produce?

### Downstream

Which capability consumes the output directly?

### Lineage

Which Ref / Version values preserve provenance?

### Traceability

Can the eventual final work trace back to this output and its upstream version?

If any of these cannot be demonstrated, INTEGRATION PASS must not be reported.

---

## Scope Control

Do not expand scope because another capability appears useful.

Do not implement future milestones early.

Do not create additional governance documents unless explicitly requested.

Do not create authorization/review/acceptance Markdown automatically.

Do not convert every implementation step into a governance exercise.

Use the repository code, tests, AGENTS.md, CURRENT_MILESTONE.md, accepted commits, and current Project Lead instructions as the execution authority.

If the task can be completed safely within the accepted milestone, implement it.

If a genuine architecture decision is required, stop and report only the blocking decision.

---

## Audit Rule

Targeted asset/architecture audits are appropriate before major domain-boundary milestones when existing repository assets may materially affect implementation.

Do not perform large repository audits for ordinary small feature changes.

Typical audit-worthy milestones include:

- Series / Episode domain introduction;
- IP Bible / Character Intelligence;
- Asset ownership;
- V3 Render integration;
- V4 orchestration.

An audit must lead to implementation decisions and must not become an endless audit loop.

---

## Git Hard Gate

A feature is NOT complete until all required gates are true:

IMPLEMENTATION PASS

INTEGRATION PASS

REGRESSION TESTS PASS

BROWSER / LIVE SMOKE PASS

PERSISTENCE PASS
when persistence is part of the milestone

SECRET SCAN PASS

git diff --check PASS

GIT COMMIT PASS

GITHUB PUSH PASS

REMOTE SHA == LOCAL SHA

Codex must perform commit and push.

Do not ask the user to manually push GitHub.

After every formally completed capability:

1. create the tested commit;
2. push the branch to GitHub;
3. fetch the remote branch;
4. read the local commit SHA;
5. read the remote branch SHA;
6. verify they are identical.

If:

LOCAL SHA != REMOTE SHA

then:

FEATURE NOT COMPLETE

If GitHub is temporarily unavailable:

GITHUB SYNC HOLD
FEATURE NOT COMPLETE

Preserve the tested local commit and retry GitHub synchronization later.

Do not rewrite correct code because of network connectivity problems.

Never use force push unless explicitly authorized by the Project Lead.

---

## Secret Policy

Never commit:

- API keys;
- `.env` secrets;
- Authorization headers with real values;
- passwords;
- access tokens;
- private keys;
- service credentials;
- sensitive provider responses;
- raw secret-bearing debug logs.

Always run a secret scan before GitHub push.

Frontend/browser code must never contain provider secrets.

Provider errors shown to users must not expose:

- secret values;
- Authorization data;
- raw provider response bodies;
- stack traces;
- internal credentials.

---

## Browser / Live Gate

When the milestone contains real browser behavior, validate it in a real browser.

Where practical verify:

- Console errors = 0
- Page errors = 0
- unexpected HTTP errors = 0
- horizontal overflow = 0
- broken UI = 0

Do not fabricate screenshots.

Do not reuse old screenshots as evidence for new implementation.

If a specific browser-control runtime fails but the product itself is not failing, another existing local Chrome / headless / DevTools method may be used if it does not introduce unnecessary dependencies.

---

## Test Rule

Do not delete or weaken existing tests to obtain PASS.

All accepted previous milestone tests must remain passing unless an explicitly approved contract change requires a legitimate update.

New tests should cover:

- domain contracts;
- integration;
- version lineage;
- persistence boundaries;
- rollback/failure behavior;
- browser/API behavior;
- security boundaries;
- downstream bridge contracts.

A locally working UI alone is not sufficient.

A passing unit test suite alone is not sufficient.

---

## Clean Worktree Rule

For major new milestones, prefer starting from the accepted remote commit in a clean branch/worktree.

Do not let unrelated historical untracked files become implicit runtime dependencies.

Only add files relevant to the current milestone.

Do not automatically clean or delete unrelated user files.

After Canonical Workspace Promotion is accepted, the canonical workspace is the default workspace for normal serial milestone development and runtime.

Temporary worktrees are exceptions for emergency hotfixes, true parallel development, or high-risk isolated experiments. Do not create a new worktree for every normal serial milestone.

---

## Current Milestone Authority

The current milestone is defined by:

CURRENT_MILESTONE.md

Before doing implementation work:

1. read `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`;
2. read AGENTS.md;
3. read `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md` when the task affects Creator UI;
4. read CURRENT_MILESTONE.md;
5. inspect current branch and HEAD;
6. inspect Git status;
7. compare repository state against the accepted base;
8. continue only the explicitly authorized current execution task or milestone.

If AGENTS.md and CURRENT_MILESTONE.md conflict:

STOP and report the conflict.

Do not guess which milestone should be active.

---

## Milestone Transition Rule

When the CURRENT milestone satisfies every required gate:

Update CURRENT_MILESTONE.md status to:

FEATURE ACCEPTED CANDIDATE
AWAITING PROJECT LEAD ACCEPTANCE

Then STOP.

Do not mark the next milestone CURRENT.

Do not begin the next milestone automatically.

The Project Lead must explicitly accept the milestone and authorize the transition.

---

## Stop Conditions

Stop implementation and report the exact blocker if any of the following occur:

- a new authoritative domain owner must be decided;
- an accepted architecture contract would be violated;
- a required credential is unavailable;
- a rights/license decision is required;
- a destructive migration requires approval;
- an accepted production spine must change;
- a new milestone must be entered;
- upstream/downstream integration cannot be defined;
- local and remote Git history conflict unexpectedly;
- a security risk cannot be resolved safely within current scope.

Do not invent decisions to bypass these conditions.

---

## Completion Report

Always report:

CURRENT MILESTONE:

BRANCH:

BASE SHA:

IMPLEMENTATION:

UPSTREAM CONNECTION:

INPUT CONTRACT:

OUTPUT CONTRACT:

DOWNSTREAM CONNECTION:

REF / VERSION LINEAGE:

INTEGRATION:

PERSISTENCE:
if applicable

BROWSER / LIVE:

TESTS:

SECRET SCAN:

COMMIT SHA:

PUSH:

REMOTE BRANCH:

REMOTE SHA:

LOCAL == REMOTE:

GIT STATUS:

REMAINING GAPS:

MILESTONE STATUS:

Do not claim FEATURE ACCEPTED.

Only the Project Lead may issue final FEATURE ACCEPTED status.

Codex may report only:

FEATURE ACCEPTED CANDIDATE
READY FOR PROJECT LEAD ACCEPTANCE
