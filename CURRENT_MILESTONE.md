# Current Milestone

## Milestone

UI-R1 — AI Cinematic Studio Enterprise UI Rebaseline

## Status

FEATURE ACCEPTED CANDIDATE
AWAITING PROJECT LEAD ACCEPTANCE

## Accepted Base

1cc768ee9db4b52a916c94ae6af7b95b811f1cb2

## Development Branch

codex/creator-ui-enterprise-rebaseline-v3

## Execution Boundary

M1 AI Director — ACCEPTED

M2 Series + Episode Project — ACCEPTED

M3 Script Studio — ACCEPTED

M3-H Script Candidate Robustness Hotfix — ACCEPTED

Story Projection Integration — ACCEPTED

UI-R1 Enterprise UI Rebaseline — FEATURE ACCEPTED CANDIDATE / AWAITING PROJECT LEAD ACCEPTANCE

M4 Series IP Bible + Character Intelligence — PAUSED / NOT STARTED

UI-R1 may change only Application presentation, navigation shells and UI baseline documentation. It must preserve the accepted production spine, create no authoritative Project fact and stop for Project Lead acceptance.

---

## Accepted M3 Contract Retained During UI-R1

AI Director
→ Series
→ Episode Project
→ Series/IP Bible
→ **Script Studio**
→ Storyboard
→ Shot
→ Asset
→ Video/Audio
→ Timeline
→ Episode Master
→ Series Release & Management
→ Performance Feedback
→ AI Director

M3 owns only the Script Studio stage.

Do not enter M4 or later stages.

---

## Goal

Build the first real production Script Studio flow:

Episode
→ ConfirmedCreativePlanBinding
→ Script Studio Bootstrap
→ Script
→ ScriptVersion
→ Human Confirmation
→ ConfirmedScriptVersion
→ Storyboard Bootstrap

The result must extend the existing production spine.

It must not become an isolated AI writing tool.

---

## Primary Upstream

The authoritative upstream chain is:

Series
→ Episode
→ ConfirmedCreativePlanBinding
→ creator.script-studio.bootstrap-input.v1

Script Studio must consume the Episode-bound confirmed CreativePlan.

It must not independently reinterpret the episode from scratch.

---

## Upstream Lineage

The Script Studio input must preserve:

seriesRef

episodeRef

sourcePlanRef

sourcePlanSchemaVersion

sourcePlanVersion

ConfirmedCreativePlanBinding

The lineage must remain traceable in Script and ScriptVersion outputs.

---

## Script Studio Bootstrap

Accepted input contract:

creator.script-studio.bootstrap-input.v1

The bootstrap should directly expose the confirmed Episode creative context including:

storyDirection

scriptDraft

productionPlan.characters

productionPlan.scenes

storyboardPlan

visualStyle

productionPlan

Bootstrap itself must not invoke an AI Provider.

Provider call count for deterministic bootstrap must remain:

0

---

## Script Ownership

Script and ScriptVersion authoritative production facts must live behind an accepted stable domain/repository boundary.

Application / UI may orchestrate commands and presentation.

Application must not become the authoritative Script store.

Browser must not become the authoritative Script store.

Do not use:

localStorage

browser-only arrays

direct Application SQL

as authoritative production persistence.

---

## Script Identity

Required identity chain:

seriesRef
→ episodeRef
→ scriptRef
→ scriptVersionRef

A Script belongs to exactly one Episode.

Script title is not identity.

Episode number is not script identity.

---

## ScriptVersion Contract

Target schema:

creator.script-studio.script-version.v1

Minimum semantic content:

schemaVersion

scriptRef

scriptVersionRef

seriesRef

episodeRef

sourcePlanRef

sourcePlanSchemaVersion

sourcePlanVersion

versionNumber

title

logline

synopsis

targetDurationSec

scenes[]

Each scene should support:

scriptSceneRef

sceneNumber

heading

location

timeOfDay

characters[]

action

dialogue[]

narration[]

subtitleText[]

estimatedDurationSec

scenePurpose

continuityNotes[]

productionNotes[]

Dialogue items should support:

speaker

text

emotion

---

## Character Boundary

M4 Character Intelligence is not implemented yet.

Therefore M3 must not fabricate authoritative Character IDs.

Characters may currently remain:

characterName

or unresolved character requirements

derived from the confirmed CreativePlan.

M3 should preserve enough information for M4 to bind authoritative Character references later.

---

## Version Rule

ScriptVersion is immutable.

Never edit an existing historical ScriptVersion in place.

Expected pattern:

Script
├─ Version 1
├─ Version 2
├─ Version 3
└─ confirmedScriptVersionRef

AI generation creates a new ScriptVersion.

Manual edits create a new ScriptVersion.

Local AI rewrites create a new ScriptVersion.

Creating a new Draft Version must not automatically replace the confirmed version.

---

## Initial Script Generation

The user may explicitly run:

生成正式剧本

The generation path is:

Script Studio Application Service
→ existing V4 TextGenerationPort
→ configured text provider
→ ScriptVersion Candidate
→ local ScriptVersion validation

The provider may generate a candidate.

The provider must not:

- confirm the Script;
- advance Storyboard;
- create Project identity;
- create Asset identity;
- create Character authority;
- modify Episode lifecycle;
- approve rights;
- approve publication.

---

## DeepSeek Rule

DeepSeek may be used as the current text intelligence provider.

Do not create a second provider stack.

Use the existing V4 TextGenerationPort and provider adapter boundary.

Script generation must remain provider-neutral at the contract/domain level.

Do not expose DeepSeek configuration in Creator UI.

---

## Manual Editing

The first M3 version must support meaningful script editing.

At minimum:

title

synopsis

scene action

dialogue

narration

subtitle text

A successful manual edit creates a new ScriptVersion.

Previous ScriptVersions remain immutable.

---

## Local AI Rewrite

Support a minimal scene-level AI rewrite.

Example requests:

- make this scene more restrained;
- shorten the dialogue;
- strengthen the opening hook;
- make the emotional transition smoother.

The rewrite must operate on the selected Scene while preserving:

Episode context

confirmed CreativePlan constraints

current ScriptVersion context

Only the target scene should be intentionally rewritten.

The result creates a new ScriptVersion.

Do not regenerate the entire Episode production chain.

---

## Duration Rule

Script Studio must respect the Episode target duration.

For example:

30-second Episode

should produce Script scenes whose estimated duration is reasonably consistent with the target.

Local validation owns final acceptance of:

- duration > 0;
- scene numbers are continuous;
- scriptSceneRef values are unique;
- required fields exist;
- dialogue structure is valid;
- total estimated duration is reasonable.

The provider cannot bypass local validation.

---

## Confirmation Gate

AI generation success does not mean Script confirmation.

Script versions initially remain:

Draft

Only explicit user confirmation may update:

confirmedScriptVersionRef

The confirmation is a Script Production Confirmation.

It is not the global Approval Engine.

---

## Primary Downstream

The immediate next milestone is:

M4 — Series IP Bible + Character Intelligence

M3 must produce a confirmed ScriptVersion with complete lineage
so M4 can bind and validate:

- character identity
- character evolution state
- world rules
- relationship context
- timeline / continuity constraints
- IP consistency

M3 should also prepare the downstream contract:

creator.storyboard.bootstrap-input.v1

However, this contract is NOT yet authorized for direct Storyboard production.

The intended future chain is:

Confirmed ScriptVersion
→ M4 IP / Character Binding & Consistency Validation
→ Storyboard Bootstrap
→ M5 Storyboard

M5 must not bypass M4 when authoritative IP / Character bindings become available.

The required chain is:

Episode
→ Script
→ confirmedScriptVersionRef
→ confirmed ScriptVersion
→ Storyboard Bootstrap

Storyboard must not bypass Script Studio and consume the original AI Director plan as its authoritative production script.

---

## Storyboard Bootstrap

The future Storyboard Bootstrap must carry:

seriesRef

episodeRef

scriptRef

scriptVersionRef

scenes[]

Each scene must provide enough information for storyboard generation, including:

action

dialogue

narration

subtitle text

estimated duration

characters

The bootstrap must also preserve lineage:

sourcePlanRef

sourcePlanSchemaVersion

sourcePlanVersion

---

## Storyboard Gate

Draft ScriptVersion
→ Storyboard Bootstrap = REJECT

Confirmed ScriptVersion
→ Storyboard Bootstrap Candidate = PASS

But actual M5 Storyboard production must wait until
M4 IP / Character binding and consistency requirements are satisfied.

Do not automatically enter M4 or M5 after Script confirmation.

---

## Subtitle Boundary

M3 owns:

subtitle text / subtitle intent

M3 does not own final frame-accurate subtitle timing.

Do not fabricate precise SRT/ASS timing in M3.

Precise timing belongs to later Audio / Video / Timeline production stages.

---

## Persistence

Reuse the accepted repository/adapter separation established by M2.

Application must not directly access SQLite or SQL.

Local SQLite, if used, remains:

LOCAL DEVELOPMENT DURABLE ADAPTER

NOT PRODUCTION DATABASE

Script and ScriptVersion must survive:

browser refresh

server restart

according to the accepted local durable persistence contract.

Version history must also persist.

---

## Atomicity

At minimum:

Failed ScriptVersion write
must not update current/confirmed references.

Failed confirmation
must not create a partial confirmed state.

Failed AI generation
must not leave an empty ScriptVersion.

Failed manual edit
must not corrupt previous ScriptVersions.

Failed local rewrite
must not mutate the source ScriptVersion.

---

## UI Scope

Creator UI V2 remains the stable visual baseline.

M3 may add or activate a project-level:

剧本

workspace.

Do not add a new top-level navigation item.

The project navigation may contain:

故事
剧本
IP圣经
角色
场景
分镜
音频
时间线
预览
...

The Script Studio UI should support:

Episode context

story summary

scene list

current scene editor

action

dialogue

narration

subtitle text

version history

AI generation / rewrite

confirmation status

Do not redesign the entire Creator Workspace.

---

## Expected User Flow

Series
→ Episode
→ 剧本

First visit:

display the source AI Director / Episode context

Then:

生成正式剧本

Result:

Script v1
状态：待确认

The user may:

edit

rewrite a scene

save a new version

view versions

select a version

Finally:

确认此版本

Result:

confirmedScriptVersionRef

Then:

Storyboard Bootstrap becomes available.

Do not begin M5 Storyboard implementation.

---

## Content Quality Smoke

A real Script generation smoke should use the current 晚灯 Episode.

Check that the generated script:

- follows the confirmed Director Plan;
- does not obviously drift from the intended character;
- reasonably matches target duration;
- contains usable scenes;
- contains producible dialogue/narration where appropriate;
- does not invent major conflicting world rules.

This is a product usability smoke, not a final literary review.

---

## Required Integration Chain

The M3 integration gate must demonstrate:

M1 AI Director
→ Confirmed CreativePlan

M2 Series
→ Episode
→ ConfirmedCreativePlanBinding

M3 Script Studio Bootstrap
→ Script
→ ScriptVersion
→ Human Confirmation
→ confirmedScriptVersionRef

Then:

confirmed ScriptVersion
→ creator.storyboard.bootstrap-input.v1

This must be one traceable production chain.

---

## Testing Baseline

Accepted previous baseline:

M1 + M2 tests must remain passing.

M2 accepted test baseline:

238 / 238 PASS

M3 must not delete or weaken previous tests.

New M3 tests should cover at least:

Bootstrap

Script identity

ScriptVersion immutability

Version increments

AI generation success/failure

Schema validation

Manual edit creates version

Local rewrite creates version

Target scene isolation

Confirmation

confirmedScriptVersionRef persistence

Storyboard draft rejection

Storyboard confirmed acceptance

Lineage

Persistence refresh/restart

Rollback behavior

HTTP endpoints

Script page rendering

Version history

Secret isolation

No direct SQL from Application

Browser does not call provider directly

M1 regression

M2 regression

Preview / Export regression

---

## Live Gate

M3 requires at least one real text-provider Script generation flow:

Episode Confirmed Plan
→ Generate Script
→ ScriptVersion V1
→ Validator
→ Browser Render

Then:

manual edit
→ V2

Then:

local AI rewrite
→ V3

Then:

human confirmation
→ confirmedScriptVersionRef

Then:

Storyboard Bootstrap PASS

Do not continue into M5.

---

## Browser Gate

Real Chrome should validate at least:

1. Episode → Script Studio
2. Generating state
3. Script V1
4. Manual edit
5. New version
6. Local AI rewrite
7. Version history
8. Confirmed state
9. Refresh persistence
10. Server restart persistence
11. Storyboard bootstrap readiness

Expected:

Console errors = 0

Page errors = 0

Horizontal overflow = 0

No broken critical UI

---

## Security Gate

Before commit/push verify no:

API keys

`.env` secrets

Authorization values

passwords

tokens

private keys

sensitive provider responses

raw secret logs

Browser code must not contain provider secrets.

---

## Git Hard Gate

M3 is not complete until:

IMPLEMENTATION PASS

INTEGRATION PASS

REGRESSION TESTS PASS

DEEPSEEK / LIVE PROVIDER PASS

BROWSER PASS

PERSISTENCE PASS

SECRET SCAN PASS

git diff --check PASS

COMMIT PASS

GITHUB PUSH PASS

REMOTE SHA == LOCAL SHA

Required branch:

codex/creator-capability-phase3-script-studio

Expected commit message:

feat(creator): add script studio production flow

Codex must perform GitHub push and remote SHA verification.

The user must not be asked to perform the push manually.

---

## Do Not Enter

M4 — Series IP Bible + Character Intelligence

Do not implement M4 capabilities during M3.

Do not implement:

full Character Intelligence

Series-wide relationship graph

Series-wide foreshadowing system

Image generation

Video generation

Audio production

Timeline production

V3 Render

V4 batch orchestration

Series release center

Performance feedback

unless explicitly required to fix an M3 integration bug and approved by the Project Lead.

---

## Completion State

When every M3 gate passes:

update this file to:

Status:
FEATURE ACCEPTED CANDIDATE
AWAITING PROJECT LEAD ACCEPTANCE

Then STOP.

Do not update M4 to CURRENT.

Do not begin M4 automatically.

Wait for Project Lead acceptance.

---

## Completion Report

Report:

CURRENT MILESTONE:

BASE SHA:

BRANCH:

SCRIPT OWNER:

UPSTREAM CONNECTION:

BOOTSTRAP:

SCRIPT CONTRACT:

VERSIONING:

DEEPSEEK SCRIPT GENERATION:

MANUAL EDIT:

LOCAL AI REWRITE:

CONFIRMATION:

STORYBOARD BRIDGE:

REF / VERSION LINEAGE:

PERSISTENCE:

INTEGRATION:

BROWSER / LIVE:

TESTS:

SECRET SCAN:

COMMIT SHA:

PUSH:

REMOTE SHA:

LOCAL == REMOTE:

GIT STATUS:

REMAINING GAPS:

M3 STATUS:
