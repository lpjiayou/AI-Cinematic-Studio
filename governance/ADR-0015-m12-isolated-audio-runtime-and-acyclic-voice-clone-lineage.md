# ADR-0015 — M12 Isolated Audio Runtime and Acyclic Voice-Clone Lineage

## 文档元数据

| 字段 | 填写内容 |
| --- | --- |
| ADR ID | `ADR-0015` |
| Title | M12 Isolated Audio Runtime and Acyclic Voice-Clone Lineage |
| Status | `Accepted` |
| 作者 | AI Cinematic Studio Architecture Checkpoint |
| 创建日期 | `2026-08-30` |
| 最后更新日期 | `2026-09-03` |
| 审批人 | Project Lead / Architecture Owner / M12 Domain Owner |
| Decision Ref | `ACS-M12-M13-ARCHITECTURE-CORRECTION-20260830` |
| 关联事项 | M12 Runtime G0；M12 voice-clone lineage；System Master Plan；Current Milestone；Risk Register |
| Supersedes | 无；Decision Ref 取代冲突的 `ACS-M12-RUNTIME-G0-UNBLOCK-AND-M13-BACKEND-COMPLETION` 原始实现授权 |
| Superseded by | 无 |
| Reinforced by | [`ADR-0020`](ADR-0020-m12-cpu-build-host-and-a100-offline-consumer.md)；保留本 ADR 第 3、4 节为 controlling boundary |

## ADR ID

`ADR-0015`

该编号是在扫描全部既有 `governance/ADR-*.md`、确认当前最大编号为
`ADR-0014` 后分配的连续、未使用编号。编号不得修改、覆盖或复用。

## Title

M12 Isolated Audio Runtime and Acyclic Voice-Clone Lineage

## Status

`Accepted`

Project Lead、Architecture Owner 和 M12 Domain Owner 已通过 Decision Ref
`ACS-M12-M13-ARCHITECTURE-CORRECTION-20260830` 批准本决策。

`Accepted` 只表示下述架构边界已获批准。它不表示运行时已安装或实现，不表示
dependency lock、wheelhouse、离线安装或 one-shot manifest 已完成，不构成
`M12_RUNTIME_G0=PASS`，也不授权启动 A100。

## Context

M12 必须区分普通固定声音 TTS 与基于受权源录音的声音克隆。固定声音 TTS 不得
冒充声音克隆，两者也不得通过把 ML 依赖安装进 Core、V4 或 ComfyUI 来实现。
Core/V4 保持领域和编排边界，模型执行必须位于隔离的本地进程运行时。

先前设计还允许 `SourceRecordingBinding` 引用 `ConsentGrantVersionDigest`，同时
`ConsentGrantVersion` 引用 `SourceRecordingBindingDigest`。该双向关系使任一首个
对象都依赖尚不存在的后代摘要，无法满足创建前重读并验证全部上游摘要的规则。

dependency lock 与 hashed wheelhouse 需要非 A100、Linux x86_64、可在受控阶段
联网且具有持久 `/data` 的 CPU 构建环境。临时容器、`/tmp`、`$HOME`、Core venv
和 A100 ComfyUI 环境均不能成为供应链证据的权威构建位置。

本 ADR 不冻结具体 Python、PyTorch 或 CUDA 版本，不选择 resolver、lock 格式、
进程传输机制、对象完整 schema、数据库表、Public API DTO、运行时安装目录或
VoiceProfile package 格式；这些内容必须在后续单一职责 PR 中另行验证，不能由
Architecture Checkpoint 臆造。

冻结起点为 Core commit `68cad32f60397c969b36257d8a894e0b52d2e162`、tree
`62084f092d4f42c5037d9c9f19e54bef266c2b1e`。若 `origin/main` 前进，必须确认
该 commit 是最新 main 的祖先，并审计 M12、M13、Timeline、Delivery、Architecture
和 `CURRENT_MILESTONE.md` 相关新增提交；有冲突即停止，不得覆盖。

## Decision

### 1. 冻结两个独立本地运行时

普通固定声音 TTS：

```text
TTS_ENGINE_ID=hexgrad/kokoro:LOCAL_FIXED_VOICE
TTS_ENGINE_COMMIT=dfb907a02bba8152ca444717ca5d78747ccb4bec
TTS_MODEL_BUNDLE_SHA256=849ed6061f60a9b82ba13ff9538380fca4014fe19f1762475ab0997a2590cc92
```

声音克隆：

```text
VOICE_CLONE_ENGINE_ID=QwenAudio/CosyVoice:CosyVoice3.ZERO_SHOT_LOCAL
VOICE_CLONE_ENGINE_COMMIT=074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
MATCHA_TTS_COMMIT=dd9105b34bf2be2230f4aa1e4769fb586a3c824e
VOICE_CLONE_MODEL_BUNDLE_SHA256=f17e288095c0514ad4bc8d7bfc976363d1bcb3f1ab5ff4e276c014740125e83d
```

两个运行时必须各自拥有：

- 独立 Python 环境；
- 独立 dependency lock；
- 独立 wheelhouse；
- 独立模型目录；
- 独立 runtime executable；
- 关闭式独立进程协议。

任一运行时都不得直接安装进 Core 或 ComfyUI。Core 与 V4 不得直接 import 运行时
ML 包。未经新的架构决定，不得使用共享环境、共享 executable、fallback 引擎或
另一个固定声音 TTS 冒充声音克隆。

### 2. 声音克隆血缘严格单向且无环

唯一正式血缘为：

```text
Admitted AUDIO AssetVersion
→ SourceVoiceRecordingAssetVersionBinding
→ ConsentGrantVersion
→ confirmed VoiceLockVersion
→ immutable VoiceProfileVersion
→ VoiceAssetVersion
→ DialogueAssetVersion
```

全链强制：

```text
NO_OBJECT_MAY_REFERENCE_A_DESCENDANT_DIGEST=true
LINEAGE_GRAPH_MUST_BE_ACYCLIC=true
```

创建任一对象前，它引用的全部上游 digest 必须已经存在，并可重新读取和验证。
不得为反向查询把后代 ref/digest 回写到祖先对象。

| 对象 | 允许的直接上游 | 明确禁止的引用 |
| --- | --- | --- |
| `SourceVoiceRecordingAssetVersionBinding` | admitted AUDIO AssetVersion ref/version/digest、file digest、PCM content digest、AudioTechnicalValidation、subjectRef、TranscriptVersion ref/digest、可独立存在的源录音 Rights evidence | ConsentGrantVersion ref/digest、VoiceLockVersion、VoiceProfileVersion、VoiceAssetVersion、DialogueAssetVersion |
| `ConsentGrantVersion` | Source binding ref/digest、subjectRef、grantorRef、RightsBinding/evidence、usage scope、territory、validity、revocation state | 任何后代对象或后代 digest |
| `VoiceLockVersion` | Source binding、ConsentGrantVersion、RightsBinding、Voice Identity version | VoiceProfileVersion、VoiceAssetVersion、DialogueAssetVersion |
| `VoiceProfileVersion` | confirmed VoiceLockVersion、固定 engine commit、固定 model bundle digest、dependency lock digest、runtime manifest digest、immutable voice profile package digest | VoiceAssetVersion、DialogueAssetVersion |
| `VoiceAssetVersion` | 已验证 VoiceProfileVersion 与必要上游摘要 | DialogueAssetVersion |
| `DialogueAssetVersion` | VoiceAssetVersion、Dialogue request、生成证据 | 不适用；它是本链终端对象 |

本 ADR 不授权创建新的 AUDIO AssetVersion admission；Source binding 只能消费已经
admitted 且可验证的 AUDIO AssetVersion。

### 3. lock 与 wheelhouse 只在持久 CPU 环境构建

M12 dependency lock 和 wheelhouse 只允许在以下环境构建：

- Linux x86_64；
- 非 A100；
- 仅在受控 `FETCH_AND_HASH` 阶段联网；
- 持久根为 `/data/k2-runtime-artifacts/m12/g0`。

禁止 fallback 到 `/tmp`、`$HOME`、当前容器临时层、A100 ComfyUI 环境或 Core
venv。若当前环境没有持久 `/data`，唯一合法状态是：

```text
M12_G0_3_STATE=ENVIRONMENT_HOLD
BLOCK_REASON=PERSISTENT_CPU_BUILD_ARTIFACT_ROOT_UNAVAILABLE
```

该状态只暂停 M12-C3/C4，不阻止 M12-C1/C2 或独立 M13 CPU 轨道，也不得成为启动
A100 的理由。

### 4. A100 只消费已关闭输入且仍需另行授权

- G0 完成不等于 A100 获得授权；
- A100 不用于 dependency resolution；
- A100 不用于探索式安装；
- A100 只消费已哈希 wheelhouse、engine archive、model manifest 和 one-shot manifest；
- A100 启动仍需新的 Project Lead 明确授权。

### 5. 本决策不开放生产或发布权威

Architecture Checkpoint 及后续已授权非 GPU 实施继续保持：

```text
A100_START_AUTHORIZED=false
GPU_CALLS_ALLOWED=false
PROVIDER_CALLS_ALLOWED=false
CANONICAL_MUTATIONS=0
ASSET_ADMISSION=0
PUBLICATION_ALLOWED=false
LEGACY_MEDIA_WRITES=0
```

Architecture Checkpoint 合入后只能记录架构冲突与摘要环已按设计解决、后续实现已
获边界内授权；不得把 fake runtime、测试替身或文档状态写成 G0 完成证据。

## Alternatives

### 方案 A：保持原阻塞状态

- 概述：不冻结运行时，也不纠正摘要关系。
- 优点：无需新增决策记录。
- 缺点：两个能力没有可实施边界，首个合法血缘对象仍不可创建。
- 风险与约束：M12 Runtime G0 无法形成可验证完成证据。
- 未采纳原因：不能满足已批准的架构纠正。

### 方案 B：共享环境或安装进 Core/ComfyUI

- 概述：两个引擎共享依赖、模型和 executable。
- 优点：表面上减少环境数量。
- 缺点：依赖污染且无法独立锁定、安装和验证。
- 风险与约束：违反隔离边界，并可能把固定 TTS 冒充 clone。
- 未采纳原因：两个完全独立运行时是冻结决定。

### 方案 C：保留双向摘要

- 概述：Source binding 与 Consent 各自保存对方 digest。
- 优点：可直接反向查找。
- 缺点：首次创建时双方都依赖未存在的摘要。
- 风险与约束：血缘无法形成 DAG 或确定重放。
- 未采纳原因：违反无后代摘要和无环总规则。

### 方案 D：隔离运行时、单向血缘和持久 CPU 构建

- 概述：采用本 ADR 的 Decision。
- 优点：运行时与供应链可独立验证，摘要可按拓扑顺序创建。
- 缺点：维护两套工件，并依赖持久 CPU 构建环境。
- 风险与约束：仍须后续真实实现和证据。
- 采纳结论：与 Decision Ref 的全部冻结决定一致。

## Consequences

### 正向影响

- 固定声音 TTS 与声音克隆不可混用；
- Core、V4、ComfyUI 不承载两个引擎的 ML 依赖；
- Source、Consent、VoiceLock、VoiceProfile、VoiceAsset 和 DialogueAsset 可按拓扑顺序创建；
- 临时容器结果不能冒充可交付供应链证据；
- A100 保持为已关闭输入的消费者，不承担依赖探索或决策职责。

### 负向影响与成本

- 必须维护两套 Python 环境、lock、wheelhouse、模型目录和 executable；
- 缺少持久 `/data` 时 C3/C4 必须暂停；
- VoiceProfileVersion 与新单向 lineage 需要后续合同和持久化实现；
- G0 全部证据完成后仍需单独取得 A100 授权。

### 风险

- `R-M12-SUP-018`：dependency/wheel 供应链；
- `R-M12-PY-019`：Python 生命周期；
- `R-M12-RIGHTS-020`：模型许可证与训练数据；
- `R-M12-PRIV-021`：私有源录音泄漏；
- `R-M12-ISO-022`：运行时隔离失效；
- `R-M12-LIN-024`：摘要环回归。

这些风险保持开放或缓解中；ADR Accepted 不会自动关闭它们。

### 受影响资产

- 架构文档：System Master Plan、Golden Contract、Current Milestone、Risk Register、本 ADR；
- 后续契约：M12-C1 单向 lineage、M12-C2 closed-process protocol 与 V4 adapters；
- 质量门禁：Architecture Checkpoint 文档验证，以及后续 contract/integration 验证；
- 安全与运维：运行时隔离、持久 CPU 构建根、A100 单独授权；
- 发布规则：Provider、GPU、Admission、canonical mutation、legacy media 与 publication 保持关闭。

## Migration Plan

### 1. 前置条件与 Architecture Checkpoint

从冻结 Core base 或已验证无冲突的最新 `origin/main` 创建
`docs/m12-m13-architecture-correction-20260830`。Checkpoint 只新增两份 Accepted
ADR，并同步 Master Plan、Golden Contract、Current Milestone、Risk Register 以及
确实受影响的责任矩阵/索引；不得包含业务代码、schema、migration、fixture、runtime、
模型、wheel 或依赖。

Checkpoint 必须通过 Markdown、Documentation Links、Unit Tests、Contract Tests
和 Integration Tests 五项 required checks，以 squash 方式合入并核验远端 SHA/tree。
在此之前不得开始实现。

### 2. 分阶段实施

1. `M12-C1`：SourceRecordingBinding → ConsentGrantVersion → VoiceLockVersion →
   VoiceProfileVersion 的单向血缘与持久化；
2. `M12-C2`：Kokoro/CosyVoice3 独立进程协议和 V4 adapters；
3. `M12-C3`：仅在持久 CPU 环境生成完整 dependency locks 和 hashed wheelhouses；
4. `M12-C4`：C3 完成后生成 one-shot A100 manifest。

每项使用独立单一职责 PR，并从当时最新 `origin/main` 开始。缺少持久 `/data` 时
C1/C2 可继续，C3/C4 保持 `ENVIRONMENT_HOLD`。

### 3. 兼容、验证与停止条件

- 既有 ADR、VoiceLock 和音频事实保持历史可读，不删除或重算摘要；
- 不建立 legacy media 写入兼容路径；
- lineage validator 必须覆盖直接、间接和自环、stale/tamper 与 restart replay；
- 隔离验证必须证明 Core/V4/ComfyUI 无 ML import/install 漂移；
- C3/C4 必须证明独立 lock/wheelhouse、离线安装和 manifest 摘要；
- 任一冻结决定需要改变、main 出现相关冲突或必须使用临时构建根时立即停止并报告；
- 本 ADR 的变更只能由新的 Accepted ADR 明确替代，不得静默改写或删除。

只有单向血缘、VoiceProfileVersion、隔离协议、精确 lock、hashed wheelhouse、离线
安装、one-shot manifest、持久 artifact root 全部通过且 A100 仍未启动，才可记录：

```text
M12_RUNTIME_G0=PASS
```

### 4. 责任人与目标事件

- 决策责任：Project Lead / Architecture Owner / M12 Domain Owner；
- 实施责任：各独立 M12-C1 至 C4 PR 的指定实现者；
- 目标事件：严格按 C1 → C2 → C3 → C4；无未经批准的日历截止日期；
- 沟通对象：Project Lead、Architecture Owner、M12 Domain Owner。

### 5. 旧设计停止使用和归档

Architecture Checkpoint 合入时，Source binding 与 Consent 的双向摘要、两个引擎
共享运行时、把 ML 包安装进 Core/ComfyUI，以及使用 A100 探索依赖的设计立即停止
作为实施依据。冲突的旧执行授权只保留为历史审计事实，不得删除或重新启用；本 ADR
及其 Decision Ref 成为后续 M12-C1 至 C4 的当前架构依据。既有合法 VoiceLock 和
音频事实继续按原合同保留，不因设计纠正被删除、回填或重算摘要。

## Phase 0 使用边界

本 Architecture Checkpoint 只记录和保护架构决策，不授权业务代码、数据库表、
migration、运行时、依赖、模型、wheel、GPU/Provider、A100、canonical mutation、
Asset Admission、legacy media write 或 publication。

Checkpoint 合入后的实现权限来自本 Accepted ADR、Decision Ref、当前
Source-of-Truth 和当时最新无冲突 main；不得扩展到这些明确关闭的边界。

## 审批记录

| 角色 | 审批人 | 结论 | 日期 | 备注 |
| --- | --- | --- | --- | --- |
| Project Lead | Decision Ref 中的批准主体 | `APPROVED` | `2026-08-30` | 批准两个隔离运行时、单向血缘、持久 CPU 构建边界与 A100 独立授权 |
| Architecture Owner | Decision Ref 中的批准主体 | `APPROVED` | `2026-08-30` | 确认摘要环删除及 Core/V4/ComfyUI 隔离边界 |
| M12 Domain Owner | Decision Ref 中的批准主体 | `APPROVED` | `2026-08-30` | 批准精确 engine commit、model bundle digest、lineage 与 C1–C4 顺序 |

## 变更历史

| 日期 | 修改人 | 变更内容 | 审批依据 |
| --- | --- | --- | --- |
| `2026-08-30` | AI Cinematic Studio Architecture Checkpoint | 创建并接受 ADR-0015；冻结 M12 隔离运行时、无环声音克隆血缘、持久 CPU 构建环境和 A100 边界 | `ACS-M12-M13-ARCHITECTURE-CORRECTION-20260830` |
| `2026-09-03` | AI Cinematic Studio Architecture Checkpoint | 仅增加 ADR-0020 双向关系 metadata/link；第 3、4 节继续控制非 A100 C3 与 A100 closed-input consumer 边界，Decision 正文未改写 | `ACS-M12-BUILD-HOST-ARCHITECTURE-CORRECTION-OPTION-A` |
