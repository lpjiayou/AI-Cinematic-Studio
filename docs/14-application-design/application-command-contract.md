# Application Layer → V5 Core OS Command Intent Contract Template

> 状态：技术中立的逻辑契约模板。模板本身不批准任何具体 Command Intent、业务行为、API 或实现。

## 1. 文档定位

本文用于记录 Application Layer UI 向 V5 Core OS 公开边界提交 Command Intent 时必须明确的稳定语义。唯一允许的调用方向是：

`Application Layer → V5 Core OS`

Command Intent 表达用户希望 V5 评估的意图，不等于 UI 对 Domain 下达命令，也不保证 Domain 事实已经改变。具体契约只有在关联任务、所有者和评审均获批准后才可生效。

本文不定义具体业务命令、业务字段、端点、API、协议、序列化、存储、框架、下游调用步骤或 Worker 实现，也不新增或改变 V2.3 架构。

## Metadata

| 元数据 | 待填写内容 |
| --- | --- |
| Contract ID | `<唯一且不可复用的契约标识>` |
| Title | `<只描述稳定意图语义，不使用技术操作名称>` |
| Status | `<Proposed / Accepted / Deprecated / Superseded>` |
| Semantic Version | `<语义版本；本文不规定编码方式>` |
| Linked Task / ADR | `<获批任务及适用决策；无 ADR 时说明依据>` |
| Initiating UI Surface | `<Dashboard / Project Workspace / Asset Library / Production Flow / Review Workspace 中的适用页面>` |
| Application Responsibility | `<Application Layer 责任人>` |
| V5 Public Contract Responsibility | `<V5 Core OS 公开契约责任人>` |
| Reviewers | `<架构、接口、安全、数据、测试等适用评审人>` |
| Effective / Review Condition | `<生效条件与复审触发条件>` |

`Proposed` 状态不构成实现或调用授权。契约实例状态为 `Accepted` 前，UI 不得据此提交意图。

## Purpose

### User Intent

`<以技术中立语言说明用户希望系统评估的意图，不描述端点、方法、组件或下游步骤>`

### Observable Goal

`<说明 Application Layer 最终需要观察到什么稳定结果，区分“收到意图”和“权威结果已成立”>`

### Scope

- `<本契约实例允许表达的语义边界>`
- `<适用的 UI 页面与用户上下文>`
- `<允许引用的既有概念域上下文>`

### Explicit Non-goals

- `<本契约不请求或不能证明的结果>`
- `<明确不涉及的数据域、生命周期或副作用>`
- 不授权 UI 直接修改任何 Domain 事实。
- 不授权 UI 直接访问任何存储。
- 不授权 UI 直接调用任何 Worker。

## Input

本节只定义逻辑输入语义，不定义业务字段、数据结构、API、传输位置或序列化形式。

### Intent Semantics

- 意图含义：`<待填写>`
- 适用范围：`<待填写>`
- 明确不包含的意图：`<待填写>`
- Application Layer 可以进行的非权威完整性提示：`<待填写>`
- V5 必须重新验证的授权、前置条件和当前事实：`<待填写>`
- UI 不得自行推断的 Domain 事实：`<待填写>`

UI 校验只用于改善交互。V5 Core OS 对公开边界验证负责；任何 Domain 事实是否可以改变，仍由获批权威责任和契约裁决。

### Context Provenance

- 用户输入或选择的来源：`<待填写>`
- V5 视图或上下文的来源与时效：`<待填写>`
- 陈旧、缺失或互相冲突的上下文如何处理：`<待填写>`
- 禁止携带的敏感信息或内部实现引用：`<待填写>`

### Identifier Applicability

| 标识符 | 适用条件 | Input 责任 | 禁止解释 |
| --- | --- | --- | --- |
| Request ID | 交互构成一次可关联请求时适用 | Application Layer 确保进入调用边界时已有有效请求关联；沿同一请求保持语义 | 不表示意图被接受、执行完成、身份或授权 |
| Trace ID | 已存在追踪上下文或该交互被纳入追踪时适用 | 传播既有 Trace ID；不适用时不得由 Request ID 推导或伪造 | 不表示业务身份、请求身份或执行结果 |
| Project ID | 意图明确属于一个已识别 Project 上下文时适用 | 只传播权威来源提供的既有 Project ID | 不表示项目所有权、成员关系或访问许可 |
| Asset ID | 意图明确引用一个已识别 Asset 时适用 | 只传播既有 Asset ID；身份尚未建立时保持不适用 | 不表示内容、版本、存储位置或修改权 |
| Job ID | 意图属于或引用一个已识别 Job 上下文时适用 | 只传播既有 Job ID；尚未建立时保持不适用 | 不表示 Job 状态、Worker、重试次数或控制权 |

统一规则：

1. 只传播已存在、适用且来源明确的 ID。
2. 不适用的 ID 不使用空含义、固定值或其他 ID 占位。
3. 五类 ID 均为不透明关联信息，不能相互推导，也不构成认证或授权。
4. 若获批结果首次权威建立某个关联身份，具体契约实例必须说明由哪个已批准责任边界返回该身份；本模板不分配该责任。

### Idempotency Declaration

- 是否声明幂等：`<是 / 否 / 条件性；不得留空>`
- 何种重复被视为同一逻辑意图：`<待填写>`
- 重复提交的可观察效果：`<待填写>`
- 幂等适用边界和限制：`<待填写>`
- 结果未知时的安全行为：`<待填写>`

使用同一个 ID 本身不能证明幂等。本模板不规定幂等键、缓存、锁、存储或去重机制。

## Output

本节定义 Application Layer 可以依赖的可观察结果语义，不暴露 V5 或任何下层的内部表示。

### Acknowledgement vs. Authoritative Outcome

- V5 收到或接受评估意图的含义：`<待填写>`
- 上述含义是否等于权威结果完成：`<待填写，必须明确区分>`
- 权威结果可被 Application Layer 观察的条件：`<待填写>`
- 结果暂时未知或不可判定时的稳定语义：`<待填写>`
- 部分完成是否适用及其安全含义：`<待填写或经批准的 N/A>`

本文不选择同步、异步、推送、轮询或其他交互机制。具体契约只说明语义，不描述下游执行步骤。

### Observable Result

- 成功判定：`<待填写>`
- Application Layer 可以稳定依赖的结果：`<待填写>`
- Application Layer 必须继续视为未知或非权威的内容：`<待填写>`
- UI 本地草稿、暂存显示或乐观呈现如何与已确认结果区分：`<待填写>`

UI 只能依据 V5 的公开结果更新已确认呈现，不能根据页面状态、超时、Worker 迹象或存储变化推断 Domain 事实已经改变。

### Identifier Propagation

- Output 必须保留所有已存在且仍适用的 Request ID、Trace ID、Project ID、Asset ID 和 Job ID。
- V5 不得静默替换、合并或改变标识符语义。
- 新建立的适用身份只能由获批责任边界通过 V5 公开结果返回；UI 不得自行生成 Domain 身份。

## Error

错误语义必须遵守 [错误码与错误语义标准](../04-interface-contract/error-code-standard.md)。本模板不定义具体错误码、异常类型或 HTTP/gRPC 映射。

### Error Semantics

- 稳定错误语义：`<待填写>`
- 责任边界：`<待填写>`
- 安全 Message 与允许披露的 Details：`<待填写>`
- Application Layer 可采取的动作：`<待填写>`
- 结果是否可能已经部分或未知地生效：`<待填写>`
- 关联缺陷、风险或补偿责任：`<待填写或无>`

错误必须保留适用的 Request ID、Trace ID、Project ID、Asset ID 和 Job ID。错误信息不得暴露存储结构、Worker、下层拓扑、堆栈、路径、凭据或敏感数据。

### Retry Boundary

- UI 只有在 V5 返回的稳定 Retry Guidance 明确允许时才能重新提交。
- Retry Guidance 必须说明不可重试、仅满足哪些条件后可重试，或调用方不得自行判断。
- 结果未知时不得自动重试，除非具体契约已定义幂等语义和安全恢复条件。
- 重试只能再次通过同一获批 Application → V5 公开契约进行。
- 重试不得变成 UI 对 Domain 的直接补偿、对存储的修复或对 Worker 的再次调用。
- 本模板不规定次数、间隔、算法、队列或重试产品。

## Ownership

### Application Layer

- 负责准确捕获用户意图、传播适用上下文、区分本地草稿与 V5 已确认结果，并安全呈现错误。
- 只拥有页面导航、选择、筛选、未提交草稿和交互反馈等临时呈现状态。
- 不拥有本契约引用的 Identity、Project、Asset、Production、Render、Business 或 Intelligence 事实。

### V5 Core OS Public Boundary

- 负责公开 Command Intent 语义、边界验证、兼容性、可观察结果与错误封装。
- 若需要下层能力，只能沿 V2.3 已批准的相邻公开契约承接；本模板不描述或批准任何下游步骤。
- V5 提供统一入口不表示 V5 自动拥有被引用的数据域或 Domain 事实。

### Domain Authority

- Domain 事实的最终裁决、有效变化和生命周期责任只能来自独立获批的所有权记录与契约。
- UI 提交意图、V5 接受意图或关联 ID 存在，都不能替代权威 owner 的决定。
- 本模板不分配 owner、不创建实体，也不定义写入实现。

### Explicitly Forbidden

1. **UI 不得直接修改 Domain 事实**：包括通过本地状态、私有实现、脚本或隐藏通道形成事实变化。
2. **UI 不得直接访问存储**：包括数据库、文件、对象存储、缓存、索引或共享持久化结构。
3. **UI 不得直接调用 Worker**：包括执行器、队列消费者、渲染单元、计算任务或任何下层运行组件。

任何 UI → V4 Platform、V3 Render Core、Compute、Foundation 或其私有实现的直接依赖同样禁止。

## Compatibility

### Stable Semantics

具体契约实例必须明确哪些意图、前置条件、结果、错误、标识符和 Retry Guidance 是 Application Layer 可以依赖的稳定承诺。

### Change Classification

- 只修改说明文字且不改变语义的变更，应保留审计历史。
- 改变意图含义、适用范围、授权条件、成功判定、错误语义、ID 适用性、幂等或 Retry Guidance，必须进行兼容性评估。
- 不能让既有 Application Layer 安全解释的变化属于不兼容变化，必须建立可区分的新语义版本和迁移计划。
- 增加可选语义也必须评估旧 UI 是否会误判、忽略安全限制或产生不同结果，不能默认兼容。

### Deprecation and Migration

- 废弃必须说明替代契约、影响页面、过渡期、停止新增使用的条件和关闭证据。
- 旧契约在迁移完成前保持其既有语义，不能原地改写。
- 实质变化必须重新执行 Contract 验证，并评估 UI 页面、错误处理和证据的适用性。
- 任何兼容性变化都不能借机新增业务命令、API、数据 owner、跨层依赖或 V2.3 模块职责。

## Security and Minimal Disclosure

- UI 只提交评估意图所需的最少信息，不传递凭据、令牌、内部引用、未授权个人信息或生产敏感数据。
- V5 返回的结果和错误遵循最小披露；关联 ID 不能作为授权证明。
- UI 不得根据页面可见性、按钮状态或缓存内容跳过 V5 的权威验证。
- 本地草稿若包含敏感内容，必须受适用治理约束；本文不选择保存机制。

## Verification and Approval

具体契约实例获准前必须确认：

- Purpose、Input、Output、Error、Ownership 和 Compatibility 均已完整填写。
- 五类 ID 的适用与不适用条件明确，且不存在伪造或相互推导。
- 错误、幂等、结果未知与 Retry Boundary 具有稳定、可验证语义。
- Application Layer 只依赖 V5 公开契约。
- 不存在 UI 直接修改 Domain、访问存储或调用 Worker 的路径。
- 没有具体业务命令、业务字段、API、下游步骤、数据库、框架或部署实现。
- Contract 证据覆盖成功、拒绝、未知结果、重复提交、陈旧上下文和适用失败边界。
- 架构、接口、数据、安全、测试和双方责任人已完成所需评审。

| 审批角色 | 责任人 | 结论 | 日期 | 备注 |
| --- | --- | --- | --- | --- |
| Application Layer | `<待填写>` | `<批准 / 拒绝>` | `<待填写>` | `<待填写>` |
| V5 Core OS | `<待填写>` | `<批准 / 拒绝>` | `<待填写>` | `<待填写>` |
| 架构 / 接口 / 数据 | `<待填写>` | `<批准 / 拒绝 / N/A>` | `<待填写>` | `<待填写>` |
| 安全 / 测试 | `<待填写>` | `<批准 / 拒绝 / N/A>` | `<待填写>` | `<待填写>` |

模板和占位内容没有实现效力。只有具体契约实例在完整评审后进入 `Accepted`，Application Layer 才能在其严格范围内向 V5 提交相应 Command Intent。
