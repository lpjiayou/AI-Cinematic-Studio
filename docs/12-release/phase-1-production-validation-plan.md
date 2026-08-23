# Phase 1 Production Validation Plan

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-P1-001` |
| 架构基线 | AI Cinematic Studio `V2.3` |
| 文档状态 | Phase 1 计划基线；尚未执行 |
| 适用范围 | Internal Content Lab 的 K2/X2 验证轨道，以及获批的 V5 MVP、V4 Stub、V3 MVP 与 Compute 最小验证边界 |
| 明确边界 | 本文件只定义范围、节奏、Gate、证据和风险，不创建代码、数据库、环境或 Release，不选择技术实现，也不修改架构 |

本计划受 [系统上下文](../../architecture/system-context.md)、[层级依赖图](../../architecture/dependency-map.md)、[接口契约基础](../04-interface-contract/README.md)、[Phase 1 验证 Gate](../11-testing/verification-gates.md)、[Release 验证流程](../11-testing/release-validation.md)、[测试证据标准](../11-testing/test-evidence-standard.md)、[完成定义](../../governance/DEFINITION_OF_DONE.md)和[架构变更流程](../../governance/ARCHITECTURE_CHANGE_PROCESS.md)约束。

V2.3 的生产依赖方向保持为：

`Application Layer → V5 Core OS → V4 Platform → V3 Render Core → Compute → Foundation`

箭头只表示相邻层依赖可以进入评审的方向，不批准任何具体接口、实现或部署关系。本计划中的 “MVP” 表示 Phase 1 的最小可验证交付 Profile，不是新模块，也不表示相应层级已经完整实现；“Stub” 表示未来获批任务可以建立的受控、临时且契约受限的验证替代边界，不是新的架构层或永久生产模块；“Production Validation” 是获批 Release 后的安全技术确认，不是生产环境业务测试。

仓库当前没有 K2 或 X2 的权威业务、模型或技术定义。因此，本计划仅将 `K2` 与 `X2` 作为 ACS-P1-001 指定的两个验证轨道标签。执行前必须分别批准它们的目标、输入边界、预期结果、允许副作用和完成判据；不得从名称推导功能、模型、数据或实现含义。

Internal Content Lab → Application Layer、V5 MVP → V5 Core OS、V4 Stub → V4 Platform、V3 MVP → V3 Render Core 均是为了检查既有依赖链而提出的**条件性验证映射**。只有 `P1-PV-G01` 由有权责任人批准后，这些映射才可用于 Phase 1 候选；它们不写入 V2.3 架构基线，不自动映射到仓库目录，也不分配数据所有权。

## 1. Phase 1 目标

Phase 1 的目标是针对一个身份明确、范围冻结且另行获批的 Release 候选，建立并执行最小纵向验证闭环，而不是完成整个 AI Cinematic Studio 产品或任一层级的完整建设。

当前仓库没有可识别的 Phase 0 正式退出决定、Phase 1 实现章程、可运行候选、验证环境、自动化证据或 Release 记录。本文件的完成只建立计划，不表示 Phase 1 已启动；在 Phase 0 退出决定（或获批且有期限的例外）与 Phase 1 范围授权齐备前，执行状态保持 `BLOCKED`。

具体目标如下：

1. 将 Internal Content Lab 限定为受控的 Application Layer 内部验证消费边界，并分别验证 K2 与 X2 两个已批准轨道。
2. 证明获批候选只沿 `Application Layer → V5 Core OS → V4 Platform → V3 Render Core → Compute` 的相邻公开契约协作；Compute 与 Foundation 的关系继续遵守既有 V2.3 基线。
3. 对 V5 MVP、V4 Stub、V3 MVP 和 Compute 的最小公开验证面建立可审查的范围、非目标和退出条件。
4. 为正常结果、边界条件、失败语义、关联标识、兼容性、停止与回退准备形成可追溯证据。
5. 在 Release 前完成适用的 Unit、Contract、Integration 与 E2E 证据；Production Validation 只确认已部署候选的受控技术状态，不替代发布前验证。
6. 形成 `Proceed / Hold / Exception Approved` 的 Release 决策输入，并在 Production Validation 后形成 `Validated / Observation Extended / Rollback Required / Incident Escalated` 结论。
7. 用明确的不实现清单、风险登记和 Gate 防止 Phase 1 范围扩张或隐式技术锁定。

Phase 1 成功只表示本计划所列获批范围达到验收标准，不表示 V5、V4、V3、Compute、Internal Content Lab 或整个 ACS 已达到完整产品、外部客户、规模化运营或商业化就绪状态，也不自动授权 Phase 2。

## 2. Internal Content Lab K2/X2 验证范围

### 2.1 边界定位

在第 9 节条件性映射获得批准后，Internal Content Lab 才可作为 Application Layer 下的受控内部验证 Profile。它只能通过获批的 Application Layer → V5 Core OS 公开契约提交验证请求和接收公开结果，不得直接依赖 V4 Platform、V3 Render Core、Compute、Foundation 或任何层的私有实现。

本计划不定义 Internal Content Lab 的界面、工作流、用户体系、部署位置或长期产品形态，也不把它登记为新的 V2.3 模块。

### 2.2 K2 与 X2 轨道共同纳入范围

每个轨道必须独立具备以下批准记录和证据，K2 的结果不能替代 X2，X2 的结果也不能替代 K2：

| 验证项 | 最低要求 |
| --- | --- |
| 轨道定义 | 记录轨道标签、批准目的、责任人、适用候选和明确非目标 |
| 输入边界 | 说明允许的输入类别、来源授权、前置条件和禁止输入，不定义数据库字段或技术格式 |
| 预期结果 | 说明可观察的成功语义、完成判据和允许副作用，不将内部表示作为契约 |
| 失败边界 | 说明可预见失败、停止条件、恢复或回退责任，以及不得发生的副作用 |
| 契约路径 | 只经过相邻层已批准的公开契约；不得反向、跨层或循环依赖 |
| 关联标识 | 按适用性连续保留 Request ID、Trace ID、Project ID、Asset ID 和 Job ID，不伪造不适用标识 |
| 候选一致性 | 每份证据对应同一可识别候选；候选实质变化后重新判断证据适用性 |
| 安全与数据 | 只使用获批、最小且可控的验证输入；不得依赖真实用户流量或未授权敏感数据 |
| 可复核性 | 记录前置条件、预期、实际结果、状态、责任人、时间、限制与 Evidence ID |

K2 与 X2 至少分别覆盖一个获批正常结果、适用的关键边界或失败结果、端到端关联标识核对和无越界副作用核对。具体样本、数量、质量阈值、性能目标和业务内容必须由独立授权记录给出；本计划不预设这些内容。

### 2.3 Internal Content Lab 退出条件

- K2 与 X2 的轨道定义均已批准，且没有用名称替代验收语义。
- 两个轨道的适用发布前证据均为 `PASS`；客观不适用项有获批 `N/A`。
- Internal Content Lab 只调用 V5 Core OS 的公开契约，未出现跨层或私有实现依赖。
- 公开结果、失败语义和关联标识可以追溯至同一候选。
- 没有未授权业务数据、不可逆副作用、真实用户试验或生产状态绕过。

## 3. V5 MVP 范围

V5 MVP 只定义 V5 Core OS 在 Phase 1 候选中的最小可验证公开边界，不定义其内部模块或完整业务职责。

### 3.1 纳入范围

- 依据 [Application–V5 契约模板](../04-interface-contract/application-v5-contract.md)形成获批契约实例，完整说明 Purpose、Input、Output、Error 与 Ownership。
- 只接收 Internal Content Lab 经批准的 K2/X2 验证上下文，并对超出范围或不满足前置条件的请求产生已批准且可关联的失败语义。
- 按适用性保持 Request ID、Trace ID、Project ID、Asset ID 与 Job ID 的语义连续性；不得用标识替代授权判断。
- 只通过 [V5–V4 契约模板](../04-interface-contract/v5-v4-contract.md)所约束的公开边界依赖 V4 Stub，不得直接触达 V3 Render Core、Compute 或 Foundation。
- 为获批公开行为提供风险相称的 Unit 与 Contract 证据，并在纵向候选中参与 Integration 与 E2E 验证。
- 保留足以支持缺陷定位、停止和回退决策的最小技术证据，但不规定日志、追踪或监控产品。

### 3.2 明确排除

- 不宣称完成 V5 Core OS 的完整产品、工作流、策略、运营或商业化能力。
- 不新增 V5 内部模块、长期状态模型、数据所有权或存储设计。
- 不允许直连 V3 Render Core、Compute、Foundation 或依赖 V4 Stub 的私有行为。
- 不把 Identity、Project、Asset、Production、Render、Business 或 Intelligence 数据域自动分配给 V5 Core OS。
- 不选择协议、语言、框架、消息机制、运行方式或部署拓扑。

### 3.3 退出条件

V5 MVP 的获批契约、正常与失败语义、关联标识、相邻层依赖和适用测试证据全部通过；任何未定义的内部行为不得被调用方当作稳定能力。

## 4. V3 MVP 范围

V3 MVP 只定义 V3 Render Core 在 Phase 1 候选中的最小可验证公开边界，不定义完整 Render Core、渲染引擎或执行流程。

### 4.1 纳入范围

- 依据 [V4–V3 契约模板](../04-interface-contract/v4-v3-contract.md)验证 V3 只接受 V4 Stub 通过公开契约提供的获批上下文。
- 依据 [V3–Compute 契约模板](../04-interface-contract/v3-compute-contract.md)验证 V3 只通过 Compute 公开契约提出获批工作请求。
- 对 K2/X2 所需的最小公开输入、输出、错误和所有权语义形成契约证据，不暴露内部表示。
- 按适用性连续传递或返回 Request ID、Trace ID、Project ID、Asset ID 与 Job ID，并保留失败关联。
- 为获批公开行为提供风险相称的 Unit 与 Contract 证据，并参与 V4 Stub、Compute 之间的 Integration 及纵向 E2E 验证。

### 4.2 明确排除

- 不定义完整渲染管线、引擎、素材格式、质量档位、资源模型或供应商。
- 不建立业务实体、数据库、Asset 状态机、作业状态机或持久化方案。
- 不把 Asset、Production、Render 或任何其他数据域自动分配给 V3 Render Core。
- 不直连 Application Layer、V5 Core OS 或 Foundation，也不把 Compute 内部行为纳入 V3 契约。
- 不将 Phase 1 的最小公开行为解释为 V3 Render Core 的最终模块责任清单。

### 4.3 退出条件

V4 Stub → V3 Render Core → Compute 的两个相邻契约边界均有一致、可追溯且通过的证据；V3 不依赖上下层私有实现，也没有扩张为未获批的完整 Render Core。

## 5. V4 Stub 范围

V4 Stub 是 Phase 1 纵向验证所需的临时、可识别、可移除边界。它仍处于 V4 Platform 的既有位置，不新增层级、不替代 V4 Platform 的长期设计，也不证明完整 V4 已经存在。

本文件不创建 V4 Stub。实际 Stub 的创建、位置、运行边界和生命周期必须由后续实现任务明确授权，并继续受本节约束。

### 5.1 纳入范围

- 仅提供获批 K2/X2 路径所需的 V5 Core OS → V4 Platform 公开契约面，并只通过 V4 Platform → V3 Render Core 公开契约依赖 V3 MVP。
- 在不引入额外业务决策或权威状态的前提下，保留已批准的输入、输出、错误和关联标识语义。
- 对相同获批前置条件给出可重复、可审查的契约行为，使 V5/V3 边界可以被隔离验证和联合验证。
- 在候选、证据和 Release 决策中显式标记 `V4 Stub`，不得伪装成完整 V4 Platform。
- 记录所有者、使用范围、停止条件、替换或移除条件及最迟复核 Gate。

### 5.2 明确排除

- 不实现完整 V4 Platform、通用平台能力、长期业务逻辑、持久化、调度或运营能力。
- 不直连 Application Layer、Compute 或 Foundation，不形成供其他未授权消费者复用的旁路。
- 不成为契约的权威来源；契约先获批准，Stub 只能符合契约。
- 不因进入受控 Production Validation 而自动获得永久生产地位。

### 5.3 退出与处置条件

V4 Stub 的 Contract 与 Integration 证据通过，未产生反向、跨层或私有依赖。Phase 1 关闭记录必须明确它是被移除、继续隔离观察，还是等待后续获批 V4 实现替换；任何继续使用都需有责任人、期限、风险接受和独立授权。

## 6. Compute 范围

Compute 在本计划中只承担 V3 Render Core 与 Foundation 之间既有高层计算边界的最小公开验证面；本计划不定义调度模型、资源类型、容量或供应商。

### 6.1 纳入范围

- 只接受 V3 MVP 通过获批 V3 Render Core → Compute 公开契约提交的工作上下文。
- 对获批输入给出可观察的接收、结果或失败语义；具体状态模型必须由独立契约授权，本计划不预设。
- 当工作单元适用 Job ID 时，按获批契约建立或沿用其权威关联；不得从 Job ID 推导状态、权限或业务含义。
- 保持适用的 Request ID、Trace ID、Project ID、Asset ID 与 Job ID 关联，为停止、问题定位和候选核对提供证据。
- 验证输入边界、失败隔离、可停止性和已批准恢复条件，并参与 Contract、Integration 与 E2E 证据链。
- 如实际候选需要 Compute → Foundation 依赖，只能使用另行获批的 Foundation 公开契约；本计划不批准或定义该具体依赖。

### 6.2 明确排除

- 不选择计算框架、执行引擎、硬件、云服务、模型供应商或资源调度方案。
- 不定义容量、弹性、队列、并发、性能数值、成本模型或可用性承诺。
- 不创建数据库、作业表、资源表、存储结构或数据访问代码。
- 不因使用 Job ID 或计算语义而推断 Compute 是 Job、Render 或其他数据域的权威所有者。
- 不依赖 V3 Render Core 的私有实现，不向上反向调用，也不允许 V3 绕过 Compute 直连 Foundation。

### 6.3 退出条件

V3–Compute 契约、关联标识、正常与失败结果、停止条件和适用验证证据全部通过；没有未经批准的资源、供应商、Foundation 依赖或技术锁定。

## 7. 明确不实现列表

ACS-P1-001 及本计划不创建或批准以下内容：

1. 任何代码、测试代码、V4 Stub 实现、服务实现、API 端点、具体事件或 Payload、Error Code 实例、脚本、配置、流水线、基础设施或环境。
2. 任何数据库、SQL Schema、表、字段、索引、迁移、ORM、数据访问层或具体存储产品。
3. V5 Core OS、V4 Platform、V3 Render Core、Compute 或 Internal Content Lab 的完整产品实现。
4. V2.3 之外的新层级、模块、服务、依赖方向、职责分配或目录映射。
5. Application Layer 绕过 V5、V5 绕过 V4、V4 绕过 V3、V3 绕过 Compute 的跨层调用，以及任何反向或循环依赖。
6. K2、X2 的业务定义、模型选择、内容类型、数据集、质量阈值、性能指标或商业语义；这些必须另行获批。
7. 完整 V4 Platform；V4 Stub 以外的通用平台、长期状态、业务规则或共享能力。
8. 完整渲染管线、计算调度、资源编排、模型供应、容量、成本或供应商设计。
9. 任何未获批的外部应用、外部客户流程、账号矩阵运营、商业化 SaaS、计费、结算或生产运营扩展。
10. 真实用户流量试验、未授权生产数据、敏感数据复制、不可逆业务副作用或在生产环境补做发布前测试。
11. 具体语言、框架、协议、数据库、消息系统、云平台、可观测性产品、测试工具或部署技术。
12. Foundation 的新增实现、内部组件、数据设施或职责变化；实际前置能力必须由独立任务授权。
13. 将 Identity、Project、Asset、Production、Render、Business 或 Intelligence 数据域实际分配给任何逻辑层，或声明新的权威数据 owner。
14. 将逻辑层或条件性验证 Profile 自动映射到 `apps/`、`services/`、`packages/`、`infrastructure/` 或其他物理目录。
15. 用本计划、Sprint、Gate、Stub 或 “MVP” 标签追认未经批准的架构、接口、数据或实现变化。
16. 将 Phase 1 通过解释为 Phase 2、外部 Release、规模化生产或商业化活动的自动授权。

## 8. Sprint 规划

Sprint 按证据成熟度排序，不预设固定时长、团队编制或实现方法。每个 Sprint 只有在其进入条件满足后才能承诺；日历结束不能替代退出条件。未来实施、环境和 Release 动作仍需独立获批工作项。

| Sprint | 进入前提 | 目标 | 计划证据与产物 | 退出条件 |
| --- | --- | --- | --- | --- |
| `P1-S0 Scope Ready` | Phase 0 正式退出，或存在获批且有期限的例外；Phase 1 计划工作已授权 | 冻结 Phase 1 范围与责任 | Phase 0 退出引用；Phase 1 授权；K2/X2 轨道定义；条件性映射；V5/V4 Stub/V3/Compute 范围；所有者；不实现清单；初始风险快照 | 授权、术语、责任、验收标准和风险均可审查；架构影响判定完成 |
| `P1-S1 Contract Ready` | S0 通过；契约责任人与评审责任已指定 | 使相邻边界可验证 | Application–V5、V5–V4、V4–V3、V3–Compute 契约实例计划；Purpose/Input/Output/Error/Ownership；关联标识与兼容性要求；证据 ID 规划 | 四个相邻边界无空缺、冲突、跨层或反向依赖；所有具体契约均有批准路径 |
| `P1-S2 Candidate Ready` | S1 通过；所有实际实现和 Stub 工作项已另行授权 | 验证各最小边界的候选就绪度 | 身份明确的获批候选；V5 MVP、V3 MVP、V4 Stub、Compute 的适用 Unit/Contract 证据；Stub 生命周期记录；缺陷与风险更新 | 强制 Unit/Contract 证据通过；候选无夹带范围；阻塞缺陷和架构冲突为零 |
| `P1-S3 Vertical Validation Ready` | S2 通过；受控非生产验证边界已获批且实际可用 | 完成发布前纵向验证 | Integration/E2E 证据；K2 与 X2 独立证据包；失败、停止、恢复、关联标识和无副作用核对 | 两个轨道均通过；证据对应同一候选；Production Validation 未被用于补做发布前测试 |
| `P1-S4 Release & Production Validation` | S3 通过；Release 候选、决策责任和目标环境分别获批 | 作出 Release 决策并在获批后关闭验证 | 候选冻结记录；风险与回退准备；`Proceed/Hold/Exception Approved` 决策；获批 Production Validation 记录；最终结论与 Phase 1 Gate 包 | 只有 `Proceed` 才能进入获批 Release；发布后完成安全验证并形成终态或有期限的升级决定 |

每个 Sprint 还必须记录工作项—验收标准—修订—Evidence ID 映射、DoD 五类门禁的适用性、责任人、阻塞项和未完成项去向。Sprint 完成不等于 Phase 1 Gate 通过；实质范围或候选变化必须重新评估受影响证据，不得静默移入后续 Sprint。

## 9. Gate 验收标准

### 9.1 Gate 状态

单项证据使用 `PASS / FAIL / BLOCKED / NOT RUN / N/A`。`N/A` 必须说明客观理由并由指定评审人批准；Gate 整体不能标记为 `N/A`。存在任何 `FAIL`、未解决 `BLOCKED`、强制 `NOT RUN`、未授权架构变化或未接受的高影响风险时，不得进入下一 Gate。

尚不存在的代码、候选、CI、测试框架、环境、自动化报告或 Release 记录必须如实标记为未具备，不能用本计划中的未来态描述充当通过证据。

### 9.2 Gate 清单

| Gate ID | 验收标准 | 最低证据 | 阻塞条件 |
| --- | --- | --- | --- |
| `P1-PV-G01 Authorization` | Phase 0 已正式退出，或存在获批且有期限的阶段例外；Phase 1 目标、范围、排除项和责任已获有权责任人批准 | Phase 0 退出决定或阶段例外记录；ACS-P1-001 范围记录；责任矩阵；验收人 | 前置决定或有效例外、授权、所有者或验收标准缺失 |
| `P1-PV-G02 Track Definition` | K2 与 X2 分别拥有无歧义、可验证的轨道定义 | 两份轨道定义；输入/结果/失败/副作用/完成判据；批准记录 | 用轨道名称代替语义，或任一轨道未批准 |
| `P1-PV-G03 Architecture` | 候选完全遵守 V2.3 层级、相邻依赖和公开边界 | 架构复核；依赖清单；适用 ADR 或 `N/A` 依据 | 反向、跨层、循环、私有实现依赖或未经批准的职责变化 |
| `P1-PV-G04 Contract` | 四个相邻边界的具体契约均完整、一致且可追溯 | Purpose/Input/Output/Error/Ownership；版本与兼容性；关联任务 | 契约空缺、冲突、由 Stub/测试反向定义或出现技术绑定越权 |
| `P1-PV-G05 Scope & DoD` | Internal Content Lab、V5 MVP、V4 Stub、V3 MVP 与 Compute 均只包含获批范围，且代码、测试、文档、审查、验收五类 DoD 均有真实结论 | 交付物—范围映射；不实现清单核对；Stub 生命周期记录；五类 DoD 证据或获批 N/A | 完整平台或额外业务被夹带；Stub 被当作永久 V4；任一强制 DoD 缺失或失败 |
| `P1-PV-G06 Layered Evidence` | 风险相称的 Unit、Contract、Integration 与 E2E 证据完成 | 测试证据索引；正常/边界/失败/兼容/恢复结果；获批 N/A | 证据缺失、不可复现、与候选不一致，或用高层验证替代低层证据 |
| `P1-PV-G07 Traceability` | 适用关联标识在公开边界保持正确语义并支持问题定位 | Request ID、Trace ID、Project ID、Asset ID、Job ID 的适用性与连续性证据 | 静默替换、伪造标识、从标识推导权限或无法关联错误 |
| `P1-PV-G08 Safety & Data` | 验证输入、访问、错误披露和副作用均在授权范围内 | 数据授权；最小披露核对；停止条件；安全评审 | 使用真实用户流量、未授权敏感数据、凭据泄露或不可控副作用 |
| `P1-PV-G09 Candidate & Recovery` | Release 候选身份冻结，停止、回退与恢复责任可信 | 候选清单；修订映射；回退计划；责任人；演练或人工复核证据 | 候选漂移、回退前置缺失或恢复责任不明 |
| `P1-PV-G10 Release Decision` | 分层证据、Gate、缺陷和残余风险支持明确 Release 决策 | 证据包；风险接受；独立评审；`Proceed/Hold/Exception Approved` 记录 | Release Decision Owner 未授权，或例外覆盖安全/架构阻塞项 |
| `P1-PV-G11 Production Validation` | 获批 Release 后只执行预先批准的安全技术确认 | 目标候选核对；健康与契约信号；停止条件；实际结果 | 在生产探索业务、补做 E2E、修改内部状态或扩大真实影响 |
| `P1-PV-G12 Phase Exit` | Production Validation 结论、文档、审查、风险和后续责任全部关闭或正式移交 | `Validated/Observation Extended/Rollback Required/Incident Escalated` 结论；DoD；Phase 1 Gate 包 | 阻塞项未清零、观察无期限、风险无人负责或证据相互矛盾 |

### 9.3 决策规则

- `P1-PV-G01` 至 `G09` 全部通过后，候选才可提交 Release 决策；Gate 通过不等于已获 Release 授权。
- 只有 Release Decision Owner 明确记录 `Proceed`，且外部发布授权与环境前置条件均满足时，才可进入获批 Release。
- `Exception Approved` 必须限时、可追溯、有补偿控制，且不得覆盖架构、安全或范围阻塞项。
- Production Validation 后必须形成 `Validated`、有期限的 `Observation Extended`、`Rollback Required` 或 `Incident Escalated`，不得以“未观察到问题”替代证据。
- 所有强制项通过、阻塞问题为零、残余风险由有权责任人接受且 `P1-PV-G12` 完成时，才可决定 **允许退出 Phase 1**。
- 实际不符合验收标准时决定为 **不允许退出**；缺少授权、前置条件、环境或有效证据时决定为 **暂停待决**。
- Phase 1 退出只证明获批范围达到最低门槛，不自动授权 Phase 2、外部客户 Release、规模化生产或商业化活动。

## 10. 风险列表

以下条目是本计划的初始 Phase 1 风险候选。`P1-S0` 退出前必须由风险所有者复核，并按 [风险登记册](../../governance/RISK_REGISTER.md)的字段、状态和接受权限正式登记；此表不替代企业级风险真源。

| 风险编号 | 风险描述 | 影响 | 概率 | 缓解措施与验证条件 | 状态 / 责任角色 |
| --- | --- | --- | --- | --- | --- |
| `R-P1-PV-001` | 若 K2/X2 缺少权威定义却直接执行，名称可能被不同参与者赋予不同语义，导致证据不可比较和范围扩张。 | 高 | 高 | S0 分别批准目的、输入、结果、失败、副作用和完成判据；定义缺失时阻塞 G02。 | 开放 / Phase Owner |
| `R-P1-PV-002` | 若 “MVP” 被解释为完整产品授权，V5/V3/Compute 可能夹带未批准能力并改变责任边界。 | 高 | 中 | 对每层维护纳入/排除清单和交付物映射；每个 Sprint 核对 G05。 | 开放 / Scope Owner |
| `R-P1-PV-003` | 若 V4 Stub 积累业务逻辑或长期状态，临时边界可能成为事实平台并阻碍后续替换。 | 高 | 中 | Stub 只符合已批准契约；记录所有者、期限、替换/移除条件；Phase 1 关闭时强制处置决定。 | 开放 / V4 Boundary Owner |
| `R-P1-PV-004` | 若为缩短纵向路径而绕过相邻层，可能形成跨层、反向或私有依赖并破坏 V2.3。 | 严重 | 中 | 每个候选执行依赖复核；发现绕过立即阻塞 G03，不得先实现后追认。 | 开放 / Architecture Owner |
| `R-P1-PV-005` | 若契约、Stub 行为和测试期望不同步，验证可能通过错误语义并把测试变成事实契约。 | 高 | 中 | 契约先批准；Contract 证据引用确定版本；候选变化后重审全部相关证据。 | 开放 / Contract Owners |
| `R-P1-PV-006` | 若关联标识不连续或被滥用，跨层失败可能无法定位，或标识被错误当作授权凭据。 | 高 | 中 | 对五类标识逐项判定适用性；验证成功与失败路径；异常阻塞 G07。 | 开放 / Validation Owner |
| `R-P1-PV-007` | 若验证使用真实用户流量、敏感数据或不可逆输入，可能造成安全、隐私或业务影响。 | 严重 | 低 | 预先批准最小输入和访问；禁止真实用户试验；定义停止与升级条件；异常阻塞 G08。 | 开放 / Security & Data Owners |
| `R-P1-PV-008` | 若 Production Validation 被用于补做 Unit、Contract、Integration 或 E2E，基本正确性问题可能首次暴露在生产。 | 严重 | 中 | G06 完成后才能申请 Release；生产验证只核对已部署候选与预先批准技术信号。 | 开放 / Release Decision Owner |
| `R-P1-PV-009` | 若验证后候选发生实质变化却继续沿用旧证据，Release 决策可能基于错误修订。 | 高 | 中 | 冻结候选；建立修订—Evidence ID 映射；变化时重新评估并执行受影响验证。 | 开放 / Change Owner |
| `R-P1-PV-010` | 若停止、回退或恢复前置条件未经验证，生产异常可能无法及时限制影响。 | 严重 | 中 | Release 前确认责任、触发条件和可执行性；恢复不可信时阻塞 G09/G10。 | 开放 / Release Decision Owner |
| `R-P1-PV-011` | 若计划提前写入框架、供应商、数据库或部署假设，Phase 1 可能形成未经批准的技术锁定。 | 高 | 中 | 保持契约与证据技术中立；任何选型走独立任务和决策流程；本计划不得作为选型依据。 | 开放 / Architecture Owner |
| `R-P1-PV-012` | 若责任人、评审人或风险接受权限未指定，Gate 可能停滞或由无权人员作出结论。 | 高 | 高 | S0 指定实际角色；空缺责任阻塞 G01；高/严重残余风险按治理规则升级批准。 | 开放 / Project Owner |
| `R-P1-PV-013` | 若根据层级或标识名称推断数据 owner，可能未经评审重新分配七个数据域并形成共享状态耦合。 | 高 | 中 | 对任何权威数据责任要求独立所有权记录；本计划全部保持未分配；发现推断即阻塞 G03/G04。 | 开放 / Data Governance Owner |
| `R-P1-PV-014` | 若把计划中的未来环境、CI 或自动化描述当作现有事实，Gate 可能在没有真实可复核证据时被错误通过。 | 高 | 高 | 只接受实际产生且对应候选的证据；不存在的能力标记 `NOT RUN` 或 `BLOCKED`，不得用占位报告替代。 | 开放 / Validation Owner |

风险状态只能使用 `开放 / 缓解中 / 监控中 / 已接受 / 已关闭`。风险接受不等于风险消失；高或严重残余风险必须由有权责任人批准并设置复核期限。任何风险缓解措施都不能自行扩大业务范围、引入技术实现或修改 V2.3 架构。
