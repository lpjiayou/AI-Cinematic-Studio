# 系统上下文

## 1. 目的与适用范围

本文档给出 AI Cinematic Studio V2.3 Core 架构基线的最高层上下文，只描述 Application Layer、V5 Core OS、V4 Platform、V3 Render Core、Compute 与 Foundation 之间的边界关系。它不定义业务模块、数据模型、接口内容、部署拓扑、技术栈或实现方式。

`ADR-0001 / Proposed` 在该六层 Core 链之外提出独立 Experience Layer。该提案只有在后续取得所需审批并形成 remote-verified 重基线后才生效；当前不构成已接受架构事实或实现授权。

拟议的唯一跨仓链为：

`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

Frontend Experience Adapter 属于 Frontend，且只能消费 Creator Public HTTP/API。Frontend 不得直接访问 Creator Application、Domain、SQL、Persistence、Provider、private V5、GPU、Worker 或 ComfyUI；两个仓库不共享客户 UI 源码。该提案不新增 V5/V4/V3 层级，也不改变下述六层相邻依赖方向。

本文使用的是系统逻辑层视图；`apps/`、`services/`、`packages/` 等是仓库工程边界。除非后续获批文档明确规定，不得将二者自动等同或据此移动、创建模块。

## 2. V2.3 基线声明

以下六个名称用于建立 ACS-P0-002 要求的高层治理视图，其中 V5、V4、V3 分别沿用现有文档分类中的规范名称 V5 Core OS、V4 Platform、V3 Render Core。该视图不新增层级、不拆分模块、不证明具体实现已经存在，也不改变任何现有模块的职责；它只固定可进入架构评审的抽象依赖方向：

`Application Layer → V5 Core OS → V4 Platform → V3 Render Core → Compute → Foundation`

箭头表示左侧到右侧是允许提出并评审的依赖方向，不代表某项具体依赖已经获批或实现，也不表示数据流、控制流、事件流、部署包含关系或组织汇报关系。

## 3. 高层关系

| 层级 | 在本上下文中的位置 | 直接允许依赖 | 本文不作出的定义 |
| --- | --- | --- | --- |
| Application Layer | 系统能力的上层消费与交付边界 | V5 Core OS 的公开契约 | 应用清单、产品流程、界面或渠道 |
| V5 Core OS | Application Layer 与 V4 Platform 之间的高层边界 | V4 Platform 的公开契约 | 内部模块、业务职责或实现技术 |
| V4 Platform | V5 Core OS 与 V3 Render Core 之间的高层边界 | V3 Render Core 的公开契约 | 内部模块、平台能力清单或接口内容 |
| V3 Render Core | V4 Platform 与 Compute 之间的高层边界 | Compute 的公开契约 | 渲染模块、引擎选择或执行流程 |
| Compute | V3 Render Core 与 Foundation 之间的高层计算边界 | Foundation 的公开契约 | 调度模型、资源类型、供应商或容量设计 |
| Foundation | 本视图的底层基础边界 | 无上层依赖 | 基础组件清单、数据设施、运行环境或技术选型 |

“直接允许依赖”只说明方向具备被评审的资格，不等同于批准任何具体依赖、契约或实现。

在 ADR-0001 后续接受的条件下，Commercial Frontend 不是 Core Application Layer 的源码子模块。禁止 Frontend 导入 Core 源码、直接调用 Application/Domain/SQL/Persistence/Provider、访问 private V5 Adapter、GPU、Worker 或 ComfyUI，或绕过 Creator Public HTTP/API。Core 不重新建立客户 Commercial UI。

## 4. 上下文边界原则

1. 上层只能通过相邻下层的公开、稳定且可审计契约建立生产依赖。
2. 下层不得依赖、导入或了解上层的内部实现。
3. 任一层不得跳过中间层直接依赖更深层，也不得形成直接或间接循环。
4. 回调、事件、配置、共享文件或其他集成方式不会改变依赖方向，亦不能用于绕过边界。
5. 测试、文档与治理资产的关系继续遵守现有仓库级依赖规则，不纳入六层生产依赖链。
6. 层内模块关系不由本文批准，必须以 V2.3 既有定义或后续经授权的独立架构记录为依据。

## 5. 明确非目标

本文不进行以下工作：

- 新增、删除、重命名或重新分配 V2.3 模块；
- 将六个逻辑层强制映射到某个仓库目录；
- 选择语言、框架、数据库、消息系统、AI 模型、云平台或计算技术；
- 定义 API、事件、数据结构、存储或数据所有权；
- 定义部署单元、运行拓扑、容量或商业化规则。

任何需要上述内容的变更都必须由独立任务授权并完成正式架构评审，不能从本上下文图推导为既定设计。

## 6. 变更控制

若提案改变六层的名称、顺序、职责、公开边界或依赖方向，该提案即构成对 V2.3 架构基线的修改。实施前必须记录动机、影响范围、迁移与回滚方案，完成授权评审，并同步更新系统上下文、依赖图、层级边界、责任矩阵和架构守卫规则。
