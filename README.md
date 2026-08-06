# AI Cinematic Studio

AI Cinematic Studio 是面向 AI 内容资产生产、账号矩阵运营与商业化 SaaS 的一体化工程基础设施。本仓库用于承载产品入口、服务、共享能力、平台基础设施以及与其配套的架构、质量和治理资产。

> 当前基线：Phase 0 Engineering Foundation Initialization（ACS-P0-001）。本阶段仅建立仓库骨架与工程规则，不包含任何业务功能、数据库设计或未来模块实现。

## 项目定位

本项目的长期目标是为 AI 驱动的内容生产与商业化平台提供可演进、可审计、可测试的工程底座。仓库采用明确的职责边界管理交付入口、独立服务、复用能力、基础设施、文档与治理规则，避免业务实现与平台约束相互污染。

## V2.3 最终架构说明

V2.3 最终架构是本阶段的既有架构基线。ACS-P0-001 只将其映射为可扩展的仓库级边界，不新增、删除、拆分或重命名未来业务模块，也不解释尚未批准的模块内部设计。

| 仓库区域 | 架构职责 | Phase 0 状态 |
| --- | --- | --- |
| `apps/` | 可交付应用与用户/运营入口的边界容器 | 已建空目录，禁止业务实现 |
| `services/` | 可独立运行或部署的服务边界容器 | 已建空目录，禁止业务实现 |
| `packages/` | 跨应用、跨服务复用的技术契约与通用能力容器 | 已建空目录，禁止提前抽象 |
| `infrastructure/` | 构建、部署、运行环境与平台资源声明的边界容器 | 已建空目录，未选择技术栈 |
| `tests/` | 单元、集成、契约与端到端质量资产 | 已建立分类骨架 |
| `docs/` | 从治理、战略、架构到商业化的版本化知识主干 | 已建立 00–13 分类骨架 |
| `architecture/` | 当前有效的跨仓库架构规则与责任边界 | 已建立基础规则 |
| `governance/` | 开发、评审、分支、提交和架构守卫规则 | 已建立基础规则 |
| `scripts/` | 可重复工程操作的自动化入口 | 已建空目录，禁止承载业务逻辑 |

V2.3 在仓库层遵循单向、显式依赖原则：应用可以组合公开的服务契约和共享包；服务只能通过公开契约协作；共享包不得反向依赖应用或服务；基础设施不得成为业务逻辑的隐式入口。详细规则见 [dependency-rules.md](architecture/dependency-rules.md)。

`docs/05-v5-core-os`、`docs/06-v4-platform` 与 `docs/07-v3-render-core` 仅保留 V2.3 文档分层位置。本任务不补写或改动这些层级的未来模块架构。

## 当前开发阶段

当前处于 **Phase 0：Engineering Foundation Initialization**。

本阶段已授权的工作：

- 建立稳定的仓库目录与文档信息架构；
- 定义仓库级职责、依赖方向和工程治理基线；
- 为后续自动化检查、测试和架构决策留出可扩展位置。

本阶段明确禁止：

- 开发产品、运营、渲染、商业化等任何业务功能；
- 设计数据库、数据表、迁移脚本或持久化模型；
- 安装大型依赖或提前锁定应用技术栈；
- 推演、修改或实现尚未批准的未来模块架构。

## 开发原则

1. **架构先行**：跨边界变更先更新架构说明或记录决策，再进入实现。
2. **边界清晰**：每项资产只有一个主要职责，依赖必须显式且方向稳定。
3. **最小变更**：只实现当前任务授权的最小闭环，不用猜测替代产品和架构决策。
4. **契约优先**：跨模块协作依赖公开、可版本化的契约，不依赖内部细节。
5. **质量内建**：代码、文档、测试和可观测性要求随功能一同评审，不留隐性债务。
6. **安全默认**：不提交凭据、个人数据或敏感配置，权限遵循最小化原则。
7. **可追溯**：变更通过任务、提交、评审与架构记录形成完整证据链。
8. **自动化优先**：重复工程操作应逐步沉淀为可验证脚本，但脚本不得承载业务逻辑。

## 基础文档入口

- [系统总览](architecture/system-overview.md)
- [系统上下文](architecture/system-context.md)
- [层级边界](architecture/layer-boundaries.md)
- [模块责任矩阵](architecture/module-responsibility-matrix.md)
- [依赖规则](architecture/dependency-rules.md)
- [层级依赖图](architecture/dependency-map.md)
- [技术栈选型记录模板](architecture/technology-stack-decision.md)
- [开发规则](governance/DEVELOPMENT_RULES.md)
- [架构守卫](governance/ARCHITECTURE_GUARD.md)
- [架构变更流程](governance/ARCHITECTURE_CHANGE_PROCESS.md)
- [ADR 模板](governance/ADR_TEMPLATE.md)
- [完成定义](governance/DEFINITION_OF_DONE.md)
- [风险登记册](governance/RISK_REGISTER.md)

当前没有运行时、构建命令或依赖安装步骤；这些内容必须由后续获批任务引入。
