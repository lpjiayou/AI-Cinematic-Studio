# M10/M11 Spike-0 E4 — Exact Binding Review

Status: `HISTORICAL_EVIDENCE / COMPLETED_WITH_EXECUTION_AUTHORITY_CONFLICTS`.
Owner: Project Lead / Core Architecture Owner / Spike-0 Execution Gate Owner.
Consolidated: `2026-09-09`; `HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true`;
`currentStateClaimsAllowed=false`.

这是对后期第一步只读复核的文档化，未重新执行 E3 或重新申请生成授权。Core 采集基线为
`f007ab3e93c3fb7f5e8b3b7f81c34fec28858176` / Tree
`b5ef06d0b4557b979cd8ab4acb02790d35ec2223`。
现场身份观察时间为 `2026-09-09T11:59:18.809084+00:00`；绑定报告时间为
`2026-09-09T12:05:01.775152+00:00`。来源和原件摘要见[证据索引](M10_M11_SPIKE_0_E4_EVIDENCE_INDEX_2026-09-09.md)。

## 1. 原包已到位与精确目标

E3 原包为 1,428,336 字节，SHA-256
`ab4399d2ad769a8f8a9fc8ca0368a2e6d8f721ab76d6499a077d0a1a586dcfc2`。
后期复核记录 140 个归档条目、111 个普通文件、110 项内部摘要通过。该阶段在本地审核相同字节，未在 A100 解包、运行包内工具或打开业务数据库。本次文档整理只读这些已提供的审核副本，不重放历史 HTTP。

| 项目 | 封存记录支持的绑定 |
| --- | --- |
| technicalTargetId | `SPIKE0-E3-SH09-VISIBLE-UPPER-BODY-HEAD-TURN-LOCKED-V2` |
| executionClass / method | `MICRO_MOTION` / `SINGLE_ANCHOR_I2V` |
| 主体 / 镜头 | 仅沈知微可见；裴昀画外；`MEDIUM_CLOSE_UP` / `LOCKED` |
| sourceSpan | `ACTION[0]` 的 `[0,36)`；无对白、旁白或音频扩展 |
| Beat | `[0,48)`；最终 48 帧 |
| Run.frameRate / 时长 | 24 fps；48 ÷ 24 = 2 秒 |
| 生成画布 | 704×1280；不混用 720×1280 编辑母版 |
| 模型 length | 最终帧数加 1，即 49；不是最终输出 49 帧 |
| 输入 | 一个 READY 绑定；998,335 字节 PNG，704×1280；CRC/非 APNG 检查通过 |

原始动作（逐字保留）：

> 沈知微保持可见躯干稳定，缓慢抬眼并作小幅头部转向，眼神在头部转动后到位。

帧数来自 Beat 范围与 Run 输出字段，而非“48 条数据库记录”。sourceTextDigest 为
`086b775126f942a97beea0e67a605d66381ec2d2731f0f416aba7b16c4fd71f0`。

## 2. 独立一致性断言的覆盖

69/69 仅指该阶段独立只读断言。它们覆盖 InputPlan → 执行计划 → Shot → Beat → 视觉需求 → 原动作，以及 InputPlan → AssetVersion → 原始 PNG、元数据 profile/证明/模型/候选参数之间的精确引用。

| 非可加载摘录 | 原始记录摘要 |
| --- | --- |
| InputPlan digest | `a4cfaf66639eb62d6dc9615f063cdbbfe6755cad6df6a57921ee8c2241e547b1` |
| ExecutionPlan digest | `55a1afa3e12af505a9f2418a02517c756370f7d5da91ebef0d75d42b2a6fa239` |
| Shot digest | `d95edd6e0c1281ffb56e029b3e55fa3d69b6770a08703f9b3d02841b737086a7` |
| Beat digest | `d80b1fffa563ac8fdcc725c651208ce34773721b63b0bb52b8c517d633495f0d` |
| AssetVersion digest reference | `8812bf83bec5157cff443d9124d0e6bd317ba71cb2023abea07e0bc6f3e70dc4` |
| Anchor content SHA-256 | `3b4f871ab59332625f0d343bde0ca1686477a135a3a2f9d6373f474f22e252ea` |
| Attestation payloadDigest | `e84e9442011be173f5817419e1554682f1ee36a54e7d477022961d653d95a6b4` |

AssetVersion 覆盖的是原包/成员完整性、引用相等、首次/重放对象相等和原图字节一致。没有声称从公开 DTO 重新封装即可复算内部 payloadDigest，没有编辑或重签密封对象。

原版 v2 验证器的历史 PASS 保留，本阶段没有重跑该验证器，没有调用完整 `validate_method_aware_envelope`，也没有形成执行 envelope。较早 30/30 参数适配、61/61 节点合同和本次 69/69 不能合计成端到端执行通过。

## 3. C1：输入许可仍不授权视频执行

| 不可变历史字段 | 保留值 |
| --- | --- |
| manifest.dispatchAllowed | `false` |
| manifest.shotPlanApprovalState | `NOT_VERIFIED` |
| manifest.cameraContractState | `NOT_READY` |
| InputAssetVersion.providerProcessingAuthorized | `false` |
| InputAuthoritySubject.providerProcessingAuthorized | `false` |

manifest 仍为 `k2.golden-episode.manifest.v2`，executionMode 为 `LOCAL_EVIDENCE`。这些原有限制不是 E3 失败、输入损坏或新模型故障。将 E3 输入许可直接作为一次视频路由、worker 派发或 Provider 处理许可，会越过其明确边界。

本次未改字段、未重发输入权限、未调用私有权威接口，也未以直接 ComfyUI 请求绕过限制。独立不可变 Grant 的设计方向已确认，但[ADR-0022](../../governance/ADR-0022-generation-dispatch-grant.md)完整验收仍 PENDING，冻结代码中的[合法派发机制仍未实现](M10_M11_GENERATION_DISPATCH_AUTHORITY_AUDIT_2026-09-09.md)。

## 4. C2：元数据绑定不是完整执行绑定

operator profile 明确限定 `TECHNICAL_METADATA_ATTESTATION_ONLY_NOT_PRODUCTION_REGISTRY`；`generationAllowed=false`、`promptSubmissionAllowed=false`、`productionBackendRegistryConfigured=false` 保留。

候选 seed=0、steps=20、cfg=5、modelShift=8、sampler=uni_pc、scheduler=simple 与既有节点选项和数值范围相容。它们是新工程候选，非 E3 既有运行参数，`selectedForGeneration=false`，未激活、未批准生成。候选 profile canonical digest 为
`85265e072cdf49a10682224be4ff5da3f76d73d05b4a83a7867e890c36341d57`。

未闭合项目仍包括：backend registry/profile 的选择及摘要、resourceShape 映射、credentialSourceRef 解析、worker 源图/输入目录映射、单次费用映射。本轮未读取凭据、建立 registry、选择实际参数、创建 Job 或 envelope。只读复核不要求提前激活生产 registry。

证明仅绑定 `2026-09-09T09:39:37.515060Z` 的已观察进程；`futureLiveCurrentnessMustBeReverified=true`。下一进程需要新的 currentness 证据，不表示历史证明损坏。一次追加源码读取被安全层阻断的原记录保留，未声称那次读取成功或通过改接口绕过。

## 5. 费用与终态

已有累计 E4 预算及人工电源责任保留在私有授权中，不按尝试重新赋额，不转化为本次文档任务的新费用授权。账户费率、计费粒度/取整、24 小时最终结算、持续及停止后存储费、完整累计账/余额、单次分摊和上限仍未核实；账单差异成因未知，不以估算补齐。

```text
E3_STATE=PREPARED_AND_VERIFIED
E4_EXACT_BINDING_REVIEW=COMPLETED_WITH_EXECUTION_AUTHORITY_CONFLICTS
TECHNICAL_COMPATIBILITY=PASS_WITHIN_EVIDENCE_SCOPE
EXACT_EXECUTION_BINDING=NOT_RELEASED
SPIKE_0_READINESS=BLOCKED
SPIKE_0_EXECUTED=false
GENERATION_AUTHORIZATION_APPLICATION_SUBMITTED=false
SECOND_STEP_STARTED=false
```

第一步的 ComfyUI 新启动、实时 GET、模型全量重哈希、数据库连接、配置变更、prompt、派发和平台电源操作均为 0；这些零值仅属于该步骤。没有覆盖所有 E4 轮次的累计计数。后续执行、输出准入、发布及 M12-C3 没有由本复核获得授权。
