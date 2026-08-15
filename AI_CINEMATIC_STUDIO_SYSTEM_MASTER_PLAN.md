# AI Cinematic Studio — System Master Plan

> Document: `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`
>
> Status: `SYSTEM MASTER GOVERNANCE BASELINE / CCV-R2-G0-G1 CLOSED / G2 GPU EXECUTION OWNER AUTHORIZED`
>
> Version: `v1.2`
>
> Date: `2026-08-15`
>
> Revision: `ACS-CCV-R2-G2-GPU-EXECUTION-ACTIVATION`
>
> Architecture Decisions: `ADR-0001 / Accepted`; `ADR-0005 — M6 Consumer Boundary / Accepted as architecture only`; `ADR-0006 — V5 Text Generation Capability Boundary / Accepted for bounded G1`
>
> Scope: AI Cinematic Studio 全系统产品、Domain、生产链、技术分层、研发顺序与验收基线
>
> Purpose: 作为 AI Cinematic Studio 长期研发的最高项目级规划依据，避免根据临时聊天、单个功能或局部实现不断改变系统方向。

---

# 0. 文档定位与权威顺序

AI Cinematic Studio 后续研发不得再主要依赖最近聊天上下文决定方向。

项目执行权威顺序固定为：

1. 适用的 `AGENTS.override.md`
2. 最近层级的嵌套 `AGENTS.md`
3. 根目录 `AGENTS.md`
4. Accepted ADR 与强制治理规则
5. `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`
6. `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`，仅在 UI、UX、Frontend 范围内生效
7. `CURRENT_MILESTONE.md`，仅控制当前任务、门禁和执行状态
8. Accepted/remote-verified Git evidence，仅证明实现事实，不得自行改变架构
9. Historical、superseded、archived evidence

如果低层级信息与高层级规划冲突：

必须停止扩张。

不得自行选择一个版本继续开发。

只有 Project Lead 可以决定是否修改 Master Plan。

---

# 1. 产品最终定位

AI Cinematic Studio 不是：

- AI 聊天写作工具；
- 图片生成工具集合；
- 视频生成模型集合；
- 普通后台管理系统；
- 一组彼此独立的 AI 功能页面。

AI Cinematic Studio 的最终定位是：

> **以 Project 为生产根，以 Series / Episode 为系列叙事结构，以 IP / Character 为一致性控制，以 Script / Storyboard / Shot 为影视生产结构，以 AssetVersion 为生产材料，以 Video / Audio 为并行生成能力，以 Timeline / V3 为合成渲染中枢，以 V4 为 AI / Compute 执行与规模化调度平台，最终形成可追溯、可局部返工、可批量扩展、可数据反哺的 AI 影视工业生产系统。**

核心目标：

```text
Idea
↓
Project
↓
Creative Intelligence
↓
Narrative Structure
↓
Production Specification
↓
Asset Production
↓
Audio / Video Production
↓
Composition
↓
Master
↓
Release
↓
Performance Feedback
↓
Next Creative Cycle
```

---

# 2. 核心执行原则

## 2.1 Project First

所有正式生产活动必须属于一个 Project。

禁止长期存在：

- 孤儿 CreativePlan；
- 孤儿 Script；
- 孤儿 Character；
- 孤儿 Storyboard；
- 孤儿 Shot；
- 孤儿 Asset；
- 孤儿 Video；
- 孤儿 Audio；
- 不知道属于哪个 Project 的 Timeline。

正式生产链必须从：

```text
Workspace
↓
Content Profile
↓
Project
```

开始。

---

## 2.2 纵向闭环优先

禁止先把所有横向模块分别开发完成，再考虑集成。

正确策略：

```text
1个 Project
↓
1个 Series
↓
1个 Episode
↓
1个 CreativePlan
↓
1个 Script
↓
1个 Storyboard
↓
若干 Shot
↓
真实 Asset
↓
真实 Video / Audio
↓
Timeline
↓
Episode Master
```

先跑通。

再扩：

```text
1集
→ 3集
→ 10集
→ 30集
→ 100集
```

---

## 2.3 系列化架构前置

系统必须从早期就支持：

```text
Project
↓
Series
↓
Episode
```

而不是完成单集系统以后再改造成百集系统。

但是：

Series 架构前置

≠

现在立即开发百集 Batch Engine。

---

## 2.4 批量能力后置

Queue、DAG、GPU Worker、Scheduler、Batch Render、Retry、Priority、Recovery 等规模化能力，必须建立在单集真实生产链已经通过之后。

不得为了“未来100集”提前建设一个没有成熟单集生产能力的批量平台。

---

## 2.5 禁止功能孤岛

任何 Milestone 开始前必须明确：

1. 上游权威对象
2. Input Contract
3. Output Contract
4. 下游直接消费者
5. Ref / Version lineage
6. 最终 Traceability

如果其中任一项无法回答：

禁止把该功能标记为完整能力。

---

# 3. 产品业务空间

AI Cinematic Studio 长期存在两个业务入口：

```text
AI Cinematic Studio
├── Internal Content Lab
└── Commercial SaaS
```

---

## 3.1 Internal Content Lab

用于内部内容生产和真实生产验证。

当前内容路线可使用：

- K2
- X2
- K1
- D2
- 未来其他内容项目

但这些内容方向：

不得硬编码进产品 Domain。

系统必须能够支持：

```text
1个 Content Profile
6个 Content Profile
60个 Content Profile
```

---

## 3.2 Commercial SaaS

面向未来：

- Creator SaaS
- Pro Studio
- Enterprise
- Private Deployment
- Cinema OS

Internal Lab 和 Commercial SaaS：

共享技术能力。

不共享业务数据。

资源池必须可隔离。

ADR-0001 已接受，PRE-M6-RB1.1 已形成 remote-verified 重基线。
Commercial SaaS 的客户体验层由独立仓库
`AI-Cinematic-Studio-Frontend` 承载，Core 仓库不再作为客户页面源码真源。

两个业务入口仍共享 Core 的 Creator Public HTTP/API、Creator Application、
V5/V4/V3 与基础能力，但 Frontend 不得通过源码导入、私有 Adapter、SQL、
Provider、GPU Worker 或 ComfyUI 绕过公开边界。

---

## 3.3 Compute Pool

未来至少支持：

```text
Commercial Cloud Pool
Internal Lab Pool
Enterprise Private Pool
```

Project / Job 必须根据业务空间和 Compute Policy 进入正确资源池。

---

# 4. Content Profile

Content Profile 是内容身份与业务定位上下文。

它不是固定“六大账号”。

它可以代表：

- 某个账号；
- 某个内容品牌；
- 某个内容业务线；
- 某个 IP 内容方向；
- 某个商业客户生产 Profile。

示意：

```text
Workspace
↓
ContentProfileRef
↓
Project
```

Content Profile 后续可包含：

- 内容定位；
- 目标受众；
- 赛道；
- 平台；
- 风格偏好；
- 内容禁忌；
- 发布规则；
- 历史表现。

但完整 Content Profile Intelligence 不在早期一次性实现。

---

# 5. Project — 全系统生产根

Project 是所有正式生产活动的根上下文。

例如：

```text
穿越大唐
```

就是一个 Project。

---

## 5.1 Project Type

新建 Project 时首先选择：

```text
单条视频
系列短剧
商品视频
品牌影片
其他影视项目
```

---

## 5.2 Project 最小上下文

目标语义：

```text
workspaceRef
contentProfileRef

projectRef

projectType
title
description

targetPlatform
aspectRatio
defaultDurationPolicy

status

createdAt
updatedAt
version
```

具体 Schema 必须服从未来 V5 Project Contract。

---

## 5.3 Project 权威归属

Project Authoritative Fact：

属于 V5 Core OS。

Creator UI：

不拥有 Project Domain Fact。

Creator Application：

负责 Command / Query orchestration。

---

# 6. Series / Episode 层级

对于系列项目：

```text
Project
↓
Series
↓
Episode
```

---

## 6.1 Series

Series 是系列叙事与系列生产上下文。

Series 负责：

- 系列核心定位；
- Series Plan；
- Series Bible；
- Episode 规划；
- 全局制作规则；
- 角色成长；
- 时间线；
- 系列级一致性。

Series 不负责：

- GPU 调度；
- Queue；
- Worker；
- Render Retry。

这些属于 V4。

---

## 6.2 Episode

Episode 是单集生产单元。

Episode 属于：

```text
Project
↓
Series
↓
Episode
```

Episode 不等于 Project。

Episode 不等于 Canonical Project。

---

## 6.3 非系列项目

非系列 Project 可以不存在 Series。

它拥有一个主要生产单元。

具体是否复用 Episode Pipeline，必须保持语义明确，不得为了代码复用向用户暴露错误的“集”概念。

---

# 7. AI Director 的最终定位

AI Director 不是系统的 Domain Root。

Project 才是生产根。

AI Director 是：

> Project 上下文中的 Creative Intelligence Capability。

---

## 7.1 AI Director 模式

统一 AI Director 能力未来支持两种主要工作模式：

### Series Director

负责：

- 系列核心创意；
- 主线；
- 支线；
- 人物弧；
- 全季节奏；
- Episode Plan；
- 伏笔规划；
- 全局视觉/叙事方向。

### Episode Director

负责：

- 单集 Narrative Goal；
- 本集故事；
- 情绪；
- 角色需求；
- 场景需求；
- 基础分镜意图；
- Visual Style；
- Production Plan。

这是同一个 AI Director Capability。

不是两个孤立 AI 模块。

---

## 7.2 当前 Provider

当前首个文本 Provider：

DeepSeek。

但 Domain 必须保持 Provider-neutral。

未来可以替换或并存：

- DeepSeek
- OpenAI
- Gemini
- Claude
- Local Models
- 其他 Provider

---

## 7.3 AI 输出权力边界

AI Provider 只能产生：

Candidate。

AI Provider 不拥有：

- Project lifecycle；
- Series lifecycle；
- Episode lifecycle；
- Character identity；
- Script confirmation；
- Asset identity；
- Rights；
- Approval；
- Publication；
- Final production authority。

---

# 8. 成熟的系列剧集生产流程

以：

```text
穿越大唐
100集
```

为例。

---

## Step 1 — 创建 Project

```text
项目名称：
穿越大唐

项目类型：
系列短剧

计划集数：
100

单集时长：
60秒

画幅：
9:16

目标平台：
短视频平台

Content Profile：
短剧业务线
```

产生：

```text
projectRef
```

---

## Step 2 — 创建 Series

Project Type = Series 时：

```text
projectRef
↓
seriesRef
```

只创建 Series Shell。

不得因为：

plannedEpisodeCount = 100

立即创建 100 个 Episode。

---

## Step 3 — Series Director

AI Director 生成 Series Plan：

- 核心概念；
- 主线；
- 支线；
- 人物成长；
- 冲突层级；
- Arc；
- 全季节奏；
- Episode Plan。

---

## Step 4 — Series Bible

建立：

```text
Series
↓
SeriesBible
↓
SeriesBibleVersion
```

包括：

- World Rules；
- Characters；
- Character States；
- Relationships；
- Timeline；
- Continuity；
- Forbidden Rules；
- Style Rules。

---

## Step 5 — 创建 Episode

例如：

```text
Episode 001
```

Episode 获取：

- Series 上下文；
- Series Plan；
- SeriesBibleVersion；
- applicable CharacterState；
- 当前 Arc / Episode Goal。

---

## Step 6 — Episode Director

产生：

```text
Episode CreativePlan
```

并进行：

Schema Validation
+
Human Confirmation。

---

## Step 7 — Story

Story 页面不是新 Domain。

Story 是 Episode Confirmed CreativePlan 的 Narrative Projection。

展示：

- Logline；
- Core Theme；
- Synopsis；
- Key Beats；
- Target Emotion；
- Episode Narrative Goal。

---

## Step 8 — Script Studio

根据：

```text
Episode CreativePlan
+
SeriesBibleVersion
+
CharacterState
+
World / Relationship / Continuity Rules
```

生成正式 Script。

---

## Step 9 — ScriptVersion

```text
Script
├── v1 AI Generation
├── v2 Manual Edit
├── v3 AI Scene Rewrite
└── confirmedScriptVersionRef
```

历史版本不可变。

---

## Step 10 — Consistency Validation

使用：

```text
ConfirmedScriptVersion
+
SeriesBibleVersion
+
CharacterState
+
Relationship Rules
+
Timeline Rules
```

执行一致性验证。

结果：

```text
PASS
WARN
BLOCK
```

---

## Step 11 — Storyboard

只有符合当前一致性要求的 Script 才进入：

```text
Storyboard
```

Storyboard 把剧本转成影视镜头计划。

---

## Step 12 — Shot

Storyboard 拆成：

```text
Shot 001
Shot 002
Shot 003
...
```

Shot 是最重要的影视生产单元之一。

---

## Step 13 — Asset Requirement

每个 Shot 产生：

```text
AssetRequirement
```

例如：

```text
Character：主角
Character State：Episode 1 求生阶段
Scene：唐代县衙
Lighting：夜景
Prop：油灯
```

---

## Step 14 — Asset Match / Generation

先搜索已有 Asset。

```text
AssetRequirement
↓
Asset Matching
├── Existing AssetVersion → Reuse
└── Missing → Generation Request
```

---

## Step 15 — Video / Audio 并行生产

```text
Shot
├── Visual Production
│   ├── Image
│   ├── Keyframe
│   ├── Motion
│   └── Video
│
└── Audio Production
    ├── Dialogue
    ├── Voice
    ├── Ambience
    ├── SFX
    └── BGM
```

Audio 与 Video 是并行能力。

---

## Step 16 — Timeline

Video / Audio / Subtitle 汇合：

```text
Timeline
```

---

## Step 17 — V3 Composition / Render

V3 将 Production Timeline 编译成可执行渲染表示：

```text
Editorial Timeline
↓
V3 Render Timeline / Composition Graph
↓
Preview Render
```

---

## Step 18 — Preview / QC

检查：

- 角色一致性；
- Shot；
- 动作；
- 音画同步；
- 字幕；
- Rights；
- 技术质量。

---

## Step 19 — 局部返工

发现问题：

不重做整集。

例如：

```text
Shot 007失败
↓
只重生成相关 Asset / Video / Audio
↓
新 AssetVersion
↓
替换 Timeline Clip
```

---

## Step 20 — Episode Master

通过 QC / Human Gate 后：

```text
EpisodeMaster
```

---

## Step 21 — Release Package

生成：

- 输出规格；
- Cover；
- Title；
- Description；
- Tags；
- Platform Variants。

---

## Step 22 — Publication / Archive

进入：

- 发布；
- 归档；
- Series 管理。

---

## Step 23 — Performance Feedback

获取真实：

- 完播；
- 留存；
- 互动；
- 转粉；
- 业务指标。

---

## Step 24 — Feedback to AI Director

```text
Performance Data
↓
Analysis
↓
Content Profile
Series Template
AI Director
↓
下一轮 Creative Cycle
```

完成闭环。

---

# 9. Story 与 Script 的边界

必须永久区分：

## Story

Story 是：

Episode CreativePlan 的 Narrative Projection。

回答：

> 这一集讲什么？

不是独立权威数据库。

---

## Script

Script 是：

正式生产剧本。

回答：

> 这一集具体怎么演、怎么说、怎么组织场次？

包含：

- Scene；
- Action；
- Dialogue；
- Narration；
- Subtitle Intent；
- Duration；
- Version。

---

# 10. Series Bible + Character Intelligence

Series Bible 是 Series 级唯一权威。

禁止每个 Episode 保存一套独立 authoritative Bible。

---

## 10.1 Character Identity

稳定：

```text
characterRef
```

例如：

晚灯。

Display Name：

不是 identity。

---

## 10.2 Character State

人物可以变化：

```text
characterRef
↓
CharacterState A
Episode 1–20

CharacterState B
Episode 21–50

CharacterState C
Episode 51–80
```

Episode 57：

自动解析 CharacterState C。

不能创建一个新的“晚灯57”。

---

## 10.3 Bible ↔ Script 闭环

成熟流程：

```text
SeriesBibleVersion
+
CharacterState
+
World / Timeline / Relationship Rules
↓
Script Generation / Rewrite
↓
ScriptVersion
↓
Consistency Validation
```

M4 不允许只成为事后检查器。

---

# 11. Storyboard / Shot Domain

必须区分：

## Creative Storyboard / Shot Specification

属于生产 Domain。

描述：

- Scene；
- Shot number；
- duration；
- shot size；
- framing；
- camera；
- movement；
- action；
- lighting；
- CharacterState；
- audio intent；
- asset requirements。

---

## V3 Render Representation

属于 Render Core。

例如：

```text
Production Shot Specification
↓
V3 Shot Graph / Render Node Representation
```

不得让两个层都拥有同一个 Shot 的权威定义。

---

# 12. Asset Architecture

Asset 不是“生成中心里产生的文件”。

Asset 是生产系统里的版本化对象。

---

## 12.1 正确链路

```text
Shot
↓
AssetRequirement
↓
Generation / Matching
↓
Asset
↓
AssetVersion
↓
Shot
```

---

## 12.2 Asset Registry

V5 负责：

- Asset identity；
- AssetVersion；
- type；
- provenance；
- Rights；
- usage relationship。

实际二进制：

可位于对象存储 / 本地存储 / 企业私有存储。

---

## 12.3 禁止孤儿素材

任何正式生成的生产素材最终必须能够回答：

> 它用于哪个 Project / Episode / Shot？

---

# 13. Generation Request

AI 生成不能直接等同 Asset。

正确结构：

```text
AssetRequirement
↓
GenerationRequest
↓
V4 Execution
↓
Provider
↓
GenerationResult
↓
Validation
↓
AssetVersion
```

Generation Request / Execution State：

属于 V4 执行语义。

AssetVersion：

属于 V5 资产事实。

---

# 14. Image Production

M10 重点实现：

- Text → Image；
- Image → Image；
- Variation；
- Character Consistency；
- Scene Consistency；
- Keyframe；
- Style Control。

所有生成：

必须来自 Shot / AssetRequirement。

---

# 15. Video Production

M11 重点实现：

- Image → Video；
- Text → Video；
- Motion Control；
- Pose / Motion；
- Character consistency；
- local regeneration；
- version management。

Video 输出：

必须登记为 AssetVersion。

---

# 16. Audio Production

Audio 与 Video 平行。

包括：

- Voice Identity；
- TTS；
- emotion acting；
- narration；
- ambience；
- Foley；
- SFX；
- BGM；
- mixing preparation。

Audio 必须引用：

Script / Scene / Shot。

---

# 17. Timeline 与 V3 Render

用户看到的是：

Creator Timeline。

权威 Production Timeline 应具有稳定 Version。

V3 负责：

- deterministic composition；
- clip placement；
- subtitle composition；
- transitions；
- virtual camera；
- color；
- audio tracks；
- render；
- encode。

禁止：

Creator Application 自己发展第二套最终 Render Engine。

---

# 18. Preview Candidate

Preview 是候选输出。

不是 Final Master。

结构：

```text
TimelineVersion
↓
Render
↓
PreviewCandidate
```

Preview 可以：

播放、审查、批注、返工。

---

# 19. Episode Master

经过：

- technical QC；
- creative confirmation；
- applicable Rights；
- required Approval；

后形成：

```text
EpisodeMaster
```

Master 是正式可交付作品版本。

---

# 20. Release & Management

Release Package 可包含：

- Master；
- export variants；
- cover；
- title；
- description；
- tags；
- platform metadata；
- archive metadata。

后续再实现真正平台发布连接器。

---

# 21. Performance Feedback

只有获取真实平台 / 业务数据后：

才能建立 Performance Intelligence。

禁止 AI 凭空“预测”并将其展示为事实。

真实数据例如：

- completion rate；
- retention；
- interaction；
- conversion；
- followers；
- revenue；
- campaign metrics。

---

# 22. Project Type 适配

同一个生产系统未来支持：

## Series Short Drama

Project
→ Series
→ Episode

## Standalone Video

Project
→ Single Production Unit

## Product Video

Project
→ Product Context
→ Script / Shot / Asset / Video

## Brand Film

Project
→ Brand Context
→ Story / Script / Production

底层生产能力尽可能复用。

---

# 23. Domain Reference Baseline

未来核心 Ref 方向：

```text
workspaceRef
contentProfileRef

projectRef

seriesRef
seasonRef?                 optional
episodeRef

creativePlanRef
creativePlanVersion

seriesBibleRef
seriesBibleVersionRef

characterRef
characterStateRef

scriptRef
scriptVersionRef

consistencyValidationRef

storyboardRef
storyboardVersionRef

shotRef
shotVersionRef

assetRequirementRef

assetRef
assetVersionRef

generationRequestRef
generationResultRef

videoAssetVersionRef
audioAssetVersionRef

timelineRef
timelineVersionRef
timelineClipRef

previewCandidateRef

episodeMasterRef

releasePackageRef

performanceRecordRef
```

不是要求现在一次性实现。

但是后续 Domain 不得随意创建相互冲突的身份体系。

---

# 24. Ref / Version / Lineage 原则

禁止依赖：

- Title；
- Character Name；
- Episode Number；
- copied text；
- copied JSON；

作为 authoritative integration。

必须使用稳定 Ref / Version。

例如：

```text
EpisodeMaster
↓
TimelineVersion
↓
TimelineClip
↓
VideoAssetVersion
↓
ShotVersion
↓
StoryboardVersion
↓
ScriptVersion
↓
CharacterState
↓
SeriesBibleVersion
↓
Episode
↓
Series
↓
Project
```

---

# 25. Version Immutability

需要历史追踪的生产对象原则上采用不可变版本。

例如：

```text
Script
├── ScriptVersion 1
├── ScriptVersion 2
└── ScriptVersion 3
```

修改：

生成新 Version。

不是覆盖历史版本。

同理适用于：

- SeriesBibleVersion；
- StoryboardVersion；
- ShotVersion；
- AssetVersion；
- TimelineVersion；
- MasterVersion。

---

# 26. Validation Staleness

任何 Validation 都必须绑定它验证的输入版本。

例如：

```text
ConsistencyValidation
=
ScriptVersion V3
+
SeriesBibleVersion V2
+
CharacterStateRefs
```

如果任何一个输入变了：

旧 Validation：

`STALE`

不能继续当作 PASS。

---

# 27. Dependency Impact / 局部重生成

系统最终必须支持影响分析。

例如：

```text
CharacterState v4
改变服装
↓
Dependency Graph
↓
Affected Shots
↓
Affected AssetVersions
↓
Affected Videos
↓
Affected Timeline Clips
```

Audio 没受影响：

不重生成。

这比：

“改一个角色 → 重做100集”

更符合工业生产。

---

# 28. Production Spine Integrity Gate

每个正式 Milestone 必须回答：

## Upstream

真实上游是谁？

## Input Contract

稳定输入是什么？

## Output Contract

产生什么结构化对象？

## Downstream

谁直接消费？

## Lineage

Ref / Version 如何保存？

## Traceability

最终作品能否追溯回来？

其中任一项 FAIL：

不得标记：

`FEATURE ACCEPTED`

---

# 29. Presentation Integrity Rule

底层真实能力已经存在以后：

UI 不得长期仍显示：

“即将上线”。

例如：

Episode 已有 Confirmed CreativePlan：

故事页面必须展示真实 Story Projection。

不是继续 Placeholder。

UI 状态必须与真实能力状态一致。

---

# 30. Creator UI 总体结构

Creator UI V2 是稳定视觉母版。

本节定义拟议的跨仓库产品体验合同，不表示该合同已生效。在 ADR-0001 后续
获得正式接受并形成 remote-verified 重基线后，该 UI 才由独立
`AI-Cinematic-Studio-Frontend` 仓库承载，Core 只提供稳定的 Creator Public
HTTP/API 与 Application 合同。

全局一级导航继续保持：

```text
首页
AI导演
项目
资产库
创作中心
作品
```

不因为每增加一个功能就增加一级导航。

---

# 31. Project Workspace 最终结构

进入具体 Project 后，未来可以逐步形成：

```text
项目首页

AI导演
├── 系列导演
└── 分集导演

系列规划

IP圣经

分集

故事

剧本

角色

场景

分镜

镜头

资产

音频

时间线

预览

审批 / QC

交付

设置
```

具体导航可随真实能力优化。

但所有页面：

必须在同一个 Project Context 中。

---

# 32. Global AI Director

首页 AI Director 仍然保留。

它是快速入口。

如果用户直接输入：

> 我要制作100集穿越短剧。

系统可以先协助整理创意。

但在进入正式生产前：

必须建立或选择 Project。

禁止让 Global AI Director 产生长期孤儿 Production Fact。

---

# 33. Architecture Layers

拟议的跨仓库依赖方向如下；其生效取决于 ADR-0001 后续接受：

```text
Commercial Frontend
↓
Frontend Experience Adapter
↓
Creator Public HTTP/API
↓
Creator Application
↓
V5 Core OS
↓
V4 Platform
↓
V3 Render Core
↓
Compute/Foundation
```

规范形式：`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

Experience Layer 位于 V2.3 Core 六层链之外，不属于 V5、V4 或 V3，也不改变
Core 内部既有相邻依赖方向。Frontend Experience Adapter 属于 Frontend，且
只能消费 Creator Public HTTP/API。Frontend 不得直接访问 Creator Application、
Domain、SQL、Persistence、Provider、private V5、GPU、Worker 或 ComfyUI；两个
仓库不共享客户 UI 源码。该提案禁止 Core 重新建立第二套客户体验层。

---

# 34. Creator Application

负责：

- public HTTP/API boundary；
- commands；
- queries；
- public DTO / error contract；
- application orchestration；
- authorization、tenant/workspace 与 idempotency enforcement（按能力适用）。
- 只通过 V5 公开 capability boundary 消费下层能力。

客户 UI、浏览器交互、响应式、可访问性与视觉呈现属于独立 Frontend
Experience Layer。Core 中只允许 Creator Server Runtime、API/Application
实现和必要的非产品技术工具，不允许继续承载第二套 Commercial SaaS UI。

不负责 authoritative production facts。

不直接 SQL。

不直接调用 private persistence adapter。

不持有 Provider Secret。

不得直接导入、配置或调用 V4 `TextGenerationPort`、Provider Factory 或 Provider
错误类型。文本生成必须经 V5 Text Generation Capability 进入 V4。

---

# 35. V5 Core OS

长期负责：

- Identity；
- Project；
- Series；
- Episode；
- Production Documents；
- IP Bible；
- Character；
- Script；
- Storyboard / Shot Spec；
- Asset Registry；
- Rights；
- Provenance；
- Version lineage；
- Approval facts；
- Master metadata；
- Audit / Outbox；
- Durable Operation semantics。
- Creator Application 消费的 public Text Generation Capability boundary，包括
  provider-neutral Application-facing request、response、error 和封闭的
  purpose-to-execution-policy 映射。

V5 Text Generation Capability 不拥有 Provider 执行或 Provider Adapter；它只通过
相邻层公开契约调用 V4 `TextGenerationPort`。Prompt、candidate schema parsing、
本地语义校验和既有最多一次 repair 编排继续由 Creator Application 负责。

---

# 36. V4 Platform

负责 Provider execution：

```text
V5 Text Generation Capability
→ TextGenerationPort
→ DeepSeek
```

Creator Application 不得成为 V4 `TextGenerationPort` 的直接消费者。V4 继续拥有
provider-neutral execution port、Provider Factory 和 Provider Adapter。

未来逐步扩展：

- Provider Registry；
- Model Router；
- Image Provider；
- Video Provider；
- Audio Provider；
- Job Execution；
- Queue；
- DAG；
- Worker；
- Retry；
- Recovery；
- Compute Router；
- GPU scheduling。

V4 不拥有生产 Domain Fact。

---

# 37. V3 Render Core

负责 deterministic audiovisual composition：

- Render timeline；
- shot composition；
- subtitles；
- transitions；
- audio tracks；
- virtual camera；
- color；
- preview render；
- final render；
- encoding。

---

# 38. Compute

负责：

- GPU nodes；
- CPU nodes；
- resource execution；
- node isolation；
- encrypted communication；
- compute pools。

---

# 39. Cross-Cutting

贯穿全部层：

- Content Safety；
- Rights；
- Security；
- Audit；
- Observability；
- Logging；
- Tenant / Workspace isolation；
- Resource isolation；
- Provenance。

---

# 40. Provider Neutral Rule

所有 AI Provider 都是 Adapter。

禁止把：

DeepSeek / 某图像模型 / 某视频模型

写死进 Domain。

Provider 可以更换。

Domain Contract 不随 Provider 改变。

---

# 41. DeepSeek 当前角色

唯一接受的调用路径是：

```text
Creator Application
→ V5 Text Generation Capability
→ V4 TextGenerationPort
→ DeepSeek Adapter
→ DeepSeek API
```

当前 DeepSeek 用于：

- AI Director；
- Script Studio；
- 后续可选 semantic consistency analysis。

DeepSeek 不拥有：

- Project；
- Script；
- Character；
- Storyboard；
- Asset；
- Approval。

---

# 42. Secret Rule

任何情况下禁止提交：

- API Keys；
- `.env` secrets；
- Authorization values；
- Tokens；
- Passwords；
- Private Keys；
- raw sensitive Provider responses。

Browser 永远不能持有 Provider Secret。

---

# 43. Persistence Target

Application 依赖：

Repository / Public Boundary。

不得直接 SQL。

当前 Local SQLite：

```text
LOCAL DEVELOPMENT DURABLE ADAPTER
```

不是：

```text
PRODUCTION DATABASE
```

Commercial SaaS 最终优先：

PostgreSQL。

但 Adapter 替换不能要求重写 Domain Contract。

---

# 44. Human Gate

AI 成功：

不等于人工确认。

Schema PASS：

不等于创意批准。

Technical PASS：

不等于 Rights PASS。

M4 Consistency PASS：

不等于 Publication PASS。

这些状态必须独立。

---

# 45. Approval / Rights

最终生产至少区分：

- Creative Confirmation；
- Script Confirmation；
- IP Consistency；
- Asset Rights；
- Technical QC；
- Publication Eligibility。

不能用一个简单：

`approved=true`

替代所有语义。

---

# 46. 百集生产扩容原则

百集生产遵循：

```text
1
↓
3
↓
10
↓
30
↓
100
```

每次扩容检查：

- consistency；
- runtime stability；
- cost；
- retry；
- throughput；
- lineage；
- operator usability。

---

# 47. V4 Batch Orchestration

只有单集真实生产链成熟后：

才进入完整 Batch。

V4 Batch 负责：

```text
Series Production Plan
↓
Episode DAGs
↓
Queue
↓
Workers
↓
GPU
↓
Retry / Recovery
```

Series Manager 可以显示状态。

Series Manager 不自己实现 Worker / GPU scheduler。

---

# 48. Internal Content Lab 应用原则

Internal Content Lab 当前实际内容方向：

例如 K2 / X2。

它们用来验证系统。

但是系统设计不得为 K2 / X2 写死。

它们只是：

Content Profile / Project 的真实用例。

---

# 49. Commercial SaaS 路线

核心生产闭环稳定后，再逐步强化：

- Multi Tenant；
- Team；
- RBAC；
- Billing；
- Usage Quota；
- Collaboration；
- Audit；
- Enterprise；
- Private Deployment；
- Offline / Cinema OS。

不得让 SaaS 基础设施提前阻塞真实生产闭环。

---

# 50. R&D Roadmap — Rebaselined

以下路线从整个最终系统反推。

除 Project Lead 明确修改 Master Plan 外，不因临时对话改变。

本章 M1–M5 的 `Status` 与当前已接受里程碑清单同步；各 Milestone 的业务描述
继续保留历史范围和证据语义。当前任务、门禁和执行状态只由
`CURRENT_MILESTONE.md` 控制。

---

## M1 — AI Director Core

Status:

`ACCEPTED`

Accepted Commit:

`8bf3dc42323007202b083663125e0c31f8e93802`

完成：

- DeepSeek Live；
- CreativePlan；
- Schema；
- Human Confirmation；
- downstream input。

---

## M2 — Series + Episode Foundation

Status:

`ACCEPTED`

Accepted Commit:

`f0fd38ab22a41e00bac3e1e39e9667625b62de15`

完成：

- Series；
- Episode；
- parent/child；
- ConfirmedCreativePlanBinding；
- persistence；
- Script Studio Bootstrap。

---

## M3 — Script Studio

Status:

`ACCEPTED`

Accepted Commit:

`e50921e8fe0872a78f62e09aa08da79631e6f9bc`

完成：

- Script；
- immutable ScriptVersion；
- DeepSeek script generation；
- manual version；
- local rewrite；
- confirmation；
- downstream bootstrap candidate。

---

## M3-H — Script Candidate Robustness Hotfix

Status:

`ACCEPTED`

目标：

- repair provider candidate/schema mismatch；
- local system owns structural refs；
- improve real Script generation reliability；
- 3x live smoke；
- regression；
- GitHub baseline。

Hotfix Accepted SHA：

`cc39a0b2e13c98a2e946ba8166764873a4be277d`

Hotfix accepted baseline effect：

未来所有新 Milestone 必须基于新的 Hotfix SHA。

---

## M4 — Project Context Foundation

Status:

`ACCEPTED`

目标：

正式建立 Project First。

完成：

```text
ContentProfile
↓
Project
↓
Series
↓
Episode
```

要求：

- Project V5 ownership；
- existing Series / Episode attach to Project；
- no duplicate Project authority；
- existing M1–M3 lineage preserved；
- project workspace context；
- Story Projection 接入真实 ConfirmedCreativePlan；
- existing UI no longer shows false placeholders where capability exists。

M4 不实现 Series Director / IP Bible。

---

## M5 — Series Planning + Series Director

Status:

`ACCEPTED`

完成：

- Series Creative Plan；
- main arc；
- sub-arcs；
- Character Arc intent；
- Episode Plan；
- planned episode structure；
- Series Director mode。

不创建100集执行任务。

---

## M6 — Series IP Bible + Character Intelligence

Status:

`P0-P1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860 / P2-G0 CONTRACT ACCEPTED / P2-G1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 8227c6c616140824fd70de920dc6fcf459bb734d / P3-G0 OWNER ACCEPTED AS GOVERNANCE-ARCHITECTURE / ADR-0005 + M6 CONSUMER CONTRACT ACCEPTED / P3-B1 OWNER ACCEPTED THROUGH B1-R1 AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7 / P3-G1 ORIGINAL 3696d6af REVISION REQUIRED / G1-R1 OWNER ACCEPTED AT e172cc7c9bfca04066153d9edad70d9074bb37e5 / TREE be7447c3 / FULL CORE 464/464 / CORE MAIN 5976263f SAME TREE / LATER M6 WORK NOT AUTHORIZED`

目标范围：

- SeriesBible；
- immutable BibleVersion；
- Character identity，包括 background、motivation、belief、conflict、goal 和
  personality；
- behavior rules、dialogue rules 和 forbidden behavior；
- visual identity rules；
- `CharacterState`；
- `RelationshipContext`；
- episode applicability；
- relationships；
- timeline and continuity；
- forbidden rules；
- style constraints。

明确非目标：

- `M6 ≠ V5 Identity Lock`；
- M6 不实现 M7；
- M6 不实现 GPU Render、ComfyUI 或 Worker；
- M6 不实现跨仓 UI；
- M6-P2 只实现本地开发 SQLite 持久化、Migration、复合完整性、持久化幂等与
  Outbox；正式 8765 数据库保持禁止访问；
- M6-P3-G0 仅接受 consumer/reconciliation target architecture；架构已接受；
- M6-P3-B1 EpisodePlanItemBinding 获得有界实现授权：治理 8 路径远端验证后，
  仅可修改冻结的 6 个生产与 9 个测试路径；
- B1 候选 `8449b521c96bb8340806ecda8649698f4771914a` 已远端验证但 Owner Review
  判定 `REVISION REQUIRED / NOT OWNER ACCEPTED`；SQLite 同一 Project 下的
  other-Series plan 被错误纳入 Episode binding 依赖扫描；
- B1-R1 的相同 8 个治理路径已在
  `716b4d298173f8123cafd93114dfc67339943ff3` 远端验证；技术候选仅修改
  `services/v5_core_os/series_planning/foundation.py` 与
  `tests/integration/test_creator_lifecycle_sqlite_p2.py`；不得改变 InMemory 生产
  行为、DDL/Migration 或其他 B1 语义；门禁结果为 SQLite `30/30`、原 B1
  `174/174`、完整 Core `449/449`、AST `63/63`；
- B1-R1 技术提交 `5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` 已远端验证；
  `2026-08-14` Owner Review 独立复现原始错误 `409` 并确认修正后，判定
  `OWNER ACCEPTED / COMPLETE`；
- B1 初始计划保持 v1，允许 v1→v1、显式 v1→v2、v2→v2，禁止 v2→v1，解绑
  必须创建显式 v2 新版本；唯一新增操作为 Core-only
  `create_episode_plan_item_binding_version`，不得新增或修改 HTTP route、handler、
  外部 DTO 源文件；Owner 明确允许既有 HTTP workspace versions 的 v2 响应透传
  `episodePlanItemBindings`，但不得扩大其他 HTTP contract；
- M6-P3-G1 的 B1 前置条件已满足；Project Lead 于 `2026-08-14` 单独授权精确
  Core-only 只读实现。必须先远端验证 8 路径治理检查点，再限于 7 个生产路径
  与 3 个新增测试路径，技术候选远端验证后停止等待 Owner Review；
- 治理检查点已远端验证；原技术候选通过 G1 `14/14`、完整 Core `463/463`、
  AST `63/63`、Markdown `88/88`、links `323/323` 与全部范围/安全门禁，但
  `3696d6af12222d30eb99b65d67e6db18897eb42f` 因未知异常语义失真保持
  `REVISION REQUIRED / NOT OWNER ACCEPTED / SUPERSEDED`；
- G1-R1 `e172cc7c9bfca04066153d9edad70d9074bb37e5` 仅将未知异常映射改为中性
  `m6_consumer_internal_error / 500` 并新增一个测试文件，五个 ADR-0005 业务码
  不变，完整 Core `464/464`，Owner Accepted；
- 受保护 `main` 通过 PR `#2` 使用 `Rebase and merge` 收敛为
  `5976263f92f7f9cbe9c091719eccb036ee8c0c2d`，tree 与 G1-R1 完全一致，
  post-merge Repository Validation 通过；
- G1 之后与 M6-P4+ 均为 `NOT AUTHORIZED / NOT STARTED`。

---

## M7 — Narrative Closed Loop

Status:

`NOT STARTED`

目标：

真正关闭：

```text
Bible
↓
Episode Director / Script
↓
Consistency
↓
Corrected Script
```

完成：

- Bible constraints → new Script generation/rewrite；
- Script consistency validation；
- PASS/WARN/BLOCK；
- Validation staleness；
- Character binding；
- Story / Script / Bible UI connection；
- M8 Storyboard readiness。

---

## M8 — Storyboard + Creative Shot Domain

Status:

`NOT STARTED`

完成：

- confirmed Script → Storyboard；
- StoryboardVersion；
- Shot；
- ShotVersion；
- camera；
- framing；
- motion intent；
- duration；
- character state binding；
- scene binding；
- asset requirements；
- audio intent。

不实现最终 Render Shot Graph。

---

## M9 — Asset Requirement + Asset Intelligence

Status:

`NOT STARTED`

完成：

- Shot → AssetRequirement；
- Asset matching；
- reuse；
- missing asset detection；
- Asset Registry connection；
- provenance；
- Rights linkage；
- Series shared asset pool。

---

## M10 — Image Generation

Status:

`NOT STARTED`

完成：

- Text → Image；
- Image → Image；
- variation；
- keyframe；
- character consistency；
- scene consistency；
- image versioning；
- Shot binding。

---

## M11 — Video Production

Status:

`NOT STARTED`

完成：

- Image → Video；
- Text → Video；
- Motion；
- identity consistency；
- shot video version；
- local regeneration；
- failure handling。

---

## M12 — Audio Production

Status:

`NOT STARTED`

完成：

- Voice Identity；
- TTS；
- emotional voice；
- narration；
- BGM；
- Ambience；
- SFX；
- preliminary mix；
- Shot / Script linkage。

Audio 与 Video 并行。

---

## M13 — V3 Timeline + Composition + Render

Status:

`NOT STARTED`

完成：

- Production Timeline；
- TimelineVersion；
- Video / Audio clips；
- Subtitle；
- transition；
- color；
- audio tracks；
- V3 composition；
- preview render；
- deterministic render。

---

## M14 — Preview / QC / Approval / Local Regeneration

Status:

`NOT STARTED`

完成：

- candidate preview；
- creative QC；
- technical QC；
- consistency feedback；
- Rights gate；
- approval separation；
- Dependency Impact；
- local regeneration；
- selective clip replacement。

---

## M15 — Episode Master + Works

Status:

`NOT STARTED`

完成：

- EpisodeMaster；
- master version；
- Works；
- archive；
- final metadata；
- final traceability。

---

## M16 — V4 Batch Production Orchestration

Status:

`NOT STARTED`

完成：

```text
1 → 3 → 10 → 30 → 100
```

包括：

- Queue；
- DAG；
- Workers；
- Retry；
- Recovery；
- Priority；
- Pause；
- Resume；
- GPU scheduling；
- Series production dashboard。

---

## M17 — Series Release & Management

Status:

`NOT STARTED`

完成：

- multi-spec export；
- episode archive；
- series archive；
- QC batches；
- cover；
- title；
- description；
- tags；
- release packages；
- platform preparation。

---

## M18 — Performance Feedback

Status:

`NOT STARTED`

完成：

- real performance ingestion；
- retention；
- completion；
- interaction；
- conversion；
- content analysis；
- feedback to AI Director；
- template improvement；
- Content Profile learning。

---

## M19 — Commercial SaaS / Enterprise Hardening

Status:

`NOT STARTED`

完成：

- multi-tenant；
- RBAC；
- team；
- billing；
- quota；
- collaboration；
- audit；
- enterprise deployment；
- private deployment；
- stronger isolation；
- Cinema OS evolution。

---

# 51. Milestone Definition of Done

每个正式 Milestone 必须全部满足：

```text
IMPLEMENTATION PASS
UPSTREAM CONNECTION PASS
INPUT CONTRACT PASS
OUTPUT CONTRACT PASS
DOWNSTREAM CONNECTION PASS
REF / VERSION LINEAGE PASS
INTEGRATION PASS
REGRESSION TESTS PASS
BROWSER / LIVE PASS
PERSISTENCE PASS（如适用）
ARCHITECTURE SCAN PASS
SECRET SCAN PASS
git diff --check PASS
COMMIT PASS
GITHUB PUSH PASS
REMOTE SHA == LOCAL SHA
```

只有 Project Lead 可以最终标记：

`FEATURE ACCEPTED`

Codex 只能报告：

`FEATURE ACCEPTED CANDIDATE`

---

# 52. Git / GitHub Hard Gate

任何经过正式测试并宣布完成的功能：

必须上传 GitHub。

固定流程：

```text
Implement
↓
Integration
↓
Tests
↓
Browser / Live
↓
Secret Scan
↓
Commit
↓
Codex Push GitHub
↓
Fetch
↓
Remote SHA Verify
↓
Project Lead Acceptance
```

不得要求用户手动 Push。

---

# 53. Clean Worktree Rule

重大 Milestone：

优先从最近 Accepted Remote SHA 创建 clean worktree。

不得让历史 untracked 文件成为隐式依赖。

不得自动删除用户历史文件。

---

# 54. Audit Rule

不是每个任务都做大审计。

以下类型 Milestone 进入前可以做针对性资产盘点：

- Project Domain；
- IP Bible / Character；
- Asset；
- V3；
- V4 Batch；
- Commercial SaaS core boundaries。

审计必须直接导向实现决策。

禁止无限治理。

---

# 55. Hotfix Rule

已接受 Milestone 出现真实 Production Bug：

允许 Hotfix。

Hotfix：

- 不改变主路线；
- 最小修复；
- Regression；
- Live Smoke；
- Commit；
- Push；
- Remote SHA Verify。

Hotfix Accepted 后：

新的 Accepted SHA 成为后续 Milestone Base。

---

# 56. UI Evolution Rule

Creator UI V2：

是稳定 Product Visual Baseline。

不是永久冻结。

允许：

真实能力驱动 UI 修改。

禁止：

无业务原因大规模重新设计。

UI 必须持续反映真实系统能力。

ADR-0001 已接受且 PRE-M6-RB1.1 已形成 remote-verified 重基线。所有客户
UI 演进在独立
`AI-Cinematic-Studio-Frontend` 仓库进行，并通过 Frontend Experience Adapter
仅消费 Creator Public HTTP/API。Core 不得以调试便利、兼容路由或 Milestone
激活为理由重新创建 Commercial SaaS 页面。Core 中历史 Creator Browser UI
已在 PRE-M6-RB1.2 完成受控退役；Server/API/Application/Domain/Persistence/Test
责任继续保留在 Core。

---

# 57. Anti-Patterns

严格禁止以下模式：

## 孤岛模块

```text
功能A PASS
功能B PASS
但没有真实合同关系
```

---

## Copy-as-Integration

复制一份 JSON：

不叫集成。

---

## Name-as-Identity

“晚灯”：

不是 characterRef。

---

## Provider-as-Domain

DeepSeek 输出 ID：

不能成为权威系统 ID。

---

## UI-as-Authority

Browser state：

不能成为正式 Domain Fact。

---

## Database-in-Application

Application：

不得直接 SQL。

---

## Batch-Before-Single

单集未打通：

不得先做100集 GPU调度。

---

## Platform-Before-Production

真实生产链未完成：

不得无限建设平台治理。

---

# 58. System Success Criteria

AI Cinematic Studio 最终成功，不是因为：

“有20个AI功能”。

而是因为用户可以做到：

```text
创建一个 Project
↓
定义一个 Series
↓
建立一个世界与角色
↓
生成100集计划
↓
生产某一集
↓
形成剧本
↓
形成镜头
↓
生成正确资产
↓
生成音视频
↓
自动合成
↓
局部修改
↓
输出成片
↓
发布
↓
数据反馈
↓
继续下一集
```

并且系统能够回答：

> 最终成片的某一秒，来自哪个 Project、哪个 Episode、哪个 ScriptVersion、哪个 CharacterState、哪个 Shot、哪个 AssetVersion 和哪次生成？

如果不能回答：

生产链仍未真正闭合。

---

# 59. Codex Startup Rule

每次 Codex / Automation 开始当前项目工作前：

必须读取：

```text
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AGENTS.md
CURRENT_MILESTONE.md
```

然后检查：

```text
Current Branch
HEAD
Git Status
Accepted Base
Current Milestone
```

不得根据最近聊天自行改变 Roadmap。

---

# 60. Conflict Rule

如果：

Master Plan

与：

CURRENT_MILESTONE

发生冲突：

STOP。

如果：

Accepted Git Baseline

与：

当前任务假设

发生冲突：

STOP。

不得静默选择一个方向。

---

# 61. Master Plan Change Rule

本文件只在以下情况修改：

1. 产品根模型发生变化；
2. Production Spine发生变化；
3. Domain Ownership发生变化；
4. Layer Architecture发生变化；
5. Roadmap发生正式重基线；
6. Project Lead明确批准。

普通 Bug、UI调整、Prompt优化：

不得频繁修改 Master Plan。

---

# 62. Current System State

以下代码块严格保留 `PRE-M6-RB1.3-CLOSEOUT-G1` 决策时点的历史快照；后续
执行状态不得回写或覆盖该快照。

截至 `PRE-M6-RB1.3-CLOSEOUT-G1`：

```text
M1 AI Director
ACCEPTED

M2 Series + Episode
ACCEPTED

M3 Script Studio
ACCEPTED

M3-H Script Candidate Robustness Hotfix
ACCEPTED

Story Projection
ACCEPTED

UI-R1 / UI-R2
PRODUCT ACCEPTANCE: ACCEPTED HISTORY

UI-R2A
PRODUCT ACCEPTANCE STATUS: NO SEPARATE ACCEPTANCE EVIDENCE / CANDIDATE
REMOTE VERIFICATION STATUS: PASS AT PRE-REBASELINE HEAD 602a78fe68fc5c69ecc31d9436ee166f5dff8a64
ACTIVE ARCHITECTURE STATUS: SUPERSEDED AS CURRENT TASK

M4 Project Context Foundation
ACCEPTED

M5 Series Planning + Series Director
ACCEPTED

PRE-M6-RB1.1 Source-of-Truth Rebaseline
CLOSED / REMOTE-VERIFIED

PRE-M6-RB1.2 Legacy UI Decommission
CLOSED / REMOTE-VERIFIED

PRE-M6-RB1.3 Full Core Current-State Audit
REMEDIATION COMPLETE / FORMALLY CLOSED BY PROJECT LEAD OWNER REVIEW

PRE-M6-RB1.3-IR1 Independent Audit Review
COMPLETED

Full Core Audit Report v1.2
INDEPENDENTLY ACCEPTED

PRE-M6-RB1.3-R1-RV1
INDEPENDENTLY ACCEPTED

RB13-F001 Governance Source-of-Truth Drift
R1 IMPLEMENTED / INDEPENDENTLY ACCEPTED / CLOSED

RB13-F002 Deletion Lifecycle Integrity
REMEDIATED / CLOSED IN CURRENT TESTED CORE BASELINE

Current Task
ACS-M6-P0-P1 — SERIES INTELLIGENCE INMEMORY BASELINE

ADR-0002 V5 Lifecycle Integrity Boundary
ACCEPTED FOR BOUNDED R2 IMPLEMENTATION

R2-P2 SQLite Lifecycle Integrity
OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 0aa14b4e426a3d968ec314029d60a47ea30cbc4d

Legacy repository capability provenance
MEDIUM / OPEN / NON-BLOCKING / OWNER GATE P3-RV1-003

M6 Series IP Bible + Character Intelligence
NOT STARTED / P0-P1 AUTHORIZED / P2-P4 NOT AUTHORIZED

M7-M19
NOT STARTED / NOT AUTHORIZED

RB1.3 Closeout
FORMALLY CLOSED BY PROJECT LEAD OWNER REVIEW

Architecture Review
SATISFIED FOR BOUNDED M6-P0/P1 ONLY

M6 Preconditions
SATISFIED FOR BOUNDED INMEMORY M6-P0/P1 ONLY

Formal 8765 Deployment
NOT PERFORMED / NOT AUTHORIZED

Frontend
FROZEN / UNTOUCHED

Production Ready
NO
```

PRE-M6-RB1.3-CLOSEOUT-G1-R1 is `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED`
at `dc9ab881b9f82ecd4a5927c456d5fe531f6850fa`. ADR-0003 accepts the bounded
M6 Series Intelligence baseline for the already authorized P1 implementation.
`ACS-M6-P0-P1-R2` is `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED` at
`e38c75aa4ff26bdea80c82d8a24096f799dad860`. ADR-0004 accepts the bounded M6-P2
local-development durable SQLite boundary.

当前执行状态（不属于上述历史快照）：

```text
Current Work Package
ACS-CCV-R2-G2-GPU-EXECUTION / RECEIPT-BOUND 45-RUN MATRIX

Execution Mode
BOUNDED GPU EXECUTION / MAXIMUM ONE IN FLIGHT / FAIL-CLOSED

Accepted Parent Checkpoint
ACS-GOV-POST-M6-P3-G1-CLOSEOUT OWNER ACCEPTED AT
20207e7f2d2123468698f453c70ce725a293976a / TREE
e3638838dd0c79201a1962bb247ec7c773b62ffa

Current Evidence Status
ORIGINAL CCV-R1 CANDIDATE 57cbbd49 REVISION REQUIRED / NOT OWNER ACCEPTED
SEED-TYPE CORRECTION OWNER ACCEPTED AT 0c2552bf49923d45c2c5542cdb39f512a7e7d15d
MAIN CONVERGED THROUGH PR #4 AT 9c13e8f8d7ccef079dd382fe11b1d173fdef13d7
G0 OWNER ACCEPTED / REMOTE-VERIFIED AT 9094a46615f2be9ca45f95418ac441326d326315
G1 REMOTE-VERIFIED AT af34ac074cb8bfbf334e4f56aad0c0d479b741be / PR #6 CI PASS
G2 COLLECTION EXECUTED / ORIGINAL CUSTODY PVC NOT ATTACHED / SUPERSEDED BY G2-R1
G2-R1 INDEPENDENT REVIEW PASS / CLOSED AT 4132458d7f92e02dbd2e4be93476294aab825db6
HISTORICAL MANIFEST REMAINS EVIDENCE_CAPTURE_PARTIAL_NOT_VALIDATION_ACCEPTED
EXPERIMENT REPORTED / INDEPENDENT REPRODUCTION NOT POSSIBLE
CCV-R2-G0 AUTOMATED REVIEW PASS / CLOSED AT 0376ee3c5b7a4c78735a04578a9a12fa1df6c2a2
CCV-R2-G1 AUTOMATED PRE-GPU REVIEW PASS / CLOSED AT 1989fd59b16c821e61ec122f89cee42e99ddacdb
45 OF 45 REQUESTS MATERIALIZED AND VALIDATED / RECEIPT 995035ee1169b7335d7c0707ea6adc31e36cd342c2a281f475fd66b7f4952c05
CCV-R2-G2 OWNER AUTHORIZED ON 2026-08-15 / 45-RUN EXECUTION ACTIVE
NO PRODUCT OR SCHEMA IMPLEMENTATION

Architecture Decision
ADR-0006 V5 TEXT GENERATION CAPABILITY BOUNDARY
ACCEPTED FOR BOUNDED G1

Current Checkpoint
B1 CANDIDATE 8449b521c96bb8340806ecda8649698f4771914a REVISION REQUIRED
B1-R1 GOVERNANCE REMOTE-VERIFIED AT 716b4d298173f8123cafd93114dfc67339943ff3
B1-R1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
5c656992d9fade3683b70e3c57f8b8ba7d26c7f7

Accepted Architecture Decision
ADR-0005 + M6 CONSUMER CONTRACT ACCEPTED AS ARCHITECTURE
G0 ACCEPTANCE ITSELF GRANTED NO IMPLEMENTATION AUTHORITY
B1 LATER SEPARATELY AUTHORIZED WITHIN FROZEN SCOPE

Completed Architecture Checkpoint
G0 COMPLETE / REMOTE-VERIFIED AT 92d1f3ac9e08c71458af04514baa659555fc55a7

Revision-Required Technical Candidate
G1 REMOTE-VERIFIED AT 0c283eb653e74784301620bdaf64bf451bb687dd
REVISION REQUIRED / NOT OWNER ACCEPTED / SUPERSEDED BY G1-R1

Accepted Corrected Technical Checkpoint
G1-R1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT
d44f471c644e319bb4a5bf73707c3274ecbaa426

Accepted Governance / Architecture Checkpoint
ACS-M6-P0-P1-R2-CLOSEOUT-G2 / M6-P2-G0

Accepted M6-P2 Technical Baseline
8227c6c616140824fd70de920dc6fcf459bb734d

M6 Series IP Bible + Character Intelligence
P0-P1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e38c75aa4ff26bdea80c82d8a24096f799dad860
P2-G0 ADR-0004 + SQLITE CONTRACT ACCEPTED / COMPLETE
P2-G1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 8227c6c616140824fd70de920dc6fcf459bb734d
G3 / P3-G0 OWNER ACCEPTED / COMPLETE AS GOVERNANCE-ARCHITECTURE / NO IMPLEMENTATION AUTHORITY
ADR-0005 + M6 CONSUMER CONTRACT ACCEPTED AS ARCHITECTURE / B1 OWNER ACCEPTED THROUGH B1-R1 / G1 BOUNDED IMPLEMENTATION AUTHORIZED
P3-B1 ORIGINAL CANDIDATE AT 8449b521c96bb8340806ecda8649698f4771914a / OWNER REVIEW REVISION REQUIRED / SUPERSEDED BY OWNER-ACCEPTED B1-R1
P3-B1 AUTHORIZED BASE 6bb9d165a693057f38e5789c408293ff0eaf5bcc
P3-B1 DOMAIN OWNERS M2 / M4 / M5 / M6 APPROVED
P3-B1 SCOPE 8 GOVERNANCE → 6 PRODUCTION + 9 TESTS → REMOTE VERIFY → STOP FOR OWNER REVIEW
P3-B1 VERSION POLICY INITIAL V1 / V1→V1 / EXPLICIT V1→V2 / V2→V2 / V2→V1 FORBIDDEN / UNBIND VIA NEW V2
P3-B1 CORE-ONLY OPERATION create_episode_plan_item_binding_version / NO ROUTE, HANDLER OR EXTERNAL DTO SOURCE CHANGE
P3-B1 OWNER HTTP CLARIFICATION EXISTING WORKSPACE VERSIONS V2 RESPONSE PASSES THROUGH episodePlanItemBindings / NO OTHER HTTP EXPANSION
P3-B1-F001 CLOSED BY OWNER-ACCEPTED B1-R1 / SQLITE SAME-PROJECT CROSS-SERIES FALSE DEPENDENCY
P3-B1-R1 AUTHORIZED BASE 8449b521c96bb8340806ecda8649698f4771914a
P3-B1-R1 GOVERNANCE REMOTE-VERIFIED AT 716b4d298173f8123cafd93114dfc67339943ff3
P3-B1-R1 SCOPE 8 GOVERNANCE → 1 PRODUCTION + 1 TEST → REMOTE VERIFY → STOP FOR OWNER REVIEW
P3-B1-R1 EVIDENCE PRE-FIX 409 REPRODUCED / SQLITE 30/30 / ORIGINAL B1 174/174 / FULL CORE 449/449 / AST 63/63
P3-B1-R1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7
P3-G1 ORIGINAL 3696d6af12222d30eb99b65d67e6db18897eb42f REVISION REQUIRED / SUPERSEDED
P3-G1-R1 OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT e172cc7c9bfca04066153d9edad70d9074bb37e5 / TREE be7447c3d60510262e428b86cd1a6a83972f64c0 / FULL CORE 464/464
CORE MAIN CONVERGED THROUGH PR #2 REBASE AND MERGE AT 5976263f92f7f9cbe9c091719eccb036ee8c0c2d / SAME TREE / POST-MERGE CI PASS
P3 AFTER G1 / M6-P4+ NOT AUTHORIZED / NOT STARTED

Architecture Risks
R-CORE-ARCH-001 CONFIRMED / HIGH / MONITORING / G1-R1 OWNER ACCEPTED
R-CORE-GOV-002 OPEN / NON-BLOCKING / AUDIT REPORT PROVENANCE

M7-M19
NOT STARTED / NOT AUTHORIZED

Formal 8765 Deployment
UNTOUCHED / NOT DEPLOYED

Frontend
FROZEN / UNTOUCHED

Production Ready
NO
```

旧仓库中的实现不得计入当前 Core 生产能力。`P3-RV1-003` 继续拥有该来源
审计债务；该债务为非阻塞项，不得被错误升级为当前 Core 能力。

M6 门禁顺序统一为：

1. R1 实施完成并通过独立复核；
2. R2 删除生命周期修复完成；
3. InMemory/SQLite 一致性、并发及 TOCTOU 验证通过；
4. RB1.3 全量回归通过；
5. RB1.3 正式关闭；
6. Architecture Review 通过；
7. M6 Preconditions 全部满足；
8. Project Lead 单独授权 M6-P1。

上述八项已由 Project Lead 于 `2026-08-13` 裁定为满足 bounded M6-P0/P1。
R2-P1 与 R2-P2 已接受，RB13-F002 已在当前测试基线关闭，PRE-M6-RB1.3 已正式
关闭。`ACS-M6-P0-P1-R2` 已在
`e38c75aa4ff26bdea80c82d8a24096f799dad860` 获得 Owner Acceptance。

Project Lead 进一步接受 ADR-0004 与 M6 SQLite Contract，并于 `2026-08-13`
接受 `ACS-M6-P2-G1` technical baseline
`8227c6c616140824fd70de920dc6fcf459bb734d` 为 `OWNER ACCEPTED / COMPLETE /
REMOTE-VERIFIED`。

`ACS-M6-P2-G1-CLOSEOUT-G3 / M6-P3-G0` 已在
`c524486c05c21b270a7dd75e89fae4312430736a` 完成远端验证。Project Lead 与
Architecture Owner 已接受 ADR-0005 和 M6 Consumer Contract 为规范架构；该接受
本身不授予实现权限。后续 Project Lead、Architecture Owner、Repository
Governance Owner 与 M2/M4/M5/M6 Domain Owners 已基于远端提交
`6bb9d165a693057f38e5789c408293ff0eaf5bcc` 单独授权 M6-P3-B1。该段保留当时
M6-P3-G1 尚未授权的时点历史；后续 G1 已单独授权并最终仅通过 G1-R1 获得
Owner Acceptance。原 proposal/review checkpoint 作为时点历史保留且不得改写。

代码审查确认 M1 AI Director、M3 Script Studio、M5 Series Director 与 Creator
Server composition 存在 Application 直接依赖 V4 的重复模式，违反固定的
`Application → V5 → V4` 相邻层链。该事实登记为 `R-CORE-ARCH-001 / CONFIRMED /
HIGH`。Project Lead 已明确选择 V5-owned Text Generation Capability，
同时以 Project Lead、Architecture Owner 和 Repository Governance Owner 身份接受
ADR-0006，并授权以下 bounded wave：

```text
ACS-ARCH-R1-V5-TEXT-GENERATION-G0
→ ACS-ARCH-R1-V5-TEXT-GENERATION-G1
→ STOP FOR OWNER REVIEW
```

规范合同为
[`V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md`](architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md)。
唯一接受的生产调用链是：

```text
Creator Application
→ V5 Text Generation Capability
→ V4 TextGenerationPort
→ Provider Adapter
```

G0 已在 `92d1f3ac9e08c71458af04514baa659555fc55a7` 完成远端验证。G1 已在
`0c283eb653e74784301620bdaf64bf451bb687dd` 完成四个 Application/V4 接触面迁移，
但其持续守卫存在动态导入别名缺口，所以该 SHA 保持历史 `REVISION REQUIRED /
NOT OWNER ACCEPTED`。G1-R1 在唯一 Contract Test 文件中建立 binding-aware AST
守卫和正反例矩阵，生产 diff 为零，并在
`d44f471c644e319bb4a5bf73707c3274ecbaa426` 完成远端验证。Project Lead 已明确
Owner Accept 该修正检查点，Architecture Remediation R1 因此关闭，
`R-CORE-ARCH-001` 转入持续监控。

`ACS-M6-P3-B1-R1-SQLITE-SERIES-ISOLATION` 的精确 8 路径治理检查点已在
`716b4d298173f8123cafd93114dfc67339943ff3` 远端验证；随后一个生产路径与一个
测试路径的修订已在 `5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` 完成远端
验证。`2026-08-14` Owner Review 独立复现原始错误并重跑完整回归后接受该
checkpoint。修订仅纠正 SQLite
exact-Series/suspicious-scope history selection 并隔离合法 other-Series plan；初始
v1、v1/v2 转换、历史绑定、Core-only operation 与 HTTP v2 pass-through 均保持不变。
该 B1-R1 时点尚未授权 M3/M6 consumer；后续 G1/G1-R1 已独立完成并接受。
Schema/Migration、正式 8765、Frontend、G1 之后的 M6 工作、M7+、V3、GPU、
Worker 或 ComfyUI 仍未授权；任何扩大 allowlist 的需要均立即停止。

Full Core Audit Report v1.2 的历史接受标签不在本次修复中重写；仓库内缺少可复核
报告实体/摘要引用的问题登记为 `R-CORE-GOV-002 / OPEN / NON-BLOCKING`，且该标签
不得作为 G1 实施授权依据。

---

# 63. Final Architecture Principle

整个系统长期坚持：

> Project First
> Production Spine First
> Domain Ownership Clear
> Ref + Version + Lineage Everywhere
> AI Generates Candidates
> Platform Owns Facts
> Human Controls Critical Gates
> Single-Episode Closure Before Batch Scale
> Real Production Before Platform Expansion
> GitHub Baseline After Every Accepted Capability

---

# 64. Final Production Spine

最终固定生产主脊柱：

```text
Workspace
↓
Content Profile
↓
Project
↓
AI Director
↓
Series
↓
Series Planning
↓
Series Bible / Character Intelligence
↓
Episode
↓
Episode CreativePlan
↓
Story Projection
↓
Script / ScriptVersion
↓
Consistency Validation
↓
Storyboard
↓
Shot
↓
Asset Requirement
↓
Asset / AssetVersion
↓
Video + Audio
↓
Timeline
↓
V3 Composition / Render
↓
Preview / QC / Approval
↓
Episode Master
↓
Series Release & Management
↓
Performance Data
↓
AI Director / Content Profile Feedback
```

未来所有新功能：

必须能够找到自己在这条 Production Spine 中的位置。

找不到位置的功能：

默认不开发。

---

# End of System Master Plan
