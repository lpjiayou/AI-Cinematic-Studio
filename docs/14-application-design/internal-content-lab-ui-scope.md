# Internal Content Lab UI Scope

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-P1-UI-001` |
| 架构基线 | AI Cinematic Studio `V2.3` |
| 文档状态 | UI MVP 设计规范；未实现、未发布 |
| 适用 Profile | Internal Content Lab 的条件性 Application Layer 验证 Profile |

## 1. 目的与授权边界

本文定义 Internal Content Lab UI MVP 的页面范围、允许交互边界和明确非目标。它补充 [Phase 1 Production Validation Plan](../12-release/phase-1-production-validation-plan.md) 中未定义的 UI 设计内容，但只是一项独立文档任务，不创建 UI、组件、路由、API、数据模型或运行环境。

Internal Content Lab → Application Layer 仍是条件性验证映射。只有 Phase 1 的 `P1-PV-G01` 获批后，这一映射才可用于候选；本文不能代替该 Gate，也不把 Internal Content Lab 登记为 V2.3 新模块、服务或部署单元。

五个页面名称只表示用户体验视图：

- Dashboard
- Project Workspace
- Asset Library
- Production Flow
- Review Workspace

页面名称不等于业务模块、数据域、权威 owner、工作流步骤或物理存储。所有公开读取与 Command Intent 都只面向 V5 Core OS；UI 不得直连 V4 Platform、V3 Render Core、Compute、Foundation、存储或 Worker。

## 2. UI MVP 通用范围

五个页面共同允许：

1. 展示 V5 Core OS 公开契约返回的稳定视图、结果、限制、时效说明和安全错误。
2. 提供页面级导航、上下文选择、筛选、排序、展开、折叠和未提交草稿等非权威呈现状态。
3. 将用户希望达成的结果表达为技术无关的 Command Intent，并只通过 Application Layer → V5 Core OS 公开契约提交。
4. 在公开结果返回前，将提交中、等待或未知状态明确标记为 UI 呈现状态，不宣称 Domain 事实已改变。
5. 按适用性保持 Request ID、Trace ID、Project ID、Asset ID 和 Job ID 的关联语义；标识不得被解析为权限、所有权、状态或业务关系。
6. 根据 V5 的稳定 Output、Error 和 Retry Guidance 更新呈现；不得解析错误文案决定业务动作。

通用范围不包括：

- 页面布局、组件树、控件、路由路径、视觉样式、设计 Token、响应式规则或交互代码；
- 认证机制、权限模型、业务规则、Domain 状态机、数据 owner、数据库或存储；
- 具体 Command 目录、API 端点、Payload、DTO、事件、协议或错误码实例；
- 下游 V4、V3、Compute、Foundation 的内部步骤、Worker 编排、资源选择或执行控制；
- K2/X2 的业务、模型或技术含义。若未来页面显示 K2/X2，它们仍只是经批准后由 V5 返回的验证轨道标签。

## 3. Dashboard

### Purpose

提供 Internal Content Lab 的受控入口和方向感，使使用者可以查看 V5 返回的概览性视图、识别当前上下文并导航到其他获批页面。

### MVP 范围内

- 展示 V5 返回的概览、时效、限制和需要关注的非权威提示。
- 选择一个已经由公开契约提供的上下文引用，并进入相应页面。
- 显示公开交互的提交状态、结果或安全错误，以及适用关联标识。
- 在存在获批 Command Intent 时收集用户意图，但不自行裁决其有效性。

### MVP 范围外

- 自行聚合或生成 Project、Business、Intelligence 或其他 Domain 的权威事实。
- 将摘要、计数、提示或派生展示解释为来源事实。
- 因页面名或概览内容而取得 Intelligence、Business 或其他数据所有权。
- 直接触发 Domain 写入、存储操作、Worker 或下层能力。

### 页面验收边界

Dashboard 的全部 Domain 相关内容均可追溯到 V5 公开结果；导航与选择只改变 UI 上下文，不改变任何 Domain 事实。

## 4. Project Workspace

### Purpose

围绕一个经公开契约识别的 Project 上下文组织可见信息、页面导航和用户意图，但不定义 Project 的业务结构或权威状态。

### MVP 范围内

- 展示 V5 返回的 Project 语境及其允许公开的相关视图。
- 保持适用 Project ID，并条件性引用 V5 返回的 Asset、Production、Render 或派生语义。
- 保存未提交的页面输入草稿和选择状态，并明确其非权威性质。
- 将获批用户意图提交给 V5，并根据公开结果刷新视图。

### MVP 范围外

- 定义 Project 实体、字段、成员结构、权限模型、生命周期或状态机。
- 自动认定 Application Layer 或页面拥有 Project 数据。
- 通过跨域联表、共享存储或私有模型组合权威事实。
- 直接写入 Project、Asset、Production、Render 或其他 Domain 事实。

### 页面验收边界

Project Workspace 只消费和引用 V5 返回的 Project 上下文；UI 草稿、选择或页面离开均不会被描述为 Project 事实变化。

## 5. Asset Library

### Purpose

提供 Asset 相关公开视图的浏览、查找、筛选和选择体验，使使用者能够引用既有 Asset 上下文，但不把页面变成资产存储或权威目录。

### MVP 范围内

- 展示 V5 返回的 Asset 视图、时效和适用来源说明。
- 在 UI 内浏览、筛选、排序和选择公开结果。
- 在后续导航或 Command Intent 中引用已有且适用的 Asset ID。
- 根据 V5 的公开 Output 或 Error 更新 Asset 相关呈现。

### MVP 范围外

- 直接访问对象存储、文件系统、数据库、缓存、索引或内部数据访问层。
- 定义 Asset 类型、格式、字段、版本结构、生命周期状态或存储位置。
- 直接创建、修改、删除、归档或移动 Asset 权威事实。
- 将 UI 选择、缩略展示、本地缓存或未提交输入当作 Asset 权威来源。

### 页面验收边界

Asset Library 的所有 Asset 内容都来自 V5 公开结果；任何可能影响 Asset 事实的动作都只能形成 Command Intent，不能由 UI 直接执行。

## 6. Production Flow

### Purpose

展示 V5 返回的 Production 语境、可观察进展和相关引用，并允许使用者表达获批意图；页面名称不定义生产工作流或状态机。

### MVP 范围内

- 展示 V5 返回的 Production 视图、限制、时效和公开结果。
- 条件性显示 Project、Asset、Render 或 Job 关联，但不从标识推断关系或状态。
- 收集未提交的 UI 草稿，并通过获批 Command Intent 向 V5 表达期望结果。
- 展示 V5 返回的接受、拒绝、完成、失败或结果暂不可判定等稳定语义；具体结果词汇由未来契约批准。

### MVP 范围外

- 定义 Production 流程步骤、任务类型、状态枚举、转换规则或完成事实。
- 直接启动、暂停、取消、重试或编排 Worker、队列、V3 Render Core 或 Compute。
- 根据本地计时、轮询结果或组件状态写入进展事实。
- 定义渲染参数、作业结构、资源策略或执行技术。

### 页面验收边界

Production Flow 只展示 V5 的公开语义并向 V5 表达意图；任何页面动作都不构成 Production 状态迁移或 Worker 指令。

## 7. Review Workspace

### Purpose

在 V5 提供的公开上下文中呈现可供查看的 Asset、Production、Render 或派生结果，并收集非权威评审草稿或获批评审意图。

### MVP 范围内

- 展示 V5 返回的候选内容引用、结果语义、证据说明、时效和限制。
- 支持页面内选择、比较、标记或未提交评审草稿等非权威呈现状态；具体交互不在本文设计。
- 通过 Command Intent 向 V5 提交经批准的评审意图。
- 只有在 V5 返回稳定公开结果后，才刷新对应展示并明确结果来源。

### MVP 范围外

- 创建 `Review` 数据域、业务实体、字段、审批状态机或商业规则。
- 将未提交草稿、本地标记或乐观呈现视为评审完成事实。
- 直接修改 Asset、Production、Render、Business 或 Intelligence 的权威语义。
- 直接读取下层结果存储、调用渲染执行或控制 Worker。

### 页面验收边界

Review Workspace 的评审内容和结果均以 V5 公开契约为边界；页面不能成为新的权威来源，也不能把评审交互解释为直接 Domain 写入。

## 8. 页面间共同边界

| 事项 | 规则 |
| --- | --- |
| 导航 | 页面切换只改变 UI 呈现与上下文，不表示业务流程推进或 Domain 状态迁移 |
| 读取 | 所有 Domain 相关视图只能由 V5 公开契约提供 |
| 意图 | 可能影响 Domain 的用户动作只形成 Command Intent，并只提交给 V5 |
| 确认 | UI 只有在 V5 返回可依赖的公开结果后才能呈现已确认结果 |
| 失败 | 依据稳定 Error 与 Retry Guidance 处理，不直接补偿存储、Domain 或 Worker |
| 标识 | 只传播已有且适用的统一标识，不推导权限、所有权、状态或标识间关系 |

允许的概念导航关系见 [User Flow Mapping](user-flow-mapping.md)，页面与概念数据域的非所有权关系见 [UI Domain Mapping](ui-domain-mapping.md)，Command Intent 的统一结构见 [Application Command Contract](application-command-contract.md)。

## 9. 变更与验收

新增页面、扩大任一页面职责、引入新的 Domain 相关意图或改变 Application→V5 边界时，必须关联独立任务并复核架构、数据所有权、接口契约和测试影响。页面名称或设计稿不能自行批准范围变化。

本规范通过的最低条件是：五个页面均具有 Purpose、范围内、范围外和验收边界；所有 Domain 内容与 Command Intent 只面向 V5；三项禁止可被逐页验证；文档没有组件、代码、API、数据库、Worker 编排或 V2.3 架构变更。
