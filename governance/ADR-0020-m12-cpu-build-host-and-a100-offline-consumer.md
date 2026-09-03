# ADR-0020 — M12 CPU Build Host and A100 Offline Consumer Boundary

## 文档元数据

| 字段 | 填写内容 |
| --- | --- |
| ADR ID | `ADR-0020` |
| Title | M12 CPU Build Host and A100 Offline Consumer Boundary |
| Status | `Accepted` |
| 作者 | AI Cinematic Studio Architecture Checkpoint |
| 创建日期 | `2026-09-03` |
| 最后更新日期 | `2026-09-03` |
| 审批人 | Project Lead / Architecture Owner / Infrastructure Owner / M12 Domain Owner |
| Decision Ref | `ACS-M12-BUILD-HOST-ARCHITECTURE-CORRECTION-OPTION-A` |
| 关联事项 | ADR-0015；ADR-0019 §10 与 Migration Plan；M12-C3/C4；M12 Runtime G0；A100 build-host reflight failure |
| Supersedes | 无；仅对 ADR-0019 的明确范围作局部 supersession |
| Superseded by | 无 |

## ADR ID

`ADR-0020`

该编号是在扫描全部既有 `governance/ADR-*.md`、确认最大已用编号为
`ADR-0019` 且 `ADR-0020` 未被分配后连续使用。编号不得修改、覆盖或复用。

## Title

M12 CPU Build Host and A100 Offline Consumer Boundary

## Status

`Accepted`

Project Lead、Architecture Owner、Infrastructure Owner 和 M12 Domain Owner 已通过
Decision Ref `ACS-M12-BUILD-HOST-ARCHITECTURE-CORRECTION-OPTION-A` 批准方案 A。

本状态只接受 M12 构建与消费主机边界、封闭制品合同和后续授权顺序。它不表示已选择
物理 CPU 主机，不表示 C3、C4 或 Runtime G0 已开始或完成，也不授权 A100、GPU、
Provider、依赖安装、模型下载、Asset Admission、live canonical mutation 或 publication。

## Context

[`ADR-0015`](ADR-0015-m12-isolated-audio-runtime-and-acyclic-voice-clone-lineage.md)
第 3 节要求 dependency lock 与 hashed wheelhouse 只在非 A100、持久 Linux x86_64
CPU 环境构建；第 4 节规定 A100 只消费已关闭输入，不用于 dependency resolution 或
探索式安装。

[`ADR-0019`](ADR-0019-upstream-execution-method-and-requirement-routing.md) 第 10 节却把
M12-C3/C4 目标主机记录为 `A100_CODE_SERVER_BUILD_HOST`，其 Migration Plan 第 8 项
也继承了 A100 build-host 假设。两份 ADR 均为 `Accepted`，且 ADR-0019 明确声称扩展而
不替代 ADR-0015，因此它们对 C3 主机类别形成不可同时满足的当前要求。

2026-09-03 A100 build-host reflight 进一步证明：磁盘预检通过，但当前主机缺少已证明的
硬离线隔离能力，批准下载来源不可达，Core checkout 因网络传输未完成而不可验证。
证据摘要为
`93c1c96dc3d852581857d1f213d158f03063cc6da47379dc7a24774be8dea1ce`。该失败不得
被改写成 checkout mismatch，也不得成为把 C3 留在 A100 的理由。

本 ADR 只解决主机职责冲突。它不选择具体云厂商、实例、Python/PyTorch/CUDA 版本、
resolver、lock 格式或制品传输产品，也不改变 ADR-0015 已冻结的运行时与模型选择。

## Decision

### 1. 权威关系与局部 supersession

当前控制关系冻结为：

```text
ADR_0015_STATUS=ACCEPTED_AND_CONTROLLING
ADR_0015_BUILD_BOUNDARY=PRESERVED
ADR_0019_STATUS=ACCEPTED
ADR_0019_SECTION_10=PARTIALLY_SUPERSEDED_BY_ADR_0020
ADR_0019_MIGRATION_PLAN_A100_C3_ASSUMPTION=SUPERSEDED_BY_ADR_0020
ADR_0020_CREATED=true
ADR_0020_STATUS=ACCEPTED
ADR_0015_STATUS=ACCEPTED
ADR_0015_CONTROLLING_BUILD_BOUNDARY=true
ADR_0019_SECTION_10_PARTIALLY_SUPERSEDED=true
ARCHITECTURE_CONFLICT_RESOLVED=true
```

ADR-0015 的非 A100 C3 边界与 A100 closed-input consumer 边界继续生效。ADR-0019 的
M3–M12 上游方法、三轴需求、显式音频桥及其他决定继续生效；只有第 10 节和
Migration Plan 第 8 项中把 A100 作为 C3 build host 的假设停止作为当前依据。

ADR-0015 不被整体 supersede，ADR-0019 也不被整体废弃或降级。

### 2. C3：非 A100 供应链闭包

```text
M12_C3_HOST_CLASS=NON_A100_LINUX_X86_64_CPU_BUILD_HOST
M12_C3_GPU_REQUIRED=false
M12_C3_A100_ALLOWED=false
```

C3 在独立授权后负责：

- 获取 ADR-0015 已钉住的精确 engine source/archive 与 model bundle；
- 冻结精确 Python、PyTorch、Torchaudio 和 CUDA wheel variant；
- 为两个运行时分别生成 dependency lock 与 hashed wheelhouse；
- 生成 SBOM、依赖许可证清单、engine/model 来源与许可证证据；
- 生成模型逐文件 SHA-256、bundle digest、runtime executable 和 one-shot install manifest；
- 明确分离受控联网 `FETCH_AND_HASH` 阶段和 hard-offline 验证阶段；
- 在 clean environment 中完成真实 offline install test。

C3 不负责 A100 安装、GPU 模型加载、GPU 推理、live Audio AssetVersion、Admission 或
publication。它不得使用 A100、Core venv、ComfyUI venv 或任一临时环境作为制品权威。

### 3. C4：A100 硬离线消费

```text
M12_C4_HOST_CLASS=A100_OFFLINE_CONSUMER
M12_C4_NETWORK_MODE=HARD_OFFLINE
M12_C4_DIRECT_PUBLIC_DOWNLOADS_ALLOWED=false
M12_C4_A100_OFFLINE_CONSUMER=true
```

C4 只消费 C3 产生并冻结的封闭制品：

```text
hashed wheelhouse
engine source/archive bundle
model bundle
SBOM
license evidence
dependency lock
runtime manifest
one-shot install manifest
files.sha256
```

C4 在独立授权后只负责接收制品、重算全部摘要、验证目标 Linux/Python/glibc/
CUDA/PyTorch ABI、安装到两个独立 runtime root、验证 executable/import/进程协议、
证明系统 Python/Core Python/ComfyUI Python 未污染，并生成 C4 install evidence。

C4 禁止 dependency resolution、公共站点直接下载、修改 lock、选择替代 wheel 或模型、
自动 fallback，以及 GPU 推理。

### 4. Runtime G0：单独授权的 A100 GPU 验证

```text
M12_RUNTIME_G0_HOST_CLASS=A100_GPU_RUNTIME
M12_RUNTIME_G0_GPU_AUTHORIZATION=SEPARATE_REQUIRED
M12_RUNTIME_G0_SEPARATE_GPU_AUTH_REQUIRED=true
```

只有 C3 与 C4 均完成、合入并通过各自门禁后，才可申请 Runtime G0。该独立任务可验证
Kokoro fixed voice、CosyVoice3 VoiceProfile 与 cloned dialogue、GPU/显存/性能、技术
音频质量、输入输出摘要和运行时网络使用为零。C3 或 C4 的完成均不自动授权 GPU。

### 5. CPU Build Host 合格条件

C3 候选主机必须同时满足：

```text
HOST_ARCH=x86_64
HOST_OS=LINUX
A100_OR_OTHER_GPU_REQUIRED=false
PERSISTENT_ROOT=/data/k2-runtime-artifacts/m12/g0
MINIMUM_FREE_BYTES=107374182400
APPROVED_ORIGIN_ALLOWLIST=true
HARD_OFFLINE_TEST_MODE=true
```

硬离线验证至少使用一种已证明能力：

```text
DOCKER_NETWORK_NONE
PODMAN_NETWORK_NONE
UNSHARE_NETNS
PLATFORM_EGRESS_DENY
```

仅设置 `PIP_NO_INDEX`、`HF_HUB_OFFLINE` 或 `TRANSFORMERS_OFFLINE` 不能单独证明网络
隔离。主机不得把 `/tmp`、`$HOME`、Windows NTFS 挂载、Core venv、ComfyUI venv、
A100 ComfyUI 环境、浮动最新版依赖、未审核镜像站或关闭 TLS 校验作为构建权威。

### 6. 物理主机选择延后

架构候选只包括类别，不构成选择：

```text
LOCAL_WSL2_UBUNTU
DEDICATED_LINUX_CPU_VM
CONTROLLED_LINUX_CPU_CONTAINER_HOST
```

任何候选均须通过独立 preflight，验证持久 Linux filesystem、100 GiB 以上精确可用
字节、批准域名可达、硬离线隔离、重启持久性、可验证 A100 制品转移、成本和生命周期。
本 ADR 不把 Windows 本机、WSL2、任何云厂商或具体实例写成已接受执行主机。

### 7. `M12ClosedRuntimeBundle.v1`

`KOKORO_FIXED_VOICE` 与 `COSYVOICE3_ZERO_SHOT` 各自形成独立 bundle。每个
`M12ClosedRuntimeBundle.v1` 至少绑定：

```text
runtimeKind
targetPlatform
pythonVersion
glibcCompatibility
pytorchVersion
torchaudioVersion
cudaWheelVariant
engineId
engineCommit
engineArchiveDigest
modelId
modelRevision
modelFiles[]
modelBundleDigest
dependencyLockDigest
wheelhouseDigest
sbomDigest
licenseEvidenceDigest
runtimeExecutableDigest
installManifestDigest
fileCount
totalByteSize
files[]
payloadDigest
```

每个 `files[]` 条目至少包含：

```text
relativePath
byteSize
sha256
sourceOrigin
sourceRevision
licenseRef
```

bundle 禁止绝对路径、token、cookie、源录音、私有用户数据、浮动 revision 和未列入
manifest 的隐藏文件。`payloadDigest` 必须覆盖全部语义字段和有序文件清单。

### 8. C3 到 C4 的制品传输

```text
C3_TO_C4_TRANSFER=BYTE_PRESERVING_DIGEST_VERIFIED_TRANSFER
```

传输前冻结 bundle digest，传输后由 A100 重算全部摘要；任一字节变化即拒绝。传输
工具不是 authority，不在聊天中传输模型或凭据，不要求 A100 访问公共模型站点，并且
必须在 CPU Build Host 之外保存耐久证据副本。

平台持久卷、受控对象存储或点对点安全复制均只是后续可评估机制；具体机制必须由后续
基础设施任务基于权限、成本、生命周期和摘要保持能力选择，本 ADR 不作臆造。

### 9. A100 离线隔离仍为 C4 前置条件

```text
A100_C3_ISOLATION_REQUIRED=false
A100_C4_HARD_OFFLINE_ISOLATION_REQUIRED=true
A100_C4_OFFLINE_ISOLATION_CURRENTLY_PROVEN=false
```

C4 前必须证明 `PLATFORM_EGRESS_DENY`、`DOCKER_NETWORK_NONE`、
`PODMAN_NETWORK_NONE` 或另一份 Accepted ADR 接受的等价硬隔离。当前 A100 上
`unshare -n` 返回 `OPERATION_NOT_PERMITTED` 保持为失败历史，不得被隐藏，也不得
导致 C3 回退到 A100。

### 10. 供应链、许可证和生产边界

Kokoro fixed voice 与 CosyVoice3 zero-shot voice clone 的 engine/model pins 继续由
ADR-0015 控制，本 ADR 不重新选择。C3 必须形成 `ENGINE_LICENSE_EVIDENCE`、
`MODEL_LICENSE_EVIDENCE`、`DEPENDENCY_LICENSE_INVENTORY` 与
`COMMERCIAL_USE_DECISION`。许可证、训练数据或商业使用边界不可接受时：

```text
C3_RESULT=BLOCKED_RIGHTS
```

技术安装成功不能自动标记生产可用。本 ADR 不创建第二 runtime authority、Audio
authority、数据库、queue、Public API 或 SQLite schema。

```text
SECOND_RUNTIME_AUTHORITY_CREATED=false
SECOND_AUDIO_AUTHORITY_CREATED=false
```

## Alternatives

### 方案 A：非 A100 CPU C3，A100 离线 C4 与独立 GPU Runtime G0

- 概述：采用本 ADR 的三阶段职责分离。
- 优点：保留 ADR-0015 的供应链边界，降低 A100 CPU-only 构建成本，并让下载、构建、
  离线安装与 GPU 验证分别具有清晰证据。
- 缺点：需要额外 CPU 主机、持久存储和 byte-preserving 制品传输。
- 风险与约束：CPU 主机与 A100 必须分别通过 preflight；ABI、摘要或隔离失败即停止。
- 采纳结论：与 Decision Ref `APPROVE_OPTION_A` 一致。

### 方案 B：在 A100 上执行 CPU-only C3

- 概述：supersede ADR-0015 的非 A100 构建边界，以平台网络拒绝或容器
  `network=none` 在 A100 上执行 C3。
- 优点：减少一次跨主机制品转移，并在目标主机直接观察 ABI。
- 缺点：A100 在依赖解析和 CPU build 期间持续计费，构建与运行环境更易相互污染。
- 风险与约束：当前 A100 硬隔离未证明；必须整体重审 ADR-0015 第 3、4 节及相关
  Consequences/Migration Plan，并取得新的成本和基础设施授权。
- 未采纳原因：Decision Ref 未批准方案 B，且当前 reflight 不能证明所需控制。

### 方案 C：维持两份 ADR 冲突并继续暂停

- 概述：不建立控制优先级，保持 architecture hold。
- 优点：不引入新的主机决定。
- 缺点：任何 C3 主机选择都可能违反一份 Accepted ADR，无法形成合法执行授权。
- 风险与约束：M12 Runtime G0 永久停在不可操作状态。
- 未采纳原因：不能解决已确认的架构权威冲突。

## Consequences

### 正向影响

- C3、C4 与 GPU Runtime G0 的主机、网络与授权责任不再混淆；
- A100 不再承担 dependency resolution 或探索式安装；
- 两个 runtime bundle 可以按精确来源、许可证、文件摘要和目标 ABI独立验证；
- A100 离线隔离失败保持显式 blocker，不会被 C3 迁移掩盖；
- ADR-0019 的上游方法闭合内容全部保留。

### 负向影响与成本

- 需要选择、预检和维护持久非 A100 Linux x86_64 CPU 主机；
- 需要管理 CPU 主机网络 allowlist、hard-offline test 和耐久制品副本；
- C3 到 C4 增加传输、摘要复算和 ABI 验证步骤；
- A100 C4 仍须解决平台级或容器级硬离线隔离，当前尚未证明。

### 风险

- `R-M12-SUP-018`：依赖、wheel 和模型供应链字节未闭合；
- `R-M12-PY-019`：Python 生命周期及目标 ABI 未冻结；
- `R-M12-RIGHTS-020`：engine/model/dependency 商业使用证据未完成；
- `R-M12-ISO-022`：两个运行时或 Core/ComfyUI 环境污染；
- `R-M12-HOST-042`：错误主机类别或未通过 preflight 的 CPU 主机进入 C3；
- `R-M12-XFER-043`：C3→C4 传输漂移或 A100 未硬离线即开始消费。

### 受影响资产

- 架构：本 ADR、System Master Plan、module responsibility matrix；
- 决策关系：ADR-0015 metadata/link、ADR-0019 metadata/link、supersession map；
- 状态：Current Milestone、M1–M19 Capability Status、Cross-Repository Baseline；
- 治理：Risk Register、Document Registry 和文档索引；
- 实现、Public API、SQLite schema、依赖、Frontend 与 M13 tag：不变。

## Migration Plan

1. 以最新无冲突 Core main 创建仅文档的 Architecture Checkpoint；新增本 Accepted ADR，
   仅向 ADR-0015/0019 增加范围准确的 metadata/link，并同步 Master、矩阵、风险和状态。
2. Checkpoint 通过 docs-only fast path 的五项 required checks 后 squash merge并删除分支。
3. 下一独立任务只选择并预检一种非 A100 Linux x86_64 CPU Build Host；不得执行 C3。
4. CPU 主机 preflight 通过并取得独立授权后，C3 分别构建两个封闭 runtime bundle，完成
   来源、rights、SBOM、lock、wheelhouse 与 clean hard-offline install 证据。
5. C3 合入后，独立 C4 授权解决 A100 hard-offline isolation、传输摘要和无污染安装。
6. C3/C4 完成后，另行申请 A100 GPU Runtime G0；无自动阶段跃迁。
7. 任一阶段发现需要改变主机类别、运行时 pins、权威边界或制品合同，停止并建立新的
   Architecture Checkpoint；历史失败证据保持不可变。

## Stop conditions

出现以下任一情况立即停止：ADR-0015 controlling boundary 无法保留；必须整体撤销
ADR-0019；ADR-0020 编号冲突；C3 必须使用 A100；候选 CPU 主机没有持久 Linux
filesystem、精确空间、批准来源或硬离线验证；bundle 含绝对路径、浮动 revision、
隐藏文件、私有数据或缺少摘要；C4 需要公共下载、依赖解析、替代选择或 GPU 推理；
需要修改生产代码、Public API、SQLite schema、依赖、Frontend 或 M13 tag；required
CI 失败；或 main 出现同范围并发变更。

## 当前实施边界

本 Architecture Checkpoint 只记录并对齐 Accepted 架构，不授权 CPU Build Host
preflight、WSL2 配置、云 CPU VM、C3、C4、Runtime G0、A100 启动、模型/wheel 下载、
runtime 创建、GPU/Provider、Asset Admission、canonical mutation 或 publication。

```text
M12_RUNTIME_G0=NOT_COMPLETE
M12_G0_3_STATE=CPU_BUILD_HOST_SELECTION_HOLD
M12_C3_READY_TO_REQUEST_AUTHORIZATION=false
M12_C3_READY_TO_START=false
M12_C3_AUTHORIZED=false
M12_C4_AUTHORIZED=false
A100_START_AUTHORIZED=false
A100_FUTURE_START_AUTHORIZED=false
```

## 审批记录

| 角色 | 审批人 | 结论 | 日期 | 备注 |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `APPROVED` | `2026-09-03` | 批准 Option A、三阶段主机职责和严格停止边界 |
| Architecture Owner | `蔺鹏` | `APPROVED` | `2026-09-03` | 批准保留 ADR-0015，并局部 supersede ADR-0019 的 A100 C3 假设 |
| Infrastructure Owner | `蔺鹏` | `APPROVED` | `2026-09-03` | 批准 CPU host preflight 先行、A100 C4 hard-offline 前置和制品传输边界 |
| M12 Domain Owner | `蔺鹏` | `APPROVED` | `2026-09-03` | 批准两个独立 closed runtime bundles 与 C3→C4→Runtime G0 顺序 |

## 变更历史

| 日期 | 修改人 | 变更内容 | 审批依据 |
| --- | --- | --- | --- |
| `2026-09-03` | AI Cinematic Studio Architecture Checkpoint | 创建并接受 ADR-0020；保留非 A100 C3 与 A100 offline-consumer 边界，局部 supersede ADR-0019 的 A100 C3 假设 | `ACS-M12-BUILD-HOST-ARCHITECTURE-CORRECTION-OPTION-A` |
