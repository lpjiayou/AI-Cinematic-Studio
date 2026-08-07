# AI Cinematic Studio

AI Cinematic Studio 是面向 AI 内容资产生产、账号矩阵运营与商业化 SaaS 的一体化工程基础设施。本仓库承载产品入口、核心服务、共享能力、基础设施边界，以及配套的架构、数据、接口、测试、发布和治理资产。

> 当前治理状态：**Phase 0 Closed；Phase 1 Scope Approved；Implementation Not Authorized。**

## 项目定位

本项目的长期目标是为 AI 驱动的内容生产与商业化平台提供可演进、可审计、可测试的工程底座。当前仓库已经从纯工程骨架演进到包含 V5 Core OS 基础实现与对应测试的早期工程状态，但尚不是完整产品、集成系统、Release Candidate 或 Production Ready 系统。

仓库事实与治理授权必须分开理解：已跟踪代码说明某项历史交付物存在，不表示当前 Phase Gate 已通过，也不自动授予后续实现、集成、Release 或 Production 权限。

## V2.3 架构基线

AI Cinematic Studio V2.3 是当前冻结的架构基线。本次入口文档同步不新增、删除、拆分、重命名或重新分配任何层级、模块职责、数据所有权或依赖方向。

仓库继续遵守已批准的单向分层关系：

```text
Application
    ↓
V5 Core OS
    ↓
V4 Platform
    ↓
V3 Render Core
    ↓
Compute
    ↓
Foundation
```

逻辑层级不自动映射为目录、服务、部署单元或技术产品。详细规则见 [系统上下文](architecture/system-context.md)、[层级边界](architecture/layer-boundaries.md)和[依赖规则](architecture/dependency-rules.md)。

## 当前仓库状态

| 仓库区域 | 架构职责 | 当前已跟踪状态 |
| --- | --- | --- |
| `apps/` | Application Layer 的交付入口 | 仅保留目录骨架；没有 Application 实现 |
| `services/` | 已跟踪工程交付物的服务代码边界 | 包含四个 V5 Core OS Foundation 包；没有网络 API、数据库或跨层集成 |
| `packages/` | 未来经批准的共享技术能力入口 | 仅保留目录骨架；没有共享包实现 |
| `infrastructure/` | 构建、部署、环境与平台资源边界 | 仅保留目录骨架；没有基础设施实现 |
| `tests/` | Unit、Contract、Integration 与 E2E 质量资产 | Unit 与 Contract 测试存在；Integration 与 E2E 仍为目录骨架 |
| `docs/` | 治理、战略、架构、数据、接口、测试、发布和 Application 设计知识主干 | 已跟踪文档覆盖 `00` 至 `14` 分类；工作树中的未跟踪文档不属于当前版本化基线 |
| `architecture/` | V2.3 跨仓库架构规则与责任边界 | 7 份架构基础文档已跟踪，V2.3 未修改 |
| `governance/` | 开发、评审、Git、完成定义、风险与架构守卫 | 已建立基础治理及 Git Workflow、Branch Protection、Baseline Process 规范 |
| `scripts/` | 经批准的可重复工程操作入口 | 仅保留目录骨架；没有自动化实现 |

## 当前 Phase 状态

| 状态维度 | 当前结论 | 含义 |
| --- | --- | --- |
| Phase 0 | `COMPLETED / CLOSED` | **Phase 0 Closed**；工程基础阶段已正式退出 |
| Phase 1 Scope | `APPROVED — MAXIMUM REVIEW ENVELOPE` | **Phase 1 Scope Approved**；只批准可进入后续评审的最大范围包络 |
| Immediate Execution Effect | `DOCUMENTATION / DESIGN / GOVERNANCE PREPARATION ONLY` | 当前只允许非实现准备活动 |
| `P1-PV-G01` | `BLOCKED` | 责任、Person、风险、接受与其他授权前置尚未闭合 |
| Phase 1 Implementation | `NOT GRANTED / BLOCKED` | **Implementation Not Authorized** |
| V4 / V3 / Compute | `NOT GRANTED` | 没有自动获得实现权限 |
| Release / Production | `NOT GRANTED` | 没有 Release Candidate、部署或 Production 授权 |

权威状态分别见 [Phase 0 Exit Record](docs/12-release/phase-0-exit-record.md)和 [Phase 1 Scope Approval](docs/12-release/phase-1-scope-approval.md)。Scope Approval 不等于 Implementation Authorization，既有历史 Commit 也不能追认或扩展当前权限。

## 已完成能力

### 工程与治理基础

- 建立仓库目录、V2.3 架构边界、模块责任和依赖规则；
- 建立 Architecture Governance、Interface Contract、Data Architecture 与 Testing Governance 基础；
- 建立 Application Layer 映射文档；
- 建立 Git Workflow、`main` 保护规范和 Repository Baseline 流程；
- 完成 Phase 0 Exit Record 与 Phase 1 Scope Approval 的版本化记录。

### V5 Core OS Foundation

当前已跟踪仓库状态包含以下进程内基础包：

| 包 | 已实现的最小事实 | 明确不表示 |
| --- | --- | --- |
| `identity_engine` | Identity 创建/查询、Workspace 创建/查询、基础 Ownership Reference | RBAC、OAuth、SSO、权限或企业租户 |
| `project_engine` | Project 创建/查询/列表、Workspace/Owner 引用、最小 `ACTIVE → ARCHIVED` 生命周期 | Asset 绑定、Production Plan、Job、Workflow 或 API |
| `asset_registry` | Asset 创建/查询/列表、基础 Asset Type、初始 Asset Version | 存储适配、Rights、Provenance、Vector Search 或媒体处理 |
| `project_asset_relationship` | Project 使用 Asset 的关联、双向列表查询、重复关联拒绝 | Ownership、Rights、Permission、Version Selection 或 Render Binding |

这些能力使用进程内状态且没有数据库、持久化、网络 API、Application 集成、V4/V3/Compute 集成或 Production 运行证明。它们是已存在的仓库事实，不构成新的 Implementation Authorization。

### 测试资产

- `tests/unit/` 包含上述四个 V5 Foundation 包的 Unit Test；
- `tests/contract/` 包含上述四个包的 Contract Test；
- `tests/integration/` 与 `tests/e2e/` 当前只有目录骨架；
- 当前测试使用 Python 标准库能力，没有引入第三方测试依赖。

测试目录和运行边界见 [tests/README.md](tests/README.md)。

## 当前限制

- Phase 1 Implementation Authorization 尚未授予，`P1-PV-G01` 仍为 `BLOCKED`；
- 没有 Application Layer、V4 Platform、V3 Render Core、Compute 或 Foundation 实现授权；
- 没有网络 API、数据库、Schema、存储适配、Job、Worker、Queue、Workflow 或 Render Pipeline；
- V5 Foundation 包之间没有形成已批准的跨引擎集成；
- Integration 与 E2E 测试尚未实现，也没有 Production Validation；
- 没有正式 Release Candidate 或本地 Baseline Tag，也没有 Production Ready 证据；
- Git 治理规范已经定义，但没有 `origin`；GitHub Repository、GitHub Release、`main` Branch Protection 与 Required Checks 状态无法从当前本地仓库核验，Baseline 状态为 `HOLD / NOT READY FOR TAG`；
- Git 分支、Commit、测试通过或代码存在都不能代替 Scope、Architecture、Risk、Gate 或 Release 决策；
- 未跟踪工作树文件不属于版本化 Repository Baseline，必须单独评审、接受或排除。

## 当前验证方式

当前 V5 Foundation 的 Unit 与 Contract 测试可使用 Python 标准库运行：

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

该命令描述当前仓库事实，不构成项目级技术栈选择。一次本地成功执行也不等于正式 Evidence、Phase Gate、Release 或 Production 结论。

## 开发原则

1. **架构先行**：跨边界变更先完成架构影响判断和必要决策，再进入实现。
2. **授权先行**：Scope、责任与 Gate 状态必须明确；代码、分支或 Commit 不产生授权。
3. **边界清晰**：每项资产只有一个主要职责，依赖必须显式且方向稳定。
4. **最小变更**：只交付当前任务授权的最小闭环，不预建未来能力。
5. **契约优先**：跨层协作依赖获批、可版本化的公开契约，不依赖内部实现细节。
6. **质量内建**：代码、测试、文档、审查和验收结论必须与风险相称。
7. **安全默认**：不提交凭据、个人数据、生产数据或敏感配置。
8. **可追溯**：任务、Commit、评审、证据、风险和决策形成可复核链路。

## 文档入口

- [系统总览](architecture/system-overview.md)
- [系统上下文](architecture/system-context.md)
- [层级边界](architecture/layer-boundaries.md)
- [模块责任矩阵](architecture/module-responsibility-matrix.md)
- [依赖规则](architecture/dependency-rules.md)
- [层级依赖图](architecture/dependency-map.md)
- [技术栈选型记录模板](architecture/technology-stack-decision.md)
- [接口契约基础](docs/04-interface-contract/README.md)
- [数据架构基础](docs/03-data-design/README.md)
- [测试治理](docs/11-testing/README.md)
- [测试资产说明](tests/README.md)
- [Phase 0 Exit Record](docs/12-release/phase-0-exit-record.md)
- [Phase 1 Scope Approval](docs/12-release/phase-1-scope-approval.md)
- [开发规则](governance/DEVELOPMENT_RULES.md)
- [完成定义](governance/DEFINITION_OF_DONE.md)
- [架构守卫](governance/ARCHITECTURE_GUARD.md)
- [Git Workflow](governance/GIT_WORKFLOW.md)
- [Branch Protection](governance/BRANCH_PROTECTION.md)
- [Baseline Release Process](governance/BASELINE_RELEASE_PROCESS.md)

当前 V5 Foundation 使用 Python 标准库和包内导入，仓库没有依赖清单。该实现事实不构成未来模块的技术栈绑定或新增架构决策。
