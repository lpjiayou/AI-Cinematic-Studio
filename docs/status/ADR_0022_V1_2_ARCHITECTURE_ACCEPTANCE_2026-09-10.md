# ADR-0022 v1.2 — 架构接受决定记录

Status: `RECORDED`; class: `HISTORICAL_EVIDENCE`; date: `2026-09-10`.
Owner: Project Lead / Core Architecture Owner / Generation Dispatch Authority Owner / Spike-0 Execution Gate Owner.
`currentStateClaimsAllowed=false`; `HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true`.

## 1. 批准来源与效果

决策人：蔺鹏。架构决定引用：`ACS-M10-M11-IMMUTABLE-GENERATION-DISPATCH-GRANT-ADR`。
接受记录引用：`ACS-ADR-0022-V1-2-ARCHITECTURE-ACCEPTANCE-20260910`。

Project Lead 在 v1.2 独立复审后明确回复 **“Accepted”**，接受下面精确字节的完整架构合同；随后对“Accepted 状态回填与文档入库”另行回复 **“授权”**。登记日期为 2026-09-10，未记录精确批准时刻，不从文件 mtime 或提交时间推导该时刻。

本记录是已有人工接受决定的公开、非运行时记录，不是审核窗口代替批准，不是 GenerationDispatchGrant 或 runtime approval bundle。架构规范以 [ADR-0022](../../governance/ADR-0022-generation-dispatch-grant.md) 为准。本次文档发布权限不授权实现、部署、费用、真实 Grant 签发/消费或生成。

## 2. 原接受对象与发布对象

| 对象 | 字节数 | SHA-256 | 含义 |
| --- | ---: | --- | --- |
| v1.2 原候选 | 72590 | `b963c12a07dea8816516752a40470df035e275714909a302ee8087963d4af75f` | Project Lead 接受的精确原字节；原 Proposed 元数据保留在仓库外原件 |
| v1.2 Accepted 发布版 | 74503 | `ecb896012ec1a501b1883d6239ba22514c07d61adab06062d453f441c1573f60` | 仅更新接受/发布元数据和历史时点说明，不改变第 1—13 节 |

原候选 Git blob 为 `029d9794e02a75d3102f2b361917599a6b210c2a`；发布版 blob 为 `738682ce878cc1560f61c944d3facccdb6c704b2`。这些是文件对象 ID，不是提交 SHA。

第 1—13 节（从 `## 1. Context 与保留边界` 起，至 `## 14. 修订记录与源码依据` 之前）UTF-8 原字节 SHA-256：`b63c0a588de2ae4f4085fa0b80fc69889d6a9836d29f133c9de5c8b8d960b7d1`。两版本该段完全相同。规范 schema、权限、摘要算法、CAS、协调、消费、幂等、时间与费用语义不得借状态回填更改。

## 3. 来源材料与范围限制

| 原件 | SHA-256 | 用途 |
| --- | --- | --- |
| ADR_0022_V1_2_ARCHITECTURE_ACCEPTANCE.md | `3998d05aed72356ecc0899397db7b101ba59e75aa53a39a293dc4bee57572e6b` | 原独立接受记录；本文件为其公开登记派生，并补充发布版摘要 |
| ARCHITECTURE_ACCEPTANCE_RECEIPT.json | `fb7fb24b9c52f250bdbffb4b003338fc4ba932885fdf43f576b86298c2ad100a` | 原机器可读接受回执；其中未回填/未发布为该次动作的历史事实 |
| v1.2 独立复审 REVIEW_RECEIPT.json | `05b2e3729e93810b768eaee8368becd5e6b93597f77ea855da5f4164fffcffd1` | 审核意见及原候选身份；不是运行验收 |
| ADR_0022_V1_2_F01_F04_EXECUTOR_DELIVERY_20260910.zip | `5fc41a1c086fc8f1e684027635b0ff29988f17cd4b5da78baf7880aeb8503ef9` | 既有单文件落稿与文档检查的封存证据；本次不重写旧日志 |

F01—F04 规范修订随完整架构接受；不追认真实 writer 覆盖、并发/崩溃测试、分阶段 transport、费用依据、执行参数或部署已验证。单次 Grant 及生成的批准仍须另行形成，不能复用本接受记录。

## 4. 不变边界与发布记录

```text
ADR_FULL_ACCEPTANCE=ACCEPTED_ARCHITECTURE_ONLY
GENERATION_DISPATCH_IMPLEMENTATION_AUTHORIZED=false
LIVE_GRANT_ISSUANCE_AUTHORIZED=false
LIVE_GRANT_CONSUMPTION_AUTHORIZED=false
PROMPT_SUBMISSION_AUTHORIZED=false
SPIKE_0_READINESS=BLOCKED
IMPLEMENTATION_AUTHORIZATION_APPLICATION_SUBMITTED=false
GENERATION_AUTHORIZATION_APPLICATION_SUBMITTED=false
```

文档对照提交：`3bf2e7a5152a7bd9c1087571aab6413a53a43bb6`。已审计 E4 执行代码 pin 仍为 `f007ab3e93c3fb7f5e8b3b7f81c34fec28858176`；新 docs 提交不移动执行 pin、Frontend pin 或既有 tag。五个历史业务字段和 E3/E4 原始回执不变。

本文件只记录接受决定及两个文件身份。实际 PR、CI、合并提交/tree、分支清理与本文件自身摘要由仓库外最终执行回执提供，避免自包含摘要循环和预报完成。接受决定不是“阻塞已解除”或“已获准生成”的结论。
