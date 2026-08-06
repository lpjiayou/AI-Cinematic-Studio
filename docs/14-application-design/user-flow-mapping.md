# User Flow Mapping

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-P1-UI-001` |
| 架构基线 | AI Cinematic Studio `V2.3` |
| 文档状态 | 概念用户流规范；未实现 |

## 1. 目的

本文定义 Dashboard、Project Workspace、Asset Library、Production Flow 与 Review Workspace 之间的概念导航和交互边界，使 UI 导航、读取、Command Intent 与 Domain 事实变化保持清晰分离。

本文不是业务流程图、Domain 工作流、路由表、组件事件图或 V2.3 调用链。页面 A 导航到页面 B 只表示 UI 呈现变化，不表示数据所有权、Domain 状态或下层执行发生变化。

页面范围以 [Internal Content Lab UI Scope](internal-content-lab-ui-scope.md) 为准，Application Layer 边界以 [Application Layer Overview](application-layer-overview.md) 为准。

## 2. 四类交互的区分

| 交互类型 | 含义 | 是否可改变 Domain 事实 |
| --- | --- | --- |
| UI Navigation | 页面进入、返回、切换、展开或选择等本地呈现变化 | 否 |
| View Request | Application Layer 通过 V5 公开契约请求可展示的公开结果 | 否；读取不产生写入授权 |
| Command Intent | UI 将用户期望的结果提交给 V5，请求权威边界判断和处理 | 否；提交意图不等于接受、完成或事实变化 |
| Confirmed Public Result | V5 通过公开契约返回 UI 可以依赖的稳定结果或错误 | UI 只能据此刷新呈现；事实是否变化由获批权威边界决定 |

UI 本地状态包括导航历史、选择、筛选、排序、展开、未提交草稿、加载提示、提交中提示和安全错误展示。它们都是非权威呈现状态，不得被包装为 Project、Asset、Production、Render、Business、Intelligence 或 Identity 事实。

## 3. 统一交互序列

每个涉及公开 Domain 语义的用户流遵守以下顺序：

1. UI 建立或沿用当前页面的非权威呈现上下文。
2. 如需公开视图，Application Layer 只向 V5 Core OS 的获批公开契约提出 View Request。
3. UI 展示 V5 返回的视图、时效、限制、适用关联标识和安全错误。
4. 用户进行导航、选择或编辑未提交草稿；这些行为保持在 UI 边界内。
5. 若用户动作可能请求 Domain 结果变化，UI 按 [Application Command Contract](application-command-contract.md)形成 Command Intent。
6. UI 只将意图提交给 V5，不携带 UI 内部引用，不指定 V4、V3、Compute、Foundation、存储或 Worker 的执行步骤。
7. V5 返回公开结果或稳定错误；UI 不把“已提交”或“已接收”自动显示为“已完成”。
8. UI 只依据 V5 公开结果刷新视图；需要最新事实时重新经 V5 获取，不直接读取存储或下层状态。
9. 失败或结果未知时，UI 遵守 Error 与 Retry Guidance，不自行重试 Worker、不直接补偿 Domain、不修改存储。

这一顺序不规定同步、异步、轮询、推送或任何技术机制。

## 4. 页面导航映射

下表只声明允许设计的概念导航和上下文连续性。实际入口条件、可用动作和公开结果必须由未来获批的 V5 契约确定。

| Flow ID | 起点 | 目标 | UI 目的 | 可携带的上下文 | 明确不代表 |
| --- | --- | --- | --- | --- | --- |
| `UF-01` | 外部未指定入口 | Dashboard | 进入受控 UI Profile 并获取 V5 概览视图 | Request ID、Trace ID 及其他适用上下文 | 创建会话实体、产生 Intelligence 事实或启动下层任务 |
| `UF-02` | Dashboard | Project Workspace | 进入一个已识别 Project 的工作视图 | 已有且适用的 Project ID；不得伪造 | 创建/修改 Project、改变成员或推进生命周期 |
| `UF-03` | Dashboard 或 Project Workspace | Asset Library | 浏览 V5 返回的 Asset 视图并选择引用 | 适用的 Project ID、Asset ID | 直接访问文件/对象存储、转移 Asset 所有权或修改元数据 |
| `UF-04` | Project Workspace 或 Asset Library | Production Flow | 查看 V5 返回的 Production 语境并准备获批意图 | 适用的 Project ID、Asset ID、Job ID | 业务流程推进、状态迁移、Worker 编排或 Compute 调用 |
| `UF-05` | Asset Library、Project Workspace 或 Production Flow | Review Workspace | 查看 V5 返回的候选结果并形成评审草稿或意图 | 适用的 Project ID、Asset ID、Job ID、Trace ID | 创建 Review 数据域、确认评审事实或修改 Render/Asset |
| `UF-06` | 任一页面 | Dashboard 或先前页面 | 返回概览或恢复 UI 导航上下文 | 只沿用仍适用的既有标识 | 回滚 Domain 事实、取消 Worker 或恢复下层执行 |

表中列出某个标识只表示其在相应交互中可能适用，不表示一定存在，也不定义标识格式、生成责任、基数或相互关系。Trace ID、Project ID、Asset ID、Job ID 之间不得相互推导。

## 5. 页面流的 Command Intent 边界

| 页面 | 纯 UI 行为示例类别 | 何时必须形成 Command Intent | 禁止的捷径 |
| --- | --- | --- | --- |
| Dashboard | 导航、选择上下文、展开摘要 | 用户请求一个可能影响公开 Domain 结果的动作时 | 从摘要直接写事实或调用下层 |
| Project Workspace | 切换视图、编辑未提交草稿、选择引用 | 请求权威边界处理 Project 语境中的获批意图时 | 直接修改 Project 或跨域共享状态 |
| Asset Library | 筛选、排序、选择 V5 返回的 Asset 引用 | 请求可能影响 Asset 相关公开结果的获批动作时 | 直接访问存储或写 Asset 元数据 |
| Production Flow | 查看 V5 结果、编辑未提交参数草稿 | 请求 Production 相关公开结果变化时 | 定义状态迁移、调用 Worker/V3/Compute |
| Review Workspace | 查看、比较、保存本地评审草稿 | 提交经批准的评审意图时 | 把本地草稿写成完成事实或直接改 Asset/Render |

“示例类别”只划分 UI 与 Command 边界，不创建具体功能、组件或业务命令。每一个真实 Command Intent 都必须先形成获批契约实例。

## 6. 结果与呈现规则

### 6.1 提交不等于完成

Command Intent 被 UI 构造、提交或由 V5 接收，都不能自动证明 Domain 事实已经改变。只有 V5 公开契约明确返回可依赖的完成语义时，UI 才能将相应呈现标记为已确认；即使如此，UI 仍不是权威事实来源。

### 6.2 未决或未知结果

当公开结果尚未完成、暂不可判定或关联上下文不足时，UI 应保持非权威的等待或未知呈现，不得猜测成功、失败或下游执行状态。后续确认仍只通过 V5 公开契约获得。

### 6.3 拒绝与错误

UI 根据 V5 的稳定 Error Code 语义、Category、Message 和 Retry Guidance 提供安全反馈。Message 只供理解，不得作为机器分支；UI 不得透传堆栈、查询、内部路径、供应商诊断或下层原始错误。

### 6.4 陈旧视图

本地显示副本可能过时。UI 可以提示时效并请求刷新，但不能用旧视图绕过 V5 的权威校验，也不能因本地值不同而直接覆盖 Domain 事实。

## 7. 关联标识连续性

- Request ID 用于关联一次逻辑请求；进入受治理调用链时按获批契约确保其存在。
- Trace ID 只在已有追踪上下文时保持连续，不与 Request ID 相互替代。
- Project ID、Asset ID、Job ID 只在对应语义适用且来源权威时携带；不适用时不得用虚构值占位。
- 输出和错误保留适用上下文，使 UI 能将结果关联到正确呈现。
- 所有标识只用于身份与关联，不证明权限、所有权、存在性、状态或 Domain 关系。

## 8. 流程记录模板

未来新增或细化用户流时，应以技术无关方式记录：

| 字段 | 要求 |
| --- | --- |
| Flow ID 与状态 | 唯一标识；拟议、已批准、已废弃等治理状态 |
| 用户目的 | 描述希望理解或达成的可观察结果 |
| 起点与目标页面 | 仅使用已批准 UI 页面名称 |
| UI Navigation | 说明本地呈现变化及保持的草稿 |
| View Request | 说明需要 V5 提供的公开语义，不列字段或端点 |
| Command Intent | 引用获批契约；纯导航时标记不适用 |
| 适用 Domain 分类 | 只作概念关联，不分配 owner |
| 关联标识 | 逐项说明五类统一标识的适用性与来源 |
| 可观察结果 | 说明 V5 返回后 UI 可以依赖的稳定语义 |
| Error 与恢复 | 引用稳定错误和 Retry Guidance，不指定下层补偿 |
| 明确非目标 | 排除 Domain 工作流、存储、Worker、API 和技术实现 |
| 责任与证据 | 记录 Application/V5 契约责任人、评审人与验证证据 |

## 9. 明确禁止与非目标

1. UI 直接修改 Domain 事实。
2. UI 直接访问 Operational、Object、Vector、Analytics Storage 或任何具体存储实现。
3. UI 直接调用、发现、配置或控制 Worker；Worker 只是下层执行实现的泛称，不是新的 V2.3 层级。
4. UI 绕过 V5 直接调用 V4、V3、Compute 或 Foundation。
5. 将页面导航图解释为业务流程、Domain 状态机、数据流或层间调用图。
6. 定义 URL、路由、组件事件、状态管理、协议、Payload、API 或执行技术。
7. 通过本地乐观状态、缓存、错误解析或重试行为建立第二个权威事实来源。

用户流变更若新增页面、Domain 意图或依赖关系，必须经过范围、契约、数据所有权和架构复核。本文件不改变 V2.3，也不授权实现任何流程。
