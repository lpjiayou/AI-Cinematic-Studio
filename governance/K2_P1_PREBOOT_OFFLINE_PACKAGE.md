# K2 P1 开机前离线工作包

- 状态：`OFFLINE PACKAGE VERIFIED / EXTERNAL FACT HOLD / P1 NOT PASSED`
- 日期：`2026-08-21`
- 范围：现有 K2 单集 lineage 的独立安全前置；不推进 P2/P3
- 创作候选：`docs/16-k2-production/K2-001-PREPRODUCTION-CANDIDATE.md`
- 机器清单：`experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json`

## 1. Project Lead 约束

本轮记录以下用户约束：

- K2 当前单集实验波次的总预算硬上限为人民币 `1000.00` 元，即
  `currency=CNY / maxTotalCostMinor=100000`；
- 当前未授权付费调用，离线包记录 `committedSpendMinor=0`；
- Provider 子上限尚未分配，后续所有 image/video/audio 子上限之和必须不大于
  `100000`；
- 不使用外部音频；当前音频候选只允许剧本内文字驱动的中性 TTS 与待核验的内部合成
  环境/效果设计；
- 禁止真人声纹克隆、演员模仿和未经 Rights Manifest 绑定的音频输入；
- 当前没有电脑/GPU 可用，因此本轮不启动 ComfyUI、Provider、模型生成、付费 API、
  域写入、候选选择或发布动作。

人民币 1000 元是硬上限，不等于 `budgetAuthorityRef`，也不等于实际支出授权。外部
Provider Authority 仍须返回可解析的预算权威引用与每种媒体的精确执行上限。

## 2. 已完成的安全前置

1. 固定 K2-001 的 30 秒、两场、四镜、24 fps、720 帧候选时间轴。
2. 整理剧本、逐镜头分镜、摄影、动作、表演、连续性、声音和失败判定候选。
3. 为林澈、顾言分别设计八视图 turnaround 与固定识别点。
4. 为四镜准备 Wan2.2 正/负提示词和现有 49-frame P1 小样参数。
5. 设计 text-only neutral TTS、环境与提示音 cue sheet；无外部音频、无克隆、P1 无音乐。
6. 建立 image/video/audio 同源实验计划；运行时必须从当前 G4 解析已有 video/audio
   的精确 `GenerationRequestRef`。当前 G4 没有 image request，此项保持 blocker，直到
   获批的同源合同扩展存在；不得以 `K2-001-SH-*` 候选键冒充 Core ref。
7. 增加 fail-closed 离线校验器，固定预算、时间轴、角色视图、模型/attestation
   摘要、三媒体覆盖和非发布边界。
8. 增加篡改测试，拒绝预算越限、实际支出、外部音频、声纹克隆、摘要漂移、时间轴
   断裂、人物视图缺失、secret-shaped 字段、domain admission 和 publication claim。

这些工作不产生 MediaJob、ProviderAttempt、AssetVersion、Identity Lock、Approval、
EpisodeMaster 或 ExportArtifact。

## 3. Rights Authority 输入模板

以下是外部权利方需要完成的字段清单，不是可激活 bundle。尖括号值故意不是有效事实，
不得把模板摘要注入运行环境。

```json
{
  "schemaVersion": "<exact-schema-from-current-external-authority-contract>",
  "rightsDecisions": [
    {
      "inputDigest": "<sha256-of-exact-script-or-reference-bytes>",
      "rightsOwnerRef": "<externally-resolvable-rights-owner-ref>",
      "grantRef": "<externally-resolvable-grant-ref>",
      "allowedUse": "<exact-K2-generation-and-release-use>",
      "territories": ["<approved-territory>"],
      "validFrom": "<timestamp>",
      "validUntil": "<timestamp>",
      "providerProcessingConsent": true,
      "evidenceRef": "<resolvable-evidence-ref>"
    }
  ]
}
```

真实 bundle 必须使用当前代码的封闭 schema，覆盖剧本、每份 identity/reference、
reference video、voice、music、font、brand 和任何其他输入的精确摘要。没有输入时不能
用空白或通配 grant 替代。

## 4. Provider Authority 输入模板

以下同样只是字段检查表，不是批准事实：

```json
{
  "schemaVersion": "<exact-schema-from-current-external-authority-contract>",
  "providerDecisions": [
    {
      "mediaKind": "<image-or-video-or-audio>",
      "providerId": "<approved-provider-id>",
      "modelId": "<approved-model-id>",
      "region": "<approved-region-or-explicitly-accepted-undisclosed-value>",
      "endpointClass": "<approved-endpoint-class>",
      "providerCapabilityRef": "<opaque-capability-ref>",
      "credentialSourceRef": "<opaque-worker-secret-ref>",
      "usageTermsRef": "<accepted-terms-ref>",
      "budgetAuthorityRef": "<external-budget-authority-ref>",
      "maxCostMinor": "<integer-sub-cap>",
      "runtimeAttestationRef": "<exact-attestation-ref-if-required>",
      "runtimeAttestationDigest": "<exact-attestation-payload-sha256-if-required>",
      "expiresAt": "<timestamp>"
    }
  ]
}
```

真实 Provider bundle 还必须匹配当前生产策略要求的安全、隐私、超时、重试和保留事实。
不得写入 API key、token、password 或 credential value；仓库和浏览器只能看到不透明的
`credentialSourceRef`。

当前视频技术证据只允许外部权威审阅以下精确对：

```text
runtimeAttestationRef:
  technical-k2-funhpc-a100-20260821T130634Z
runtimeAttestationDigest:
  be03a079d17cad524b5e2e061e0c651a8f41f6f5221dfe80a8244398817ded53
```

该精确对来自 `2026-08-21` 当前启动，并已通过上传归档外层摘要、内部 manifest、
跨文件语义、敏感信息扫描和确定性逐字节重建。`2026-08-20` 的 attestation 仅作为
历史技术证据保留，不再作为本清单的当前运行时钉扎值。

`region=provider-not-disclosed` 必须被真实 Provider Authority 显式接受，或由其提供
真实 region；代码和操作者不得根据域名、GPU 型号或机房猜测。

## 5. 三媒体适配器状态

| mediaKind | 当前状态 | 开机前可做 | 仍缺少 |
| --- | --- | --- | --- |
| image | `NOT_SELECTED` | 人物八视图、构图、输入/输出/QC 候选契约 | 获批的同源 current G4 image request 扩展、精确 Provider/model/region、V4 adapter、真实尝试 |
| video | `TECHNICAL_PREREQUISITE_ONLY` | 现有 V4 ComfyUI/Wan2.2 adapter、49-frame profile、runtime attestation、四镜提示词 | Rights/Provider/Budget Authority、current G4 video request、同源真实尝试 |
| audio | `NOT_SELECTED` | 两句 text-only neutral TTS、无外部音频 cue sheet、48kHz stereo 候选 | 精确 Provider/model/region、V4 adapter、current G4 audio request、真实尝试 |

image/audio 不应通过在脚本中直接调用某个 SDK 来“补齐”。它们必须像现有视频路径一样，
进入 V4 media adapter 边界，由 V5 验证当前 lineage、策略、权利、费用、probe 和候选状态。
在精确 Provider 决定前，只保留 provider-neutral 的契约与测试，避免形成孤立路径。

## 6. 同源实验记录最小字段

开机后的每种 mediaKind 至少需要：

- 当前 workspace/run/CreativeShotVersion/GenerationRequest 的 exact refs、versions、digests；
- 当前 ProductionPolicy、RightsManifest 与 ProviderExecutionPolicy 的 refs/digests；
- provider/model/region/endpoint class 与 usage terms/budget authority refs；
- attempt ref、provider request ref、开始/结束时间、latency 和精确 cost minor；
- runtime attestation ref/digest、device facts 和 capability probe；
- output media type、bytes、SHA-256、时长/尺寸/帧率/声道等独立 probe；
- `UNTRUSTED_PROVIDER_CANDIDATE / UNSELECTED / NOT_ADMITTED`；
- `publicationAllowed=false`。

任何一类被阻断都必须记录为 blocked media type，并继续阻断发布；不能用视频成功替代
image 或 audio 的 P1 退出条件。

## 7. 当前停止决定

离线包可继续维护并接受人工创意审阅，但自动生产进度仍停在 P0→P1：

- Rights Authority bundle 缺失；
- Provider Authority bundle 缺失；
- `budgetAuthorityRef` 与媒体子上限缺失；
- image/video/audio 同源真实实验缺失；
- 候选显式选择与 V5 admission 缺失。

因此 P1 为 `NOT PASSED`，P2/P3 不得开始，所有创意资料保持候选。
