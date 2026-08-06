# Internal Content Lab UI — 概念数据域映射

## 1. 文档定位

本文为 Internal Content Lab 的五个 UI 页面建立到七个概念数据域的**非所有权语义映射**，用于评审页面可以展示什么上下文、传播什么关联，以及 Command Intent 可以引用什么既有身份。

本文不定义业务实体、字段、状态、数据结构、API、存储或实现，也不分配数据所有权。页面、Application Layer 和 V5 Core OS 都不会因为本映射自动取得任何数据域或责任范围的权威 owner 身份。

七个数据域的权威概念定义来自 [数据域概念模型](../03-data-design/data-domain-model.md)，实际所有权只能按 [数据权威所有权治理](../03-data-design/data-ownership.md) 的独立获批记录确定。UI 的唯一允许依赖方向是 [Application Layer → V5 Core OS](../04-interface-contract/application-v5-contract.md)。

## 2. 强制边界

所有页面均必须遵守：

- UI 只通过 V5 Core OS 的已批准公开契约取得视图、提交 Command Intent 并接收结果或错误。
- UI 不直接修改 Identity、Project、Asset、Production、Render、Business 或 Intelligence 中的任何 Domain 事实。
- UI 不直接访问数据库、文件、对象存储、缓存、索引或其他存储。
- UI 不直接调用 Worker、执行器、队列、渲染运行单元或其他下层能力。
- UI 不绕过 V5 Core OS 依赖 V4 Platform、V3 Render Core、Compute、Foundation 或其私有实现。
- UI 本地筛选、选择、导航、展开状态和未提交草稿均为临时呈现状态，不能成为权威事实。
- V5 返回某个视图不表示 V5 自动拥有该视图所引用的数据域；权威性仍由独立所有权记录决定。

## 3. 映射标签

| 标签 | 语义 | 明确不代表 |
| --- | --- | --- |
| `VIEW` | 页面可在获批契约范围内展示 V5 返回的视图或摘要 | UI 读取 Domain 内部模型、访问存储、拥有来源事实或自行计算权威结论 |
| `CONTEXT` | 页面可传播已存在、适用且来源明确的关联标识或上下文 | 身份认证、授权、所有权、写入权或从一个 ID 推导另一个 ID |
| `INTENT_REF` | 获批的 Application → V5 Command Intent 可引用该域的既有身份或上下文 | UI 直接修改该域、命令 Domain/Worker、创建 API 或保证意图必然生效 |
| `—` | 本 UI MVP 不预设该页面与该域的默认语义关系 | 永久禁止未来经独立任务和契约批准的关系 |

表中带 `*` 的标签表示**条件性适用**：只有具体 Application → V5 契约实例明确批准后才能使用。任何标签都只是语义相关性，不是 owner、存储、API、调用路径或实现授权。

## 4. 五页面 × 七概念数据域矩阵

| UI 页面 | Identity | Project | Asset | Production | Render | Business | Intelligence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Dashboard** | `VIEW*` `CONTEXT` | `VIEW` `CONTEXT` `INTENT_REF*` | `VIEW*` `CONTEXT*` | `VIEW*` `CONTEXT*` | `VIEW*` `CONTEXT*` | `—` | `VIEW*` |
| **Project Workspace** | `VIEW*` `CONTEXT` | `VIEW` `CONTEXT` `INTENT_REF*` | `VIEW*` `CONTEXT*` `INTENT_REF*` | `VIEW*` `CONTEXT*` `INTENT_REF*` | `VIEW*` `CONTEXT*` | `—` | `VIEW*` |
| **Asset Library** | `CONTEXT` | `CONTEXT*` | `VIEW` `CONTEXT` `INTENT_REF*` | `VIEW*` `CONTEXT*` | `VIEW*` `CONTEXT*` | `—` | `VIEW*` |
| **Production Flow** | `CONTEXT` | `VIEW*` `CONTEXT*` | `VIEW*` `CONTEXT*` `INTENT_REF*` | `VIEW` `CONTEXT` `INTENT_REF*` | `VIEW*` `CONTEXT*` `INTENT_REF*` | `—` | `VIEW*` |
| **Review Workspace** | `VIEW*` `CONTEXT` | `VIEW*` `CONTEXT*` | `VIEW*` `CONTEXT*` `INTENT_REF*` | `VIEW*` `CONTEXT*` `INTENT_REF*` | `VIEW*` `CONTEXT*` `INTENT_REF*` | `—` | `VIEW*` |

本矩阵不是页面需求清单。非空单元格仍需具体契约授权；空单元格也不能被解释为修改架构基线。

## 5. 页面映射说明

### 5.1 Dashboard

- 可组合展示 V5 返回的已批准摘要视图，但不得自行将多个域的观察结果合成为新的权威事实。
- Project、Asset、Production 或 Render 上下文只用于导航和关联；其存在不表示 UI 获得修改权。
- Business 不在当前 UI MVP 的默认范围内。Intelligence 仅能条件性展示 V5 返回的派生视图，且必须保留来源、时效和限制，不能将其提升为来源事实。

### 5.2 Project Workspace

- Project 是页面上下文，不是页面拥有的实体或状态模型。
- 页面可以展示 V5 返回的相关 Asset、Production、Render 或 Intelligence 视图，但不能通过本地拼接建立跨域权威关系；Business 不在当前 UI MVP 默认范围内。
- 任何 `INTENT_REF` 只允许把既有上下文提交给 V5；Project Workspace 不直接改变 Project 或相关域事实。

### 5.3 Asset Library

- Asset 是主要展示语义，但页面不拥有 Asset 身份、内容、版本、血缘、保留或处置事实。
- Project、Production 与 Render 只在获批契约返回相应关系时作为条件上下文展示，不得从名称、路径或相似性推断关系。
- Intelligence 仅作为可追溯的派生视图；不得覆盖 Asset 来源语义。
- 页面不得直接读取、写入、上传、移动或删除任何存储内容。

### 5.4 Production Flow

- Production 是主要展示语义，但页面不定义 Production 状态机、转换规则、流程步骤或完成事实。
- Asset 与 Render 只能作为 V5 返回的已治理上下文或获批 Command Intent 引用。
- 页面不得调度、启动、停止或补偿 Worker，也不得把 UI 交互状态当作执行状态。
- Intelligence 若适用，只能显示带来源和限制的派生理解。

### 5.5 Review Workspace

- Review Workspace 是 UI 表面名称，不创建第八个数据域、Review 业务实体或新的所有权边界。
- 页面可以条件性展示与 Project、Asset、Production、Render 或 Intelligence 有关的 V5 视图，并形成经批准的 Command Intent。
- 本地选择、比较和未提交意见均为非权威草稿；只有 V5 返回的公开结果才能改变 UI 对已确认结果的呈现。
- 页面不得直接修改候选 Asset、Production 或 Render 事实，也不得直接控制 Worker。

## 6. 七域使用约束

### Identity

Identity 只提供受治理身份上下文。UI 可以显示或传播适用上下文，但不能自行认证、授权、签发凭据或根据标识符结构推断权限。

### Project

Project 只提供项目语境。Project ID 可在适用页面中作为上下文或 Intent 引用，但不授权 UI 定义项目成员、生命周期或其他事实。

### Asset

Asset 只提供可识别内容资产的概念语义。UI 可以显示 V5 返回的身份、版本或血缘视图，但不得将展示副本变成权威来源。

### Production

Production 只提供生产上下文和过程语义。UI 可以显示 V5 返回的观察结果或提交意图，但不得实现状态转换、编排或流程裁决。

### Render

Render 只提供渲染语境及结果语义。UI 不定义渲染参数、作业结构、执行协议，也不直接调用任何执行能力。

### Business

Business 只提供商业解释性语义。当前 UI MVP 对五个页面均不预设 Business `VIEW`、`CONTEXT` 或 `INTENT_REF`；未来若需引入，必须由独立任务和 Application → V5 契约批准，且不能创建商业规则、计费、价格或合同事实。

### Intelligence

Intelligence 只提供可追溯的派生理解。UI 必须区分派生视图和来源事实，不得隐藏不确定性、时效或来源限制。

## 7. 标识符适用性

- Request ID 用于关联一次适用的 Application → V5 请求，不表示完成、身份或授权。
- Trace ID 只在已建立追踪上下文时传播，不能由 Request ID 推导。
- Project ID、Asset ID 与 Job ID 只在相应语义确实存在且来源权威时传播。
- 不适用的 ID 保持不适用；UI 不得使用固定值、空含义或其他 ID 冒充。
- 所有 ID 都是不透明关联信息，不能被 UI 解析为数据域、权限、状态、位置或存储键。

## 8. 评审检查清单

具体页面或 Command Intent 进入评审前必须确认：

- 页面使用的每个 `VIEW`、`CONTEXT` 和 `INTENT_REF` 都有 Application → V5 契约依据。
- 映射没有声明或暗示 UI、Application Layer 或 V5 自动成为数据 owner。
- 不存在 UI → Domain、UI → 存储、UI → Worker 或 UI → V4/V3/Compute/Foundation 的直接路径。
- 没有从页面名称推导实体、字段、API、状态机或数据关系。
- UI 本地状态与 V5 返回的已确认语义清晰区分。
- Business 保持当前 UI MVP 不预设，Intelligence 的条件性视图没有覆盖来源事实。
- 任何变化都不新增、拆分、合并或重新分配 V2.3 模块职责。

本文只建立 UI 与概念数据域之间的非所有权映射，不实现任何 UI、契约或数据能力。
