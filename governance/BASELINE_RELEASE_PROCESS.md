# AI Cinematic Studio Baseline Release Process

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-GIT-001` |
| 文档类型 | Repository Baseline Tag & GitHub Release Governance |
| 流程状态 | `DEFINED` |
| 当前执行状态 | `BLOCKED`；无 remote、无 GitHub 保护证据、无获批 Baseline 候选 |
| 架构影响 | `NONE`；Baseline 不修改或重命名 V2.3 Architecture |
| 授权影响 | `NONE`；Baseline、Tag 与 GitHub Release 不自动授权部署、Production 或 Phase 变化 |
| ADR | `NOT TRIGGERED`；本文不定义构建、部署、环境晋级或产品发布机制 |

## 1. 目的与术语

本文定义一个仓库修订如何经过 Development、Validation、Review、Tag 和 Release，成为不可歧义、可追溯的 Repository Baseline。

**Repository Baseline** 是对特定 Git Commit 及其证据的治理快照。**GitHub Release** 是该 Baseline 的发布记录。二者都不等于软件已部署、Production Ready、商业化完成、Phase 已退出或 V2.3 架构发生变化。

产品 Release 或 Production Validation 仍受 [Release 验证流程](../docs/11-testing/release-validation.md)、适用 Phase Gate、风险接受和独立 Release Decision 约束。

本文只治理 Git Commit、Tag 和 GitHub Release 记录，不新增或修改全仓库构建、部署、环境晋级及产品发布机制，因此不改变 [架构守卫](ARCHITECTURE_GUARD.md) 所保护的发布架构，也不触发 ADR。未来若 Baseline 流程扩展到这些机制，必须重新执行架构变更判断。

## 2. Baseline 原则

- **唯一候选**：一次 Baseline 决定只对应一个完整 Commit SHA。
- **主线来源**：正式 Baseline Tag 只指向受保护 `main` 上的 Commit。
- **证据先行**：没有验证、评审和风险结论不得创建正式 Tag。
- **不可变**：正式 Tag 不移动、不复用、不静默删除。
- **内容真实**：Release Notes 只记录该 Commit 已存在且已验证的事实。
- **权限分离**：开发、验证、评审、Tag 和 Release 决定由明确角色承担；责任不自动等于授权。
- **范围不扩张**：Baseline 不能追认未批准代码、API、数据库、架构或 Phase 范围。

## 3. 标准流程

```text
Development
    ↓
Validation
    ↓
Review
    ↓
Tag
    ↓
Release
```

任何阶段发现范围漂移、证据失效、未解决阻塞或候选变化，都必须回到相应前置阶段。流程不能因日历期限或演示需要跳过。

Review Stage 包含 Pull Request 审查、受保护合并、最终 `main` SHA 冻结、对最终 SHA 的 post-merge 强制验证，以及对该最终证据的接受。它仍是一个 Stage，不在 Review 与 Tag 之间隐藏未受治理的合并步骤。

## 4. 责任模型

| 角色 | 最低责任 | 不得代替 |
| --- | --- | --- |
| Change Owner | 冻结候选范围、Commit、包含项、排除项和回退方式 | 独立验证与批准 |
| Validation Owner | 汇总适用检查、实际结果、Evidence ID 和限制 | Release Decision |
| Independent Reviewer | 复核范围、证据、历史、风险和治理一致性 | 作者自检 |
| Repository Governance Owner | 确认分支保护、Tag 规则、权限和审计链 | 架构或产品授权 |
| Tag Custodian | 在批准后创建并验证 annotated Tag | 决定候选是否可发布 |
| Release Decision Owner | 作出 `PUBLISH / HOLD / WITHDRAW` 决定 | Phase Exit 或 Production 授权 |

具体 Person/Function 必须在每次 Baseline Record 中接受指派。角色未指派时流程为 `BLOCKED`。

## 5. Stage 1 — Development

### 5.1 进入条件

- 工作对应已批准任务和允许范围；
- 从获批源分支创建符合命名规则的短期分支；
- 架构、数据、安全、依赖和 Phase 影响已判断；
- 工作区中的其他变更已识别并隔离。

### 5.2 活动

1. 只实现当前任务所需变化；
2. 使用原子 Commit 并关联任务；
3. 保持代码、测试、文档和治理记录同步；
4. 记录新增、修改、删除文件与已知限制；
5. 在提交评审前完成作者自检。

### 5.3 Development 输出

- 候选工作分支与 Commit 列表；
- 变更范围和明确排除项；
- 任务/ADR/风险引用；
- 初步验证结果与未解决问题；
- 回退或撤销路径。

Development 完成只表示候选可以申请 Validation，不表示可以合并、Tag 或 Release。

## 6. Stage 2 — Validation

Validation 必须绑定同一个不可变候选 SHA，并遵守 [测试证据标准](../docs/11-testing/test-evidence-standard.md)。

最低核对：

| 领域 | 验证要求 |
| --- | --- |
| Scope | 文件清单只包含获批任务，没有无关或禁止内容 |
| Git | Commit 可解析、历史清晰、没有意外 merge、Tag 或未说明二进制 |
| Documentation | Markdown、链接、章节、术语和权威引用有效 |
| Code / Tests | 适用 Unit、Contract、Integration、E2E 具有真实结果；无实现时明确 `N/A` 依据 |
| Architecture | 符合 V2.3；存在 Accepted ADR 或批准的 `ADR NOT REQUIRED` 结论 |
| Security / Data | 没有凭据、未授权数据、危险权限或最小披露问题 |
| Dependency | 没有未批准依赖、锁定变化或外部来源 |
| Reproducibility | 候选、命令/方法、上下文、预期和实际结果可复核 |

状态使用 `PASS / FAIL / BLOCKED / NOT RUN / N/A`。强制项目存在 `FAIL`、`BLOCKED` 或 `NOT RUN` 时不得进入 Review；`N/A` 必须有客观理由和批准。

候选 SHA 发生实质变化后，受影响验证必须重新执行，不能复用旧绿色状态。

## 7. Stage 3 — Review

Review 通过 Pull Request 执行并满足 [分支保护规范](BRANCH_PROTECTION.md)。评审包至少包含：

- 完整候选 SHA 和目标 `main`；
- 任务、范围、包含项与排除项；
- 验证证据索引及所有非 PASS 状态；
- 架构、数据、安全、依赖与 Release 影响；
- 风险、例外、限制、回退和后续责任；
- 建议 Baseline 版本及 Release Notes 草案。

Review 只有在以下条件全部成立时才能结论为 `APPROVED FOR TAG`：

1. Pull Request 候选已经完成 Stage 2 Validation，并取得满足分支保护要求的合并前批准；
2. Pull Request 已通过受保护流程合入 `main`，且最终 `main` 完整 SHA 已冻结；
3. 全部强制验证已针对最终 `main` SHA 重新执行并形成新的 Evidence 记录；合并前候选的绿色状态不能代替该证据；
4. 候选 SHA—最终 SHA 的 tree、任务、Pull Request 与证据映射完整，并且最终证据已由所需评审者接受；
5. 所有必需检查和审批通过，阻塞对话为零；
6. 残余风险已关闭、转移或由有权责任人限时接受；
7. Tag Custodian 和 Release Decision Owner 已接受责任；
8. Release Notes 没有夸大未实现能力。

Squash 或 rebase 产生的新 SHA 必须按第 3 项重新验证；tree 映射只支持追溯，不能替代最终 SHA 的验证。若最终内容、范围或验证语义与已评审候选不一致，候选必须返回 Development / Validation，修正后重新进入 Review。

## 8. Stage 4 — Tag

### 8.1 Tag 命名

正式 Repository Baseline 使用：

```text
acs-baseline-v<major>.<minor>.<patch>
```

版本含义只描述 Repository Baseline 序列，不等于 V2.3 Architecture 版本、Phase 编号或产品兼容承诺：

- `major`：Baseline 治理或兼容含义发生经批准的不兼容变化；
- `minor`：新增一组已验证、向前累积的工程能力或治理基线；
- `patch`：不扩大能力范围的修正、文档或治理澄清。

首个建议名称为 `acs-baseline-v0.1.0`，但只有第 5 至第 7 节全部通过后才能创建；本文不创建该 Tag。

### 8.2 Tag 创建规则

- 只创建 annotated Tag，禁止使用 lightweight Tag 作为正式 Baseline；
- Tag 必须指向受保护 `main` 的完整 Commit SHA；
- Tag message 必须包含 Baseline ID、任务范围、Commit、验证证据、Review 决定、已知限制和日期；
- 当签名身份与密钥治理完成后，正式 Tag 必须使用可验证签名；在此之前应记录签名状态和风险，不能虚构 Verified；
- 创建后立即验证 Tag 对象、目标 Commit、消息和远端可见性；
- 禁止移动、复用或覆盖已发布 Tag。

Tag 创建失败或目标不一致时，状态为 `HOLD`，不得通过强制更新修正。应废弃错误候选并创建新的版本号和审计记录。

## 9. Stage 5 — Release

GitHub Release 必须从已验证 Baseline Tag 创建，至少包含：

| 字段 | 必需内容 |
| --- | --- |
| Release Title | Baseline 名称与版本 |
| Tag / Commit | 完整 Tag 和 Commit SHA |
| Scope | 已纳入任务、里程碑和文件范围 |
| Exclusions | 明确未纳入、未实现和未授权事项 |
| Validation | Evidence ID、检查状态和复核结论 |
| Architecture | V2.3 影响和 ADR 状态 |
| Security / Data | 审查结论和未解决风险 |
| Known Limitations | 只记录真实限制，不作未来承诺 |
| Rollback / Supersession | 撤销、替代和后续版本规则 |
| Decision | Release Decision Owner、日期与 `PUBLISH / HOLD / WITHDRAW` |

Repository Baseline Release 默认不得描述为 Production Release。若未来同一个 Tag 同时作为产品 Release 候选，仍须独立满足 Release Validation、Phase Gate、环境和外部发布授权。

## 10. Baseline 状态

| 状态 | 含义 |
| --- | --- |
| `DEVELOPMENT` | 变更正在形成，尚未冻结 |
| `VALIDATION` | 候选已冻结并正在形成证据 |
| `REVIEW` | 验证完成，等待独立评审 |
| `APPROVED FOR TAG` | 评审通过且责任完整，可由 Tag Custodian 操作 |
| `TAGGED` | annotated Tag 已创建并验证，尚未发布 GitHub Release |
| `PUBLISHED` | GitHub Release 已发布并可追溯 |
| `HOLD` | 存在阻塞，不允许继续 |
| `WITHDRAWN` | Baseline 保留历史但不再推荐使用 |

状态必须有时间、责任人、目标 SHA 和证据，不能只在口头或分支名中表达。

## 11. 不可变性、纠错与撤回

- 已发布 Tag 和 Release 不得静默重写。
- 发现内容错误时，保留原记录，发布新 patch Baseline 并建立 supersedes 关系。
- 出现安全、完整性或错误候选问题时，将 Release 标为 `WITHDRAWN`，说明影响和替代项；除法律或安全保全要求外不删除审计线索。
- Git revert 产生新 Commit；它不移动旧 Tag，也不改变旧证据的历史状态。
- Release Notes 更正必须保留修订记录，不能把历史失败改写为当时已通过。

## 12. 当前 Repository Baseline Readiness

`ACS-GIT-001` 执行前事实：

| 检查项 | 观察结果 | Baseline 影响 |
| --- | --- | --- |
| `main` | 指向 `5b970ae` Phase 0 tracked repository baseline | 尚未包含当前后续历史 |
| Task Start HEAD | `67986f9`，由 Phase 1 Scope Approval 分支继承为本任务起点 | 不是受保护 `main` 候选 |
| Git remote | 无 | 无法推送、创建 PR、Ruleset 或 GitHub Release |
| Git Tag | 无 | 没有正式 Baseline Tag |
| Branch Protection Evidence | 无 | 无法证明主线保护 |
| Required Checks | 未配置或无法核验 | 不能形成 GitHub 强制 Gate 证据 |
| 工作区 | 存在本任务之外的未跟踪材料 | 必须隔离并分别决定，不得夹带进入 Baseline |

因此当前 Baseline 状态为 `HOLD / NOT READY FOR TAG`。本任务只建立流程，不执行 Tag 或 GitHub Release。

## 13. 首个 Baseline 建议

首个正式 Baseline 建议采用 `acs-baseline-v0.1.0`，但必须依次完成：

1. 创建并核验 GitHub Repository 与 `origin` remote；
2. 指定 Repository Governance Owner、Validation Owner、至少两名非作者 Reviewer、Tag Custodian 和 Release Decision Owner；
3. 应用并验证 `main` Branch Protection 与真实 Required Checks；
4. 对当前未跟踪材料逐任务接受、提交或排除，确保候选工作区边界清晰；
5. 执行 Development：决定纳入的获批任务与 Commit，在短期分支冻结 Pull Request 候选 SHA、文件清单和排除项；
6. 执行 Validation：对 Pull Request 候选形成绑定准确 SHA 的强制证据；
7. 执行 Review：完成独立审批并通过受保护流程合入 `main`；
8. 冻结最终 `main` SHA，对该 SHA 重新执行全部强制验证、形成新 Evidence 并完成 Review Stage 的 post-merge 接受；
9. 由 Tag Custodian 创建并验证 annotated Tag；
10. 由 Release Decision Owner 决定 `PUBLISH / HOLD / WITHDRAW`；
11. 发布明确标识为 Repository Baseline 的 GitHub Release。

这些步骤不授权业务实现、V4/V3、API、数据库、部署、Production Validation、Phase 变化或商业化。

## 14. 变更控制

以下变化必须独立批准并更新本文：

- Tag 命名、版本含义或不可变规则；
- 正式 Baseline 的来源分支；
- 省略 Validation、Review 或责任分离；
- 把 Repository Baseline 解释为产品 Release；
- 允许移动、覆盖或删除已发布 Tag；
- 改变 Release Decision 或撤回规则。

流程例外必须记录范围、原因、风险、责任、期限和补偿控制，且不得覆盖架构、安全、数据或 Phase 授权阻塞项。
