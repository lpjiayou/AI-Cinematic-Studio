# AI Cinematic Studio Branch Protection

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-GIT-001` |
| 文档类型 | GitHub Branch Protection Configuration Specification |
| 首要保护目标 | `main` |
| 配置状态 | `CORE RULESET ACTIVE / CONFIGURATION-CONFORMING UNDER OWNER-APPROVED SINGLE-OPERATOR ZERO-APPROVAL SCOPE / PARTIALLY VERIFIED`; `FRONTEND RULESET ACTIVE / EFFECTIVE / CONFIGURATION-CONFORMING`; `BOTH OPERATIONAL BEHAVIOR VERIFICATIONS PENDING` |
| 当前核验 | `2026-08-25` 远端配置复读；Core ruleset `20544466`，Frontend `main-protection-v1` ruleset `21413134` |
| 当前差异 | Core 已按 Owner 决定采用 `0 approvals`，因此 PR #11 不再有 Reviewer capacity blocker；仓库级 General settings 仍允许 merge/squash/rebase，只有生效的 Core `main` ruleset 是 squash-only，且 Core 受控行为验证仍未闭合；Frontend 继续要求两名批准且 Reviewer 容量/行为验证仍未闭合 |
| 架构与 Phase 影响 | `NONE`；保护规则不授予实现、Release 或架构变化 |

## 1. 目的

本文定义 GitHub 上 `main` 以及未来可能启用的 `develop` 的最低保护规则、审批要求、例外流程和验证证据。它是配置规范，不是 GitHub 已配置证明。

本规范受 [Git Workflow](GIT_WORKFLOW.md)、[代码评审规则](CODE_REVIEW_RULES.md)、[提交约定](COMMIT_CONVENTION.md)、[完成定义](DEFINITION_OF_DONE.md)和[架构守卫](ARCHITECTURE_GUARD.md)约束。

## 2. 保护原则

- 默认拒绝直接修改受保护分支。
- 自动化检查、人工审批和正式授权各自独立，不能相互替代。
- 管理员和自动化账号不默认获得绕过权。
- 只要求真实存在、稳定且有 Owner 的检查，禁止用虚构检查名称制造“已保护”状态。
- 规则配置、例外使用和变更历史必须可审计。
- Branch Protection 只控制 Git 入口，不证明变更正确、可发布或符合 Production 条件。

## 3. `main` 必需保护规则

| GitHub 保护项 | 必需规则 | 通过条件 |
| --- | --- | --- |
| Pull Request | 合并前必须有 Pull Request；禁止直接推送 | 每次主线变化关联可访问 PR |
| Approving Reviews | 通用 `main` Pull Request 至少 `2` 名非作者批准者；Core 当前只适用第 3B 节零批准精确例外 | Frontend 保持 `2 approvals`；Core 当前 GitHub ruleset 为 `0 approvals`，不得扩张到其他仓库 |
| High-impact Reviews | 通用规则下，架构、安全、数据、全仓库治理、分支保护与 Release 变更的两名批准者中，至少一个来自对应责任职能 | Core 第 3B 节例外下由 Project Lead / Repository Governance Owner 显式决定并保留独立技术审查证据；这不降低其他仓库或专项授权 |
| Stale Approvals | 新 Commit 或实质性变更后撤销旧批准 | 最新修订重新获批 |
| Conversation Resolution | 所有阻塞意见和未解决对话必须关闭 | 没有 Blocking thread |
| Required Status Checks | 所有已注册且适用于变更的强制检查通过 | 没有 `FAIL`、`BLOCKED` 或强制 `NOT RUN` |
| Up-to-date Requirement | 合并前基于最新目标分支重新验证；可由 Merge Queue 或等价规则保证 | 验证修订与合并候选一致 |
| Linear History | 要求线性历史；禁用普通 merge commit | 按第 6 节当前规范使用 squash merge；若 Governance Owner 另行批准修改策略，可使用同样保持线性的 rebase merge |
| Force Push | 禁止 | 无人拥有常规 force-push 权限 |
| Branch Deletion | 禁止 | `main` 不可删除 |
| Bypass | 默认禁止管理员、Repository Role 和 App 绕过 | 只有已记录 break-glass 例外 |
| Restrict Pushes | 只允许受控合并机制写入 | 人员和普通 token 不能直接写入 |

`main` 的含义仅为“仓库接受主线”。即使所有保护项通过，也不能自动得到 Implementation、Architecture、Release、Production 或 Phase Exit 授权。

### 3A. Core 单人运营一批准例外（历史 / 已取代）

本节保留 `2026-08-25` 同日较早快照：Core `main` 曾采用 `1 approval`，且必须
来自合格非作者；PR #11 因 author=`lpjiayou`、reviews=`[]` 而处于 `0/1`
Reviewer capacity blocker。该配置与阻塞结论已由第 3B 节的后续 Owner 决定取代，
不得再作为现状引用。

### 3B. Core 单人运营零批准精确例外（当前）

Project Lead / Repository Governance Owner `蔺鹏` 于 `2026-08-25` 明确确认 Core
当前为单人运营，并批准 [Git Workflow 第 4B 节](GIT_WORKFLOW.md#4b-core-单人运营零批准精确例外当前2026-08-25)
所记录的精确例外：Core `main` ruleset 的平台最低批准数为 `0`，不是通用规范的
`2`。该例外只适用于 Core 仓库当前单人运营期，不适用于 Frontend，也不降低
Release、安全、风险接受、Phase Exit 或其他专项治理所需的决定。

`0 approvals` 不是作者批准自己，也不是将自动化或独立技术审查计为 GitHub
approval。Core 仍强制使用 Pull Request、精确候选独立技术审查、conversation
resolution、五项 strict checks、linear history、squash-only、force/delete
protection 和空 bypass。dismiss-stale、latest-push 与 unattributed-Copilot
extra-approval 因平台批准计数为零而关闭；不得以此推导“无需审查”或“自动可合并”。

## 4. Required Checks 逻辑基线

GitHub 只能绑定已真实注册的 Check 名称。初始启用时，Repository Governance Owner 必须把以下逻辑门禁映射到仓库实际检查，并记录名称、Owner、触发范围和失败处置：

| 检查类别 | 最低目的 | 适用性 |
| --- | --- | --- |
| Change Scope | 确认提交只包含任务范围，排除凭据、生成物和无关文件 | 所有 PR |
| Documentation | 验证 Markdown、内部链接、必需章节和术语一致性 | 文档或治理变化 |
| Formatting / Static Validation | 验证仓库已批准的格式与静态规则 | 存在对应实现时 |
| Unit | 验证局部行为与边界 | 存在获批代码变化时 |
| Contract | 验证公开契约兼容性 | 影响接口或跨层语义时 |
| Integration / E2E | 验证获批集成边界 | 风险与阶段 Gate 要求时 |
| Security / Secret Detection | 阻止凭据、已知高风险内容和未经批准依赖 | 所有适用 PR |
| Architecture Guard | 检测跨层、反向、循环或未经批准的架构变化 | 架构敏感变化 |

若必需逻辑检查尚未实现，状态应为 `NOT CONFIGURED`，对应高风险合并或 Baseline 应保持 `BLOCKED`；不得创建永远返回成功的占位检查。

检查结论必须绑定具体 Commit SHA。合并候选变化后，旧检查结果不能直接证明新候选。

## 5. Review 与 Ownership 规则

1. 通用 `main` 最低审批数为二；Frontend 继续执行两名批准。Core 在第 3B 节的 Owner-approved 单人运营精确例外期执行零名平台批准。
2. Core 的零批准例外不产生作者自批或 `0/0` 审批证据；精确候选独立技术审查仍是强制治理证据，但不是 GitHub approval。其他适用仓库和专项决定仍要求真实、合格且独立的批准者。
3. 当责任体系批准并创建 CODEOWNERS 后，启用 `Require review from Code Owners`；在此之前状态为 `PENDING`，不能虚构 Owner。
4. 架构变化必须具有 Accepted ADR 或明确 `ADR NOT REQUIRED` 依据。
5. 安全、数据、风险例外、Release 与 Phase Exit 由各自有权角色决定，普通 PR 批准不能代决。
6. 机器人只能报告检查结果，不能承担风险接受、架构批准或最终验收责任。

## 6. Merge 规则

- 受保护 `main` 的生效 ruleset 只允许 squash merge；普通 merge commit 与 rebase merge 均不得通过该规则集。
- Repository General settings 即使仍显示 merge/squash/rebase 三种方法，也不能据此声称普通 merge 或 rebase 对受保护 `main` 有效；同样不能把该事实写成“整个仓库只启用 squash”。准确结论必须限定为“有效 `main` ruleset squash-only”。
- Squash 后的 Commit body 或 footer 保留 `Refs: <task-id>`，并由 GitHub 保留 Pull Request 关系。
- 合并前核对目标分支、候选 SHA、检查结果、审批状态和未解决对话。
- 合并后如发现错误，使用 `revert` 或新修复 PR 恢复，不改写 `main` 历史。
- 自动合并或 Merge Queue 只能在全部条件满足后执行，不能覆盖人工阻塞意见。

## 6A. 2026-08-25 远端配置历史与当前差异账本

| Repository / Snapshot | 远端观察 | 剩余差异 / 限制 | 修复或关账验收条件 |
| --- | --- | --- | --- |
| Core / historical pre-fix snapshot | ruleset ID `20544466` 已 `active`，但 required approvals=`0`；仓库允许 merge/squash/rebase；ruleset 未要求 linear history、dismiss stale approvals、latest-push approval、conversation resolution 或 strict up-to-date，且缺少 `Integration Tests` | 这是修复前历史事实，不得继续作为当前配置结论，也不得删除其审计意义 | 已由下行 current snapshot 的 Owner-approved 配置取代 |
| Core / historical one-approval snapshot | ruleset ID `20544466` 为 `active`；required approvals=`1`；dismiss stale=`true`；latest-push approval=`true`；unattributed-Copilot extra-approval=`true`；thread resolution=`true`；allowed merge methods=`[squash]`；strict=`true`；`do_not_enforce_on_create=false`；五项 required checks、linear/deletion/non-fast-forward 与 bypass=`[]` 均已配置 | 这是本日中间配置历史；PR #11 当时 author=`lpjiayou`、reviews=`[]`，故形成 `0/1` Reviewer capacity blocker。该配置已由下行当前零批准决定取代 | 保留为审计轨迹，不再作为当前合并条件 |
| Core / current single-operator zero-approval snapshot | ruleset ID `20544466` 为 `active`；required approvals=`0`；dismiss stale=`false`；latest-push approval=`false`；unattributed-Copilot extra-approval=`false`；thread resolution=`true`；allowed merge methods=`[squash]`；strict=`true`；`do_not_enforce_on_create=false`；required checks 为 `Markdown`、`Documentation Links`、`Unit Tests`、`Contract Tests`、`Integration Tests`，且远端 UI 继续显示 GitHub Actions source；linear history、deletion protection、non-fast-forward protection 生效；bypass=`[]` | 配置符合第 3B 节 Core 单人运营零批准精确例外。远端设置页保存后已复读，但本轮变更后的 API integration ID 未独立复读；受控负向/正向行为验证尚未完成。Repository General settings 仍允许 merge/squash/rebase，因此只能称有效 `main` ruleset squash-only。PR #11 author=`lpjiayou`、reviews=`[]` 不再构成 approval blocker | 保持五项 required checks、thread resolution、strict、linear、no force/delete/bypass；在精确候选上完成独立技术审查和全部检查；完成直接推送/force/delete/失败检查/未解决 thread 的负向验证及正常 PR 正向对照。缺少 approval 的负向验证在本例外下为 `N/A` |
| Frontend | 远端分支仅剩 `main`，并保留 `20` 个 annotated archive tags；`main-protection-v1` ruleset ID `21413134` 为 `active` 且对 `main` effective；要求 `2` approvals、dismiss stale approvals、latest-push approval、conversation resolution、linear history；仓库为 squash-only；严格要求 `verify`、`gate-c-k2-browser`、`gate-k2-control-plane-browser` 三项检查；bypass actor 为空 | 当前合格 Reviewer 容量不足，无法据此证明任一作者都能取得两名合格非作者批准；直接推送/force/delete/缺审批/失败检查/未解决对话的负向验证及正常受保护 PR 的正向验证尚未完成。`delete_branch_on_merge=false` 是仓库级分支生命周期自动化缺口；当前“仅 `main`”快照不证明未来自动清理 | 补足合格 Reviewer 容量；完成并留存负向/正向行为证据；决定并记录短期分支自动删除或等价受控清理机制。完成前只可称配置 active/effective，不可称端到端 `VERIFIED` |

Core current snapshot 的配置结论是
`CONFIGURATION-CONFORMING / PARTIALLY VERIFIED / BEHAVIOR VERIFICATION PENDING`。
它不是 `END-TO-END VERIFIED`，也不使 PR #11 自动可合并。PR #11 的平台 approval
gate 依 Owner 决定为 `N/A / REQUIRED=0`；精确候选仍须通过独立技术审查、五项
required checks、conversation resolution 和线性 squash 路径，且 Core ruleset
没有 bypass actor。

两个最终基线 SHA 的 GitHub Actions 均成功；但各有一个内容为空的 Cursor check
suite 仍为 `queued`。该外部 suite 既不能被描述为已完成，也不应作为必需检查；
required checks 只绑定仓库真实存在、由 Actions 产生且有明确 Owner 的检查。

## 7. `develop` 条件性保护

`develop` 当前未创建、未启用。若依 [Git Workflow](GIT_WORKFLOW.md) 通过独立决定激活，至少应用：

- Pull Request 必需；禁止直接推送、强制推送和删除；
- 至少一名独立批准者，实质性更新后撤销旧批准；
- 所有适用 Required Checks 通过；
- 所有阻塞对话解决；
- 合并候选与最新 `develop` 同步；
- 管理员默认不得绕过；
- `develop → main` 必须使用新的 Pull Request，并满足完整 `main` 保护，不能沿用部分分支检查作为主线批准。

`develop` 的保护不能低于其承载风险，也不能把集成状态解释为 Baseline 或 Release Ready。

## 8. 工作分支规则集

对 `feature/**`、`docs/**`、`governance/**`、`experiment/**` 等工作分支，建议通过 GitHub Ruleset 实施：

- 禁止删除仍有关联开放 PR 或保留要求的分支；
- 分支进入评审后禁止未经协调的 force push；
- 限制创建不符合命名约定的分支；
- 阻止直接把 `experiment/**` 合并到 `main`；
- 合并后由受控机制删除短期分支；
- 不把工作分支保护误认为主线保护或实施授权。

## 9. Break-glass 例外

只有恢复仓库可用性或处置紧急安全事件时，才能申请临时绕过。例外记录必须包含：

- 事件、任务或风险编号；
- 目标分支和准确 Commit 范围；
- 请求人、批准人、执行人及职责分离；
- 正常保护无法使用的事实原因；
- 影响、补偿控制、回退和有效期；
- 操作后的独立复核、保护恢复和后续 PR。

例外不得覆盖未经批准的架构变化、Phase 范围、敏感数据使用或 Release 决策。到期后权限必须自动或人工撤销，并验证保护已恢复。

## 10. 配置应用顺序

1. 创建并验证 GitHub Repository 和 `origin` remote；
2. 指定 Repository Governance Owner 与通用规范要求的至少两名非作者 Reviewer；Core 单人运营零批准精确例外期将平台 Reviewer capacity 标记为 `N/A`，但仍须安排精确候选独立技术审查；
3. 确认默认分支为 `main`；
4. 配置 Pull Request、审批、对话、历史、删除、force-push 与 bypass 规则；
5. 注册真实检查并记录逻辑门禁映射；
6. 配置允许的合并策略和可选 Merge Queue；
7. 使用非管理员账号验证直接推送被拒绝；
8. 使用测试 Pull Request 验证缺少审批、失败检查和未解决对话均会阻塞；
9. 保存配置快照、验证结果、时间和责任人；
10. 定期复核 Ruleset 漂移和 bypass 记录。

## 11. 验证证据标准

只有以下证据齐备时，`main` Branch Protection 才能标记为 `VERIFIED`：

- GitHub Repository 标识与默认分支；
- Ruleset/Branch Protection 配置导出或受控截图；
- 配置修订、应用责任人和复核时间；
- 直接推送、force push 和删除被拒绝的实际结果；
- 适用的缺少审批、失败检查、未解决对话被阻塞的实际结果；Core 零批准精确例外将“缺少审批”负向项标记为 `N/A`；
- 正常 Pull Request 成功合并的对照结果；
- bypass actor 清单和例外流程核对；
- 对应 Evidence ID 与独立审查结论。

计划、本文内容或本地 Git 设置均不能代替 GitHub 侧实际证据。

## 12. 当前状态与风险

本节的原始 `ACS-GIT-001` 初始快照曾记录“没有 remote / Ruleset 未应用”。
2026-08-25 已有远端只读证据，当前状态由下表和第 6A 节覆盖；初始快照不再作为
现状结论：

| 项目 | 状态 |
| --- | --- |
| 保护规范 | `DEFINED` |
| Core GitHub Ruleset | `20544466 / ACTIVE / CONFIGURATION-CONFORMING UNDER SINGLE-OPERATOR ZERO-APPROVAL EXCEPTION / PARTIALLY VERIFIED` |
| Frontend GitHub Ruleset | `main-protection-v1 / 21413134 / ACTIVE / EFFECTIVE / CONFIGURATION-CONFORMING` |
| Frontend 远端分支归档 | `REMOTE BRANCHES=main ONLY / ANNOTATED ARCHIVE TAGS=20 / delete_branch_on_merge=false` |
| 合格 Reviewer 容量 | `CORE PR #11: PLATFORM APPROVAL N/A, REQUIRED=0 / FRONTEND INSUFFICIENT FOR TWO ELIGIBLE NON-AUTHOR APPROVALS` |
| `main` 直接推送、force、delete、审批/检查/thread 阻塞及正常 PR 对照行为 | `CONTROLLED NEGATIVE / POSITIVE VERIFICATION NOT COMPLETED` |
| Required Checks | `CORE FIVE STRICT CHECKS CONFIGURED; PRIOR API SNAPSHOT integration_id=15368, NOT RE-READ AFTER ZERO-APPROVAL MUTATION / FRONTEND THREE STRICT CHECKS CONFIGURED` |
| Merge methods | `CORE REPOSITORY GENERAL SETTINGS=merge+squash+rebase / EFFECTIVE main RULESET=squash-only`; `FRONTEND=squash-only` |
| Bypass | `CORE=[] / FRONTEND=[]` |
| 外部 Cursor check suites | `EMPTY / QUEUED / NOT A REQUIRED CHECK / NOT COMPLETE` |
| CODEOWNERS | `NOT REVERIFIED IN THIS SNAPSHOT` |
| Baseline Tag / GitHub Release | `OUTSIDE THIS SNAPSHOT'S VERIFIED CLAIMS` |

当前可以声称 Frontend `main` 的技术 ruleset 已 active/effective，配置字段满足本规范，
且远端分支已清理为仅 `main` 并由 `20` 个 annotated tags 保留归档入口；不能因此声称
Frontend 治理已端到端 `VERIFIED`，因为 Reviewer 容量和行为验证仍未关账。Core 可
声称 ruleset 配置在 Owner-approved 单人运营零批准精确例外下合规，并已在远端设置
页保存后复读；不能声称本轮变更后的 API integration ID 已独立复读，也不能声称行为
或运营关账。PR #11 不再受 approval gate 阻塞，但仍受精确候选审查、检查、thread
与 squash 合并条件约束。
两仓的空 Cursor suite 仍为 `queued`，不得扩张为“所有 check suites 已完成”。这些
残余缺口继续在风险登记册中跟踪，不影响本文作为配置规范的有效性。

## 13. 变更控制

降低审批数、允许直接推送、开放 force push、允许 Tag 移动、扩大 bypass actor 或删除必需检查，均属于高影响治理变化，必须：

1. 独立任务与风险评估；
2. Repository Governance Owner 和独立 Reviewer 批准；若 Core 处于第 3B 节单人运营例外且不存在独立平台 Reviewer，必须由 Project Lead / Repository Governance Owner 显式作出精确决定，并保留不计为平台 approval 的独立技术审查证据；
3. 说明有效期、迁移、回退和审计影响；
4. 同步 Git Workflow、Baseline Process 和相关 Gate；
5. 配置后重新执行保护验证。

第 3B 节的 Core `0 approvals` 已由 Project Lead / Repository Governance Owner
作为单人运营精确决定记录，并由远端设置页保存后复读。它不是 break-glass，不允许
bypass，也不降低 Frontend 的 `2 approvals` 或任何通用 Release/安全/风险接受
规范。扩大适用仓库、降低其他门禁或再次改变批准数仍须重新执行本节全部变更控制。
