# V3 Render Core 文档索引

## 1. 目录定位

`docs/07-v3-render-core/` 保存 V3 Render Core 的技术无关边界说明、评审记录与后续获批设计知识。该目录不是代码位置、部署单元、服务清单或数据所有权声明。

当前文档只定义 Phase 1 Vertical Slice 所需的最小 V3 语义边界，不批准完整 Render Core、渲染引擎、执行流程、技术栈或生产能力。

## 2. 架构位置

V3 在冻结 V2.3 链路中的位置为：

`V5 Core OS → V4 Platform → V3 Render Core → Compute`

- V3 只从 V4 Platform 相邻公开契约接收输入。
- 具体 V3–Compute 契约获批后，V3 才可通过该相邻公开边界表达下层计算需求；当前模板不构成授权。
- V3 不直接调用、依赖或了解 V5 Core OS 的内部实现。
- 结果或错误沿相邻调用上下文返回，不形成 V3 对 V4 或 V5 的反向生产依赖。

完整约束见 [系统上下文](../../architecture/system-context.md)与 [层级依赖图](../../architecture/dependency-map.md)。

## 3. 文档索引

| 文档 | 作用 | 状态 |
| --- | --- | --- |
| [Render Core Boundary](render-core-boundary.md) | 定义 V3 输入、输出、责任与明确非责任 | Phase 1 技术无关边界评审 |
| [V5–V3 Vertical Slice Review](../04-interface-contract/v5-v3-vertical-slice-review.md) | 评审经 V4 中介的端到端生产与 Asset Return 语义 | 条件性架构相容；未批准实现 |
| [V4–V3 Contract Template](../04-interface-contract/v4-v3-contract.md) | 提供 V4 调用 V3 时具体契约必须填写的基础结构 | 模板；不是具体接口 |
| [V3–Compute Contract Template](../04-interface-contract/v3-compute-contract.md) | 提供 V3 调用 Compute 时具体契约必须填写的基础结构 | 模板；不是具体接口 |

## 4. V3 最小定位

在本阶段，V3 Render Core 只承担以下边界责任：

- 接收 V4 通过获批相邻契约提交的 Render Request；
- 验证渲染边界所需的最小完整性与支持范围；
- 封装 V3 内部语义，只通过 Compute 公开契约表达下层需求；
- 形成可观察 Render Result 或稳定 Error，并保持适用关联上下文；
- 不接管 Project、Production、Shot 或 Asset 的上层核心语义。

“Render Request” 不是 API、Job 或队列消息；“Render Result” 不是文件、Asset 或 Job 状态。具体含义以 [Render Core Boundary](render-core-boundary.md) 为准。

## 5. 目录守卫

本目录不得用于创建或追认：

- V5→V3 直连、V3→V5 回调或绕过 V4 的数据通道；
- V3 对 Project、Production、Asset 或 Render 数据域的自动所有权；
- 数据库、Schema、API、Job、Worker、队列、存储或部署实现；
- 渲染引擎、AI 模型、文件格式、资源规格或供应商选择；
- 未经批准的 V3 模块、状态机、Workflow 或跨层依赖。

任何具体实现必须等待相邻契约、责任、Open Questions 和验证 Gate 独立获批。当前参考范围见 [Phase 1 Production Validation Plan](../12-release/phase-1-production-validation-plan.md)。
