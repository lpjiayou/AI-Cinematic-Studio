# AI Cinematic Studio — UI Master Plan

> Document: `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`
>
> Status: `UI MASTER / UI-R1 ACCEPTED HISTORY / ADR-0001 ACCEPTED / COMMERCIAL FRONTEND SEPARATED`
>
> Version: `v1.2`
>
> Date: `2026-08-13`
>
> UI-R1 Historical System Base:
> `1cc768ee9db4b52a916c94ae6af7b95b811f1cb2`
>
> UI-R1 Accepted SHA:
> `c9536fc0c745d0bf9e9c3eb543f4ab6c0566798a`
>
> Revision: M6-P3-G1 Core-only authorization synchronization; product IA and visual baseline unchanged.
>
> Scope:
> AI Cinematic Studio Creator / Project Workspace / Production Editors /
> Enterprise Management 的长期 UI、UX、Information Architecture 基线。

---

# 0. UI 总目标

## 0.1 UI Source-of-Truth Repository

ADR-0001 已接受，PRE-M6-RB1.1 与 RB1.2 已形成 remote-verified 重基线。
AI Cinematic Studio 继续只有一个客户产品 UI，其源码真源是独立仓库
`AI-Cinematic-Studio-Frontend`，不是 Core 仓库。

本文件继续定义跨仓库的产品体验、信息架构、视觉与交互基线。已接受边界
保留 Core 对 Creator Server Runtime、Creator Public HTTP/API、Creator
Application 和 V5/V4/V3 等下层能力的责任；Core 不再承载第二套 Commercial
SaaS 客户页面。

该边界要求 Frontend Experience Adapter 只通过公开 Creator HTTP/API 消费
Core；禁止 Frontend 直接导入 Core 源码、访问 Creator Application、Domain、
SQL、Persistence、Provider、private V5 Adapter、GPU、Worker 或 ComfyUI。

AI Cinematic Studio UI 不得演化成：

“AI 功能菜单集合”。

最终 UI 必须表现为：

“以 Project 为中心的专业 AI 影视生产工作站”。

核心结构：

Workspace
↓
Global Product Shell
↓
Project Workspace
↓
Production Stage
↓
Production Object
↓
Editor / Inspector / Version / Lineage / Job

未来新增能力原则上只能：

1. 点亮已经规划的区域；
2. 增强已经规划的 Editor；
3. 增加现有 Domain 对象的 Detail View。

不得因为新增一个模型或功能，
就在 Global Navigation 中新增一个一级菜单。

---

# 1. UI 与系统架构关系

UI Architecture 必须映射真实 Domain Architecture。

固定原则：

UI SHALL mirror Domain Architecture.

Project-first UI 必须由真实：

projectRef
seriesRef
episodeRef

驱动。

禁止：

前端通过名称、复制 JSON、URL 文本或 Mock 数据，
模拟实际上不存在的 Domain 关系。

UI 不拥有正式生产事实。

---

# 2. UI 权威顺序

UI 相关决策按照：

1. 适用的 `AGENTS.override.md`
2. 最近层级的嵌套 `AGENTS.md`
3. 根目录 `AGENTS.md`
4. Accepted ADR 与强制治理规则
5. `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`
6. `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`，仅在 UI、UX、Frontend 范围内生效
7. `CURRENT_MILESTONE.md`，仅控制当前任务、门禁和执行状态
8. Accepted/remote-verified Git evidence，仅证明实现事实，不得自行改变架构
9. Historical、superseded、archived evidence

执行。

聊天中的临时 UI 想法不能直接改变产品结构。

PRE-M6 严格路线为：

`PRE-M6-RB1.1 Source-of-Truth Rebaseline`
→ `PRE-M6-RB1.2 Legacy UI Decommission`
→ `PRE-M6-RB1.3 Full Core Current-State Audit`
→ `Architecture Review`
→ `M6 Preconditions`
→ `M6-P1`

PRE-M6-RB1.1、RB1.2 与 RB1.3 均已关闭。M6-P0/P1 与 bounded M6-P2 已 Owner
Accepted；`c524486c05c21b270a7dd75e89fae4312430736a` 的 M6-P3-G0 架构提案已由
Project Lead 与 Architecture Owner 接受为规范架构，但未授予任何实现权限。
原 G1 `0c283eb653e74784301620bdaf64bf451bb687dd` 保持历史 `REVISION REQUIRED /
NOT OWNER ACCEPTED`；修正后的 G1-R1 已在
`d44f471c644e319bb4a5bf73707c3274ecbaa426` 获得 Owner Acceptance。B1 候选
`8449b521c96bb8340806ecda8649698f4771914a` 已远端验证但 Owner Review 判定
`REVISION REQUIRED`。B1-R1 Core-only 有界修订的 8 路径治理检查点已在
`716b4d298173f8123cafd93114dfc67339943ff3` 远端验证；一个生产与一个测试路径的
技术提交 `5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` 已通过 SQLite `30/30`、
原 B1 `174/174`、完整 Core `449/449` 与 AST `63/63`，并于 `2026-08-14`
获得 Owner Acceptance。该 Core-only 结论不改变 Frontend 产品 IA 或视觉基线。

---

## 2.1 Current Milestone Status Synchronization

以下是当前治理状态，不是 UI-R1 接受时点的 historical snapshot：

- M4 — Project Context Foundation：`ACCEPTED`；implementation evidence：
  `4ec5de7273076d3b4f66272b6a4f0e3eecd89073`；
- M5 — Series Planning + Series Director：`ACCEPTED`；implementation evidence：
  `8c3e4271662e1e02e963618ade3c29d6e9f91e89`；
- M4/M5 Accepted 状态的既有控制证据：
  `55813b26be76a3476820dd1f638ac2f4561da448`；
- M6-P0/P1 — Series IP Bible + Character Intelligence：
  `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860`；
- M6-P2-G1：`OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
  8227c6c616140824fd70de920dc6fcf459bb734d`；
- M6-P3-G0：`OWNER ACCEPTED / COMPLETE AS GOVERNANCE-ARCHITECTURE / NO
  IMPLEMENTATION AUTHORITY`；
- ADR-0005 / M6 Consumer Contract：`ACCEPTED AS ARCHITECTURE / B1 OWNER ACCEPTED
  THROUGH B1-R1 / G1 BOUNDED CORE IMPLEMENTATION AUTHORIZED`；
- M6-P3-B1 EpisodePlanItemBinding：`ORIGINAL CANDIDATE AT
  8449b521c96bb8340806ecda8649698f4771914a REVISION REQUIRED / CORRECTED AND
  OWNER ACCEPTED THROUGH B1-R1 AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7`；
- M6-P3-B1 Scope：`8 GOVERNANCE → 6 PRODUCTION + 9 TESTS → REMOTE VERIFY →
  STOP FOR OWNER REVIEW`；
- M6-P3-B1 Version policy：`INITIAL V1 / V1→V1 / EXPLICIT V1→V2 / V2→V2 /
  V2→V1 FORBIDDEN / UNBIND VIA NEW V2`；
- M6-P3-B1 Public/UI boundary：`CORE-ONLY create_episode_plan_item_binding_version /
  NO ROUTE, HANDLER, EXTERNAL DTO SOURCE OR FRONTEND CHANGE`；
- M6-P3-B1 Owner HTTP clarification：`EXISTING WORKSPACE VERSIONS V2 RESPONSE PASSES
  THROUGH episodePlanItemBindings / NO OTHER HTTP CONTRACT EXPANSION`；
- M6-P3-B1-F001：`CLOSED BY OWNER-ACCEPTED B1-R1 / SQLITE SAME-PROJECT
  CROSS-SERIES FALSE DEPENDENCY`；
- M6-P3-B1-R1：`OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
  5c656992d9fade3683b70e3c57f8b8ba7d26c7f7 / SQLITE 30/30 / ORIGINAL B1
  174/174 / FULL CORE 449/449 / AST 63/63`；
- M6-P3-B1-R1 UI boundary：`CORE SQLITE READ + CORE INTEGRATION TEST ONLY / NO ROUTE,
  HANDLER, DTO OR FRONTEND CHANGE`；
- ADR-0006 / V5 Text Generation Capability：`ACCEPTED FOR BOUNDED G1`；
- ACS-ARCH-R1-V5-TEXT-GENERATION-G0：`COMPLETE / REMOTE-VERIFIED AT
  92d1f3ac9e08c71458af04514baa659555fc55a7`；
- ACS-ARCH-R1-V5-TEXT-GENERATION-G1：`REMOTE-VERIFIED CANDIDATE AT
  0c283eb653e74784301620bdaf64bf451bb687dd / REVISION REQUIRED / NOT OWNER
  ACCEPTED / SUPERSEDED BY G1-R1`；
- ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1：`OWNER ACCEPTED / COMPLETE /
  REMOTE-VERIFIED AT d44f471c644e319bb4a5bf73707c3274ecbaa426`；
- Frontend M6 activation：`FROZEN / NOT AUTHORIZED`；
- M6-P3-G1：`BOUNDED CORE-ONLY IMPLEMENTATION AUTHORIZED / GOVERNANCE REMOTE
  VERIFICATION REQUIRED BEFORE CODE / NO FRONTEND AUTHORITY / NOT OWNER ACCEPTED`；
- M6-P3 after G1 / M6-P4+：`NOT AUTHORIZED / NOT STARTED`；
- M7-M19：`NOT STARTED / NOT AUTHORIZED`。

Milestone acceptance、implementation evidence、remote verification、UI/Product
acceptance 和 current task status 是不同语义。M4/M5 的 Accepted 状态本身并未
授权 ADR-0001、Legacy UI 退役或 M6；这些事项后来通过各自独立治理 checkpoint
接受。Cross-repository Gate C 与 Frontend M6 activation 仍未授权。

---

# 3. Creator Enterprise Dark Cinematic Visual Baseline

Revision note:

Enterprise Dark Cinematic Visual Baseline integrated after UI-R1 acceptance.

UI-R1 接受记录：

- Task: `ACS-CREATOR-UI-R1-ENTERPRISE-REBASELINE-001`；
- System Accepted Base: `1cc768ee9db4b52a916c94ae6af7b95b811f1cb2`；
- UI-R1 Accepted SHA: `c9536fc0c745d0bf9e9c3eb543f4ab6c0566798a`；
- Status: `FEATURE ACCEPTED`；
- M4 at the historical UI-R1 acceptance point: `PAUSED / NOT STARTED`；当前状态：
  `ACCEPTED`。

UI-R2A 状态分层：

- Product acceptance status：`NO SEPARATE ACCEPTANCE EVIDENCE / CANDIDATE`；
- Remote verification status：`PASS`，pre-rebaseline HEAD
  `602a78fe68fc5c69ecc31d9436ee166f5dff8a64`；
- Active architecture status：`SUPERSEDED AS CURRENT TASK`。

Enterprise Dark Cinematic Workstation 是当前唯一 Creator Visual Baseline，取代此前“管理页面偏明亮、专业编辑工作区偏深色”的双重视觉方向。Light Mode 若未来需要，必须作为独立主题能力处理，不得形成第二套 Creator UI。

原 Creator UI V2 的长期产品原则继续保留：

- 中文优先；
- Professional SaaS；
- Enterprise Production Software；
- Industrial / Cinematic；
- 清晰层级；
- 充足留白；
- 低噪音；
- Cyan / Blue-Green 核心强调体系；
- 减少装饰性渐变；
- 控制卡片数量；
- 强调状态、数据、版本和生产对象。

冻结视觉原则：

- Professional AI Film Production Platform；
- Enterprise Cinematic Workstation；
- Industrial / Precise / Low Noise / Production-oriented；
- 90% 深色 Neutral、8% Teal、2% Amber / Purple 氛围；
- 中文优先，不在产品视图暴露 GPU、Model、Queue、Worker、Server 或 Debug 信息；
- 普通 Card 依靠 Surface + Border 分层，不使用重阴影；
- Gradient / Glow 只用于 AI Candidate、Focus、运行中任务、Timeline Playhead 或极少数关键 CTA。

冻结颜色 Token：

```css
--acs-bg: #0F1318;
--acs-sidebar: #161C23;
--acs-surface: #1E252D;
--acs-surface-deep: #11171D;
--acs-surface-hover: #252E37;
--acs-surface-selected: #193B39;
--acs-border: #2C353F;
--acs-border-strong: #3A4652;
--acs-primary: #22D1B6;
--acs-accent: #E8A868;
--acs-text-primary: #F4F7FA;
--acs-text-secondary: #CBD5E1;
--acs-text-muted: #8894A3;
--acs-danger: #E55959;
--acs-success: #36D399;
--acs-info: #5DADE2;
--acs-overlay: rgba(5, 8, 12, 0.72);
--acs-primary-soft: rgba(34, 209, 182, 0.12);
--acs-accent-soft: rgba(232, 168, 104, 0.12);
--acs-danger-soft: rgba(229, 89, 89, 0.12);
--acs-success-soft: rgba(54, 211, 153, 0.12);
```

Dark Form System：

- Input、Select、Textarea、Segmented Option 和 selectable Card 使用深色 Surface；
- Normal 使用 `--acs-surface-deep` + `--acs-border`；
- Hover 使用 `--acs-surface-hover` + `--acs-border-strong`；
- Selected 使用 `--acs-surface-selected` + `--acs-primary`；
- Focus / Selected ring 仅允许使用克制的 `--acs-primary-soft`；
- Selected 状态禁止回退到白色或浅色 Surface。

冻结 Global Shell：

- Global Sidebar: `240px → 72px` collapse；
- Main Workspace: `flex: 1`；
- Optional Project Navigator；
- Inspector: `340px → 0` collapse；
- Optional Bottom Drawer；
- Workflow Action Bar；
- Top Bar 包含 Breadcrumb、Search / Command、Jobs、Notifications、Help、User / Workspace；
- Global Navigation 固定为：首页、AI导演、项目、资产库、创作中心、作品。

冻结 Project Shell：

- Project Context Bar 显示 Project、Series、Episode、Stage、Object、Version；
- 无真实 Project Context 时使用 Context-null Shell，不得创建虚假 `projectRef`；
- Navigator 固定为概览、策划、内容、制作、后期、交付六组；
- Editor Framework 固定支持 Script、Bible、Storyboard、Shot、Timeline；
- Inspector 只展示当前对象、状态、版本、来源和影响；
- Bottom Drawer 承载 Version、Job、Activity；
- 专业 Editor 使用统一暗色工作区、对象导航、主编辑区、Inspector、Version / Job / Activity Drawer 和 Workflow Action Bar；
- M4–M19 原则上只激活既有壳层，不再重做全局 IA、Project Shell 或 Editor 框架。

ADR-0001 与 PRE-M6-RB1.1 remote-verified 重基线已经接受以下运行时与验收规则：

- ONE CREATOR UI = 独立 `AI-Cinematic-Studio-Frontend` 仓库中的客户体验层；
- Frontend Experience Adapter 属于 Frontend，且只能通过 Creator Public
  HTTP/API 连接真实 Creator Server Runtime；
- UI 源码不需要且不得继续以第二套商业产品形式保存在 Core 仓库；
- Frontend 最终 UI 证据必须来自其真实 HTTP Runtime；
- `file://` 仅可用于临时视觉检查，不得作为最终 Browser、Live、Integration 或视觉验收证据；
- UI Shell 不得虚构尚未存在的 Domain fact、Ref、Version、Lineage、Job 或生产状态；
- 已接受的 M1 / M2 / M3 能力必须在当前 Shell 中保持真实，不得退化为静态 Demo 或“即将上线”。

完整跨仓依赖链为：

`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

Frontend 不得直接访问 Creator Application、Domain、SQL、Persistence、Provider、
private V5、GPU、Worker 或 ComfyUI。Core 不重新建立客户 Commercial UI；两个
仓库不共享客户 UI 源码。

验收门禁拆分为：

- Gate A — Frontend Experience Gate：由独立 Frontend 仓库负责 build、browser、responsive、accessibility、visual 与客户流程；
- Gate B — Core HTTP Runtime Gate：由 Core 负责 Creator Server、公开 API、Application、授权、租户/Workspace、持久化、幂等、集成与错误合同；
- Gate C — Cross-Repo Integration Gate：未来验证
  `Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`；
  当前未实现，不允许共享源码集成。

Core 中 `apps/creator-workspace-mvp` 的历史客户浏览器 UI 已通过
PRE-M6-RB1.2 完成受控退役，不是新的 UI 真源。下划线路径
`apps/creator_workspace_mvp` 继续保留 Creator Server/API/Application runtime，
不得与已退役客户 UI 路径混淆。

UI-R1 接受后，后续重点继续是稳定 Information Architecture、点亮真实能力和提升工作流效率，而不是无业务原因的整体换肤。

---

# 4. UI 三层结构

整个产品长期只存在三个主要 UI 层级。

## Level 1 — Global Product Shell

负责：

Workspace 范围管理和入口。

## Level 2 — Project Workspace

负责：

一个 Project 内完整影视生产。

## Level 3 — Production Editor

负责：

Script / Bible / Storyboard / Shot / Asset / Timeline 等专业对象编辑。

不得把 Level 3 的功能不断提升成 Global Navigation。

---

# 5. Global Product Shell

全局一级导航长期冻结为：

首页

AI导演

项目

资产库

创作中心

作品

原则上 M4–M19 不增加一级导航。

---

# 6. Global Header

Global Header 长期结构：

左侧：

AI Cinematic Studio
Workspace Switcher

中央：

可选 Global Search / Command

右侧：

任务
通知
帮助
用户 / Workspace Menu

Workspace Menu 后续承载：

工作空间设置
团队成员
权限
模型与算力
存储
安全
审计
账单
集成

这些 Enterprise 功能不得污染创作一级导航。

---

# 7. 首页 Dashboard

首页不是 Landing Page。

是：

Production Command Center。

主要区域长期规划：

继续制作

最近项目

待处理

待审批

失败任务

最近完成

生产状态

资源 / Compute 状态

最近活动

示意：

继续制作

穿越大唐
第01集
当前阶段：剧本已确认
下一步：一致性检查

[继续制作]

---

待处理

第03集
Consistency BLOCK

[查看]

---

最近完成

晚灯 · Episode 001
Script v4 已确认

首页最重要动作：

+ 新建项目

---

# 8. AI 导演 — Global Entry

Global AI Director：

是 Creative Discovery Entry。

不是 Production Root。

用户可以输入：

“我要做一个100集穿越爽剧。”

AI Director 可以：

理解创意
形成候选方案
推荐项目类型

但进入正式生产前必须：

创建 Project

或

加入已有 Project。

正式 CreativePlan 不允许长期成为 Project 外孤儿对象。

---

# 9. 项目 — Global Project Center

“项目”是整个产品最重要的一级管理模块。

页面长期支持：

所有项目
最近项目
进行中
暂停
完成
归档

项目卡片长期结构：

Project Name

Project Type

Content Profile

Production Status

Series / Episode Progress

Current Stage

Warnings / Blocks

Last Updated

Continue Action

例如：

穿越大唐

系列短剧
100集计划
9:16 · 60秒

当前：
Episode 001

阶段：
剧本制作

进度：
1 / 100 Production Started

[继续制作]

---

# 10. 新建项目

正式生产入口必须统一为：

新建项目。

第一步：

选择项目类型。

长期支持：

系列短剧

单条视频

商品视频

品牌影片

其他影视项目

---

系列短剧示例：

项目名称：
穿越大唐

项目类型：
系列短剧

内容类型：
穿越 / 古装 / 爽剧

计划集数：
100

默认单集时长：
60秒

画幅：
9:16

目标平台：

Content Profile：

创建后：

生成 projectRef

然后进入 Project Workspace。

---

# 11. Project Workspace 顶层 IA

所有 Project 长期使用统一 Workspace Shell。

Project Workspace 顶层导航固定为：

概览

策划

内容

制作

后期

交付

项目设置不进入主要生产导航。

通过：

Project Menu / Gear

进入。

---

# 12. 为什么使用“内容”而不是固定“分集”

Project Type 不只有 Series。

所以 Project Workspace 顶层不能永久写死：

“分集”。

统一使用：

内容

对于 Series Project：

内容
→ 分集列表
→ Episode Workspace

对于 Standalone Project：

内容
→ Story / Script

对于 Product Video：

内容
→ Product Narrative / Script

因此：

顶层 IA 保持稳定，

Project Type 决定内部表现。

---

# 13. Project Context Bar

进入任何 Project 后永久显示 Project Context Bar。

示意：

穿越大唐

系列短剧 · 100集 · 9:16

Series:
穿越大唐

Episode:
第01集

状态：
制作中

Breadcrumb：

Project
/
Series
/
Episode
/
Current Object

例如：

穿越大唐
/
第01集
/
剧本
/
v4

后台必须由真实：

projectRef
seriesRef
episodeRef

驱动。

---

# 14. Project Overview

概览是项目 Command Center。

长期区域：

Project Summary

Production Stage

Current Episode

Next Action

Blocks / Warnings

Recent Versions

Recent Production Jobs

Recent Activity

Series Progress

Master Status

Cost / Compute
（后期启用）

最核心元素：

NEXT ACTION

例如：

第01集
剧本已确认

下一步：
执行 IP / Character 一致性验证

[继续制作]

系统必须尽量告诉用户：

“现在应该做什么”。

而不是让用户自己在20个工具中寻找下一步。

---

# 15. Project Lifecycle Navigation

Project 内生产阶段固定为：

策划
↓
内容
↓
制作
↓
后期
↓
交付

这是影视生命周期导航。

不是技术模块导航。

---

# 16. 策划 Planning

Series Project 长期规划：

策划
├── AI导演
├── 系列规划
├── IP圣经
├── 角色
└── 世界与连续性

---

# 17. Project AI Director

进入 Project 后：

AI Director 自动处于当前 Project Context。

Series Project 支持：

系列导演

分集导演

两者使用同一个 AI Director Capability。

不是两个系统。

---

# 18. 系列规划 Series Planning

负责：

Series Concept

Main Arc

Sub Arc

Character Arc Intent

Episode Plan

Season / Chapter

Foreshadowing Plan

Narrative Rhythm

对于100集项目：

可以显示100个：

Episode Plan Item。

但是必须区分：

PLANNED EPISODE

与：

CREATED EPISODE。

UI 不得把 Episode Plan Item 假装成已经创建的 Domain Episode。

---

# 19. Series Planning UI

推荐企业级布局：

左侧：

Arc / Chapter Tree

中央：

Series Planning Board

右侧：

Inspector

例如：

ARC 01
EP01–20
求生

ARC 02
EP21–50
建立势力

ARC 03
EP51–80
朝堂冲突

ARC 04
EP81–100
最终选择

Episode Plan 可以：

列表
表格
Timeline

切换。

---

# 20. IP Bible UI

IP Bible 是专业结构化工作区。

布局：

左侧：

Bible Sections

World
Characters
Relationships
Timeline
Continuity
Forbidden Rules
Style

中央：

当前规则 / 内容编辑区

右侧：

Inspector
Version
Source
Lineage

顶部：

SeriesBible vN

状态：

Draft
Candidate
Confirmed
Stale

---

# 21. Character Intelligence UI

角色页面不是普通“角色卡片库”。

M6 Character Intelligence 的规范范围至少包含：background、motivation、belief、
conflict、goal、personality、behavior rules、dialogue rules、forbidden behavior、
visual identity rules、`CharacterState`、`RelationshipContext`、timeline and
continuity。

必须支持：

Character Identity

Background

Motivation

Belief

Conflict

Goal

Personality

Behavior Rules

Dialogue Rules

Forbidden Behavior

Character State

Character Arc

Relationship

Visual Identity

Visual Identity Rules

Voice Identity

Continuity

`RelationshipContext`

Timeline and Continuity

M6 边界：`M6 ≠ V5 Identity Lock`。M6 不实现 M7、GPU Render、ComfyUI、
Worker 或跨仓 UI；M6-P0/P1 与 bounded M6-P2 已 Owner Accepted。M6-P3-G0 的
Core 内部 consumer contract 已作为架构规范接受，其 consumer 行为仍未实施且不
授予 Public API、G1 或任何 UI 激活权限。B1 仅获 Core-only
EpisodePlanItemBinding 有界实现授权，
不得新增或修改 HTTP route、handler、外部 DTO 源文件或 Frontend。Owner 明确
允许既有 HTTP workspace versions 的 v2 响应透传 `episodePlanItemBindings`；这不
构成 UI 激活，且不得扩大其他 HTTP contract。已接受的 V5 Text Generation 修复也
不改变任何 UI/UX/Frontend contract；Frontend 仍为
`FROZEN / NOT AUTHORIZED`。

示意：

李明

characterRef: ...

当前 Episode：
EP30

Resolved State：
建立势力阶段

State Timeline：

EP01–20
求生

EP21–50
建立势力

EP51–80
权力冲突

EP81–100
最终选择

不能通过创建多个同名角色表达角色成长。

---

# 22. 内容 Content

Series Project：

内容
├── 分集列表
└── Episode Workspace

Episode Workspace：

故事
剧本
一致性
生产状态

以后 Storyboard 不放这里。

Storyboard 属于：

制作。

---

# 23. Episode List

Episode List 必须支持大规模 Series。

至少规划：

Episode Number

Title

Plan State

Created State

Story State

Script State

Consistency State

Production State

Master State

Blocked State

支持：

Filter
Search
Status
Arc
Batch selection
（Batch 后期启用）

100集不得通过100个巨大 Card 实现。

使用：

Table / Dense List

为主。

---

# 24. Episode Workspace Header

进入 Episode 后固定显示：

Episode 001

Title

Episode Status

Current Production Stage

Applicable Bible Version

Current Script Version

Consistency Status

Next Action

---

# 25. Story

Story 不拥有新的 Authoritative Domain。

Story 页面继续使用：

Episode
→ ConfirmedCreativePlanBinding
→ sourcePlan
→ creator.story-view.v1

展示：

Title

Logline

Theme

Target Emotion

Synopsis

Key Beats

Narrative Structure

Character Requirements

Scene Requirements

Production Context

Story 页面必须显示：

来源：

AI导演方案 vN

并可以进入：

剧本工作台。

---

# 26. Script Studio

Script Studio 使用标准 Professional Editor。

布局：

左侧：

Scene Navigator

中央：

Script Editor

右侧：

Inspector

底部：

AI / Job / Version Drawer

顶部：

Script Name

Current Version

Confirmation Status

Consistency Status

Actions

---

Script Studio 必须支持：

Version History

AI Generate

Manual Edit

Scene Rewrite

Compare

Confirm Version

Source Lineage

---

确认按钮必须明确：

确认 Script vN

确认后形成：

confirmedScriptVersionRef。

---

# 27. Consistency UI

Consistency 不应该只是一个绿色 PASS Badge。

页面必须展示：

Overall Status

PASS
WARN
BLOCK
STALE

Findings

Rule Source

Affected Scene

Evidence

Suggested Fix

Bible Version

Character State

Script Version

用户可以：

返回 Script Studio 修复

生成新 ScriptVersion

重新验证

不得直接覆盖旧 ScriptVersion。

---

# 28. 制作 Production

长期固定：

制作
├── 分镜
├── 镜头
├── 场景
├── 项目资产
└── 生成任务

Image Generation

Video Generation

Audio Generation

不是 Project Production 的顶层中心。

真正 Production Spine：

Storyboard
↓
Shot
↓
AssetRequirement
↓
Production

---

# 29. Storyboard UI

Storyboard 页面规划：

顶部：

Storyboard Version
Script Version
Readiness

左侧：

Scenes

中央：

Storyboard Board

右侧：

Shot Inspector

支持未来：

Grid View

Sequence View

Shot List

每张 Storyboard Card：

Shot Number

Thumbnail

Duration

Characters

Scene

Camera

Status

Warnings

---

# 30. Shot Editor

Shot Editor 是未来核心 Production Workbench。

标准结构：

左侧：

Shot List

中央：

Preview / Canvas

右侧：

Inspector

底部：

Generation / Version / Job Drawer

右侧 Inspector 分组：

基础

画面

Camera

Action

Character

Scene

Lighting

Audio

Assets

Generation

Version

Lineage

---

Shot 中可以使用：

Image Generation

Video Generation

Audio Production

但这些是 Shot Capability，

不是孤立页面。

---

# 31. Scene UI

Scene 负责生产场景上下文。

与：

Script Scene

Shot

Scene Asset

必须明确区分。

Scene UI 可管理：

Location

Environment

Time

Weather

Lighting

Visual Reference

Continuity

Associated Shots

Associated Assets

---

# 32. Project Assets

Project 内：

项目资产

只显示属于当前 Project 的正式 Production Assets。

分类：

Characters

Scenes

Props

Images

Videos

Audio

References

每个 Asset 显示：

Current Version

Rights

Source

Usage

Associated Shots

Associated Episodes

---

# 33. Global Asset Library

全局：

资产库

负责 Workspace 级 Asset Registry 浏览。

可以跨 Project 搜索。

但用户必须明确知道：

Global Asset

与：

Project Usage

的关系。

Asset Detail 需要长期支持：

属性

版本

Rights

Provenance

Usage

Lineage

---

# 34. Creation Center

创作中心长期定位：

Global Creative Sandbox。

包括：

图片实验

视频实验

声音实验

模型实验

Prompt Lab

Templates

Quick Tools

它不是正式 Production Spine。

Sandbox 结果若进入正式生产：

必须执行：

添加到项目

选择：

Project
Episode
Shot / AssetRequirement

然后：

登记为正式 AssetVersion。

---

# 35. Generation UX

任何 AI Generation 长期统一状态：

QUEUED

RUNNING

RETRYING

SUCCEEDED

FAILED

CANCELLED

禁止不同页面各自发明一套“生成中”状态。

---

# 36. Global Job Drawer

专业编辑工作区底部预留：

Job Drawer。

显示：

Generation Jobs

Provider Calls

Render Jobs

Retries

Failures

例如：

VIDEO-0231
RUNNING

IMAGE-0441
PASS

AUDIO-0128
FAILED

M16 后再扩展成完整 Batch Job Center。

---

# 37. 后期 Post Production

固定：

后期
├── 时间线
├── 预览
├── 质检
└── 审批

---

# 38. Timeline UI

Timeline 是完整 Professional Editor。

布局：

左侧：

Media / Tracks / Objects

中央上方：

Preview Monitor

中央下方：

Timeline

右侧：

Inspector

底部：

Render / Job Drawer

Timeline 必须从真实：

VideoAssetVersion

AudioAssetVersion

Subtitle

Shot

读取。

---

# 39. Preview

Preview 显示：

PreviewCandidate

而不是 Final Master。

用户可以：

Playback

Comment

Mark Issue

Jump to Shot

Jump to Timeline

Request Regeneration

---

# 40. QC

QC 长期分类：

Creative

Visual

Character Consistency

Audio

Subtitle

Technical

Rights

Content Safety

各类型状态必须独立。

---

# 41. Approval

禁止：

approved=true

覆盖全部生产语义。

UI 长期区分：

Creative Confirmation

Script Confirmation

Consistency

Rights

Technical QC

Final Approval

Publication Eligibility

---

# 42. Local Regeneration UX

用户发现：

Shot 007 有问题。

UI 必须能够：

定位 Shot 007
↓
查看 Dependency
↓
重新生成相关 Asset / Video / Audio
↓
产生新 Version
↓
替换 Timeline Clip
↓
重新 Preview

不要求重做整集。

---

# 43. 交付 Delivery

固定：

交付
├── Master
├── 导出
├── 系列管理
├── 发布
└── 数据

---

# 44. Master

只有正式：

EpisodeMaster

进入 Master 页面。

显示：

Master Version

Episode

Source Timeline

Approval State

Rights State

Render Metadata

CreatedAt

Lineage

---

# 45. Works

Global “作品”：

只管理正式作品。

主要包括：

Episode Masters

Series

Release Packages

Published Works

Archived Works

半成品不要进入 Works。

---

# 46. Release

未来支持：

Platform Variant

Cover

Title

Description

Tags

Export Specification

Release Package

Publication State

真正的平台连接器后期实现。

---

# 47. Analytics / Performance

只展示真实数据。

例如：

Completion

Retention

Engagement

Followers

Conversion

Revenue

不得把 AI 预测数据表现成真实运营结果。

---

# 48. Standard Enterprise Editor Layout

所有核心 Editor 尽量复用统一结构：

┌──────────────────────────────────────────────┐
│ Global Header                                │
├──────────────────────────────────────────────┤
│ Project Context Bar                          │
├───────────┬─────────────────────┬────────────┤
│           │                     │            │
│ Navigator │   Main Workspace    │ Inspector  │
│           │                     │            │
│           │                     │            │
├───────────┴─────────────────────┴────────────┤
│ Job / Version / Activity Drawer              │
└──────────────────────────────────────────────┘

---

# 49. Navigator

左侧 Navigator 根据 Editor 变化：

Script：
Scenes

Bible：
Sections

Character：
Characters / States

Storyboard：
Scenes / Shots

Timeline：
Tracks / Assets

保持模式统一。

---

# 50. Inspector

右侧 Inspector 长期统一 Tab：

属性

版本

来源

检查

高级

不是所有对象都显示全部 Tab。

但交互位置保持一致。

---

# 51. Version UX

版本是系统一级 UX 能力。

对象如：

Script

Bible

Storyboard

Shot

Asset

Timeline

Master

都必须能展示版本。

例如：

Script

v4
当前确认

v3
AI Rewrite

v2
Manual Edit

v1
Initial Generation

用户长期可以：

查看

比较

恢复为新版本

检查来源

不得直接覆盖历史。

---

# 52. Lineage UX

重要对象需要：

来源 / Lineage Drawer。

例如：

Video Asset v7

Project:
穿越大唐

Episode:
EP01

Script:
v4

Storyboard:
v2

Shot:
SHOT-007

Character:
李明

CharacterState:
求生阶段

Generation:
GEN-...

底层使用真实 Ref。

默认 UI 展示可读名称。

工程 Ref 放在 Inspector 中提供复制能力。

---

# 53. Status System

全系统统一 Semantic Status。

生产内容常用：

DRAFT

CANDIDATE

PENDING_CONFIRMATION

CONFIRMED

PROCESSING

WARN

BLOCKED

STALE

FAILED

COMPLETED

ARCHIVED

Job：

QUEUED

RUNNING

RETRYING

SUCCEEDED

FAILED

CANCELLED

状态不得仅依赖颜色表达。

必须：

Icon + Text + Color。

---

# 54. Capability State

研发期间允许内部 Development Mode 显示：

未启用

但正式产品模式中：

未实现能力不得大量以“即将上线”死页面暴露给用户。

正确方式：

隐藏不可用行为

或

根据真实上游状态显示：

尚未准备
等待剧本确认
等待资产
被一致性检查阻塞

如果真实能力已经存在：

UI 必须立即反映。

不得继续显示：

即将上线。

---

# 55. Empty State

Empty State 必须说明：

为什么为空

下一步是什么

例如：

没有 Confirmed CreativePlan：

尚未确认故事方案

[前往 AI导演]

没有 Script：

尚未创建剧本

[生成剧本]

不能简单：

暂无数据。

---

# 56. Error State

Error 必须区分：

User Input

Provider

Validation

Rights

Persistence

Network

Compute

Render

不得所有错误显示：

“请稍后重试”。

用户可见信息保持产品化。

详细工程错误进入 Diagnostics / Logs。

---

# 57. Action Hierarchy

每个页面原则上只有一个主要 Primary Action。

例如：

确认剧本

生成分镜

开始资产准备

生成视频

提交审批

避免一个页面出现多个同权重高亮按钮。

危险操作：

统一放入 Secondary / More Menu

并进行确认。

---

# 58. AI Candidate UI

AI 输出必须明确显示：

AI Candidate

而不是直接表现为正式事实。

例如：

AI Script Candidate
↓
Validation
↓
User Review
↓
Confirm
↓
ScriptVersion Fact

UI 必须让用户理解：

“AI生成”

和：

“已经确认”

不是同一状态。

---

# 59. Enterprise Permission UX

长期角色预留：

Owner

Admin

Producer

Director

Writer

Storyboard Artist

Asset Artist

Editor

Reviewer

Viewer

UI Action 必须能够根据 Permission：

显示

隐藏

禁用

Read Only。

M19 再完整实现。

---

# 60. Workspace / Business Separation

未来 Workspace Switcher 支持：

Internal Content Lab

Commercial SaaS

Enterprise Workspace

UI 框架共用。

数据、权限、资源和 Compute Pool 隔离。

不得开发两个完全不同 UI 产品。

---

# 61. Project Type Adaptation

Project Workspace Shell 保持统一。

不同 Project Type 只调整内部能力。

Series Short Drama：

Project
→ Series
→ Episodes

Standalone Video：

Project
→ Content

Product Video：

Project
→ Product Context
→ Content

Brand Film：

Project
→ Brand Context
→ Content

不得因为 Project Type 不同复制整套产品 Shell。

---

# 62. Route Architecture

长期路由原则：

以下客户路由由独立 Frontend 仓库实现，并通过公开 Creator HTTP/API 获取
权威状态。路由字符串不是 Core API 路径、Domain identity 或跨仓库源码合同。

/creator

/creator/ai-director

/creator/projects

/creator/projects/new

/creator/assets

/creator/create

/creator/works

Project：

/creator/projects/:projectRef/overview

/creator/projects/:projectRef/planning/director

/creator/projects/:projectRef/planning/series

/creator/projects/:projectRef/planning/bible

/creator/projects/:projectRef/planning/characters

/creator/projects/:projectRef/planning/continuity

Series / Content：

/creator/projects/:projectRef/episodes

/creator/projects/:projectRef/episodes/:episodeRef/story

/creator/projects/:projectRef/episodes/:episodeRef/script

/creator/projects/:projectRef/episodes/:episodeRef/consistency

Production：

/creator/projects/:projectRef/production/storyboard

/creator/projects/:projectRef/production/shots

/creator/projects/:projectRef/production/scenes

/creator/projects/:projectRef/production/assets

/creator/projects/:projectRef/production/jobs

Post：

/creator/projects/:projectRef/post/timeline

/creator/projects/:projectRef/post/preview

/creator/projects/:projectRef/post/qc

/creator/projects/:projectRef/post/approvals

Delivery：

/creator/projects/:projectRef/delivery/masters

/creator/projects/:projectRef/delivery/exports

/creator/projects/:projectRef/delivery/release

/creator/projects/:projectRef/delivery/analytics

具体路由实现可以兼容现有 Route Contract。

不得为了符合文档一次性破坏当前稳定路由。

---

# 63. Existing Route Migration

已有：

AI Director

Series / Episode

Story

Script

等页面：

不得重写 Domain。

只需要逐步迁移到新的：

Project Workspace IA。

旧 Route 必须在必要时期：

Redirect / Compatibility Route。

本节现指独立 Frontend 仓库内的客户路由迁移。Core 中历史 Creator Browser
Route 不再是客户产品入口；仅当 Creator Server/API 兼容性确有需要时保留
服务端 HTTP 行为，且不得借兼容名义维持第二套客户 UI。

---

# 64. Desktop Strategy

AI Cinematic Studio 是专业生产工具。

主要编辑体验：

Desktop First。

Reference Layout：

1440px+

完整可用：

1280px+

较窄屏：

Collapse Navigator / Inspector

Tablet：

重点支持 Review / Approval / Monitoring

Mobile：

重点支持：

查看
审批
通知
任务

不强求完整 Timeline / Storyboard 专业编辑。

---

# 65. Browser Baseline

保持：

Chrome

Edge

360 Chromium

为主要桌面兼容目标。

任何正式 UI Milestone：

必须在独立 Frontend 仓库执行 Gate A — Frontend Experience Gate，并使用
真实 HTTP Runtime。涉及真实 Core 能力的客户流程还必须执行 Gate C —
Cross-Repo Integration Gate。

Core 仓库执行 Gate B — Core HTTP Runtime Gate；该 Gate 验证公开 API 和
Application 行为，不以客户 UI 视觉截图作为 Core 完成证据。

---

# 66. Interaction Quality

统一要求：

Loading Skeleton

Optimistic UI 只用于安全场景

Explicit Save State

Keyboard Focus

Unsaved Change Warning

Retry

Cancel

Undo where appropriate

No accidental destructive action

---

# 67. Accessibility

企业 UI 必须：

不只靠颜色传递状态

保证可读 Contrast

支持 Keyboard Focus

按钮具有文本或 Tooltip

错误明确定位

表单具有 Label

---

# 68. M4–M19 UI Activation Map

本章是独立 Frontend 仓库的 Experience activation map。Core Milestone 负责
提供相应公开合同和真实能力，不在 Core 仓库内重新实现这些客户页面。

## M4 — Project Context Foundation

点亮：

New Project

Project List

Project Workspace Shell

Project Overview

Project Context Bar

真实 Project → Series → Episode

现有 Story / Script 迁入 Project Context。

---

## M5 — Series Planning + Series Director

点亮：

策划 → AI导演

策划 → 系列规划

Series Arc

Episode Plan

---

## M6 — IP Bible + Character

点亮：

策划 → IP圣经

策划 → 角色

策划 → 世界与连续性

---

## M7 — Narrative Closed Loop

完整点亮：

内容 → Story

内容 → Script

内容 → Consistency

Bible → Script → Validation 闭环。

---

## M8 — Storyboard + Shot

点亮：

制作 → 分镜

制作 → 镜头

Professional Shot Editor。

---

## M9 — Asset Intelligence

点亮：

制作 → 场景

制作 → 项目资产

AssetRequirement

Asset Matching。

---

## M10 — Image

点亮：

Shot Editor → Visual Production

Image Generation。

---

## M11 — Video

点亮：

Shot Editor → Video Production。

---

## M12 — Audio

点亮：

Shot / Scene → Audio Production。

---

## M13 — Timeline

点亮：

后期 → 时间线。

---

## M14 — QC

点亮：

预览

QC

审批

Local Regeneration。

---

## M15 — Master

点亮：

交付 → Master

Global → 作品。

---

## M16 — Batch

增强：

Project Overview

Episode List

Job Drawer

Batch Production Dashboard。

不改变 IA。

---

## M17 — Release

点亮：

系列管理

Export

Release。

---

## M18 — Feedback

点亮：

数据

Performance Feedback

AI Director feedback entry。

---

## M19 — Enterprise

点亮：

Workspace Admin

Team

RBAC

Billing

Quota

Compute

Audit

Security

Integrations

Private Deployment administration。

仍不修改 Creator 一级导航。

---

# 69. UI Hard Rules

以后严格禁止：

新增一个能力就新增 Global Navigation。

同一个 Domain 出现两个正式编辑页面。

在 Browser 中创造权威 Ref。

使用名称作为 Identity。

将 AI Candidate 显示成确认事实。

使用 Mock 数据伪装已完成 Domain。

能力已经存在但 UI 长期“即将上线”。

Project Context 不明确。

用户不知道当前编辑的是哪个 Episode。

修改对象却看不到 Version。

正式资产却不知道 Source / Usage。

Shot 生成内容却与 Shot 没有关系。

Timeline 使用无法追溯的媒体文件。

Admin 功能污染 Production Workspace。

---

# 70. UI Success Criteria

最终用户进入系统以后应该自然理解：

我在哪个 Workspace

我在哪个 Project

我在哪个 Series

我在哪个 Episode

现在处于哪个生产阶段

当前对象是什么版本

它来自哪里

是否已经确认

有什么问题

下一步应该做什么

如果修改它，会影响什么

而不是首先思考：

“我应该点哪个 AI 工具？”

---

# 71. Final Enterprise UI Map

AI CINEMATIC STUDIO

GLOBAL
│
├── 首页
├── AI导演
├── 项目
├── 资产库
├── 创作中心
└── 作品
     │
     ▼
PROJECT WORKSPACE
│
├── 概览
│
├── 策划
│   ├── AI导演
│   ├── 系列规划
│   ├── IP圣经
│   ├── 角色
│   └── 世界与连续性
│
├── 内容
│   ├── 分集
│   ├── 故事
│   ├── 剧本
│   └── 一致性
│
├── 制作
│   ├── 分镜
│   ├── 镜头
│   ├── 场景
│   ├── 项目资产
│   └── 生成任务
│
├── 后期
│   ├── 时间线
│   ├── 预览
│   ├── 质检
│   └── 审批
│
└── 交付
    ├── Master
    ├── 导出
    ├── 系列管理
    ├── 发布
    └── 数据

ENTERPRISE ADMIN
│
├── Workspace
├── Team
├── RBAC
├── Models
├── Compute
├── Storage
├── Billing
├── Audit
├── Security
└── Integrations

---

# 72. Final UI Principle

整个 UI 长期坚持：

Project First

Production Lifecycle First

Domain-driven Navigation

Stable Global Shell

Stable Project Workspace

Professional Editors

Version Visible

Lineage Visible

Status Visible

Next Action Visible

AI Candidate ≠ Domain Fact

Enterprise Management ≠ Creative Workspace

Milestones Activate UI

Milestones Do Not Redesign UI

One Commercial Frontend Repository

Public HTTP/API Integration Only

No Second Customer UI in Core

---

# End of UI Master Plan
