# M10/M11 — Generation Dispatch Authority Audit

Status: `HISTORICAL_EVIDENCE / MECHANISM_NOT_IMPLEMENTED_AT_AUDITED_COMMIT`.
Owner: Project Lead / Core Architecture Owner / Generation Dispatch Authority Owner.
Documented: `2026-09-09`; `HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true`;
`currentStateClaimsAllowed=false`.

本文件是本次补录整理的既有审计结论，依据 `DISPATCH_AUDIT_HANDOFF.md` 与固定源码复核。
交接摘要是审核窗口后写汇总，不是前次 A100 导出的原始 JSON 或终端回执。
前次审计的精确开始/结束时间未随该摘要提供；本文件不补造时间、raw 日志或独立原包摘要。
来源字节身份见[证据索引](M10_M11_SPIKE_0_E4_EVIDENCE_INDEX_2026-09-09.md)。

## 1. 结论与计数语义

```text
AUDITED_CORE_COMMIT=f007ab3e93c3fb7f5e8b3b7f81c34fec28858176
AUDITED_CORE_TREE=b5ef06d0b4557b979cd8ab4acb02790d35ec2223
MECHANISM_EXISTS=false
WRITE_PATH_COUNT=0
GENERATION_DISPATCH_MECHANISM_AT_AUDITED_COMMIT=NOT_IMPLEMENTED
GENERATION_DISPATCH_DESIGN_DIRECTION=INDEPENDENT_IMMUTABLE_GRANT_CONFIRMED
ADR_0022_STATUS=PROPOSED
ADR_0022_FULL_ACCEPTANCE=PENDING
GENERATION_DISPATCH_IMPLEMENTATION_AUTHORIZED=false
```

`WRITE_PATH_COUNT=0` 专指将 Project Lead 的精确批准转化为以下五目标字段合法授权状态转换的已实现路径，不能解释为源码中没有赋值、预检或默认值。

| 五个历史目标字段 | 冻结值 |
| --- | --- |
| manifest.dispatchAllowed | `false` |
| manifest.shotPlanApprovalState | `NOT_VERIFIED` |
| manifest.cameraContractState | `NOT_READY` |
| InputAssetVersion.providerProcessingAuthorized | `false` |
| InputAuthoritySubject.providerProcessingAuthorized | `false` |

前次审计记录：唯一冻结来源的 632 文件 Tree 已核对；领域目录 44 个 Python 文件，四个字段名命中 8 个文件、54 行。providerProcessingAuthorized 涉及两个不同权威对象，所以共有五个目标字段。

本次独立静态观察时间为 `2026-09-09T13:45:25.320373+00:00`：在同一 commit 的 CPU 工作树读取 15 份源码中的指定段落及相关合同；领域目录检索另得到 44 文件、8 个命中文件、54 行。对 services/apps/scripts/tests/architecture/governance 内 Python、JSON、Markdown 的 `GenerationDispatchGrant` 检索为 0 行，执行于新 ADR 文件创建前。两个时点的计数分别记账；字符串未命中仅是辅助证据，结论还依赖下面的命令、守卫和存储边界。没有运行产品模块、连接业务数据库或重做 A100 审计。

## 2. 固定源码证据

以下行号只针对上述完整 commit；链接用于导航，文件身份由 commit/Tree 限定，不随未来 main 的行号移动重新解释。

| 文件及固定行号 | 实际语义 |
| --- | --- |
| [foundation.py](../../services/v5_core_os/episode_production/foundation.py)，1039–1045 | manifest v2 创建时保留未批准的安全值 |
| 同文件，353–359；1075–1188 | repository 只有 create/get/get_by_idempotency/list；create 字段闭集及 currentness 重解析，没有目标批准更新命令 |
| [method_aware_media.py](../../services/v5_core_os/episode_production/method_aware_media.py)，1632–1658 | 原安全值一致仍拒绝 v2 video routing；擅自改值报 stale |
| [method_aware_input_assets.py](../../services/v5_core_os/episode_production/method_aware_input_assets.py)，152–164 | InputAssetVersion 要求 immutable=true、providerProcessingAuthorized=false |
| 同文件，307–354 | 以原 manifest、精确 Beat 和输入内容构造 subject，Provider 处理许可仍 false |
| 同文件，410–473；608–659 | E3H intake 四记录原子追加；Admission/AssetVersion 两记录原子追加；没有升级派发权限 |
| [input_append_authority.py](../../services/v5_core_os/episode_production/input_append_authority.py)，35–51；379–406 | 允许输入生命周期操作，显式排除 Provider、媒体生成、派发等；固定安全值及三个 bool 强制 false |
| [shot_graph.py](../../services/v5_core_os/episode_production/shot_graph.py)，1093–1107；2879–2888 | 草稿安全值校验和投影，不是 ShotPlan 或 camera 批准 |
| [media_candidate_review.py](../../services/v5_core_os/episode_production/media_candidate_review.py)，609–650 | v2 普通 review 仍拒绝；只有经验证的精确输入例外 |
| [dynamic_media_revision.py](../../services/v5_core_os/episode_production/dynamic_media_revision.py)，498–502、552、565、604、629、655、757 | 预检验证与 false 投影，不发放派发许可 |
| [audio.py](../../services/v5_core_os/episode_production/audio.py)，1937–1951 | 非持久化音频规划为 CONTRACT_ONLY_NOT_DURABLE / dispatchAllowed=false |
| [server.py](../../apps/creator_workspace_mvp/server.py)，232–315 | public request 字段闭集和禁止客户端注入的权威字段，不含目标批准载荷 |
| [public.py](../../services/v5_core_os/episode_production/public.py)，879–905 | 服务端解析 InputPlan 后进入同一拒绝 v2 的路由 |
| [输入 authority CLI](../../scripts/method_aware_input_append_authority.py)，94–151 | build/validate 只构造、校验输入 bundle，不写生产 journal |
| [method_aware_worker.py](../../services/v4_platform/method_aware_worker.py)，39–96；98–135 | 按已配置 backend 和指定 Job 执行；不能代替 V5 签发许可 |
| [internal_execution.py](../../services/v5_core_os/episode_production/internal_execution.py)，68–192；195–246 | 既有 P1 进程配置 grant，不是五字段原子授权转换 |
| [production_policy.py](../../services/v5_core_os/episode_production/production_policy.py)，832–923 | 创建独立政策 bundle，不改 Run、输入 subject 或 AssetVersion |
| [evidence.py](../../services/v5_core_os/episode_production/evidence.py)，1794–1936 | 已有 journal 事务、幂等与 CAS；没有目标 GenerationDispatchGrant 业务命令 |

交接表的 worker 第二段标为 99–143；固定文件实际止于 135 行，main 从 98 行开始。本次按实际 98–135 引用，保留该导航差异，不修改原交接或产品源码；职责判断不变。

## 3. 控制合同与邻接机制

[ADR-0019](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) 252–254 行明确 method planning 与 provider dispatch 分阶段；[M3–M11 合同](../../architecture/M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md) 292–293、315–343 行保留 planning/routing 的非执行含义。
[ADR-0021](../../governance/ADR-0021-manifest-v2-technical-input-append-authority.md) Decision 5/9 与 Verification 继续禁止把 READY 输入及可用 backend 直接变成 v2 视频许可；更广权限需要另一个 Accepted 决策。
[ADR-0014](../../governance/ADR-0014-k2-001-archive-k2-002-changan-start.md) 的精确批准、身份/权利/运行时/预算与 GPU 独立边界保留。

可复用邻接机制包括 E3H 精确 subject 与独立 digest pin、HumanSelection 人类决策、Admission 血缘、V5 evidence journal 原子追加，以及 E1 的 V4 worker/Attempt/lease/CAS。它们分别承担输入权威、选择、资产、持久化或执行职责；已有这些机制不能记作 GenerationDispatchGrant 已实现。

## 4. 设计方向与未批准范围

Project Lead 已选定独立、不可变 GenerationDispatchGrant 方向，原五字段及 AssetVersion/InputAppendAuthority 历史摘要保持原值。[ADR-0022](../../governance/ADR-0022-generation-dispatch-grant.md) 记录完整审议稿，分类为 DRAFT，Status 为 Proposed，完整审批仍 PENDING。

文档登记与合并不等于 Accepted，不实施 schema、Terminal、CAS 或消费规则，不签发真实 Grant，不修改配置、DDL 或队列。`SPIKE_0_READINESS=BLOCKED`、`SPIKE_0_EXECUTED=false`；本次没有提交生成执行授权申请，也不启动后续实现任务。
