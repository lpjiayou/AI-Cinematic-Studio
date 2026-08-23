# AI Cinematic Studio Application Design

## 1. 目的与边界

`docs/14-application-design/` 是 ACS-P1-UI-001 明确授权的知识分类扩展，用于保存 Application Layer 的技术中立设计说明。该目录不是新的 V2.3 架构层、模块、服务、应用实例或运行时边界，也不自动映射到 `apps/`、`services/`、`packages/`、`infrastructure/` 或其他物理目录。

本目录中的文档只描述职责、交互意图、映射规则和契约要求，不创建代码、UI 组件、API、Worker、数据库、存储、数据所有权、技术选型或已经存在的产品能力。任何具体实现仍需独立任务、明确责任和适用评审授权。

## 2. V2.3 依赖基线

本目录必须保持以下 V2.3 生产依赖方向：

`Application Layer → V5 Core OS → V4 Platform → V3 Render Core → Compute → Foundation`

箭头表示上层可在具体契约获批后依赖相邻下层的公开边界，不表示数据流、事件流、响应方向、目录映射或实现已经获批。Application Layer 只能直接依赖 V5 Core OS 的公开契约；它与 V4 Platform、V3 Render Core、Compute 和 Foundation 的关系均为经由相邻层契约形成的间接关系。

权威约束见 [系统上下文](../../architecture/system-context.md)、[层级依赖图](../../architecture/dependency-map.md)与[Application–V5 契约模板](../04-interface-contract/application-v5-contract.md)。若本文档分类中的说明与权威架构冲突，应停止变更并按架构流程澄清，不得以 UI 或交付便利建立例外。

## 3. 文档索引

| 文档 | 作用 |
| --- | --- |
| [README](README.md) | 说明本目录的导航、权威边界和统一禁止事项 |
| [Application Layer Overview](application-layer-overview.md) | 定义 Application Layer 的职责、状态边界及层间关系 |
| [Internal Content Lab UI Scope](internal-content-lab-ui-scope.md) | 记录 Internal Content Lab 条件性 UI 范围与非目标 |
| [UI–Domain Mapping](ui-domain-mapping.md) | 记录 UI 语义与既有概念数据分类之间的治理映射 |
| [User Flow Mapping](user-flow-mapping.md) | 记录获批交互流程的展示级映射与边界 |
| [Application Command Contract](application-command-contract.md) | 记录 Application Layer 向 V5 Core OS 表达 Command Intent 时必须遵守的契约 |

索引中的文件名只定义知识位置，不证明对应 UI、流程、命令、模块或实现已经存在。

Internal Content Lab UI MVP 的页面范围严格包含以下五个视图名称：Dashboard、Project Workspace、Asset Library、Production Flow、Review Workspace。它们只是 UI 页面范围，不是模块、服务、数据域、工作流步骤、部署单元或数据 owner。

## 4. 三项禁止

1. **UI 不得直接修改 Domain 事实**：UI 只能保存非权威呈现状态并向 V5 表达 Command Intent；页面状态、草稿、缓存或乐观呈现不能成为权威事实。
2. **UI 不得直接访问存储**：UI 不得直接读写数据库、文件、对象存储、缓存、索引、抽象存储能力或内部数据访问层；所有公开视图只经 V5 获得。
3. **UI 不得直接调用 Worker**：UI 不得发现、配置、启动、暂停、重试或控制任何下层执行实现。“Worker”只是泛称，不是新增的 V2.3 层级或模块。

上述禁令同时禁止跨层依赖：Application Layer 不得直接调用、导入或了解 V4 Platform、V3 Render Core、Compute、Foundation 或任何层的私有实现，不得以回调、事件、共享配置或其他机制形成反向、跳层或循环依赖。本目录也不得创建代码、组件、API、Worker、服务、运行时流程、技术选型或物理目录映射。

## 5. 演进规则

Application 设计必须引用已批准事实，区分当前状态、条件性映射、提案和未来事项。新增具体接口、改变契约所有权、引入新的跨层依赖或重新解释 V2.3 职责时，必须先完成适用的任务授权、契约评审与架构变更流程。
