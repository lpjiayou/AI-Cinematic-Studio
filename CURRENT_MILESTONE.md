# AI Cinematic Studio — Current Execution State

> Document: CURRENT_MILESTONE.md
>
> Execution Mode: MANUAL
>
> Current Task: UI-R2 — Professional Workspace Layout Optimization
>
> Task Type: CROSS-CUTTING UI BASELINE OPTIMIZATION
>
> M6 Authorization: NOT AUTHORIZED

---

# 0. Canonical Baseline

Canonical Workspace:

D:\Codex使用\AI CINEMATIC STUDIO

Accepted Base:

8c3e4271662e1e02e963618ade3c29d6e9f91e89

Accepted Milestones:

M1 — AI Director Core — ACCEPTED

M2 — Series + Episode Foundation — ACCEPTED

M3 — Script Studio — ACCEPTED

M3-H — Script Candidate Robustness — ACCEPTED

Story Projection — ACCEPTED

UI-R1 — Enterprise Cinematic UI — ACCEPTED

M4 — Project Context Foundation — ACCEPTED

M5 — Series Planning + Series Director — ACCEPTED

M6 — Series IP Bible + Character Intelligence — NOT STARTED

---

# 1. Current Task

UI-R2 — Professional Workspace Layout Optimization

Status:

CURRENT

Purpose:

Optimize workspace space allocation across the existing Enterprise Creator UI
before M6 begins.

UI-R2 is NOT a new Domain milestone.

UI-R2 must not change:

- V2.3 architecture;
- Production Spine;
- Domain ownership;
- Project / Series / Episode contracts;
- M4 Project model;
- M5 Series Planning model;
- Provider architecture;
- persistence authority;
- Global information architecture;
- Enterprise Dark Cinematic visual baseline.

---

# 2. Core Objective

Prioritize the real production workspace over permanent navigation chrome.

Space priority:

Production Content
>
Object Navigator
>
Inspector
>
Project Navigator
>
Global Navigator

The user must receive maximum usable working space for:

- Script;
- IP Bible;
- Character;
- Storyboard;
- Shot;
- Timeline.

---

# 3. Layout Modes

UI-R2 establishes five reusable workspace modes.

## L1 — Management

Global Sidebar 240px
+
Main Workspace

Used by:

- 首页
- 项目
- 资产库
- 作品

Inspector appears only when required.

---

## L2 — Project Reading / Management

Global Sidebar 72px
+
Project Navigator about 220px
+
Main Workspace
+
Optional Inspector about 300px

Used by:

- 项目概览
- 系列规划
- 分集
- 故事

---

## L3 — Professional Editor

Global Sidebar 72px
+
Object Navigator about 200–220px
+
Main Editor
+
Inspector about 320px
+
Optional Bottom Drawer

Used by:

- Script Studio
- IP Bible
- Character Intelligence

Project Navigator becomes collapsible / drawer-based.

---

## L4 — Visual Canvas

Global Sidebar 72px
+
Object Navigator about 180–220px
+
Canvas
+
Inspector about 320px

Used by:

- Storyboard
- Shot
- Scene

Project Navigator must not permanently consume another column.

---

## L5 — Timeline

Global Sidebar 72px
+
Media / Track Navigator about 200px
+
Preview + Timeline Workspace
+
Inspector about 300px

Timeline receives the highest horizontal workspace priority.

---

# 4. AI Director Layout

Move the permanent left-side Creative Input form
into a top Creative Parameter area.

Default state:

compact parameter summary.

Display:

- 主题
- 类型
- 目标用户
- 时长
- 发布平台
- 视觉风格
- 角色设定

Actions:

- 编辑参数
- 重新生成

Expanded state:

2–3 column parameter grid.

The Director Result Workspace must receive the released horizontal space.

Do not change AI Director Domain behavior.

Do not change M1 Provider flow.

---

# 5. Global Sidebar Behavior

Global management pages:

default width about 240px.

Inside Project Workspace / Professional Editor:

default collapsed width about 72px.

User may expand/collapse manually.

Collapse is presentation state only.

It must not become a Domain fact.

No empty-width fake collapse is allowed.

---

# 6. Project Navigator

Project Navigator target width:

about 220px.

Use collapsible groups:

概览

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

Current group may remain expanded.

Other groups may collapse.

Avoid one permanently long scrolling menu.

“分集工作台” must not become a duplicate permanent navigation concept.

Episode Workspace may remain as the Episode overview route.

Maintain route compatibility.

---

# 7. Compact Context Bar

Replace the current database-like multi-cell context header
with a compact production context bar.

Target height:

about 48–52px.

Example:

晚灯系列制作 › 晚灯 › 第1集 › 剧本

v3 · 已确认

Detailed Refs / Lineage belong in Inspector.

Context Bar must still use real:

- projectRef
- seriesRef
- episodeRef
- object/version context

internally.

---

# 8. Inspector Rules

Inspector must be collapsible.

Management pages:

hidden by default unless an object is selected.

Reading pages:

optional.

Professional Editors:

visible when space allows.

At smaller widths:

collapsed by default.

Suggested widths:

300–320px.

Inspector must not leave a large empty permanent column
when it contains little information.

---

# 9. Story Layout

Story becomes a reading-first workspace.

Main Story Canvas receives priority.

Inspector contains:

- 来源
- 版本
- Episode
- CreativePlan
- Lineage

Story remains the existing accepted Story Projection.

Provider calls remain 0.

No new Story authority.

---

# 10. Script Studio Layout

Script Studio becomes a real Professional Editor layout.

Global Sidebar:
72px

Scene Navigator:
about 220px

Script Editor:
flex

Inspector:
about 320px

Bottom Drawer:
AI / Version / Jobs / Activity

Project Navigator must not permanently occupy an additional full column.

Preserve all real M3 behaviors:

- Generate
- Validate
- Controlled Repair
- Manual Edit
- Scene Rewrite
- Immutable Versions
- Confirmation
- Persistence

---

# 11. Storyboard / Shot / Scene Reservation

Storyboard and Shot must already receive their long-term canvas layout.

Storyboard:

Scene / Shot Navigator
+
Storyboard Canvas
+
Inspector

Shot:

Shot Navigator
+
Preview / Canvas
+
Inspector

Scene:

Scene Navigator
+
Scene Workspace
+
Inspector

Do not implement M8 Domain.

Only optimize the existing shell layout.

---

# 12. Timeline Reservation

Timeline must receive maximum horizontal priority.

Project Navigator should not remain permanently visible
inside Timeline editing mode.

Layout:

Media / Track Navigator
+
Preview Monitor
+
Timeline
+
Inspector

Reserve tracks for future:

- Video
- Dialogue
- Ambience
- BGM
- SFX
- Subtitle

Do not implement M13 Render capability.

---

# 13. Creation Center Responsive Fix

Fix the current card layout where Chinese text is compressed
into near-vertical character wrapping.

Recommended responsive behavior:

large desktop:
3 columns when card width remains usable

medium desktop:
2 columns

narrow desktop:
1 column

Use a minimum useful card width.

Do not force 3 columns when content becomes unreadable.

Ensure normal Chinese text flow.

---

# 14. Pages To Preserve

The following current management layouts are generally accepted
and should not be unnecessarily redesigned:

- 首页
- 项目列表
- 全局资产库
- 作品

Only shared shell/responsive corrections are allowed.

---

# 15. UI Architecture Hard Rule

UI-R2 must reuse:

- current Enterprise Dark Cinematic visual baseline;
- current Global Navigation;
- current Project IA;
- current routes where possible;
- one Creator UI;
- current Creator HTTP Runtime.

Do not create another frontend.

Do not perform framework migration.

Do not create a second static UI.

---

# 16. Responsive Gate

Verify at minimum:

1920×1080

1600×900

1366×768

1280×800

1024 width

Requirements:

- no horizontal overflow;
- no broken text wrapping;
- no unusably narrow main editor;
- navigator and inspector collapse correctly;
- current object remains visible;
- primary actions remain reachable.

---

# 17. Real Capability Regression

Must preserve real:

M1 AI Director

M2 Series / Episode

M3 Script Studio

Story Projection

M4 Project Context

M5 Series Planning / Series Director

No accepted capability may become a shell or placeholder.

---

# 18. Browser Gate

Use real:

http://127.0.0.1:8765/

Accepted browser methods:

Chrome
or
Chrome Headless + DevTools CDP

Do not use file:// as final evidence.

Verify:

Console errors = 0

Page errors = 0

Unexpected HTTP errors = 0

Horizontal overflow = 0

---

# 19. Key Visual Evidence

Provide HTTP Runtime evidence for:

1. AI Director compact parameter mode
2. AI Director expanded parameter mode
3. Project Overview
4. Story
5. Script Studio
6. Series Planning
7. Storyboard shell
8. Shot shell
9. Timeline shell
10. Creation Center
11. Asset Library
12. Works

---

# 20. Required Gates

UI LAYOUT IMPLEMENTATION PASS

AI DIRECTOR SPACE OPTIMIZATION PASS

GLOBAL SIDEBAR PASS

PROJECT NAVIGATOR PASS

CONTEXT BAR PASS

INSPECTOR PASS

STORY PASS

SCRIPT EDITOR PASS

STORYBOARD RESERVATION PASS

SHOT RESERVATION PASS

TIMELINE RESERVATION PASS

CREATION CENTER RESPONSIVE PASS

M1 REGRESSION PASS

M2 REGRESSION PASS

M3 REGRESSION PASS

STORY REGRESSION PASS

M4 REGRESSION PASS

M5 REGRESSION PASS

BROWSER PASS

RESPONSIVE PASS

ARCHITECTURE PASS

SECRET SCAN PASS

git diff --check PASS

GIT COMMIT PASS

GITHUB PUSH PASS

REMOTE SHA == LOCAL SHA

GIT STATUS CLEAN

---

# 21. Git Checkpoint

Suggested branch:

codex/creator-ui-r2-workspace-layout

Suggested implementation commit:

feat(creator): optimize professional workspace layouts

UI-R2 must have a Remote-Verified checkpoint.

---

# 22. Stop Rule

After all UI-R2 gates PASS:

report:

UI-R2
FEATURE ACCEPTED CANDIDATE
AWAITING PROJECT LEAD ACCEPTANCE

STOP.

Do NOT enter M6.

M6 remains:

NOT STARTED

until Project Lead final acceptance.

---

# 23. Final Report

UI-R2 BASE SHA:

BRANCH:

GLOBAL SIDEBAR:

PROJECT NAVIGATOR:

CONTEXT BAR:

AI DIRECTOR:

STORY:

SCRIPT STUDIO:

SERIES PLANNING:

STORYBOARD SHELL:

SHOT SHELL:

TIMELINE SHELL:

CREATION CENTER:

INSPECTOR:

RESPONSIVE:

M1 REGRESSION:

M2 REGRESSION:

M3 REGRESSION:

STORY REGRESSION:

M4 REGRESSION:

M5 REGRESSION:

TESTS:

BROWSER:

ARCHITECTURE:

SECRET SCAN:

DIFF CHECK:

COMMIT SHA:

PUSH:

REMOTE SHA:

LOCAL == REMOTE:

GIT STATUS:

M6 ENTERED:

NO

UI-R2 STATUS:

FEATURE ACCEPTED CANDIDATE
/
AWAITING PROJECT LEAD ACCEPTANCE

STOP.

# End of CURRENT_MILESTONE.md