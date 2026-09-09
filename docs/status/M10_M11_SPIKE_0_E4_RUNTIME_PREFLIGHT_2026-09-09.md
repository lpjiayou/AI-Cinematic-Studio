# M10/M11 Spike-0 E4 — Runtime and Cost Preflight Evidence

Status: `HISTORICAL_EVIDENCE / VERIFIED_TECHNICAL_ONLY`; consolidated: `2026-09-09`.
Owner: Project Lead / Core Architecture Owner / Spike-0 Execution Gate Owner.
`HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true`; `currentStateClaimsAllowed=false`.

本回执整理 E4 后期现场材料，分析基线为 Core
`f007ab3e93c3fb7f5e8b3b7f81c34fec28858176`，Tree
`b5ef06d0b4557b979cd8ab4acb02790d35ec2223`。本次文档整理没有连接 A100、运行服务或重验模型。
文件身份、原始观察时间与保管范围见[证据索引](M10_M11_SPIKE_0_E4_EVIDENCE_INDEX_2026-09-09.md)。

## 1. 分阶段事实与已解决缺项

以下时间均为 UTC；日期除旧 R3/R4 外均为 2026-09-09。各行属于独立采集或审核，不能相加成一次端到端验收。

| 阶段与观察时点 | 证据支持的事实 | 保留的范围限制 |
| --- | --- | --- |
| 旧 R3/R4，2026-09-08 | 旧实例驱动 580.95.05；该阶段 ComfyUI 启动次数为 0 | 不能描述后期新实例，也不是 E4 全期间累计计数 |
| 当前实例采集，07:47:22.089–07:48:16.150 | 驱动 560.35.03；模型完整字节哈希 3/3 相符；当时未观察到 ComfyUI 进程 | torch 当时仅为包元数据，尚非实测运行时 |
| 首次实时元数据，08:31:16.959911–08:31:26.814347 | 现有 ComfyUI 启动 1 次；4 次 GET 均 200；11 个必需节点存在；队列前后均空 | 本进程没有生成正式 v2 证明，也没有推理 |
| 节点合同复核，08:45–08:57 | 对上述进程的既有 JSON 作 61/61 独立检查 | 没有新增实时 GET；不能冒充新服务 currentness |
| 冻结源码装配，09:07:15.602176 完成；09:09:14.200816 导入检查 | 632 文件、13,988,711 字节、Git blob/模式重建 Tree 相符；20 个冻结模块来源核对；原版 CLI 与 v2 builder/validator 可用 | 已完成，不再列为缺项；没有覆盖两份旧 checkout |
| 正式证明，09:39:31.208414–09:40:20.297120 | 本阶段启动 1 次；6 次 GET；原版 builder 全字节校验三模型；v2 IMAGE_TO_VIDEO 原版验证器 PASS | 仅对应本阶段同一服务进程；无推理、上传或生成请求 |
| 后期精确绑定，11:59:18.809084 现场身份，12:05:01.775152 本地整理 | E3 原包已到位；69/69 独立只读断言通过 | [C1/C2 执行边界](M10_M11_SPIKE_0_E4_EXACT_BINDING_REVIEW_2026-09-09.md)未放行 |

08:31 的 4 次 GET 为一次 system_stats、一次 object_info、前后两次队列；09:39 的 6 次为原版 CLI 的两次、独立交叉检查的两次，以及前后两次队列。它们来自不同服务进程。61 项节点合同、30 项较早离线适配和 69 项精确绑定检查的对象与覆盖面均不同。

## 2. 新实例技术规格

| 项目 | 2026-09-09 现场证据 |
| --- | --- |
| Provider / GPU | FunHPC；NVIDIA A100-PCIE-40GB，nvidia-smi 显示 40960 MiB |
| 驱动 / OS | 560.35.03；Ubuntu 24.04.1 LTS |
| CPU | 96 个可见逻辑 CPU；cgroup 配额约 10 CPU，不能将可见数当作实例配额 |
| 内存 | 宿主可见约 754 GiB；实例 memory.max 为 95,563,022,336 字节，即 89 GiB |
| 数据盘 | 07:47 采集总量 192,105,938,944 字节，余量 62,247,321,600 字节；不声称后续余量相同 |
| Python / torch | 既有解释器 3.12.7；torch 2.11.0+cu126；后期实际启动与实时接口验证，区别于早期静态包读取 |
| ComfyUI | 0.28.0；源码 commit `feca51a8544511dd73d43602f387def0cc601a9d`；所述现场 tracked diff 为空 |

正式证明中的 `vramTotalBytes=42409000960` 是运行时接口值；nvidia-smi 的 40960 MiB 是另一采集字段，保留各自来源，不改写为完全相同的测量值。早期终端未找到名为 torch 的 Conda 环境，不表示后期已定位的既有 venv 不存在；本次整理没有安装或重建环境。

## 3. 模型与节点合同

| 模型角色 / 文件名 | SHA-256 |
| --- | --- |
| UNET / `wan2.2_ti2v_5B_fp16.safetensors` | `456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e` |
| TEXT_ENCODER / `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68` |
| VAE / `wan2.2_vae.safetensors` | `e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156` |

07:47 现场采集对三模型共 18,144,966,705 字节计算摘要，前后文件身份稳定；08:31 仅复核文件身份，未全量重哈希；09:39 原版 builder 再次读取完整模型字节并通过 3/3 比对。文档执行窗口仅核验回执副本，没有取得或本地重验模型本体。

所需 11 节点为 `LoadImage`、`UNETLoader`、`CLIPLoader`、`VAELoader`、`CLIPTextEncode`、`Wan22ImageToVideoLatent`、`ModelSamplingSD3`、`KSampler`、`VAEDecode`、`CreateVideo`、`SaveVideo`。61 项复核覆盖 required/optional 字段、工作流枚举、三个模型名称、start_image 的 IMAGE 类型、设备与队列。`uni_pc/simple`、`mp4/h264` 等选项存在，不等于选定了实际生成参数或验证了视觉质量。

## 4. 正式 v2 证明与 operator profile

下表是原件必要字段的非可加载摘录；未改写、重签或重新封装原始 JSON。原件字节摘要与本回执派生摘要分别登记在证据索引。

| 字段 | 历史值 |
| --- | --- |
| schemaVersion / capabilityMode | `v4.comfyui-runtime-attestation.v2` / `IMAGE_TO_VIDEO` |
| authorityState / publicationAllowed | `TECHNICAL_EVIDENCE_ONLY` / `false` |
| observedAt | `2026-09-09T09:39:37.515060Z` |
| attestation 文件 SHA-256 | `c58d70cfcf6dfd77ae7c25b9d789e9f133b7e6a759730a8947cf6eed9de1516c` |
| factsDigest | `3899cb4def930e547096090c14b8333019acfa8d01d34ac066efb3b7fdf80ff1` |
| payloadDigest | `e84e9442011be173f5817419e1554682f1ee36a54e7d477022961d653d95a6b4` |
| operator profile 文件 SHA-256 | `04fc2cbad12c43ee8cc93c91bdfced8a4e2962d314cf54ac051255178ef784cb` |
| operator profile canonical digest | `646d1afe5c12321a101994291262fb5697c1301d14f3d83d9cd64dab1ab878a8` |
| 原版 validate_runtime_attestation | 历史同进程 PASS |
| futureLiveCurrentnessMustBeReverified | `true` |

该 profile 是当轮新建、实际使用并与证明绑定的元数据配置，不是恢复出的旧生产配置。providerId/modelId 为 `funhpc-self-hosted` / `wan22-ti2v-5b-fp16`；region 仅表示操作员选择的逻辑部署范围，地理位置未验证。实际端点、会话、主机标识、完整 argv 和环境字典留在私有原件。

`generationAllowed=false`、`promptSubmissionAllowed=false`、`productionBackendRegistryConfigured=false` 保留。原版 CLI、builder 和验证器未改；任务 wrapper 的副作用约束不是 OS 沙箱。正式证明已创建，不能再记成缺失，也不能用已结束进程的证明代替下一进程的 currentness。

## 5. 源码处置、清理与费用边界

| 源码角色 | 身份 | 处置 |
| --- | --- | --- |
| 历史 Core checkout | `0a6962be17b2b8809fb2de77bcd8b55723a9c550` | 不用于 E4/Spike-0；原位保留 |
| 历史 lineage-fixed checkout | `ade3ba1dd9ace5a21a57aead5453b29e9d69723e` | 不用于 E4/Spike-0；原位保留 |
| 唯一冻结工具快照 | f007ab3e commit / b5ef06d0 Tree（完整值见首段） | 已用于正式证明；不因本次 docs tip 变化而升级执行 pin |

精确目录映射留在私有交接清单。本次没有删除、改名、pull、checkout 或在这三处写标记。

09:39 的任务服务已正常结束，进程组无存活进程，显存回到 1 MiB；退出瞬间利用率 1% 按实保留。09:44:33 封包、10:46:47 后期观察均未见 ComfyUI 监听。持续接入代理未由这些阶段停止。这些是历史服务清理证据，不是平台关机或停止计费证明；本次文档任务未读取控制面，退出电源状态为 `UNKNOWN`。

既有累计 E4 预算及人工电源/数据保管责任已有独立批准，原件和账户账单留仓库外。本次没有新费用授权。账户适用费率、粒度/取整、24 小时订单最终结算、持续/停止后存储费用、完整累计账与单次执行费用映射仍未核实；已记录账单分项与总计存在未解释差异。CLI 内部 USD/0 构造占位不是免费证明，运行时间盒也不是停止计费证明。

## 6. 结论

```text
E3_STATE=PREPARED_AND_VERIFIED
E4_RUNTIME_EVIDENCE=VERIFIED_TECHNICAL_ONLY
FROZEN_TOOL_SNAPSHOT=READY
E4_V2_I2V_ATTESTATION=CREATED_AND_VALIDATED
E4_OVERALL=BLOCKED
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
GENERATION_AUTHORIZATION_APPLICATION_SUBMITTED=false
```

技术元数据、原版 v2 验证和输入就绪均不授予派发、Provider 处理、输出准入、Master/Export 或发布权。后期精确绑定结论以[绑定复核](M10_M11_SPIKE_0_E4_EXACT_BINDING_REVIEW_2026-09-09.md)为准；缺失的许可机制见[固定源码审计](M10_M11_GENERATION_DISPATCH_AUTHORITY_AUDIT_2026-09-09.md)。
