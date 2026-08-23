# Repository Baseline v0.1.0 Candidate Manifest

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-GIT-003` |
| Record Type | `Repository Baseline Candidate Manifest` |
| Preparation Date | `2026-08-07` |
| Architecture Impact | `NONE`；不修改 AI Cinematic Studio V2.3 Architecture |
| Phase Impact | `NONE`；不修改 Phase 范围或授权状态 |
| ADR | `NOT TRIGGERED`；本记录只清点 Repository 事实与 Baseline 阻塞 |

## 1. Baseline Identity

| 字段 | 当前值 |
| --- | --- |
| Candidate ID | `acs-baseline-v0.1.0-candidate` |
| Proposed Tag | `acs-baseline-v0.1.0` — `NOT CREATED` |
| Candidate Stage | `DEVELOPMENT / ACCEPTANCE PREPARATION` |
| Readiness | `HOLD / NOT READY FOR TAG` |
| Content Candidate Commit | `a1a3b9a098bfd7212ec7841e6261218305308c36` |
| Content Candidate Tree | `043bfede80bf74ead5afd535b7301bc5b6eda0f0` |
| Source Branch | `docs/acs-doc-baseline-001-documentation-consistency` |
| Target Branch | `main` |
| Current `main` | `5b970ae6ed7d9a30b90a882f46b3df88dbe6be10` |
| Branch Relationship | Content Candidate is `8` commits ahead of and `0` commits behind current `main` |
| Candidate Tracked Files | `97` |
| Manifest Revision | `WORKTREE / UNVERSIONED`；由未来包含本文件的 Git Commit 决定 |
| Remote | `NONE`；未配置 `origin` |

本记录严格区分 **Content Candidate** 与 **Manifest Revision**。Content Candidate 是上述 Commit 及其 Git tree；本 Manifest 在该 Commit 之后创建，不属于该 tree，也不会通过自引用改变候选身份。任何将本文件纳入候选的后续 Commit 都会产生新的候选 SHA，并要求重新验证受影响项目。

`acs-baseline-v0.1.0` 目前只是建议名称。本文不创建 Tag、GitHub Release，不合并 `main`，也不把工作分支声明为正式 Baseline。

## 2. Included Components

本节的 Included 只表示资产存在于指定 Content Candidate Git tree。它不追认历史实现授权，不构成 Phase Gate Pass、Implementation Authorization、Release Authorization、Production Readiness 或商业化证明。

| 组件 | Candidate 中的已跟踪事实 | 主要修订 |
| --- | --- | --- |
| Repository Foundation | 根目录说明、仓库骨架、编辑器与忽略规则 | `5b970ae6ed7d9a30b90a882f46b3df88dbe6be10` |
| V2.3 Architecture Foundation | System Overview、Layer Boundaries、Responsibility、Dependency、System Context 与技术选型记录模板 | `5b970ae6ed7d9a30b90a882f46b3df88dbe6be10` |
| Governance Foundation | 开发、评审、分支、Commit、架构变更、DoD 与风险治理规范 | `5b970ae6ed7d9a30b90a882f46b3df88dbe6be10` |
| Interface / Data / Testing / Application Documentation | Phase 0 接口、数据与测试治理文档，以及 Application Layer 映射规范 | `5b970ae6ed7d9a30b90a882f46b3df88dbe6be10` |
| V5 Identity Engine Foundation | 进程内 Identity、Workspace 与 Ownership Reference 基础能力及 Unit/Contract Tests | `d439e3cd894b6f91d0f161e28b92b080e589c5f6` |
| V5 Project Engine Foundation | 进程内 Project Create/Query/List、引用与最小生命周期及 Unit/Contract Tests | `5759fc0c6dc91f43ca6cc912e8e76758dc59bd25` |
| V5 Asset Registry Foundation | 进程内 Asset Create/Get/List、基础分类与初始版本及 Unit/Contract Tests | `e4f1a5d9247119b75e4fe863242cee9a3abe41c1` |
| V5 Project–Asset Relationship Foundation | 进程内 Attach、双向查询与重复关系处理及 Unit/Contract Tests | `139024327ea9cfcd7328f7a5b4ac385fb1e1a1ea` |
| Phase 0 Exit Record | Phase 0 `COMPLETED / CLOSED` 的版本化退出记录 | `8e15009f38926e4528e773f848cf63bee90af900` |
| Phase 1 Scope Approval | `APPROVED — MAXIMUM REVIEW ENVELOPE`；Implementation 仍为 `NOT GRANTED / BLOCKED` | `67986f9c6f7cb92335122a7a63446b4afdb5c375` |
| Git Governance | Git Workflow、Branch Protection Specification 与 Baseline Release Process | `cbe77e07a78220a55ab7f089447a9c2480d08e46` |
| Documentation Consistency | 根 README 与测试入口文档同步到当前 Repository 事实 | `a1a3b9a098bfd7212ec7841e6261218305308c36` |

Content Candidate 从当前 `main` 之后累计八个 Commit。它包含四个已有 V5 进程内 Foundation 包和对应 Unit/Contract Tests，但这些 Repository 事实不能回溯证明当前 Phase 1 Implementation 已获授权。

## 3. Excluded Components

### 3.1 未跟踪文件处置

分类定义：

- `Accepted Baseline Candidate`：已获得明确 Baseline 接受决定，可进入候选版本化流程；
- `Pending Review`：属于正式项目资产候选，但尚未完成修订、接受或版本化；
- `Excluded`：已有明确拒绝、废弃或本次候选排除决定；
- `Temporary`：缓存、编辑器状态、构建输出或其他不应进入 Repository 的临时资产。

审计开始时的 13 个未跟踪文件分类如下：

| 分类 | 数量 | 当前结论 |
| --- | ---: | --- |
| Accepted Baseline Candidate | 0 | 没有文件具备显式 Baseline 接受记录 |
| Pending Review | 13 | 均位于 Content Candidate tree 之外 |
| Excluded | 0 | 未发现正式拒绝、废弃或排除决定 |
| Temporary | 0 | 13 个文件均为结构化 Markdown 项目资产候选 |

| 未跟踪路径 | 分类 | 处置依据 |
| --- | --- | --- |
| `AI_CINEMATIC_STUDIO_GENERATION_2_DEVELOPMENT_CHARTER.md` | Pending Review | Source baseline 无法在当前仓库解析，且 5 个 informed-by 本地链接缺失；需要来源核验和接受决定 |
| `docs/00-governance/gen2-charter-integration-record.md` | Pending Review | 依赖尚未版本化、尚未接受的 Charter；需要成组协调治理状态 |
| `docs/04-interface-contract/v5-v3-vertical-slice-review.md` | Pending Review | 内容可进入正常评审，但 Open Questions、文档接受和版本化尚未闭合；应与 V3 两份文档成组处理 |
| `docs/07-v3-render-core/README.md` | Pending Review | 正式索引候选，依赖同批未跟踪的 Vertical Slice 与 Boundary 文档 |
| `docs/07-v3-render-core/render-core-boundary.md` | Pending Review | 技术无关边界候选，仍缺架构/文档接受和版本化 |
| `docs/12-release/phase-1-execution-authorization.md` | Pending Review | 已跟踪 Scope Approval 将其标记为未接受草案；其中 Scope 状态快照需要与当前 Scope Decision 协调 |
| `docs/12-release/phase-1-responsibility-assignment.md` | Pending Review | 文件自述 `DRAFT / REVIEW INPUT / NOT ACCEPTED`，关键 Person/Owner 仍未指派 |
| `docs/12-release/phase-1-vertical-slice-authorization.md` | Pending Review | 仍包含“没有 Phase 0 正式退出”的过期陈述，与已跟踪 Phase 0 Exit Record 冲突 |
| `docs/15-investor-readiness/README.md` | Pending Review | 正式证据索引候选，应与 M001–M004 原子评审和接受 |
| `docs/15-investor-readiness/milestones/M001-v5-identity-engine-foundation.md` | Pending Review | 目标 Commit 可解析且事实可复核，但里程碑文档尚未被接受或版本化 |
| `docs/15-investor-readiness/milestones/M002-v5-project-engine-foundation.md` | Pending Review | 目标 Commit 可解析且事实可复核，但里程碑文档尚未被接受或版本化 |
| `docs/15-investor-readiness/milestones/M003-v5-asset-registry-foundation.md` | Pending Review | 目标 Commit 可解析且事实可复核，但里程碑文档尚未被接受或版本化 |
| `docs/15-investor-readiness/milestones/M004-v5-project-asset-relationship-foundation.md` | Pending Review | 目标 Commit 可解析且事实可复核，但里程碑文档尚未被接受或版本化 |

其中 8 个文件属于“内容初审可进入正常接受流程，但仍未接受”：V5–V3/V3 文档三件套和 Investor Readiness 五件套。其余 5 个文件需要先完成来源、状态或治理一致性修订。该细分不改变全部 13 个文件的 `Pending Review` 分类。

### 3.2 其他不包含项

- 本 Manifest 本身不在 Content Candidate Commit 中；其版本必须由后续 Commit 明确记录；
- `__pycache__/`、`*.pyc` 等本地运行缓存已由 `.gitignore` 排除，不属于 13 个未跟踪项目资产；
- API、数据库、持久化、Storage Adapter、Application 实现、V4、V3、Compute、跨层 Integration、E2E、Production Validation、部署和商业化能力不存在于候选范围，且未由本文授权；
- GitHub Repository 配置、`origin`、Branch Protection Evidence、Required Checks、CODEOWNERS、正式 Tag 与 GitHub Release 不属于本地 Content Candidate 事实；
- 任何未在指定 Commit tree 中的本地文件、环境状态、凭据、生成物或外部材料均不属于该候选。

## 4. Verification Status

以下结果是 `2026-08-07` 对指定 Content Candidate 的本地观察。除非另有说明，它们不是具有 Evidence ID、责任接受和独立复核的正式 Baseline Evidence；候选 SHA 变化或合入 `main` 后必须重新执行受影响验证。

| 验证项 | 状态 | 当前证据或限制 |
| --- | --- | --- |
| `git status` | PASS — LOCAL OBSERVATION | 审计开始时 tracked index/worktree 无修改；存在上述 13 个未跟踪文件 |
| `git branch -a` | PASS — LOCAL OBSERVATION | 当前为本地 docs 分支；没有 remote-tracking branch |
| `git remote -v` | BLOCKED | 无输出，`origin` 不存在 |
| `git log --oneline --decorate -20` | PASS — LOCAL OBSERVATION | Candidate Commit、包含该 Commit 在内的八个 post-main Commits 和当前 `main` 均可解析 |
| Candidate Commit / Tree | PASS — LOCAL OBSERVATION | Commit、Tree 和 97 个 tracked files 可解析 |
| Candidate Markdown 相对链接 | PASS — LOCAL OBSERVATION | 对 Content Candidate tree 中 50 个 Markdown 文件检查 209 个相对链接，未发现缺失目标 |
| Documentation / Governance Semantic Consistency | BLOCKED | Candidate 存在已识别的阶段、测试与风险状态漂移；见第 4.1 节 |
| 未跟踪 Markdown 相对链接 | BLOCKED | 13 个文件共检查 90 个相对链接；Charter 存在 5 个缺失本地目标 |
| Unit / Contract | PASS — LOCAL OBSERVATION | `python -m unittest discover -s tests -p "test_*.py" -v`：86/86 通过；尚无正式 Evidence ID、Owner 接受或独立复核 |
| Integration / E2E | N/A — APPROVAL PENDING | 当前只有目录骨架；正式 `N/A` 仍需有权责任人批准 |
| Architecture / ADR Disposition | NOT RUN | 尚未对最终候选形成独立 Baseline 架构复核；本文自身不修改架构且不触发 ADR |
| Security / Data / Dependency Review | NOT RUN | 尚未形成绑定 Candidate Commit 的正式证据 |
| 未跟踪文件正式处置 | BLOCKED | 13 个文件均未获得明确接受、排除或废弃决定 |
| Baseline Roles | BLOCKED | Validation Owner、Independent Reviewers、Repository Governance Owner、Tag Custodian 与 Release Decision Owner 尚未接受本次 Baseline 指派 |
| Branch Protection / Required Checks | BLOCKED | 无 remote，GitHub 侧规则未应用或无法验证 |
| Pull Request / Independent Approval | NOT AVAILABLE | 未形成面向受保护 `main` 的 PR 或两名非作者批准证据 |
| Final `main` SHA / Post-merge Validation | NOT AVAILABLE | Candidate 尚未通过受保护流程合入 `main`，不存在最终主线 SHA 的重新验证 |
| Local Tag | NOT CREATED | `git tag --list` 无输出；本任务不创建 Tag |
| GitHub Release | NOT VERIFIABLE | 无 remote，无法从本地核验外部 Release 状态；本任务不创建 Release |

本地 86/86 测试通过和 Markdown 链接检查只支持候选准备判断，不能替代最终 `main` SHA 的 post-merge Validation，也不能单独把候选状态提升为 `APPROVED FOR TAG`。

### 4.1 Known Documentation Consistency Blockers

以下问题存在于 Content Candidate 的已跟踪文档中。本 Manifest 只记录事实，不在本任务中修改它们：

- `governance/DEVELOPMENT_RULES.md:11-20` 仍将“当前阶段”声明为 Phase 0 并全面禁止服务实现，与 Phase 0 已关闭及候选中存在历史 V5 Foundation 代码的 Repository 事实不一致；
- `docs/11-testing/testing-strategy.md:122` 仍声明当前阶段不编写测试代码，与候选中已跟踪的 Unit/Contract Tests 不一致；
- `docs/12-release/phase-1-production-validation-plan.md:27` 仍保留“没有 Phase 0 正式退出决定”的 pre-exit 快照，与 `docs/12-release/phase-0-exit-record.md:164-170` 不一致；
- `governance/RISK_REGISTER.md:5,53-60` 仍保留 Phase 0 初始状态和旧责任信息，尚未同步 Phase 0 Exit Record 的退出处置；该缺口继续阻塞 `P1-PV-G01`；
- `docs/12-release/phase-1-scope-approval.md:254` 的“当前没有实现”与候选中已有历史 V5 代码存在字面歧义；本 Manifest 仅按“没有由该 Scope Approval 授权的实现或 Vertical Slice/Release Candidate”理解，原文仍需治理同步；
- Phase 1 Plan 的 K2/X2 双轨要求与 Scope Approval 记录的 X2-first/K2-later 方向尚未形成协调决定，`P1-PV-G02` 保持 `BLOCKED`。

在这些冲突完成独立修订、复核和版本化之前，Documentation / Governance Semantic Consistency 不得标记为 `PASS`。

## 5. Limitations

1. 本记录描述的是 **Repository Baseline Candidate**，不是产品 Release Candidate、Production Release 或部署候选。
2. Phase 0 已 `COMPLETED / CLOSED`；Phase 1 只批准 `MAXIMUM REVIEW ENVELOPE`，Implementation 仍为 `NOT GRANTED / BLOCKED`。
3. 四个 V5 Foundation 包只使用进程内状态，没有 API、数据库、持久化、Application/V4/V3/Compute 集成或 Production 运行证明。
4. 当前只有 Unit 与 Contract Tests；Integration、E2E 和 Production Validation 尚不存在。
5. Candidate 尚未合入 `main`；当前 `main` 仍位于 `5b970ae6ed7d9a30b90a882f46b3df88dbe6be10`，其保护状态未验证。
6. 仓库没有 remote 或本地 Tag，也没有 GitHub Branch Protection/Required Checks 证据；GitHub Repository 与 GitHub Release 的外部状态无法从当前本地仓库核验。
7. Baseline 责任角色、风险接受、PR 审查、最终主线验证和 Release Decision 均未闭合。
8. Candidate 仍包含第 4.1 节列出的文档状态漂移，且 `P1-PV-G01/G02` 尚未关闭。
9. 13 个既有未跟踪文件不属于 Content Candidate，且尚未完成正式处置；本 Manifest 也尚未版本化。
10. 本机 Git 因 Repository 所有者 SID 与执行用户不同触发 `safe.directory` 保护；本次审计只使用命令级 `-c safe.directory=...`，未修改全局 Git 配置。
11. Scope Approval、历史 Commit、测试通过或本 Manifest 均不能追认、产生或扩大 Implementation Authorization。

因此当前决定为：**`HOLD / NOT READY FOR TAG`**。

只有在未跟踪资产完成有权处置、候选通过绑定同一 SHA 的正式 Validation、责任与风险闭合、GitHub 保护得到验证、PR 取得规定独立审批并合入 `main`、最终 `main` SHA 完成 post-merge 重新验证后，才能进入 `APPROVED FOR TAG` 评审。即使未来达到该状态，也必须由 Tag Custodian 和 Release Decision Owner 分别执行后续决定；本任务不创建 Baseline。
