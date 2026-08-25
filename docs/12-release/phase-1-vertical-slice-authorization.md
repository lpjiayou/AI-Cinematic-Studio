# Phase 1 Vertical Slice Authorization Review

> Applicability notice — `2026-08-25`
>
> 本文正文是 `2026-08-06` 的 `REVIEW INPUT / NOT ACCEPTED` 时点记录，不得
> 静默改写。其 X2/K2 与 Implementation 状态表不覆盖后续精确决定。当前唯一
> K2-002 non-GPU repository work package 仅由
> [ACS-K2-002 Non-GPU Preproduction Governance Rebaseline](../../governance/ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md)
> 授权；本文继续约束其 V2.3 相邻依赖、无重复 authority、无 live production、
> 无 Provider/GPU、无 Release/Publication 等通用边界。

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-P1-007` |
| 架构基线 | AI Cinematic Studio `V2.3` |
| 前置评审 | `ACS-P1-006` Phase 1 V5–V3 Vertical Slice Architecture Review |
| 文档状态 | `REVIEW INPUT / NOT ACCEPTED`；不是开工、集成、Release 或 Production Validation 批准 |
| Scope Decision | `APPROVED — MAXIMUM REVIEW ENVELOPE`：由 [Phase 1 Scope Approval](phase-1-scope-approval.md) 在 Commit `67986f9c6f7cb92335122a7a63446b4afdb5c375` 作出；本文件仍是未接受的评审输入 |
| Effective Status | `BLOCKED`：Phase 0 Exit 与 Scope 条件已满足，但 G01 所需 Person Assignment、责任接受、风险 owner / 接受及完整审批记录尚未闭合 |
| Execution Authorization | `NOT GRANTED` |
| Integration Authorization | `NOT GRANTED` |
| Release Authorization | `NOT GRANTED` |
| Production Validation Authorization | `NOT GRANTED` |

本文件细化 Phase 1 第一条 Vertical Slice 的**实现授权评审边界**：说明后续实现提案在已批准最大评审包络内最多可以覆盖什么、必须按什么顺序进入评审、由哪些 Gate 阻止越界。它本身仍未被接受，不创建代码、V4 Stub、API、数据库、候选、环境或 Release，也不替代实际授权记录或具体实现工作项的审批。

权威依据包括 [Phase 0 Exit Record](phase-0-exit-record.md)、[Phase 1 Scope Approval](phase-1-scope-approval.md)、[Phase 1 Production Validation Plan](phase-1-production-validation-plan.md)、[V5–V3 Vertical Slice Review](../04-interface-contract/v5-v3-vertical-slice-review.md)、[V3 Render Core Boundary](../07-v3-render-core/render-core-boundary.md)、[系统上下文](../../architecture/system-context.md)、[层级依赖图](../../architecture/dependency-map.md)、[架构变更流程](../../governance/ARCHITECTURE_CHANGE_PROCESS.md)、[Phase 1 验证 Gate](../11-testing/verification-gates.md)、[测试证据标准](../11-testing/test-evidence-standard.md)与[完成定义](../../governance/DEFINITION_OF_DONE.md)。

必须保持的生产依赖方向为：

```text
Application Layer
       ↓
V5 Core OS
       ↓
V4 Platform（Phase 1 仅允许受控 V4 Stub Profile）
       ↓
V3 Render Core
       ↓
Compute
```

结果和错误只能沿各自相邻契约逐层返回。返回信息不形成反向生产依赖；任何回调、事件、轮询、共享状态或其他机制也不能绕过上述方向。`Foundation` 不在本次 Slice 授权内；若 Compute 需要该边界，必须另行授权具体 `Compute → Foundation` 契约和工作项。

## 1. Vertical Slice 目标

本 Slice 的当前目标是为已批准最大评审包络中的 Internal Content Lab X2 主验证轨道，建立最小、可停止、可追溯的 Application 至 Compute 内容生产语义闭环，并形成风险相称的分层证据。K2 只保留为受限次实验，当前不在实现授权包络内。

拟议包络内可以编制并提交评审的端到端语义仅包括：

1. Application Layer 通过公开边界表达获批的 View Request 或 Command Intent。
2. V5 Core OS 保持上层 Project、Production Intent、Shot 与 Asset 关联语义，并形成最小 V5–V4 投影。
3. V4 Stub 只按两条独立相邻契约保持、裁剪或翻译获批语义。
4. V3 Render Core 接收 Render Request，形成 Render Result 或 Error，并只通过获批 V3–Compute 契约表达下层计算需求。
5. Compute 返回最小、稳定且可观察的结果或失败语义。
6. Render Result 候选经相邻契约返回；在获批 Asset 权威责任边界接纳前，不得被声明为 Asset 事实。

K2 与 X2 当前仍只是验证轨道标签。本文件不定义其业务、模型、数据、质量、技术或商业含义；X2 是主实验方向，K2 是受限次实验且当前 `IMPLEMENTATION NOT AUTHORIZED`。任一轨道没有独立批准记录时，不能据其名称启动实现。在 Phase 1 Plan 被正式修改前，其 K2/X2 双轨退出要求仍有效；该遗留要求必须在 G02 正式协调，不能被解释为当前 K2 实现许可。

## 2. Application 范围

拟议 Application 范围上限是现有 Application Layer 中的受控 Internal Content Lab 验证 Profile，不创建新的 V2.3 模块、应用层级或长期产品形态。

| 授权维度 | 范围边界 |
| --- | --- |
| 可进入工作项准备 | 选择已批准的 Project 与 Asset 公开引用；形成获批 View Request 或 Command Intent；只向 V5 公开契约提交；展示 V5 返回的稳定 Output、Error、限制和未知状态 |
| 页面上限 | 只能从既有 Dashboard、Project Workspace、Asset Library、Production Flow、Review Workspace 设计范围中选择轨道实际所需的最小子集；本文件不授权实现全部页面或新增页面 |
| 状态边界 | 只维护导航、选择、草稿、等待、失败提示等非权威 UI 状态；提交、接收或本地显示均不等于 Domain 事实已改变 |
| 标识边界 | 按适用性保持 Request ID、Trace ID、Project ID、Asset ID 与 Job ID；不适用标识不得伪造，标识不得被解释为权限、所有权或状态 |
| 证据要求 | Application–V5 Contract、范围核对、失败与未知呈现、关联连续性、无跨层依赖及适用 Unit/Contract 证据 |

Application 明确不得：

- 直接修改 Project、Asset、Production、Render 或其他 Domain 事实；
- 直接访问数据库、文件、对象存储、缓存、索引或任何存储抽象；
- 直接发现、启动、重试、取消或控制 Worker、Job、V3 或 Compute；
- 绕过 V5 直接调用 V4、V3、Compute 或 Foundation；
- 从 V3、Compute 或 V4 Stub 私有状态推断完成、失败或重试许可；
- 定义 API 端点、DTO、Payload、协议、组件、路由或技术栈。

## 3. V5 范围

拟议 V5 范围上限是 Vertical Slice 所需的最小公开行为，不扩张为完整 V5 Core OS，不新增内部模块，也不改变既有 Identity、Project、Asset Registry 或 Project-Asset Relationship 基础能力的当前边界。

| 授权维度 | 范围边界 |
| --- | --- |
| Application 输入 | 只接收获批 K2/X2 轨道通过 Application–V5 契约提交的最小上下文；对缺失、冲突或超出范围的语义形成稳定失败 |
| 上层语义 | 保持正式契约允许的 Project、Production Intent、Shot 和输入 Asset 关联；不把内部对象下传 |
| V4 输出 | 形成 V5–V4 契约批准的最小 render-facing 投影；只依赖 V4 公开边界 |
| 返回处理 | 只消费 V5–V4 契约拥有的 Output/Error，保持关联与限制；Render Result 只作为候选返回，不自动成为 Asset |
| 既有能力 | 任何既有 V5 基础能力只能在独立实现工作项明确引用当前公开行为后参与；本授权不自动批准跨 Engine 集成或能力扩展 |
| 证据要求 | V5 单元边界、Application–V5 与 V5–V4 Contract、错误翻译、关联连续性、范围拒绝和无 V3 直连证据 |

V5 明确不得：

- 直接调用、导入或了解 V3 Render Core、Compute 或 Foundation 私有实现；
- 创建新的 Production、Shot、Workflow、Job、Render、Rights、Permission 或 Provenance 模块；
- 把 Render Request 定义为跨 V5–V3 共享对象，或复用同一 DTO 穿越两条契约；
- 选择渲染引擎、资源、Worker、队列、存储、Asset 物化方式或 Compute 执行步骤；
- 因层级位置自动取得 Project、Production、Asset 或 Render 数据权威所有权；
- 在所有权记录缺失时接纳、登记或关联输出 Asset 事实。

## 4. V4 Stub 范围

V4 Stub 是 V4 Platform 既有架构位置中的临时验证 Profile，不是新模块、完整 V4 Platform、通用代理、编排器或永久服务。

| 授权维度 | 范围边界 |
| --- | --- |
| 前置授权 | 实际 Stub 必须由独立实现工作项批准，并记录位置、运行边界、owner、适用轨道、期限和停止条件 |
| V5 侧 | 只接受获批 V5–V4 契约语义，不依赖 V5 私有实现 |
| V3 侧 | 只通过独立 V4–V3 契约调用 V3，不共享 V5 内部模型 |
| 映射责任 | 只执行两条具体契约明确批准的验证、保持、裁剪或翻译；不得由 Stub 自行补充业务默认值 |
| Error 边界 | 将 V4–V3 Error 翻译为 V5–V4 契约自身拥有的错误语义；收敛必须显式，不透传 V3/Compute 私有错误对象 |
| 证据要求 | 两侧 Contract、可识别 Stub 标记、确定性行为、无长期状态、无旁路、停止与移除证据 |

V4 Stub 明确不得：

- 成为 Project、Production Intent、Shot、Asset、Render Request 或 Render Result 的权威来源；
- 持有长期业务状态、调度状态、持久化、缓存真源、权限判断或业务规则；
- 直连 Application、Compute 或 Foundation；
- 通过共享数据库、共享 DTO、文件、事件旁路或私有导入连接 V5 与 V3；
- 因候选通过而获得永久生产地位。

Phase 1 关闭记录必须明确 Stub 被移除、继续隔离观察，或等待另行获批的 V4 实现替换。任何继续使用必须具有责任人、期限、风险接受和独立授权。

## 5. V3 Render MVP 范围

拟议 V3 Render MVP 范围上限是 P1-006 定义的最小 Render Core 边界，不授权完整渲染管线、引擎、工作流或执行平台。

| 授权维度 | 范围边界 |
| --- | --- |
| 输入边界 | 只接受 V4 通过获批 V4–V3 契约提交的 Render Request；Project、Shot 与 Asset 只作为契约允许的不透明关联或 render-facing 上下文 |
| 验证责任 | 只验证 V3 边界可以判断的完整性、支持范围、契约版本和前置条件 |
| Compute 边界 | 只有具体 V3–Compute 契约获批后，才能通过该相邻公开边界表达最小计算需求 |
| 输出边界 | 向 V4 返回稳定 Render Result 或 Error；封装 V3 和 Compute 内部表示，并明确候选、部分、失败或未知边界 |
| Asset 边界 | 不选择 Asset 权威版本，不推断内容位置，不写 Asset Registry；结果在获批 Asset 权威边界接纳前不是 Asset |
| 证据要求 | V4–V3 与 V3–Compute Contract、输入拒绝、结果与错误、关联连续性、封装及适用 Unit/Integration 证据 |

V3 明确不得：

- 直接调用、回调、发事件或写入 V5 或 Application；
- 创建 Job 系统、Worker、队列、调度器、重试器、取消系统或状态机；
- 创建数据库、持久化、Storage Adapter、文件路径、对象地址或共享存储耦合；
- 选择渲染引擎、模型、格式、GPU、供应商、资源规格或部署拓扑；
- 创建或分配结果 Asset ID、选择新 Asset 或新版本、验证 Rights/Permission，或实现 Provenance Ledger；
- 将 Phase 1 MVP 解释为 V3 Render Core 的最终责任清单。

## 6. Compute 范围

拟议 Compute 范围上限是 V3 Render Core 下游的最小、公开、可停止计算边界，不获得 Render、Job、Asset 或其他数据域的自动所有权。

| 授权维度 | 范围边界 |
| --- | --- |
| 输入边界 | 只接受 V3 通过具体获批 V3–Compute 契约提交的最小工作语义 |
| 输出边界 | 返回契约允许的可观察接收、结果或失败语义；不向上泄漏内部资源或供应商表示 |
| 关联边界 | 保持适用 Request ID、Trace ID、Project ID、Asset ID 与 Job ID；Job ID 适用性不创建 Job 系统 |
| 安全边界 | 支持获批停止条件、失败隔离和恢复前置验证，不制造自动重试或成功事实 |
| Foundation 边界 | 本 Slice 不授权 Compute–Foundation 实现；实际需要时必须另行批准具体契约和工作项 |
| 证据要求 | V3–Compute Contract、正常与失败结果、停止条件、关联连续性、封装和适用 Unit/Integration 证据 |

Compute 明确不得：

- 反向依赖或调用 V3、V4、V5 或 Application；
- 创建调度平台、队列、Worker、资源管理、容量、弹性、成本或可用性承诺；
- 选择计算框架、执行引擎、硬件、云服务、模型供应商或部署技术；
- 创建数据库、作业表、资源表、存储结构或数据访问层；
- 在未获独立授权时引入 Foundation 实现或依赖。

## 7. 禁止范围

本任务本身以及本文件提出的范围包络，均不创建或批准：

1. 任何代码、测试代码、V4 Stub 实现、API 实现、服务实现、脚本、配置、CI/CD、基础设施、环境或部署。
2. API 端点、DTO、Payload、序列化 Schema、协议、事件实现、Callback、Webhook、轮询机制或消息系统。
3. 数据库、SQL Schema、表、字段、索引、ORM、迁移、数据访问代码或具体存储产品。
4. 新的 V2.3 层级、模块、服务、职责、数据域、数据 owner、物理目录映射或依赖方向。
5. Application 绕过 V5、V5 绕过 V4、V4 绕过 V3、V3 绕过 Compute，以及任何反向、循环或私有实现依赖。
6. V5–V3 直接契约、共享 DTO、共享数据库、共享状态或绕过 V4 的事件通道。
7. Job 系统、Worker、队列、调度、工作流、状态机、补偿系统、自动重试或取消系统。
8. 完整 Application 产品、完整 V5 Core OS、完整 V4 Platform、完整 V3 Render Core 或完整 Compute 平台。
9. K2/X2 的业务定义、模型、内容类型、数据集、质量阈值、性能指标或商业语义。
10. Rights、Permission、RBAC、OAuth、SSO、Billing、Tenant、Provenance、Recommendation 或其他未授权能力。
11. 数据库、框架、语言、协议、渲染引擎、模型、GPU、供应商、云平台、可观测性产品或测试框架选型。
12. Foundation 的新增实现、数据设施、组件或职责变化。
13. 真实用户流量、未授权敏感数据、不可逆业务副作用、外部客户 Release、规模化生产或商业化活动。
14. 用本授权文件、Gate、测试、Stub 或 MVP 标签追认未批准的实现或架构变化。

## 8. 实现顺序

以下是**准入顺序**，不是排期，也不构成任何步骤的自动开工许可。每一步都必须有独立责任人、工作项、验收标准和适用 Gate 结论。

| 顺序 | 进入条件 | 可编制并提交评审的工作 | 退出条件 |
| --- | --- | --- | --- |
| 1. 阶段与范围授权 | Phase 0 正式退出与最大范围包络已记录；项目、架构、验收与风险责任仍须完成指派和接受 | 确认本 Slice 目标、排除项、角色、验收人与风险接受权限 | `P1-PV-G01` 实际为 `PASS`；本文件不能自行标记 |
| 2. 轨道与阻断问题关闭 | G01 通过 | 冻结并批准 X2 主轨道；记录 K2 受限次轨道边界；正式协调既有双轨退出要求与 X2-first 顺序；按 [P1-006 Open Questions](../04-interface-contract/v5-v3-vertical-slice-review.md#11-open-questions)关闭与当前轨道相关的问题 | G02 通过；不得由实现默认值代替答案，也不得据此启动 K2 实现 |
| 3. 架构与所有权复核 | 轨道定义明确 | 复核 V2.3、数据权威、最小披露、依赖和例外需求 | G03 通过；需要 ADR 时必须为 `Accepted` |
| 4. 相邻契约批准 | 架构边界无阻塞 | 分别形成 Application–V5、V5–V4、V4–V3、V3–Compute 具体契约 | G04、G07、G08 的契约前置满足；四条契约无共享内部模型 |
| 5. 独立执行授权 | 契约批准且责任明确 | 为各层候选和 V4 Stub 分别建立文件范围、行为范围、测试与停止条件清晰的实现工作项 | 每个实际工作项获得明确 Execution Authorization |
| 6. 分层候选实现 | 对应工作项已授权 | 在不改变生产依赖方向的前提下，候选就绪可按 `Compute → V3 → V4 Stub → V5 → Application` 顺序推进，并同步形成 Unit/Contract 证据 | 每层 DoD 与适用 G05/G06 证据通过 |
| 7. 相邻集成 | 两侧候选与 Contract 均通过 | 依次验证 V3–Compute、V4–V3、V5–V4、Application–V5；失败语义和关联标识逐边界核对 | 相邻 Integration 证据通过，无反向或跨层通道 |
| 8. 非生产 Vertical Validation | 全部相邻集成通过，受控环境另行获批 | 仅对获得独立授权的轨道执行 E2E、停止、失败、恢复与无副作用验证；当前最大实现申请包络只覆盖 X2，K2 仍未获授权 | G01–G09 全部通过且候选冻结 |
| 9. Release 决策 | 候选、证据、风险与恢复准备完整 | 仅提交 Release Decision Owner 作出 `Proceed / Hold / Exception Approved` 决定 | 只有明确 `Proceed` 加外部授权才可 Release |
| 10. Production Validation 与退出 | 已获批 Release 完成 | 只执行预先批准的安全技术确认，并关闭风险、文档和 Stub 去向 | G11、G12 形成真实证据与终态结论 |

第 6 步的候选就绪顺序是降低集成不确定性的构建顺序，不是运行时依赖方向。运行时仍只能是 `Application → V5 → V4 → V3 → Compute`。独立 Unit 工作是否并行，由具体获批工作项决定；并行不能绕过契约或 Gate。

## 9. Gate 定义

本文件不新建与 Phase 1 计划平行的 Gate。Vertical Slice 必须逐项继承 `P1-PV-G01` 至 `P1-PV-G12`：

| Gate | 对本 Slice 的判定重点 | 最低证据 | 不自动授权 |
| --- | --- | --- | --- |
| `P1-PV-G01 Authorization` | 阶段前置、范围、责任与验收已由有权责任人批准 | Phase 0 Exit；Phase 1 Scope Approval；已接受的授权边界；责任矩阵；验收人与风险接受记录 | 代码、Stub、契约实例或环境 |
| `P1-PV-G02 Track Definition` | K2 与 X2 分别可验证且语义无歧义 | 两份独立轨道定义与批准记录 | 未列明的业务或模型含义 |
| `P1-PV-G03 Architecture` | 候选只沿 V2.3 相邻依赖并无职责漂移 | 架构复核、依赖清单、适用 ADR 或获批 `N/A` | 任何架构例外 |
| `P1-PV-G04 Contract` | 四条具体相邻契约完整、一致、独立 | Purpose、Input、Output、Error、Ownership、兼容与版本证据 | 实现、共享 DTO 或跨层契约 |
| `P1-PV-G05 Scope & DoD` | 各层候选、Stub 与五类 DoD 未超授权 | 交付物映射；代码、测试、文档、审查、验收证据 | Integration、Release 或完整产品能力 |
| `P1-PV-G06 Layered Evidence` | Unit、Contract、Integration、E2E 按风险完成 | Evidence ID、修订、契约版本和实际结果 | 用高层测试替代低层证据 |
| `P1-PV-G07 Traceability` | 适用关联标识连续且未被滥用 | 正常、失败、未知路径的 ID 适用性与连续性 | 身份、权限、所有权或状态推断 |
| `P1-PV-G08 Safety & Data` | 输入、访问、错误披露和副作用获批 | 数据授权、最小披露、安全评审和停止条件 | 真实用户试验或敏感数据扩张 |
| `P1-PV-G09 Candidate & Recovery` | 候选冻结，停止、回退与恢复可信 | 修订映射、候选清单、责任人及复核或演练证据 | Release |
| `P1-PV-G10 Release Decision` | 独立责任人基于证据和风险作出决定 | `Proceed / Hold / Exception Approved` 记录 | Phase 退出、Phase 2 或商业化 |
| `P1-PV-G11 Production Validation` | 仅核对已批准 Release 的安全技术状态 | 目标候选、预批准信号、停止条件与实际结果 | 补做 Unit、Contract、Integration 或 E2E |
| `P1-PV-G12 Phase Exit` | 结论、DoD、风险、责任和 Stub 去向关闭 | 最终 Gate 包与 `Validated / Observation Extended / Rollback Required / Incident Escalated` | Phase 2、外部客户或规模化生产 |

Gate 状态只允许 `PASS / FAIL / BLOCKED / NOT RUN / N/A`；Gate 整体不能为 `N/A`。任何 `FAIL`、未解决 `BLOCKED`、强制 `NOT RUN`、未授权架构变化或未接受的高影响风险都阻止进入下一 Gate。

### 9.1 当前就绪快照

| 项目 | 当前状态 | 依据 |
| --- | --- | --- |
| Scope Boundary | `APPROVED — MAXIMUM REVIEW ENVELOPE / THIS RECORD NOT ACCEPTED` | `ACS-P1-GOV-005` 已批准最大评审包络；本文件仍是未接受评审输入，可以编制并提交契约、责任分配和工作项提案，但不得据此执行 |
| `P1-PV-G01` | `BLOCKED` | Phase 0 Exit 与 Scope 条件已满足，但 Person Assignment、强制责任接受、风险 owner / 接受及完整审批记录尚未闭合 |
| `P1-PV-G02` | `BLOCKED` | X2 主实验、K2 受限次实验的战略顺序已记录，但两条轨道的冻结定义尚未批准，且既有并列退出表述与 X2-first 顺序仍待协调 |
| `P1-PV-G03` | `NOT RUN` | P1-006 提供边界评审证据，但尚不存在可识别实现候选供候选级架构 Gate 验证 |
| `P1-PV-G04` 至 `G12` | `NOT RUN` | 具体契约、实现、环境、证据、候选与 Release 均未由本任务创建 |

因此，本任务完成不等于 `P1-S0 Scope Ready`、Candidate Ready 或 Phase 1 已启动。

## 10. 风险列表

下表是本授权评审的风险视图，不替代 [企业风险登记册](../../governance/RISK_REGISTER.md)。`P1-S0` 退出前，实际风险 owner 必须复核并正式登记；“开放”不表示风险已接受。

| 风险引用 | 风险描述 | 影响 | 概率 | 缓解与验证条件 | 状态 / 责任角色 |
| --- | --- | --- | --- | --- | --- |
| `R-P1-PV-001` | K2/X2 未定义即启动，导致范围和证据不可比较 | 高 | 高 | 分别批准目的、输入、结果、失败、副作用和完成判据；缺失时阻塞 G02 | 开放 / Phase Owner |
| `R-P1-PV-002` | 把 MVP 或本授权解释为完整产品许可 | 高 | 中 | 每层维护纳入/排除与交付物映射；G05 逐项核对 | 开放 / Scope Owner |
| `R-P1-PV-003` | V4 Stub 积累业务逻辑或长期状态并事实永久化 | 高 | 中 | 明确 owner、期限、停止与移除条件；Phase 关闭强制处置 | 开放 / V4 Boundary Owner |
| `R-P1-PV-004` | 为缩短演示路径而绕过 V4 或其他相邻层 | 严重 | 中 | 候选依赖复核；发现旁路立即阻塞 G03 | 开放 / Architecture Owner |
| `R-P1-PV-005` | 契约、Stub、实现与测试语义漂移，测试反向成为契约 | 高 | 中 | 契约先批准；证据绑定契约版本与候选修订 | 开放 / Contract Owners |
| `R-P1-PV-006` | 关联 ID 中断、伪造或被误作授权和状态依据 | 高 | 中 | 逐标识判断适用性并覆盖正常、失败、未知路径；异常阻塞 G07 | 开放 / Validation Owner |
| `R-P1-PV-007` | 使用真实流量、敏感数据或不可逆输入 | 严重 | 低 | 预先批准最小输入、访问和停止条件；异常阻塞 G08 | 开放 / Security & Data Owners |
| `R-P1-PV-008` | 用 Production Validation 补做发布前验证 | 严重 | 中 | G06 完成后才能申请 Release；生产只核对预批准信号 | 开放 / Release Decision Owner |
| `R-P1-PV-009` | 候选变化后继续使用旧证据 | 高 | 中 | 冻结候选；维护修订—契约—Evidence ID 映射；变化后重验 | 开放 / Change Owner |
| `R-P1-PV-010` | 停止、回退或恢复不可执行 | 严重 | 中 | G09/G10 前验证责任、触发条件和恢复可信度 | 开放 / Release Decision Owner |
| `R-P1-PV-011` | 在授权文档中隐含框架、存储、供应商或部署选择 | 高 | 中 | 保持技术中立；具体选型走独立任务和决策流程 | 开放 / Architecture Owner |
| `R-P1-PV-012` | 责任人、验收人或风险接受权限缺失，或由无权人员作出结论 | 高 | 高 | G01 前实名或明确团队责任；空缺即阻塞 | 开放 / Project Owner |
| `R-P1-PV-013` | 从层级或 ID 名称推断数据 owner，形成未批准共享状态 | 高 | 中 | 权威责任必须有独立所有权记录；推断即阻塞 G03/G04 | 开放 / Data Governance Owner |
| `R-P1-PV-014` | 把未来代码、CI、环境或自动化描述当作现有证据 | 高 | 高 | 只接受实际产生且对应候选的证据；不存在即 `NOT RUN` 或 `BLOCKED` | 开放 / Validation Owner |
高或严重残余风险只有项目负责人和对应专项责任人共同批准并设置复核期限后才能接受。风险缓解不能扩大范围、引入技术实现、绕过 Gate 或修改 V2.3。

### 10.1 Open Question 派生风险候选

下列事项来自 P1-006 Open Questions，不是正式风险登记记录，也没有风险接受或关闭效力。实际风险 owner 必须评估后分配唯一 Risk ID，并按风险登记册使用标准状态。

| 候选引用 | Open Question 来源 | 风险候选描述 | 提交正式登记前的控制 | 登记状态 |
| --- | --- | --- | --- | --- |
| `VS-RC-01` | `OQ-03` 至 `OQ-09` | Shot、Asset Version、内容物化、Render Result 与 Asset 权威边界可能被实现默认值替代 | 在对应契约或候选 Gate 前形成获批结论；未关闭不得实现 | 待正式登记 |
| `VS-RC-02` | `OQ-10` 至 `OQ-11` | 同步/异步与幂等问题可能被偷换为 Job、Worker、队列或事件系统 | 机制保持未选；任何方案走独立授权且不得扩大本 Slice | 待正式登记 |

## 11. 授权效力、责任与变更控制

### 11.1 范围决定与本文件效力

[Phase 1 Scope Approval](phase-1-scope-approval.md) 已批准第 1 至第 7 节所受约束的最大评审包络，但本文件本身仍未被接受，且 `P1-PV-G01` 保持 `BLOCKED`。在本文件形成正式接受记录并满足 G01 前，它只能作为评审输入，不授予任何行动权限。已批准的范围决定具有以下效力：

- 将第 1 至第 7 节的范围和排除项确立为后续提案的最大审查包络；
- 允许编制并提交 K2/X2 定义、责任矩阵、具体相邻契约、风险登记与独立实现工作项供评审；
- 允许 Gate 责任人将已审批版本作为范围证据之一；
- 对超出包络的提案要求停止并重新评审。

即使范围记录获批，也不授予代码、Stub、测试候选、集成、环境、部署、Release 或 Production Validation 的执行许可，不能单独把任何 Gate 标为 `PASS`。

### 11.2 必须指定的责任角色

| 责任角色 | 最低责任 | 当前记录 |
| --- | --- | --- |
| Project / Phase Owner | 确认阶段、目标、范围、资源与最终实施授权 | 待指定 |
| Architecture Owner | 复核 V2.3、依赖、职责、例外与架构风险 | 待指定 |
| Ongoing Scope Maintenance Owner | 管理获批包络、排除项、交付物映射和变更追溯 | 待指定；一次性 Scope Decision 已由 `ACS-PGA` 通过 `ACS-P1-GOV-005` 记录 |
| Application–V5、V5–V4、V4–V3、V3–Compute Contract Owners | 分别拥有具体相邻契约的语义、兼容和变更 | 待指定 |
| V4 Boundary Owner | 管理 Stub 范围、期限、停止、替换与移除 | 待指定 |
| Data Governance Owner | 评审 Asset 等权威责任和所有权记录 | 待指定 |
| Security & Data Owners | 批准输入、访问、最小披露与安全停止条件 | 待指定 |
| Validation Owner | 管理证据、修订一致性与 Gate 状态 | 待指定 |
| Release Decision Owner | 独立作出 `Proceed / Hold / Exception Approved` | 待指定 |
| Acceptance Owner | 逐项确认验收标准、证据、日期和最终结论 | 待指定 |

责任角色未指定是 G01 阻塞条件，不能用文档作者、提案人或自动化工具代替必需审批人。

### 11.3 重新评审触发条件

出现以下任一情况时，本范围授权停止适用，必须按架构与治理流程重新评审：

- 新增层级、模块、服务、数据 owner、依赖方向或跨层接口；
- 扩大 K2/X2、页面、业务能力、数据、副作用、外部用户或环境范围；
- V4 Stub 超期、增加长期状态或不能按原计划移除；
- 引入 API、数据库、Job/Worker、存储、框架、供应商、部署或其他技术绑定；
- P1-006 Open Questions 的关闭结论改变既有边界或所有权；
- 候选修订、契约版本、停止、回退或恢复前置发生实质变化；
- 出现反向、跨层、循环、共享状态或私有实现依赖；
- 高或严重风险未被有权责任人接受。

最终授权结论：`ACS-P1-GOV-005` 已批准 Phase 1 Vertical Slice 的最大评审包络；`ACS-P1-007` 本文件仍为 `REVIEW INPUT / NOT ACCEPTED`，`P1-PV-G01` 保持 `BLOCKED`，Execution Authorization 保持 `NOT GRANTED`。只有轨道定义、责任角色、相邻契约、Open Questions、风险与具体工作项分别通过适用 Gate 后，才可以逐项授予后续实现权限；本文件不改变 V2.3 架构。
