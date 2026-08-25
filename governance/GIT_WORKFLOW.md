# AI Cinematic Studio Git Workflow

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-GIT-001` |
| 文档类型 | GitHub Repository Governance Specification |
| 适用范围 | AI Cinematic Studio 仓库内的代码、测试、文档、治理、脚本、配置与基础设施变更 |
| 架构影响 | `NONE`；不修改 AI Cinematic Studio V2.3 架构 |
| Phase 影响 | `NONE`；不授予或修改任何 Phase 范围与实施权限 |
| 当前平台状态 | 本文创建时未配置 Git remote；GitHub 规则尚未应用或验证 |

## 1. 目的与权威关系

本文把现有 [分支策略](BRANCH_STRATEGY.md)、[提交约定](COMMIT_CONVENTION.md)、[代码评审规则](CODE_REVIEW_RULES.md)、[开发规则](DEVELOPMENT_RULES.md)和[完成定义](DEFINITION_OF_DONE.md)组织为可执行的 Git 协作流程。

本文只定义 Repository Governance，不创建 GitHub 仓库、remote、分支保护、业务模块、API、数据库、Release 候选或 Production 权限。平台配置只有在实际应用并留下可复核证据后，才能声称已启用。

如本文与架构、Phase 授权或其他已批准治理文件冲突，应停止合并并执行以下规则：

1. 架构与 Phase 授权边界不因 Git 分支、Commit、Pull Request、Tag 或 Release 而改变；
2. 在冲突关闭前采用更严格、不会扩大权限的规则；
3. 架构变化按 [架构变更流程](ARCHITECTURE_CHANGE_PROCESS.md)处理；
4. Git 治理变化通过独立治理变更评审，不能由仓库配置静默改写文档。

## 2. Git 工作原则

- **任务驱动**：每个分支、Commit 和 Pull Request 必须关联明确任务、缺陷或获批治理决定。
- **最小变更**：一个工作分支只承载一个可独立评审的目标，不混入无关文件。
- **受保护主线**：`main` 只接收通过验证与评审的变更，不接受直接开发。
- **短生命周期**：除已明确启用的长期分支外，工作分支合并或终止后应删除。
- **证据先于状态**：分支名、绿色界面、Tag 或 GitHub Release 不能替代测试、评审、风险和授权证据。
- **历史可追溯**：禁止改写共享历史、移动正式 Tag 或删除不利审计记录。
- **权限不扩张**：创建 `feature/` 或 `experiment/` 分支不表示功能或实验已经获得实施授权。

标准流程为：

```text
Approved Task / Change Record
            ↓
Create Scoped Working Branch
            ↓
Atomic Commits + Local Validation
            ↓
Pull Request + Required Evidence
            ↓
Independent Review + Required Checks
            ↓
Merge into Approved Target Branch
            ↓
Delete Working Branch + Preserve Audit Trail
```

## 3. 分支模型

| 分支类别 | 默认来源 | 默认目标 | 生命周期 | 使用边界 |
| --- | --- | --- | --- | --- |
| `main` | 不适用 | 不适用 | 长期、受保护 | 已评审且满足当前 Gate 的仓库主线 |
| `develop` | `main` | `main` | 条件性长期分支，当前未启用 | 只有独立治理决定明确激活后，才可作为多工作包集成线 |
| `feature/<task-id>-<description>` | `main`；若 `develop` 已正式启用则从 `develop` | 与来源一致 | 短期 | 仅承载已获授权的产品或工程行为变更 |
| `docs/<task-id>-<description>` | `main`；若适用可从获批集成基线创建 | 与来源一致 | 短期 | 仅文档变更，不夹带代码、配置或依赖变化 |
| `experiment/<task-id>-<description>` | 明确记录的不可变基线 | 不直接合并 `main` | 有期限、默认处置 | 仅执行已获授权、隔离且可停止的实验 |

现有 `foundation/`、`governance/`、`test/`、`fix/` 与 `chore/` 分类继续遵守 [分支策略](BRANCH_STRATEGY.md)。新增分支类别是工作分类，不创建 V2.3 模块或产品边界。

`feature/` 与 `experiment/` 当前为条件性分类：只有对应工作项取得独立实施或实验授权后才可使用。本文定义其使用规则，但不把它们加入当前可无条件创建的分支清单，也不构成任何实现授权。

分支名必须使用小写、短横线和可追溯任务编号：

```text
<type>/<task-id>-<short-description>
```

## 4. `main` 规则

`main` 是唯一默认长期分支，代表仓库已接受的主线状态，不等于 Production Ready、Release Authorized 或商业化完成。

强制规则：

1. 禁止直接推送、强制推送和删除；所有变更通过 Pull Request。
2. Pull Request 必须关联任务，说明范围、排除项、验证、风险、架构/数据/安全影响和回退方式。
3. 所有适用强制检查必须通过，`FAIL`、`BLOCKED` 或强制 `NOT RUN` 不得合并。
4. 通用规则至少取得两名非作者评审者批准；Core 当前单人运营期适用第 4B 节零批准精确例外，Frontend 当前单人运营期适用第 4C 节独立零批准精确例外。架构、安全、全仓库治理或 Release 高影响变更仍须满足对应责任职能和专项治理要求。
5. 所有阻塞意见和对话必须解决；实质性更新后重新执行检查并重新评审。
6. 合并历史保持线性；仓库启用后默认使用 squash merge，并使最终提交符合 Commit Convention。
7. 合并结果必须保留任务、Pull Request、验证证据和审批记录之间的追溯关系。
8. 不允许用管理员绕过、紧急标签或临时关闭保护来替代正式例外流程。

具体 GitHub 配置见 [分支保护规范](BRANCH_PROTECTION.md)。

## 4A. Core 单人运营一批准例外（历史 / 已取代，2026-08-25）

本节保留同日较早治理状态的审计轨迹：当时 Core `main` ruleset 被决定为
`1 approval`，且批准必须来自合格非作者；PR #11 author=`lpjiayou`、
reviews=`[]`，因此形成 `0/1` Reviewer capacity blocker。该配置及阻塞结论已由
第 4B 节的后续 Owner 决定取代，不得再作为当前规则或当前 PR 状态引用。

## 4B. Core 单人运营零批准精确例外（当前，2026-08-25）

Project Lead / Repository Governance Owner `蔺鹏` 明确记录：项目当前只有一名
运营者，Core `main` 的 GitHub ruleset 在该运营期采用 `0 approvals`。本决定取代
同日较早记录的 `1 approval` 单人运营配置及其 Reviewer capacity blocker。它是
Core 仓库级 Pull Request 入口的精确治理决定，不是作者自批，不把自动化或技术
审查伪装成 GitHub approval，也不自动扩张到 Frontend；Frontend 的当前批准模型
由第 4C 节单独决定。

该精确例外的强制条件是：

1. GitHub 平台批准计数明确为 `0`；approval-dependent 的 dismiss-stale、
   latest-push 和 unattributed-Copilot extra-approval 选项关闭，不得虚构
   `0/0`、作者自批或其他平台批准证据；
2. 独立技术审查继续作为合并前强制治理证据，必须绑定精确候选 SHA/tree 并报告
   blocker/high/medium；它不产生 GitHub approval，也不替代 Project Lead、架构、
   安全、风险接受或 Release 等专项决定；
3. Pull Request、conversation resolution、五项 strict required checks、linear
   history、force/delete protection 全部继续生效；
4. bypass actor 必须为空，不能为解决其他门禁阻塞而临时增加；
5. 有效 Core `main` ruleset 只允许 squash；仓库 General settings 即使仍显示
   merge/squash/rebase，也不能被描述为整个仓库 squash-only，或被用来绕过
   `main` ruleset；以及
6. Release、安全、风险接受、Phase Exit、Script/ShotPlan、媒体准入和发布仍使用
   各自通用或专项规范；本例外不满足、替代或降低那些决定。

当 Core 不再是单一运营账号，或 Repository Governance Owner 重新决定审批模型时，
必须按第 13 节重新评估并显式取代本例外；不得静默恢复、提高或降低批准数。

当前精确事实记录在 [Branch Protection](BRANCH_PROTECTION.md#6a-远端配置历史与当前差异账本)。
Core PR #11 author=`lpjiayou`、reviews=`[]`；在本例外下该事实不构成 approval
blocker。该 PR 后续在精确候选独立技术审查、五项 required checks、conversation
resolution 和线性 squash 条件满足后合入 Core `main`，结果为
`af7f50a8dc7cdccdb7dd47cd425d33a288961cc9`。这项历史正向对照不改变规则：
`0 approvals` 不等于无审查或自动可合并。

## 4C. Frontend 单人运营零批准精确例外（当前，2026-08-26）

Project Lead / Repository Governance Owner `蔺鹏` 对 Frontend 作出独立决定：项目
当前只有一名运营者，Frontend `main` 的 `main-protection-v1` ruleset（ID
`21413134`）在该运营期采用 `0 approvals`。本决定不是从 Core 第 4B 节推导或继承，
也不是作者自批；通用两名批准规则仅在本精确例外终止后或另有治理决定时恢复适用。

Frontend 当前精确强制条件是：

1. 平台批准数为 `0`，dismiss-stale、latest-push 和 unattributed-Copilot
   extra-approval 均为 `false`；不得虚构 `0/0`、作者自批或自动化批准；
2. 精确候选的独立技术审查仍是合并前强制治理证据，必须报告
   blocker/high/medium；它不是 GitHub approval；
3. Pull Request、conversation resolution、strict up-to-date、linear history、
   deletion/non-fast-forward protection、有效 `main` ruleset 的 squash-only 路径及
   `verify`、`gate-c-k2-browser`、`gate-k2-control-plane-browser` 三项 required
   checks 全部继续生效；
4. bypass actor 必须为空；以及
5. Release、安全、风险接受、Phase Exit、Script/ShotPlan、媒体准入和发布仍须各自
   独立决定，本例外不降低或替代任何专项门禁。

Frontend 不再是单一运营账号，或 Repository Governance Owner 重新决定审批模型
时，必须按第 13 节显式取代本例外。当前配置与残余行为验证边界记录在
[Branch Protection](BRANCH_PROTECTION.md#6a-远端配置历史与当前差异账本)。
`0 approvals` 不等于无审查、自动可合并或治理端到端已验证。

## 5. `develop` 规则

`develop` 在当前仓库中为 **DEFINED / INACTIVE**。本文定义其未来适用规则，但不创建或激活该分支，从而保持现有 [分支策略](BRANCH_STRATEGY.md)“默认只有 `main` 长期存在”的基线。

只有同时满足以下条件，才能通过独立治理决定激活 `develop`：

- 存在两个或以上必须持续集成、且不能通过短期分支和 `main` 小批量合并安全处理的获批工作包；
- 明确 Branch Owner、集成目标、保护规则、同步频率、退出条件和最长存续复核点；
- `main` 保护已配置并验证，`develop` 拥有不低于风险要求的 Pull Request 与检查保护；
- 激活不会绕过 Phase Gate、Release 决策或 V2.3 相邻依赖规则；
- 更新相关治理记录并由 Repository Governance Owner 接受。

激活后：

1. `develop` 只能从受保护的 `main` 创建；
2. 工作分支通过 Pull Request 合入 `develop`，禁止直接推送；
3. `develop` 只表示集成状态，不表示可发布或可进入生产；
4. 提升到 `main` 必须使用独立 Pull Request，重新核对完整范围、证据和风险；
5. `main` 的紧急修复必须及时回流到 `develop`；
6. 不再需要集成线时，完成最终同步、证据归档并通过治理决定停用。

## 6. `feature` 规则

- 只有具体实现工作包已经获得授权时才允许创建 `feature/` 分支。
- 每个分支只覆盖一个任务和一个可评审交付目标。
- 默认从最新 `main` 创建；只有 `develop` 正式启用且任务被分配到该集成线时才从 `develop` 创建。
- 禁止夹带架构变化、数据库、API、依赖或 Phase 范围扩张；涉及这些事项必须先取得独立批准。
- 必须提供与风险相称的 Unit、Contract、Integration、E2E 或批准的 `N/A` 证据。
- 合并后删除分支；未完成内容必须拆为新任务，不能把分支作为永久存储。

`feature/` 是 Git 分类，不是 Implementation Authorization。

## 7. `docs` 规则

- 只允许 Markdown、图示源文件和当前任务明确授权的文档资产变化。
- 不得夹带业务代码、测试实现、配置、依赖、Schema 或生成物。
- 必须验证 Markdown 结构、内部链接、术语、权威引用及事实状态。
- 架构描述变化即使只修改文档，也必须执行架构变更判断，不能以 `docs/` 规避 ADR。
- 文档中的未来态必须标为 Proposal、Draft、Blocked 或 Not Authorized，不能陈述为已实现事实。

## 8. `experiment` 规则

- 只有实验目标、范围、Owner、时间盒、资源上限、数据/Rights 边界、停止条件和处置计划全部获批后才可创建。
- 分支必须记录来源 Commit，不持续吸收无关主线变化。
- 禁止真实生产副作用、未经授权用户数据、永久基础设施和隐性产品实现。
- 实验 Commit、Tag 或演示结果不构成 Release、Production、Phase Exit 或商业证明。
- `experiment/` 不得直接合并 `main`。可复用成果必须经过 extraction review，拆入新的获批 `feature/`、`docs/`、`test/` 或 `governance/` 任务，并重新验证。
- 到达停止条件、期限或结论后，记录 `ADOPT / HOLD / DISCARD`，随后归档证据并删除活动分支；需要保留时保留 Git 引用或归档记录，而不是保持可继续写入的长期分支。

## 9. Commit Convention

Commit 必须遵守 [提交约定](COMMIT_CONVENTION.md)：

```text
<type>(<scope>): <subject>

<body>

Refs: <task-id>
```

最低规则：

- 标题清楚、使用祈使式且建议不超过 72 个字符；
- `scope` 必须是已存在工程范围，不能通过提交信息发明模块；
- `feat` 只用于已获授权的功能，不能用类型名称替代授权；
- 一个 Commit 只表达一个逻辑目的，并可独立审查和撤销；
- 不提交凭据、生成物、本地状态、临时调试文件或无关变化；
- 破坏性变化必须预先获批并使用 `BREAKING CHANGE:` footer；
- 合并到受保护分支的最终 Commit 必须保留任务编号和变更意图。

## 10. Pull Request、验证与合并

Pull Request 最低内容：

1. Task/ADR/风险或缺陷引用；
2. 变更目的、文件范围与明确不在范围内事项；
3. 架构、接口、数据、安全、依赖和 Release 影响；
4. 验证命令或方法、实际结果、Evidence ID 与限制；
5. 回退方式、残余风险和后续责任；
6. 目标分支与合并策略。

作者完成自检后才能请求评审。自动化检查与人工评审相互独立，任何一方不能覆盖另一方的失败。批准后如发生实质性变更，旧批准失效并重新评审。

## 11. 同步、冲突与历史管理

- 工作分支定期同步其批准来源分支；同步后重新执行受影响验证。
- 只在个人未共享历史或明确协调后使用 rebase；禁止改写共享分支历史。
- 冲突解决必须审查语义结果，不能只证明 Git 可以合并。
- 已合并主线发生问题时使用新修复或 `revert` Commit，禁止静默移动主线。
- 正式 Baseline Tag 不得移动或复用，具体规则见 [Baseline Release Process](BASELINE_RELEASE_PROCESS.md)。

## 12. 当前 GitHub 启用状态

截至 `ACS-GIT-001` 执行前检查：

- Git remote：未配置；
- GitHub Repository：无法从本地事实核验；
- `main` Branch Protection：未配置或无法核验；
- Required Checks、CODEOWNERS、Merge Queue：未配置或无法核验；
- Git Tag：不存在。

因此本文的规则状态为 `DEFINED`，平台执行状态为 `NOT APPLIED / NOT VERIFIED`。在远端创建、权限确认和证据核验完成前，不得声称 GitHub Governance 已技术强制执行。

## 13. 例外与变更控制

紧急性只能缩短等待时间，不能取消范围、架构、安全、证据、回退和审计要求。任何绕过保护的例外必须：

- 在操作前由有权 Repository Governance Owner 批准；
- 记录原因、目标分支、Commit、权限使用者、风险、补偿控制和截止时间；
- 限于恢复稳定状态所需的最小范围；
- 操作后立即复核保护配置并建立常规 Pull Request 或修复记录；
- 不得覆盖未授权架构变化、敏感数据泄露或 Phase 范围阻塞。

改变长期分支模型、主线含义、必需审批、Tag 不可变性或 Baseline Gate 时，必须独立评审并更新全部受影响治理文档。
