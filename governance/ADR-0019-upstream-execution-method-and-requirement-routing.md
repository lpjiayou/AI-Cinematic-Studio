# ADR-0019 — Upstream Execution Method and Requirement Routing

## 文档元数据

| 字段 | 填写内容 |
| --- | --- |
| ADR ID | `ADR-0019` |
| Title | Upstream Execution Method and Requirement Routing |
| Status | `Accepted` |
| 创建日期 | `2026-09-02` |
| 最后更新日期 | `2026-09-03` |
| 审批人 | Project Lead / Architecture Owner / M3–M12 Domain Owners |
| Decision Ref | `ACS-M3-M11-UPSTREAM-METHOD-CLOSURE` |
| Extends | `ADR-0005`, `ADR-0015`, `ADR-0016`；不替代其既有决定 |
| Supersedes | 无 |
| Superseded by | 无 |
| Scope amended by | [`ADR-0020`](ADR-0020-m12-cpu-build-host-and-a100-offline-consumer.md)；仅第 10 节与 Migration Plan 第 8 项的 A100 C3 假设被局部 supersede |

## ADR ID

`ADR-0019`

该编号是在确认 `ADR-0018` 为当前最大已用编号后连续分配。编号不可修改、覆盖或
复用。

## Status

`Accepted`

Project Lead、Architecture Owner 与 M3–M12 Domain Owners 已通过
`ACS-M3-M11-UPSTREAM-METHOD-CLOSURE` 接受本决策，并授权在本架构检查点合入后
严格串行执行 PR-B 至 PR-F 与最终 Frontend 行为 pin。

本状态只接受架构和明确的后续有界实施波，不表示 M3–M12 的下述机制已经实现，
不表示 Contact/Gait/Audio runtime 已安装，也不授权 A100、GPU、Provider、资产准入、
live canonical mutation、Master、Export 或 publication。

## Context

当前 Core 已有 M3 ScriptVersion、M6 active Episode baseline reader、K2 范围内的
Storyboard/Shot/AssetRequirement/GenerationRequest 证据、M11 Wan I2V adapter、M12
音频领域及隔离运行时协议，以及已接受的 M13 deterministic CPU backend。它们没有
共同证明一般产品链已按执行方法闭合。

已确认的上游机制缺口是：新 ScriptVersion 没有不可变绑定影响它的精确 M6 baseline；
M7 的通用验证、Finding、staleness 和 M8 readiness 未形成；M8 没有结构化动作 beat
和关闭式执行分类；M9 仍可能把一个 Shot 无条件映射成视频和音频请求；M10/M11 没有
按方法区分所需 conditioning 输入及当前真实能力；M12 还缺少对显式 M9
AudioRequirement 的唯一入口；Creator capability projection 可能把局部仓库事实、
runtime 未安装和产品完成混为一谈。

这些缺口不能通过 K2 专用分支、复制 M6/Identity/Shot/Asset 事实、默认 Wan fallback
或建立 sidecar database 关闭。新设计必须复用现有 ScriptVersion SQLite content/schema
projection、Episode Production evidence journal、canonical AssetVersion authority、
MediaJobCoordinator 和唯一 Timeline authority。

## Decision

### 1. Production Spine 与 Owner

本波唯一生产主链固定为：

```text
Confirmed ScriptVersion
→ M6ConsumerBinding
→ M7 ConsistencyValidation
→ M8 Storyboard / CreativeShot / ActionExecutionBeat
→ M9 Visual / Audio / Postprocess Requirements
→ M10 Image / Conditioning Asset Production
→ M11 Video Production
→ M12 Audio Production
→ M13 Timeline / Composition / Render
```

Owner 固定为：

| 里程碑 | 唯一 Owner |
| --- | --- |
| M3 | ScriptVersion |
| M6 | SeriesBible、CharacterContinuity、M6BaselineSnapshot |
| M7 | ConsistencyValidation、Finding、result、M8 readiness 与 staleness |
| M8 | Storyboard、CreativeShot、ActionExecutionBeat |
| M9 | VisualExecutionRequirement、AudioRequirement、PostprocessRequirement 与 routing disposition |
| M10 | Image 和 conditioning Asset production planning |
| M11 | video method execution |
| M12 | audio production |
| M13 | Timeline、composition、deterministic post 与 render |

既有 V5 Identity authority 保持身份权威；`K2AuthorityIdentityService` 只提供已接受的
Identity reference projection。`M6EpisodeBaselineInput` 与
`IdentityReferenceVersionProjection` 是两个独立、只读且分别摘要绑定的输入；Identity
facts 不得写入 M6 baseline。

### 2. M3 ScriptVersion 与 M6ConsumerBinding

所有在本决策生效后受 M6 影响的新建或 rewrite ScriptVersion 必须由服务端调用
`ActiveM6BaselineReader`，并不可变保存关闭式 `M6ConsumerBinding`：

```text
workspaceRef
projectRef
seriesRef
episodeRef
seriesPlanVersionRef
seriesPlanVersionDigest
m6BaselineSnapshotRef
m6BaselineCanonicalDigest
activationRevision
seriesBibleVersionRef
seriesBibleVersionDigest
characterContinuityVersionRef
characterContinuityVersionDigest
payloadDigest
```

`payloadDigest` 是上述全部语义字段的 canonical SHA-256，不包含普通时钟值。客户端
不得提交 raw binding、任一 M6 digest 或 activation revision。M3 继续拥有 ScriptVersion；
M6 不得创建、编辑、确认、替换或修正 ScriptVersion。

历史 ScriptVersion v1 保持字节和摘要可读，不回填、不推断、不重新绑定。受 M6 影响的
create/rewrite 使用 additive successor schema；修改 ScriptVersion 或 current M5/M6
baseline 只会使旧 binding 变为 `STALE`，不会改写历史。

首选且唯一获授权的持久化方式是现有 ScriptVersion SQLite `content_json`/schema
projection 的 additive version dispatch。若实现需要新表、新数据库、独立 binding
repository 或第二 ScriptVersion authority，实施必须停止。

### 3. M7 通用叙事验证

M7 拥有不可变 `ConsistencyValidationVersion`，每个版本精确绑定：

- confirmed ScriptVersion ref/digest；
- 该 ScriptVersion 的 M6ConsumerBinding 与 digest；
- current `M6EpisodeBaselineInput` ref/digest components；
- Workspace/Project/Series/Episode scope；
- validation profile ref/version/digest。

`result` 是关闭集 `PASS|WARN|BLOCK`。Finding category 的首版关闭集恰好为：

```text
WORLD_RULE_CONFLICT
TIMELINE_CONFLICT
LOCATION_CONFLICT
PROP_STATE_CONFLICT
CHARACTER_STATE_CONFLICT
RELATIONSHIP_CONFLICT
FORBIDDEN_BEHAVIOR
DIALOGUE_RULE_CONFLICT
UNRESOLVED_REFERENCE
SOURCE_BINDING_STALE
```

每个 Finding 保存稳定 ref、category、severity、精确 Script source span、规则来源
ref/digest、证据与 payload digest。自由文本不能替代 category。

M8 readiness 固定为：

```text
PASS  → READY_FOR_M8
WARN  → NOT_READY_PENDING_DISPOSITION
BLOCK → NOT_READY
```

本波不实现 WARN waiver。ScriptVersion、binding、M5/M6 source 或 profile 任一漂移使
validation 为 `STALE`，stale validation 不得进入 M8。M7 不自动修改剧本、不创建
ScriptVersion、不把 WARN 当 PASS、不创建 human Approval，也不写入 M6。

持久化必须复用 existing Episode Production evidence journal 或另一已确认的唯一边界。
需要新数据库或并行 persistence authority 时停止。

### 4. M8 ActionExecutionBeat

Storyboard/CreativeShot 使用 additive v2，并为每个 Shot 保存
`actionExecutionBeats[]`。每个 beat 至少包含：

```text
beatRef
beatOrder
sourceSpan
sourceTextDigest
subjectRefs[]
targetRefs[]
frameRangeStartInclusive
frameRangeEndExclusive
executionClass
postprocessRequirementKey
payloadDigest
```

`sourceSpan` 由服务器从 exact ScriptVersion 解析，关闭字段为
`scriptSceneRef`、`sourceField`、`sourceIndex`、`startOffsetInclusive` 和
`endOffsetExclusive`。`sourceField` 只允许 `ACTION|DIALOGUE|NARRATION|SUBTITLE_TEXT`；
`sourceIndex` 在 `DIALOGUE`、`NARRATION` 和 `SUBTITLE_TEXT` 中选择该 scene 的精确
数组项，`ACTION` 固定为 0。
`sourceTextDigest` 对该范围内精确文本计算 SHA-256。

`executionClass` 关闭集为：

```text
STATIC_HOLD
MICRO_MOTION
CONTACT_ACTION
GAIT_LOCOMOTION
DETERMINISTIC_EVENT
```

Camera instruction 与主体动作分类必须分离；Camera movement 不能充当 actor movement。
frame range 必须落在 Shot 的 `[0, frameCount)` 内，同一主体的 beat 不得重叠。Shot
中未被动作 beat 覆盖的帧必须由显式 `STATIC_HOLD` beat 覆盖。
`DETERMINISTIC_EVENT` 必须绑定非空 `postprocessRequirementKey`；其他 class 禁止携带
该 key。M8 只消费 current `READY_FOR_M8` validation。v1 Storyboard/CreativeShot
保持历史可读与 exact replay。

### 5. M9 三轴需求与 disposition

M9 从 ActionExecutionBeat 派生三个正交集合：

```text
VisualExecutionRequirements[]
AudioRequirements[]
PostprocessRequirements[]
```

每个 requirement 具有稳定 ref、source beat/shot/version ref+digest、关闭式 type/method、
disposition 和 payload digest。Disposition 关闭集为：

```text
REUSE_EXISTING_ASSET
GENERATE_NEW_ASSET
DERIVE_DETERMINISTIC_POSTPROCESS
CAPABILITY_UNAVAILABLE
NO_ASSET_REQUIRED
```

视觉映射固定为：

| executionClass | visual method | 路由结果 |
| --- | --- | --- |
| `STATIC_HOLD` | `STATIC_PLATE_OR_REUSE` | 复用、静态 plate 或无需资产；不得无条件生成视频 |
| `MICRO_MOTION` | `SINGLE_ANCHOR_I2V` | 进入 M10 anchor 规划，满足条件后才可进入 M11 |
| `CONTACT_ACTION` | `CONTACT_CONDITIONED_VIDEO` | 需要 contact conditioning；当前执行能力可为 unavailable |
| `GAIT_LOCOMOTION` | `POSE_OR_TRAJECTORY_CONDITIONED_VIDEO` | 需要 pose/trajectory conditioning；当前执行能力可为 unavailable |
| `DETERMINISTIC_EVENT` | `V3_DETERMINISTIC_COMPOSITION` | 创建 PostprocessRequirement，绝不进入 M11 |

AudioRequirement type 首版关闭集为
`DIALOGUE|NARRATION|AMBIENCE|SFX|MUSIC|SILENCE`。`DIALOGUE` 与 `NARRATION` 必须
绑定精确 sourceSpan；`SILENCE` 不创建 GenerationRequest。视觉 class 不自动决定
audio：GAIT 可有脚步 SFX 但不强制，STATIC_HOLD 可有对白/环境声，
DETERMINISTIC_EVENT 可有独立 SFX 或无声。一个 Shot 可有零个或多个 AudioRequirement。

v2 禁止 `one shot → unconditional video request + unconditional audio request`。
method planning 与 provider dispatch 是不同阶段。历史
`v5.asset-requirement.v1`、`v5.generation-request.v1` 和
`v5.asset-resolution-manifest.v1` 保持可读、不可重解释。

### 6. M10 方法感知输入规划

M10 继续复用唯一资产链：

```text
Candidate
→ TechnicalValidation
→ SemanticVisualQC
→ HumanSelection
→ AssetAdmission
→ AssetVersion
```

输入规划固定为：

| method | 必需输入 |
| --- | --- |
| `STATIC_PLATE_OR_REUSE` | existing plate 或 static plate requirement |
| `SINGLE_ANCHOR_I2V` | action-ready single anchor |
| `CONTACT_CONDITIONED_VIDEO` | contact-ready conditioning assets |
| `POSE_OR_TRAJECTORY_CONDITIONED_VIDEO` | pose / trajectory conditioning assets |
| `V3_DETERMINISTIC_COMPOSITION` | event-free base plate 与明确 mask/resource/static asset requirements |

缺少方法所需输入时返回 blocker，不得静默降级。K2 exact-four 是历史项目专用
revision contract，不得成为通用项目限制。历史 K2 real-media revision v1 保持可读；
不得创建第二 Candidate、QC、Selection、Admission 或 AssetVersion authority。本波不
安装图像模型、不产生 live admission。

### 7. M11 多方法能力边界

M11 video method capability 关闭集为：

```text
SINGLE_ANCHOR_I2V
CONTACT_CONDITIONED_VIDEO
POSE_OR_TRAJECTORY_CONDITIONED_VIDEO
```

现有 `self-hosted-wan22-image-to-video-v1` 只可绑定：

```text
MICRO_MOTION + SINGLE_ANCHOR_I2V
```

禁止 CONTACT_ACTION 或 GAIT_LOCOMOTION fallback 到 SINGLE_ANCHOR_I2V；禁止把
DETERMINISTIC_EVENT 转成 Wan prompt；禁止为 STATIC_HOLD 创建无意义视频。当前能力
事实为：

```text
CONTACT_CONDITIONED_VIDEO=CAPABILITY_UNAVAILABLE
POSE_OR_TRAJECTORY_CONDITIONED_VIDEO=CAPABILITY_UNAVAILABLE
```

`CAPABILITY_UNAVAILABLE` 是正确的 fail-closed planning 结果，不是系统故障。M11
复用现有 MediaJobCoordinator，不建立第二 queue。本波不安装 Contact/Gait 模型、不
启动 ComfyUI、不提交 `/prompt`。

### 8. M9 → M12 显式音频桥

唯一音频链为：

```text
M9 AudioRequirement
→ M12 AudioGenerationRequest
→ typed Audio AssetVersion
→ AudioCue
→ M13 Timeline
```

AudioGenerationRequest 必须绑定 AudioRequirement ref/digest、ScriptVersion
ref/digest、sourceSpan、CreativeShotVersion ref/digest、speaker characterRef、
audioRole 与 timing reference；需要 clone 时还必须绑定 current Consent、VoiceLock、
VoiceProfile 的精确 ref/version/digest。SFX/Ambience 不得伪装成 TTS，SILENCE 不
创建请求，MUSIC 未实现时必须显式返回 `NOT_IMPLEMENTED`。

M12 不再以 M11 为通用前置依赖。M12 继续拒绝 legacy sine media 写路径，保留已接受
runtime protocol，但真实 runtime 仍未安装，Runtime G0 仍未完成。

### 9. Creator capability projection

公共 capability projection 必须区分 repository/backend 事实、runtime 安装、产品面和
production authority。只能复用现有状态关闭集：

```text
available
authority_required
local_evidence_only
production_policy_required
not_open
```

不得新增自由状态字符串。M12 不得把 M11 作为通用硬依赖，必须显示 Runtime G0 未
完成；M13 base backend 与 product surface 状态不得混淆；已存在的 RenderCandidate
资源应准确投影；不得声明 M12/M13 production ready。若这些事实无法用现有 schema
准确表达，实施必须停止并单独提出 capability projection v2。

### 10. M12 后续主机与本波运行边界

M12-C3/C4 未来目标主机记录为 `A100_CODE_SERVER_BUILD_HOST`，但本波保持：

```text
M12_RUNTIME_G0=NOT_COMPLETE
M12_C3_READY_TO_START=false
A100_START_AUTHORIZED=false
A100_GPU_EXECUTION_AUTHORIZED=false
```

未来独立授权可只允许主机启动和 CPU build，并继续要求
`CUDA_VISIBLE_DEVICES=""`、`COMFYUI_START_ALLOWED=false`、
`MODEL_INFERENCE_ALLOWED=false`。本 ADR 与当前实施波不启动 A100。

## Alternatives

### 方案 A：保持 K2 专用、每镜无条件生成

- 优点：局部改动最小。
- 缺点：不能证明非 K2 通用链，静态镜头浪费生成，动作方法错误。
- 未采纳原因：无法关闭当前确认的产品机制缺口。

### 方案 B：所有动作继续使用单锚 Wan I2V

- 优点：只维护一个现有 adapter。
- 缺点：Contact/Gait 缺少所需 conditioning，确定性事件不可精确复现。
- 未采纳原因：会把能力缺失伪装成 fallback，并重复已确认的 SH12 机制错误。

### 方案 C：分别建立 M7、M9、M12 sidecar store

- 优点：局部实现表面独立。
- 缺点：复制 scope、version、digest、replay 和 owner，产生并行权威。
- 未采纳原因：违反唯一 persistence/authority 边界。

### 方案 D：采用不可变 binding、结构化 beat、三轴需求和 fail-closed routing

- 优点：上游事实可追溯，方法与能力事实准确，音视频真正并行。
- 缺点：需要多个严格串行的有界 PR 和 additive compatibility。
- 采纳结论：本 ADR 的决定。

## Consequences

### 正向影响

- 新 ScriptVersion 可证明使用了哪一版 M5/M6 事实；
- M7 currentness 与 M8 readiness 可确定重放；
- Camera、actor action 和 deterministic event 不再混淆；
- M9 不再无条件产生视频与音频请求；
- M10/M11 能准确表达方法输入与尚未安装的能力；
- M12 从显式 AudioRequirement 并行进入 Timeline；
- 一般非 K2 CPU fixture 可证明链路而不调用 GPU/Provider。

### 负向影响与成本

- 需要 additive Script、Storyboard/Shot 和 requirement schemas；
- M7、M8/M9、M10/M11、M9/M12 必须分别维护 exact replay 和 staleness；
- Contact/Gait 在 runtime 安装前会明确返回 unavailable；
- 公共 projection 必须谨慎保持 Frontend 现有 closed validation。

### 风险

由风险登记册 `R-UPSTREAM-LIN-035` 至 `R-UPSTREAM-PROJ-041` 跟踪 binding 漂移、
validation staleness、beat 分类、三轴需求、Wan fallback、音频桥和 projection 失真。

### 受影响资产

- 架构：System Master Plan、责任矩阵、本 ADR 与
  `M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md`；
- 状态：Current Milestone 与 M1–M19 Capability Status；
- 实现：M3/M6/M7、M8/M9、M10/M11、M9/M12 的后续有界 PR；
- Frontend：仅在全部 Core 行为完成后更新 Core behavior pin；
- 运行与发布：无 GPU/Provider/A100、无 live admission/canonical mutation、无发布。

## Migration Plan

1. PR-A 仅合入本 Accepted ADR、规范合同、风险和状态/索引同步；业务代码为零。
2. PR-B additive 实现 M3/M6 binding 与 M7 validation/currentness；历史 v1 可读。
3. PR-C additive 实现 M8 v2 ActionExecutionBeat 与 M9 三轴 requirement；历史 v1 可读。
4. PR-D 实现 M10 method-aware planning 与 M11 fail-closed router；无模型调用。
5. PR-E 实现 M9→M12 bridge 并纠正公共 capability projection；runtime 不安装。
6. PR-F 只增加 generic non-K2 acceptance fixture/tests，不修改 production source。
7. 上述 Core 行为全部合入后，Frontend 只更新精确 Core behavior pin；若需 adapter
   contract change 则停止并另行授权。
8. 最终只读 closeout 后停止；下一任务只能是
   `ACS-M12-C3-C4-A100-BUILD-HOST-PREFLIGHT`。

每一步从当时最新无冲突 `origin/main` 开始，使用 full suite CI（PR-A 仅使用已验证的
docs-only fast path），通过 required checks 后 squash merge。旧 schema、历史 K2 事实、
M13 tag object/target 和 Frontend product IA 保持不变。

## Stop conditions

出现以下任一情况立即停止：需要第二 Script/M6/Identity/Shot/Asset/Queue/Timeline
authority；需要新 sidecar database；binding 必须由客户端自报；M7 必须自动改写
Script 或让 WARN 自动进入 M8；executionClass 只能保留为自由文本；M9 无法移除 v2
无条件 video/audio；Contact/Gait 必须 fallback 到 Wan；deterministic event 必须进入
M11；M10 必须把 K2 exact-four 作为通用合同；M12 必须依赖 M11；需要 GPU、Provider、
模型安装或修改 M13 base tag；generic acceptance 只能依赖 K2 分支；required CI 失败；
或 `main` 出现并发范围冲突。

## Phase 0 使用边界

PR-A 是架构检查点，只允许文档与索引变更。业务行为、schema、migration、fixture、
runtime、模型、A100、GPU/Provider、Admission、canonical mutation、Master/Export 与
publication 必须为零。后续业务实现权限来自本 Accepted ADR 与 Project Lead 的精确
串行任务授权，不得由 PR-A 的文字自行扩大。

## 审批记录

| 角色 | 审批人 | 结论 | 日期 | 备注 |
| --- | --- | --- | --- | --- |
| Project Lead / Architecture Owner | `蔺鹏` | `APPROVED` | `2026-09-02` | 批准上游方法闭合、严格串行 PR 波次与停止条件 |
| M3–M7 Domain Owners | `蔺鹏` | `APPROVED` | `2026-09-02` | 批准 Script/M6 binding、M7 finding/currentness/readiness 边界 |
| M8–M11 Domain Owners | `蔺鹏` | `APPROVED` | `2026-09-02` | 批准 action beat、三轴需求、method-aware planning 与 fail-closed routing |
| M12/M13 Domain Owners | `蔺鹏` | `APPROVED` | `2026-09-02` | 批准显式 audio bridge、M13 deterministic handoff 与运行边界 |

## 变更历史

| 日期 | 修改人 | 变更内容 | 审批依据 |
| --- | --- | --- | --- |
| `2026-09-02` | Architecture Checkpoint | 创建并接受 ADR-0019，冻结 M3–M12 上游方法闭合与串行实施波次 | `ACS-M3-M11-UPSTREAM-METHOD-CLOSURE` |
| `2026-09-03` | Architecture Checkpoint | 仅增加 ADR-0020 双向关系 metadata/link；第 10 节及 Migration Plan 第 8 项的 A100 C3 假设被局部 supersede，其余 Decision 保持 Accepted | `ACS-M12-BUILD-HOST-ARCHITECTURE-CORRECTION-OPTION-A` |
