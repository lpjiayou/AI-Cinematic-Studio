# ADR-0016 — M13 Timeline, Render Candidate and Deterministic Post Boundary

## 文档元数据

| 字段 | 填写内容 |
| --- | --- |
| ADR ID | `ADR-0016` |
| Title | M13 Timeline, Render Candidate and Deterministic Post Boundary |
| Status | `Accepted` |
| 作者 | AI Cinematic Studio Architecture Checkpoint |
| 创建日期 | `2026-08-30` |
| 最后更新日期 | `2026-08-30` |
| 审批人 | Project Lead / Architecture Owner / M13 Domain Owner |
| Decision Ref | `ACS-M12-M13-ARCHITECTURE-CORRECTION-20260830` |
| 关联事项 | M13 Timeline；deterministic post；RenderCandidate；M14/M15 boundary；System Master Plan；Golden Contract |
| Supersedes | 无；Decision Ref 取代冲突的 `ACS-M12-RUNTIME-G0-UNBLOCK-AND-M13-BACKEND-COMPLETION` 原始实现授权 |
| Superseded by | 无 |

## ADR ID

`ADR-0016`

该编号是在扫描全部既有 `governance/ADR-*.md`、确认新分配的 `ADR-0015` 后取得的
连续、未使用编号。编号不得修改、覆盖或复用。

## Title

M13 Timeline, Render Candidate and Deterministic Post Boundary

## Status

`Accepted`

Project Lead、Architecture Owner 和 M13 Domain Owner 已通过 Decision Ref
`ACS-M12-M13-ARCHITECTURE-CORRECTION-20260830` 批准本决策。

`Accepted` 只表示下述架构边界获批。Architecture Checkpoint 合入前，不授权业务
代码、schema、migration、runtime 或依赖；合入后也不得把架构接受写成
`M13_BACKEND_CAPABILITY_COMPLETE=true`，不得扩张到 M14/M15、GPU、Provider、
资产准入或发布。

## Context

M13 是 Timeline、V3 Composition 和 deterministic render 的里程碑；M14 负责
Preview/QC/Approval/Local Regeneration，M15 负责 EpisodeMaster 与正式输出。

当前 Core 已有由 `K2DeliveryService` 和 V5 Episode Production lineage/persistence
管理的最小 TimelineVersion、TimelineClip、PreviewCandidate 技术证据路径，以及
精确汉字显形的 V5 Requirement、V4 执行边界和 V3 FFmpeg 合成能力。这些现有事实
保持不可变历史，但不构成完整 Timeline、Master、Export、Asset Admission 或发布。

当前边界缺口包括：完整 Clip 编辑语义尚未形成；八项确定性后期仅第一项有实现
基础；其余七项不能继续交由 M11 自由扩散模型承担；上位规范尚未定义供 M14 QC
使用的非发布 RenderCandidate；若 M13 创建 ExportCandidate、EpisodeMaster 或
ExportArtifact，会绕过 M14 QC/Approval 与 M15 权威。

本 ADR 不实现 M14 QC/Approval、M15 Master/Export、Frontend、GPU 或 Provider，
也不创建第二 Timeline/AssetVersion/Preview authority、M13 sidecar database 或
K2 专用 Timeline model。

## Decision

### 1. Timeline 保持单一权威

Timeline / TimelineVersion 的唯一权威继续是：

```text
K2DeliveryService
+
V5 Episode Production lineage/persistence
```

| 层或里程碑 | 负责 | 明确不得负责 |
| --- | --- | --- |
| V5 Episode Production / `K2DeliveryService` | Timeline、TimelineVersion、TimelineClip、Composition、CompositionVersion、PreviewCandidate、RenderCandidate、RenderManifest 的权威 ref/version/digest、血缘、持久化、staleness 和 replay | FFmpeg 执行、worker 编排、EpisodeMaster、ExportArtifact、publication eligibility |
| V4 Platform | closed/sealed execution request、job/attempt、runtime orchestration、路径与 artifact 验证 | Timeline/Preview/Render 领域权威、AssetVersion admission、QC/Approval、Master、Export |
| V3 Render Core | Timeline execution、composition、CPU/FFmpeg deterministic post、preview/render 编码 | 生产领域事实、Timeline persistence、QC/Approval、Master、Export、发布 |
| M14 | 对精确 Candidate 形成 QCReport 与显式 ApprovalDecision | 重写 Timeline、把 job success 当作批准、创建 Master/Export |
| M15 | 在完整且非 stale 的 M14 QC/Approval 后创建 EpisodeMaster 与 ExportArtifact | 绕过 Timeline、Candidate、QC 或 Approval |

禁止第二 Timeline authority、第二 AssetVersion authority、第二 Preview authority、
M13 sidecar database、K2 专用 Timeline model，以及 V3/V4 自行持久化权威领域事实。
本地文件、FFmpeg 返回值或 V4 job success 均不能直接成为权威对象。

### 2. M13 允许与禁止的输出

M13 可以创建：

- `Timeline`；
- `TimelineVersion`；
- `TimelineClip`；
- `Composition`；
- `CompositionVersion`；
- `PreviewCandidate`；
- `RenderCandidate`；
- `RenderManifest`。

这些对象必须具有稳定 opaque ref、workspace/run ownership、immutable version、
canonical payload digest、精确上游 ref/version/digest、staleness 语义，以及既有 V5
persistence 的幂等、restart 和 replay 能力。TimelineVersion 变更创建新版本，不得
原地覆盖；调用方任意绝对路径不得成为权威引用。

M13 不得创建：

- `ExportCandidate`；
- `ExportArtifact`；
- `EpisodeMaster`；
- `Work`；
- `ReleasePackage`；
- publication eligibility；
- 任何功能等价但以其他名称绕过禁令的对象。

不得新增 `ExportCandidate` schema、class、table、repository、event、route、
projection 或 fixture，也不得把任一 Candidate/Manifest 重命名或解释为 Export。

### 3. RenderCandidate 是非发布技术候选

每个 `RenderCandidate` 必须：

- 精确绑定一个非 stale TimelineVersion ref/version/digest；
- 绑定 CompositionVersion、RenderManifest、artifact evidence 与 render result；
- 记录 render profile、分辨率、codec、字幕模式、输出摘要和 probe 事实；
- 可作为 M14 QC 的精确输入；
- immutable、digest-sealed 且 restart-readable；
- 不形成 AssetVersion admission；
- 不直接进入发布、下载交付或 Master 权威。

服务端固定产生以下状态，调用方不得提交或覆盖：

```text
publicationAllowed=false
masterState=NOT_CREATED
exportState=NOT_CREATED
```

可播放不等于可交付、可发布、已批准或已成为 Master。

### 4. M15 独占 EpisodeMaster 和 ExportArtifact

唯一正式链保持为：

```text
TimelineVersion
→ PreviewCandidate and/or RenderCandidate
→ M14 QCReport
→ explicit ApprovalDecision
→ M15 EpisodeMaster
→ M15 ExportArtifact
```

只有 M15 可以创建 `EpisodeMaster` 和 `ExportArtifact`。QCReport 只是评估事实，
不会自动批准 Candidate。Candidate 的存在不能使状态机直接进入 `MASTER_READY`；
缺失、拒绝、stale 或摘要不匹配的 QC/Approval 必须阻止 M15。

### 5. 八项确定性后期全部归属 M13

1. 精确汉字显形；
2. 刮痕和光带动画；
3. 灯焰熄灭；
4. 烟雾；
5. 局部曝光变化；
6. 名牌文字；
7. 距离和状态变化；
8. 面部小痣或旧疤补偿。

每项必须通过同一受控链：

```text
V5 deterministic-post Requirement
→ V4 closed sealed execution request
→ V4 job/runtime orchestration
→ V3 CPU/FFmpeg deterministic execution
→ immutable artifact evidence
→ digest-bound result
→ Timeline Effect Clip
→ PreviewCandidate and/or RenderCandidate integration
→ V5 persistence and replay
```

每项必须具有 closed-world Requirement、精确 shot/time/frame 与 AssetVersion 绑定、
无隐藏随机项的确定性参数、sealed request、artifact/result 摘要、Effect Clip、
Preview/Render 集成、restart/replay 和 fail-closed 负例。相同输入、参数和固定工具链
必须产生相同的合同定义内容摘要。工具或参数变化形成新版本和新证据。

八项均不得由自由扩散视频模型替代。M11 可以提供不含该确定性事件的基底片段，
但不拥有事件的最终时间、状态或合成事实。

### 6. Composition 与 RenderManifest 边界

Composition 是对精确 TimelineVersion 的确定性组合描述；语义变化创建新的
CompositionVersion。V3 只执行 V5/V4 已封装和密封的 composition，不得补充未声明
的 clip、effect、subtitle、transition、color、audio 或 delivery 参数。

RenderManifest 精确绑定 TimelineVersion、CompositionVersion、选定的 Video/
Audio/Subtitle/Effect clips、全部输入 ref/version/digest、render profile、V3/
FFmpeg identity、参数摘要和验证合同。缺失、stale、跨 workspace、摘要不匹配或
unsupported profile 必须在执行前 fail closed。

### 7. CPU-only 和非发布边界

本 ADR 后续授权的 M13 轨道是 CPU-only，继续保持：

```text
A100_START_AUTHORIZED=false
GPU_CALLS_ALLOWED=false
PROVIDER_CALLS_ALLOWED=false
CANONICAL_MUTATIONS=0
ASSET_ADMISSION=0
PUBLICATION_ALLOWED=false
LEGACY_MEDIA_WRITES=0
```

不得调用自由扩散模型、创建或准入 AssetVersion、修改 live canonical K2 lineage，
或创建 M14/M15 事实。M12-C3/C4 的环境 hold 不阻止独立 M13 CPU 轨道。

## Alternatives

### 方案 A：保持最小 Timeline/Preview 范围

- 概述：不扩展完整 Timeline、其余七项后期或 RenderCandidate。
- 优点：短期改动最小。
- 缺点：M13 不完整，确定性事件继续缺少正确 Owner。
- 风险与约束：M14 无完整、精确、可重复的 QC 输入。
- 未采纳原因：不能满足已批准的 M13 CPU 后端范围。

### 方案 B：建立 M13/K2 独立 Timeline 数据库

- 概述：新建 sidecar database、专用 Timeline model 或 Preview store。
- 优点：局部实现可能更快。
- 缺点：产生第二权威并复制 workspace/version/staleness 规则。
- 风险与约束：V5 与 sidecar 的 restart/replay 会分叉。
- 未采纳原因：违反单一权威。

### 方案 C：在 M13 创建 ExportCandidate

- 概述：把达到技术交付规格的 RenderCandidate 提升为 ExportCandidate。
- 优点：表面上缩短交付路径。
- 缺点：候选命名掩盖 Master、Export、QC 和 Approval 的权威差异。
- 风险与约束：绕过 M14/M15 并可能直接交付或发布。
- 未采纳原因：`ExportCandidate` 被明确禁止。

### 方案 D：继续由 M11 扩散模型生成确定性事件

- 概述：用生成提示词表达显字、灯灭、光带等事件。
- 优点：无需新增确定性合成能力。
- 缺点：时间、形状、文字与状态不可精确复现。
- 风险与约束：无法满足 deterministic repeatability 与精确 QC。
- 未采纳原因：八项事实 Owner 已冻结为 M13。

### 方案 E：复用 V5 权威、V4 编排和 V3 CPU/FFmpeg

- 概述：采用本 ADR Decision，并把 Master/Export 留给 M15。
- 优点：不增加第二权威，保留 lineage、staleness、replay 与 M14/M15 门禁。
- 缺点：需要分阶段扩展领域、持久化、执行和渲染合同。
- 风险与约束：必须持续阻止 RenderCandidate 被解释为 Master/Export。
- 采纳结论：与 Decision Ref 的冻结决定一致。

## Consequences

### 正向影响

- Timeline、Candidate 和 deterministic post 位于同一 V5 lineage；
- V3 专注确定性执行，不获得生产事实或批准权威；
- 八项精确后期不再依赖自由扩散模型；
- RenderCandidate 为 M14 提供精确、可重复、非发布的输入；
- M15 Master/Export 门禁不可由 Candidate 命名绕过。

### 负向影响与成本

- 需要扩展 TimelineClip、CompositionVersion、RenderManifest 和 RenderCandidate；
- 七项新效果各自需要 Requirement、sealed request、executor、evidence、result 和 replay；
- FFmpeg identity、参数和内容摘要必须固定；
- CPU-only 渲染可能较慢，但性能不构成越权使用 GPU 的理由。

### 风险

- `R-M13-BOUND-023`：Timeline/M15 边界绕过；
- `R-K2-LIN-005`：Timeline/Clip/Candidate lineage 或 restart replay 不完整；
- `R-K2-QC-009`：render success 或 machine QC 被解释为 human approval；
- `R-K2-PUB-010`：publication 状态被调用方或 Candidate 越权写入；
- 工具链漂移：输出摘要变化时必须创建新版本，不能重解释旧证据。

### 受影响资产

- 架构文档：System Master Plan、Golden Contract、Current Milestone、Risk Register、本 ADR；
- 后续契约：Timeline/Clip、Composition、Candidate/Manifest、八类 Requirement/result；
- 执行边界：V4 sealed request 与 V3 CPU/FFmpeg composition；
- 质量门禁：closed-world、repeatability、persistence/replay、M13/M15 boundary guards；
- 发布规则：no ExportCandidate、no M13 Master/Export、no publication。

## Migration Plan

### 1. Architecture Checkpoint 前置条件

Architecture Checkpoint 必须同时包含 ADR-0015、ADR-0016 和上位规范同步，仅修改
治理/架构文件。它必须通过 Markdown、Documentation Links、Unit Tests、Contract
Tests 和 Integration Tests 五项 required checks，以 squash 方式合入并核验远端
SHA/tree。在此之前不得开始业务代码、schema、migration 或 runtime 实现。

### 2. 分阶段实施

1. `M13-T1`：完整 Timeline / TimelineVersion / Clip 编辑语义；
2. `M13-E1`：刮痕、光带、局部曝光；
3. `M13-E2`：灯焰熄灭、烟雾；
4. `M13-E3`：名牌文字、面部标记；
5. `M13-E4`：距离和状态变化；
6. `M13-R1`：PreviewCandidate / RenderCandidate / RenderManifest；
7. `M13-R2`：完整 CPU 后端垂直验收。

每项使用独立单一职责 PR，并从当时最新 `origin/main` 开始。精确汉字显形只接入
统一 Effect Clip 和 Preview/Render 链，不重写既有历史。

### 3. 兼容、验证与停止条件

- 既有 Timeline、PreviewCandidate 与 Glyph 事实保持不可变历史，不自动改名、
  回填、提升 authority 或重算 digest；
- 如后续需要 migration，必须 additive、单事务、幂等、restart-safe，并保持旧 row、
  digest 与 typed readback；未知、部分或 tampered schema fail closed；
- 必须验证 workspace/ref/version/digest、staleness、path safety、repeatability、
  artifact/probe、Effect Clip、Candidate、SQLite restart/replay 和 Public API；
- 必须验证 ExportCandidate 不存在，M13 创建 EpisodeMaster/ExportArtifact 数量为零，
  RenderCandidate 不能直达 `MASTER_READY`；
- 如需第二 authority、sidecar、ExportCandidate、M13 Master/Export、V3/V4 领域持久化、
  GPU/Provider/A100、diffusion、canonical mutation、Admission 或 legacy write，立即停止；
- 回滚仅撤销当前未接受代码/事务并保留已有 immutable 历史，不得删除历史、重算摘要、
  降级 schema 或把 Candidate 提升为 Master/Export。

只有完整 Timeline、Clip editing、8/8 deterministic post、PreviewCandidate、
RenderCandidate、SQLite restart、Public API、repeatability 全部通过，且无
EpisodeMaster、ExportArtifact、ExportCandidate，才可记录：

```text
M13_BACKEND_CAPABILITY_COMPLETE=true
```

### 4. 责任人与目标事件

- 决策责任：Project Lead / Architecture Owner / M13 Domain Owner；
- V5 权威复核：V5 Episode Production owner；
- V4/V3 边界复核：Platform/Render Core owners；
- 实施责任：各独立 M13 PR 的指定实现者；
- 目标事件：严格按 T1 → E1 → E2 → E3 → E4 → R1 → R2；
- 沟通对象：Project Lead、Architecture Owner、M13 Domain Owner。

### 5. 旧设计停止使用和归档

Architecture Checkpoint 合入时，`ExportCandidate`、M13 delivery-candidate
authority、RenderCandidate 直达 `MASTER_READY`、M13 创建 Master/Export，以及由
M11 自由扩散模型承担八项确定性事件的设计立即停止作为实施依据。相关旧命令只保留
为历史审计事实，不得删除或重新启用；本 ADR 及其 Decision Ref 成为后续 M13-T1
至 R2 的当前架构依据。既有 Timeline、PreviewCandidate 和 Glyph 技术证据继续按
原合同保留，不自动改名、升级 authority、回填或重算摘要。

## Phase 0 使用边界

本 Architecture Checkpoint 只记录和保护架构决策，不授权业务代码、数据库表、
migration、Timeline/RenderCandidate 实现、fixture、依赖、FFmpeg/runtime 安装、
GPU/Provider、A100、canonical mutation、Asset Admission、M14/M15、Master、Export
或 publication。

Checkpoint 合入后的实现权限来自本 Accepted ADR、Decision Ref、当前
Source-of-Truth 和当时最新无冲突 main；不得扩展到明确关闭的边界。

## 审批记录

| 角色 | 审批人 | 结论 | 日期 | 备注 |
| --- | --- | --- | --- | --- |
| Project Lead | Decision Ref 中的批准主体 | `APPROVED` | `2026-08-30` | 批准单一 Timeline 权威、RenderCandidate 非发布边界与 M15 Master/Export 所有权 |
| Architecture Owner | Decision Ref 中的批准主体 | `APPROVED` | `2026-08-30` | 批准 V5/V4/V3 分层及 Architecture Checkpoint 顺序 |
| M13 Domain Owner | Decision Ref 中的批准主体 | `APPROVED` | `2026-08-30` | 批准八项 deterministic post 与完整 CPU backend 实施范围 |

## 变更历史

| 日期 | 修改人 | 变更内容 | 审批依据 |
| --- | --- | --- | --- |
| `2026-08-30` | AI Cinematic Studio Architecture Checkpoint | 创建并接受 ADR-0016；冻结 M13 Timeline/RenderCandidate/deterministic post 边界和 M15 EpisodeMaster/ExportArtifact 独占所有权 | `ACS-M12-M13-ARCHITECTURE-CORRECTION-20260830` |
