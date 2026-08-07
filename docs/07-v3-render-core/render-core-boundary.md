# V3 Render Core Boundary

> 状态：Phase 1 技术无关边界评审；不代表具体接口、模块或实现已经获批。

## 1. 目的与适用范围

本文定义 V3 Render Core 在第一条 Phase 1 Vertical Slice 中可承担的最小边界责任，说明它如何接收 Render Request、形成 Render Result，并与 Project、Production Intent、Shot、Asset Return 及 Compute 保持职责隔离。

本文与 [V5–V3 Vertical Slice Review](../04-interface-contract/v5-v3-vertical-slice-review.md)配套。端到端评审名称不创建 V5–V3 直接契约；V3 的唯一上游调用方仍是 V4 Platform，其唯一可评审下游方向仍是 Compute。

## 2. V2.3 位置与依赖不变量

```text
V5 Core OS → V4 Platform → V3 Render Core → Compute
```

| 不变量 | V3 边界要求 |
| --- | --- |
| 上游 | 只接受 V4 Platform 通过获批 V4–V3 公开契约提交的输入 |
| 下游 | 只通过获批 V3–Compute 公开契约表达计算需求 |
| 返回 | 结果和错误返回 V4；不得直接调用、回调、发事件或写入 V5 |
| 封装 | 不暴露 V3/Compute 内部对象、异常、资源、供应商或执行步骤 |
| 数据 | 不因接触 Project、Production、Shot、Asset 或 Render 语义而自动取得数据所有权 |
| 中介 | 不假设 V4 Stub 是透明代理、编排器或永久 V4 实现 |

上述约束沿用 [V4–V3 契约模板](../04-interface-contract/v4-v3-contract.md)、[V3–Compute 契约模板](../04-interface-contract/v3-compute-contract.md)和 [Phase 1 Production Validation Plan](../12-release/phase-1-production-validation-plan.md)。

## 3. V3 职责

V3 负责：

1. 解释 V4–V3 具体契约批准的 Render Request 语义。
2. 验证 V3 边界可判断的完整性、支持范围与前置条件。
3. 保持 Request ID、Trace ID 以及适用 Project ID、Asset ID 的关联语义。
4. 将上层 Project、Production Intent 与 Shot 只视为 render-facing 上下文，不重定义其核心含义。
5. 如需下层能力，只经 V3–Compute 公开契约表达需求，不暴露上层内部语义或 V3 私有实现。
6. 形成 V4 可以稳定消费的 Render Result 或 Error。
7. 对未知、部分或失败结果保持明确边界，不制造成功或 Asset 事实。

V3 不负责：

- 创建、查询或修改上游 Project、Asset 权威事实或 Project-Asset Relationship；
- 定义完整 Production Intent、Shot 实体、业务 Workflow 或生命周期；
- 选择 Asset 权威版本、推断内容位置、验证 Ownership、Rights 或 Permission；
- 直接创建 Asset ID、Asset Version 或向 Asset Registry 写入结果；
- 创建 Job、Job 状态机、队列、Worker、调度器、重试器或取消系统；
- 选择数据库、存储、渲染引擎、AI 模型、资源、格式、协议或部署技术；
- 直接调用 V5、Application Layer、Foundation 或 V4 私有实现。

## 4. Render Request 输入边界

Render Request 是 **V4 → V3** 公开输入语义，不是 V5 与 V3 共享的对象。V5 只向 V4 提交 Production Intent 的获批下游投影；V4 如何验证、裁剪或映射为 Render Request，必须由两条相邻具体契约分别说明。

### 4.1 V3 可要求的语义类别

| 类别 | V3 可依赖的最小含义 | V3 不得推断 |
| --- | --- | --- |
| 关联上下文 | 本次请求的 Request ID、Trace ID 与适用 Project 关联 | 身份、权限、执行状态或幂等 |
| Render Intent | 已经由相邻边界形成的渲染相关目标与约束 | 完整 Production 规则、UI 状态或 Workflow |
| Shot Context | 用于组织本次渲染输入和输出的概念上下文 | Shot 实体、Shot ID、时间线位置或状态 |
| Asset References | 本次请求引用的既有 Asset 身份 | 版本、路径、格式、内容可用性、Rights 或 Permission |
| Output Expectations | V3 可以验证的结果目标和限制 | 具体引擎、资源、供应商或 Compute 指令 |
| Contract Context | 当前获批契约、兼容范围和未知语义处理要求 | V4 私有默认值或未来行为 |

上表不定义字段、必填性、数据结构或传输方式。具体 V4–V3 契约必须说明每类语义何时必需、条件适用、未知、拒绝或不适用。

### 4.2 输入拒绝边界

V3 必须能够按获批错误契约拒绝以下类型的输入，但本文不登记具体 Error Code：

- 缺少契约声明为必要的关联或渲染语义；
- 提供无法安全解释、冲突或超出获批范围的语义；
- Asset 只具有 ID，但精确版本、内容物化或完整性前置条件未满足；
- 请求要求 V3 承担上层业务判断、权限决定或未获批下层能力；
- 契约版本或兼容条件无法满足。

拒绝不证明 Project 或 Asset 不存在，也不授权 V3 暴露内部拓扑或敏感原因。

## 5. Render Result 输出边界

Render Result 是 V3 通过 V4–V3 Output/Error 返回的稳定可观察语义。它必须与 V3 私有执行细节、Compute 结果和权威 Asset 事实区分。

V3 的结果边界应能够表达：

- 与原 Render Request 对应的适用关联上下文；
- 是否存在可供下一边界评估的输出候选；
- 输出候选的最小、不透明引用或证据类别；
- 契约允许披露的限制、警示或未知内容；
- 没有形成候选时的稳定 Error 与调用方动作。

本文不选择成功枚举、状态字段、文件格式、存储地址、结果数量、同步或异步机制。收到 Render Result 不表示结果已经持久化、验证、可用、具有 Asset ID 或符合业务接纳条件。

V3 不得向上返回：

- Compute 或供应商原始对象、内部异常、堆栈或资源拓扑；
- 文件路径、凭据、内部存储地址或未批准的敏感内容；
- V5、Project、Production、Asset 或权限事实的推断；
- 虚构 Asset ID、Job ID、完成状态或重试许可。

## 6. Project、Production Intent 与 Shot 边界

| 上层概念 | V3 如何使用 | V3 必须保持的隔离 |
| --- | --- | --- |
| Project | 仅用于关联 Render Request 与 Render Result 的项目语境 | 不查询 Project Engine，不修改生命周期，不从 Project ID 推断权限 |
| Production Intent | 只消费经 V4–V3 契约形成的 render-facing 投影 | 不接管完整 Production 意图、业务规则、审批或状态 |
| Shot | 只消费渲染所需的概念上下文 | 当前不得假设 Shot 模型、Shot ID、版本、顺序或状态已存在 |

Shot 的身份、责任与兼容规则尚未确定，是 Render Request 具体契约前必须关闭的 Open Question。

## 7. Asset 输入与 Asset Return 边界

### 7.1 输入 Asset

- V3 接收的是 V4–V3 契约中的 Asset 引用语义，不是上游 Asset 权威边界的内部模型或存储对象。
- Asset ID 只提供身份关联，不提供版本、内容、路径、格式、权限或可渲染性。
- V3 不选择“初始”“当前”或“最新”版本；精确版本必须由获批上游责任和契约明确。
- 内容如何安全、完整地提供给 Render 属于未决边界；不得通过共享数据库、路径、URL 或私有存储耦合绕过。
- V3 不修改输入 Asset，也不因处理它而取得 Asset 权威所有权。

### 7.2 Asset Return

- V3 只形成 Render Result 候选，并经 V4 返回 V5 侧。
- Render Result 在被具有获批所有权记录的 Asset 权威责任边界接纳前不是 Asset；本文不分配该权威 owner。
- V3 不创建或分配结果 Asset ID，不写入 Asset Registry，不选择新 Asset 或新版本。
- 结果数量、身份建立、接纳、版本、Project 关系和失败处理必须由后续具体契约批准。
- 需要保留输入、请求、结果与最终 Asset 的可追溯关系，但 Trace ID 或时间信息不能替代 Provenance 证据。

完整端到端步骤见 [Vertical Slice Review](../04-interface-contract/v5-v3-vertical-slice-review.md#7-asset-如何进入-render) 与 [Render 结果返回](../04-interface-contract/v5-v3-vertical-slice-review.md#8-render-结果如何进入-asset-体系)。

## 8. Error 与关联责任

- 错误遵守 [错误码标准](../04-interface-contract/error-code-standard.md)，具体契约分别定义错误语义、责任、Retry Guidance、部分或未知结果。
- V3 保留所有已存在且仍适用的 Request ID、Trace ID、Project ID 与 Asset ID，不生成无意义占位。
- 关联 ID 不构成身份、授权、Job、状态、幂等、版本或存在性证明。
- V3 的内部诊断与对外安全错误分离；V4 必须把 V4–V3 错误翻译为 V5–V4 契约自身拥有的错误语义。任何信息收敛必须显式，不得伪造原因或透传 V3/Compute 错误对象。
- 结果未知时不得自动重试或宣称回滚；重试、超时、取消和补偿必须由后续契约定义。

## 9. 边界验收条件

V3 Vertical Slice 候选进入实现前，至少需要：

1. `P1-PV-G01 Authorization` 已通过：Phase 0 已正式退出或存在获批且有期限的例外，Phase 1 范围、责任与验收已获授权。
2. V4–V3 具体契约完整定义 Purpose、Input、Output、Error、Ownership、兼容与验证责任。
3. Shot、Asset Version、内容物化、Render Result 与 Asset Return 的阻断问题已关闭，Asset 权威责任边界具有获批所有权记录。
4. V4 Stub 已由独立实现任务授权，其范围、位置、运行边界、所有者、生命周期、停止与移除条件已批准。
5. 具体 V3–Compute 契约已经批准且最小公开边界可验证，并且没有泄漏到 V4–V3 契约。
6. 正常、拒绝、部分、未知和失败语义具有风险相称的 Contract 证据计划。
7. 与 V4 Stub、Compute 的 Integration 以及纵向 E2E 计划引用已批准契约，不以测试代替设计。
8. Phase 1 关闭记录明确 V4 Stub 被移除、继续隔离观察或等待获批实现替换；继续使用具备责任人、期限、风险接受和独立授权。
9. 未出现 V5 直连、反向依赖、共享状态、共享存储或私有实现耦合。

## 10. V3 Open Questions

以下问题由 [Vertical Slice Review 的 Open Questions](../04-interface-contract/v5-v3-vertical-slice-review.md#11-open-questions)统一跟踪；V3 边界特别依赖：

- V3 可验证的 Render Request 最小语义和拒绝边界是什么？
- Shot 是否需要稳定身份，V3 可见多少 Shot 上下文？
- 精确 Asset Version 与内容物化责任如何建立？
- Render Result 的稳定身份、候选数量、限制和未知结果如何表达？
- V4 对 V3 Output/Error 如何执行最小披露映射而不改写含义？
- V3–Compute 提供哪些已批准、可停止且可验证的公开能力？
- 同步或异步、幂等、重试、超时和取消如何由相邻契约表达？
- 哪些 Contract、Integration、E2E、安全与可观测性证据构成实现 Gate？

## 11. 明确非目标

本文不创建代码、数据库、API 实现、Job 系统、Worker、队列、状态机、存储、渲染引擎、Compute 实现、部署拓扑、业务 Workflow、权限系统、数据所有权记录、ADR 或 V2.3 架构变更。
