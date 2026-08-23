# AI Cinematic Studio Branch Protection

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-GIT-001` |
| 文档类型 | GitHub Branch Protection Configuration Specification |
| 首要保护目标 | `main` |
| 配置状态 | `DEFINED / NOT APPLIED / NOT VERIFIED` |
| 当前限制 | 本地仓库没有 Git remote，无法应用或核验 GitHub Ruleset |
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
| Approving Reviews | 所有 `main` Pull Request 至少 `2` 名非作者批准者 | GitHub 使用统一的 `2` approvals 配置，不依赖按语义动态切换数量 |
| High-impact Reviews | 架构、安全、数据、全仓库治理、分支保护与 Release 变更的两名批准者中，至少一个来自对应责任职能 | 专项责任和独立性有记录；缺少合格责任职能时保持阻塞 |
| Stale Approvals | 新 Commit 或实质性变更后撤销旧批准 | 最新修订重新获批 |
| Conversation Resolution | 所有阻塞意见和未解决对话必须关闭 | 没有 Blocking thread |
| Required Status Checks | 所有已注册且适用于变更的强制检查通过 | 没有 `FAIL`、`BLOCKED` 或强制 `NOT RUN` |
| Up-to-date Requirement | 合并前基于最新目标分支重新验证；可由 Merge Queue 或等价规则保证 | 验证修订与合并候选一致 |
| Linear History | 要求线性历史；禁用普通 merge commit | 使用 squash merge 或经批准的 rebase merge |
| Force Push | 禁止 | 无人拥有常规 force-push 权限 |
| Branch Deletion | 禁止 | `main` 不可删除 |
| Bypass | 默认禁止管理员、Repository Role 和 App 绕过 | 只有已记录 break-glass 例外 |
| Restrict Pushes | 只允许受控合并机制写入 | 人员和普通 token 不能直接写入 |

`main` 的含义仅为“仓库接受主线”。即使所有保护项通过，也不能自动得到 Implementation、Architecture、Release、Production 或 Phase Exit 授权。

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

1. `main` 的 GitHub 统一最低审批数为二，且两名批准者均不得是作者；该固定配置保证规则可被平台直接执行。
2. 作者不得计入两名必需批准者；两名批准者都必须独立审查，不能由 Committer 身份或自动化结果替代。
3. 当责任体系批准并创建 CODEOWNERS 后，启用 `Require review from Code Owners`；在此之前状态为 `PENDING`，不能虚构 Owner。
4. 架构变化必须具有 Accepted ADR 或明确 `ADR NOT REQUIRED` 依据。
5. 安全、数据、风险例外、Release 与 Phase Exit 由各自有权角色决定，普通 PR 批准不能代决。
6. 机器人只能报告检查结果，不能承担风险接受、架构批准或最终验收责任。

## 6. Merge 规则

- GitHub 默认只启用 squash merge；最终标题遵守 Commit Convention。
- Squash 后的 Commit body 或 footer 保留 `Refs: <task-id>`，并由 GitHub 保留 Pull Request 关系。
- 合并前核对目标分支、候选 SHA、检查结果、审批状态和未解决对话。
- 合并后如发现错误，使用 `revert` 或新修复 PR 恢复，不改写 `main` 历史。
- 自动合并或 Merge Queue 只能在全部条件满足后执行，不能覆盖人工阻塞意见。

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
2. 指定 Repository Governance Owner 与至少两名可承担非作者审批的 Reviewer；
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
- 缺少审批、失败检查、未解决对话被阻塞的实际结果；
- 正常 Pull Request 成功合并的对照结果；
- bypass actor 清单和例外流程核对；
- 对应 Evidence ID 与独立审查结论。

计划、本文内容或本地 Git 设置均不能代替 GitHub 侧实际证据。

## 12. 当前状态与风险

`ACS-GIT-001` 执行前没有 remote、GitHub 配置证据或 Tag，因此：

| 项目 | 状态 |
| --- | --- |
| 保护规范 | `DEFINED` |
| GitHub Ruleset | `NOT APPLIED / NOT VERIFIABLE` |
| `main` 直接推送限制 | `NOT VERIFIED` |
| Required Checks | `NOT CONFIGURED / NOT VERIFIED` |
| CODEOWNERS | `NOT CONFIGURED` |
| Baseline Tag / GitHub Release | `NOT CREATED` |

在这些状态关闭前，不得声称主分支已受 GitHub 技术保护。该缺口应继续作为 Repository Governance 风险跟踪，不影响本文作为配置规范的有效性。

## 13. 变更控制

降低审批数、允许直接推送、开放 force push、允许 Tag 移动、扩大 bypass actor 或删除必需检查，均属于高影响治理变化，必须：

1. 独立任务与风险评估；
2. Repository Governance Owner 和独立 Reviewer 批准；
3. 说明有效期、迁移、回退和审计影响；
4. 同步 Git Workflow、Baseline Process 和相关 Gate；
5. 配置后重新执行保护验证。
