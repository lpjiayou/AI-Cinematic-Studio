# AI Cinematic Studio 系统总览

## 1. 文档目的

本文给出 AI Cinematic Studio 源自 Phase 0 的仓库级系统视图，用于统一术语、物理边界和演进方式。它是 V2.3 最终架构的工程承载说明，不是业务方案、部署拓扑或模块详细设计。Phase 0 治理与当前已接受里程碑之间的历史漂移登记为 `OPEN / DEFERRED TO PRE-M6-RB1.3`；本次七文件修订不静默改写其他治理资产。

## 2. 架构基线

AI Cinematic Studio 定位为 AI 内容资产生产、账号矩阵运营与商业化 SaaS 的一体化基础设施。V2.3 最终架构视为当前有效基线；任何后续模块、接口、数据或部署设计都必须由独立任务和正式评审批准。

Phase 0 只固化以下事实：

- 交付入口、独立服务、共享能力与基础设施具有不同的工程边界；
- 文档、架构、治理、测试和自动化是一等工程资产；
- 依赖必须通过公开边界并保持可替换、可测试、可审计；
- 目录名称不是业务模块承诺，空目录也不代表已批准实现。

## 3. 仓库逻辑视图

| 逻辑层 | 物理位置 | 主要作用 |
| --- | --- | --- |
| 交付层 | `apps/` | 继续承载 Core Creator Server、公开 HTTP/API 运行入口及获批的非客户技术工具；根据已接受的 ADR-0001，不承载 Commercial SaaS 客户体验层 |
| 服务层 | `services/` | 承载未来获批的独立运行或部署单元 |
| 复用层 | `packages/` | 承载经过验证的共享契约与通用能力 |
| 平台层 | `infrastructure/` | 承载环境、构建、部署和平台资源声明 |
| 质量层 | `tests/` | 承载跨边界质量验证资产 |
| 知识与控制面 | `docs/`、`architecture/`、`governance/` | 承载依据、规则、决策和演进控制 |
| 工程自动化 | `scripts/` | 承载可重复、无业务语义的工程操作 |

生产资产只能从明确的上层入口依赖稳定的下层公开能力。治理和架构文档约束生产资产，但不得作为运行时依赖。测试可以依赖被测资产，生产资产不得依赖测试。

`ADR-0001 / Accepted` 确立：客户 Commercial Frontend 位于独立 `AI-Cinematic-Studio-Frontend` 仓库，Core 通过公开 Creator HTTP/API 提供 Application 能力，并且不通过 `apps/` 维护第二套客户 UI。该规则已由 remote-verified 的 PRE-M6-RB1.1 治理基线生效。

唯一跨仓链为：

`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

Frontend Experience Adapter 属于 Frontend，只能消费 Creator Public HTTP/API；两个仓库不共享客户 UI 源码。Frontend 不得直接访问 Creator Application、Domain、SQL、Persistence、Provider、private V5、GPU、Worker 或 ComfyUI，Core 不重新建立客户 Commercial UI。

## 4. 文档知识主干

`docs/` 使用固定编号保持导航稳定：

| 编号 | 主题 |
| --- | --- |
| 00 | 治理 |
| 01 | 战略 |
| 02 | 架构 |
| 03 | 数据设计 |
| 04 | 接口契约 |
| 05 | V5 Core OS |
| 06 | V4 Platform |
| 07 | V3 Render Core |
| 08 | 计算 |
| 09 | 安全 |
| 10 | 可观测性 |
| 11 | 测试 |
| 12 | 发布 |
| 13 | 商业化 |

这些目录当前仅定义信息归档位置，不代表相关方案已经设计或批准。当前有效的跨仓库强制规则位于根目录 `architecture/` 与 `governance/`；后续专题文档不得与其冲突。

## 5. 横切质量属性

后续架构与实现应持续满足以下属性，但 Phase 0 不为它们选择具体技术：

- 可维护性：职责单一、边界稳定、变更影响可预测；
- 可测试性：公开契约可独立验证，测试分层清晰；
- 可观测性：关键运行行为最终具备统一证据链；
- 安全性：身份、权限、机密与数据边界显式管理；
- 可演进性：技术替换不要求跨层泄漏内部实现；
- 可审计性：架构决策、代码变更和发布结果可追溯。

## 6. Phase 0 非目标

本阶段不定义：

- 业务域、产品流程或用户体验；
- 服务清单、模块拆分、API 或消息协议；
- 数据库、数据模型、存储或迁移策略；
- 云厂商、计算框架、AI 模型或渲染技术栈；
- 部署拓扑、容量指标、商业化规则或计费模型。

## 7. 演进机制

需要扩展本总览时，变更必须关联获批任务，并同步检查层级边界、责任矩阵、依赖规则和架构守卫。改变 V2.3 既有模块架构的提案不应直接修改本文，而应先形成独立架构决策记录并完成授权评审。
