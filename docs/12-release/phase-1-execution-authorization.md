# Phase 1 Execution Authorization & Gen2 Alignment Review

> Applicability notice — `2026-08-25`
>
> 本文正文完整保留 `2026-08-06` 时点的条件授权审查。对唯一精确工作包
> `ACS-K2-002-CHANGAN-ONBOARDING-AND-EP01-CHAIN`，后续已接受的
> [ACS-K2-002 Non-GPU Preproduction Governance Rebaseline](../../governance/ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md)
> 已完成本文第 4 节与第 10.1 节预留的 independent priority review 和 separate
> K2 authorization。本文原 `BLOCKED / NOT GRANTED` 快照仍是历史事实，但不再
> 否定该精确 non-GPU repository package；它仍不授予 live production、Provider、
> GPU、Script/ShotPlan 接受、Asset admission、Release、Publication 或 Phase Exit。

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-P1-GOV-002` |
| Document Type | Phase Governance Conditional Authorization Record |
| Decision Date | `2026-08-06` |
| ACS Phase | ACS Engineering Phase 1 Production Validation |
| Architecture Baseline | AI Cinematic Studio V2.3，未修改 |
| Phase 0 Exit | `SATISFIED`；依据 [Phase 0 Exit Record](phase-0-exit-record.md)，记录 Commit `8e15009f38926e4528e773f848cf63bee90af900` |
| Gen2 Governing Input | Charter 内容仅作为受限、未跟踪的评审输入；[Baseline Asset Acceptance Decision Record](baseline-asset-acceptance-decision-record.md) 将 Gen2 Charter 与 Gen2 Charter Integration Record 均记录为 `DEFER / NOT INCLUDED IN CURRENT BASELINE` |
| Gen2 Source Status | 文件内容声明 `FINAL FOUNDING CHARTER`；当前文件未被 Git 跟踪，且其 Source Baseline `9da3835c3bf7f69ed4085fa28d6206fa3f84ed25` 无法在本仓库解析 |
| Scope Envelope | `APPROVED FOR DESIGN AND AUTHORIZATION PREPARATION ONLY`；依据 [Phase 1 Scope Approval](phase-1-scope-approval.md)，记录 Commit `67986f9c6f7cb92335122a7a63446b4afdb5c375` |
| Phase 1 Implementation Authorization | `BLOCKED / NOT GRANTED` |
| V4 Implementation Authorization | `NOT GRANTED` |
| V3 Implementation Authorization | `NOT GRANTED` |
| Release / Production Authorization | `NOT GRANTED` |
| ADR | 未触发；本记录不修改 V2.3 架构，也不创建 ADR |

本记录建立 Phase 1 执行授权所需的条件、责任、Gate 和变更控制，并对 Generation 2（Gen2）一致性作出日期化审查。它不是代码、API、数据库、V4 Stub、V3 Render、Compute、集成、Release 或生产执行许可。

必须区分两个阶段命名空间：

| 名称 | 本记录中的含义 | 不得推断 |
| --- | --- | --- |
| ACS Engineering Phase 1 | 现有 V2.3 仓库中的 Production Validation 治理阶段 | 不等于 Gen2 产品已经启动 |
| Gen2 Phase 0 | Charter 中的 Content Lab Foundation，以及其要求的独立 X2 experiment design/review | 不因 ACS Phase 0 已退出而自动完成 |
| Gen2 Phase 1 | Charter 中的 X2 Validation | 不因 ACS Engineering Phase 1 已进入授权评审而自动获准执行 |
| Gen2 Phase 2 | Charter 中的 K2 Validation | 不得提前并入 X2 主实现线 |

## 1. Phase 1 Scope Authorization

### 1.1 已记录的范围决定

[Phase 1 Scope Approval](phase-1-scope-approval.md) 已将当前范围批准为最大评审包络；本记录仅同步该决定并说明后续执行授权条件。批准范围限于：

1. 将 X2 确立为 Gen2 主实验，将 K2 保持为受限次实验；
2. 编制并评审 X2 execution design、责任分配、风险、契约、所有权和证据计划；
3. 重新评审 [Phase 1 Vertical Slice Authorization Review](phase-1-vertical-slice-authorization.md) 的拟议范围；
4. 关闭 [V5–V3 Vertical Slice Review](../04-interface-contract/v5-v3-vertical-slice-review.md) 中适用于 X2 的 Open Questions；
5. 为未来单一、最小实现包准备独立授权申请。

该批准是设计与授权准备许可，不是实现许可。它不追认既有 Phase 1 Commit，不把既有 V5 能力自动归入 Gen2，也不批准任何 V4、V3 或 Compute 开发。

### 1.2 Implementation Authorization 必要条件

**Phase 1 Implementation Authorization 只有在以下四项全部为 `PASS` 时才可能生效：**

- **Phase 0 Exit Complete**
- **Scope Approved**
- **Responsibility Defined**
- **Gate Defined**

这四项是共同必要条件，不可相互替代；满足它们也只允许有权责任人审查具体实现包，不能自动授权 V3、V4、Release 或 Production Validation。

| 必要条件 | 当前状态 | 当前证据 | 关闭要求 |
| --- | --- | --- | --- |
| Phase 0 Exit Complete | `PASS` | `ACS-P1-GOV-001` 明确 Phase 0 `COMPLETED` | 已满足；不得据此追认后续实现 |
| Scope Approved | `PASS — DECISION RECORDED` | `ACS-P1-GOV-005` 已在 Commit `67986f9c6f7cb92335122a7a63446b4afdb5c375` 批准 Phase 1 最大评审包络；该决定明确 `Scope Approval ≠ Implementation Authorization` | 本条件已满足；X2 冻结设计、P1-007 接受、K2/X2 协调和具体实现包仍分别受 G01、G02 与独立 Execution Authorization 约束 |
| Responsibility Defined | `BLOCKED` | 本记录定义责任类别，但 X2 决策人、实验负责人、四条契约 owner、V4/V3 owner 等尚未被正式指派并接受责任 | 对第 9 节所有强制角色形成明确团队或实名指派、权限边界和接受记录 |
| Gate Defined | `PASS — DEFINITION ONLY` | [Phase 1 Production Validation Plan](phase-1-production-validation-plan.md) 已定义 `P1-PV-G01` 至 `G12`；Gen2 Charter 已定义实验决策、质量与证明层级 | Gate 已定义不代表任何 Gate 已通过；实际证据仍须生成并评审 |

当前总体结论：`BLOCKED / NOT GRANTED`。允许继续治理与设计准备，不允许启动实现。

## 2. Gen2 Alignment Check

### 2.1 对齐结果

| Gen2 Charter 要求 | 本记录中的处理 | 结论 |
| --- | --- | --- |
| 真实内容需求先于工具、平台和企业能力 | 只允许面向 Internal Content Lab 的 X2 实验设计；不授权平台扩张 | `ALIGNED` |
| X2 first | X2 是唯一主实验线 | `ALIGNED` |
| K2 是 bounded secondary experiment | K2 仅保留受限次实验边界，不获实现授权 | `ALIGNED` |
| 一条主内容线、一个受限次实验、一个 active implementation package | 当前不允许实现；未来最多一次批准一个 X2 实现包 | `ALIGNED BY CONTROL` |
| Manual workflow → repeated success → measured bottleneck → automation | 任何自动化必须说明为何不能继续人工执行 | `ALIGNED BY CONTROL` |
| 商业假设、指标、阈值和观察窗口在执行前冻结 | X2 execution design 尚未形成 | `BLOCKED` |
| Technical、Production、Commercial Proof 分开陈述 | Gate 不允许用较低证明层级替代较高证明层级 | `ALIGNED BY CONTROL` |
| Creative、Production、Platform Quality Gate 分开记录 | 纳入第 8 节 Gate 证据要求 | `ALIGNED BY CONTROL` |
| Gen1/既有代码只可经 extraction review 进入 Gen2 | 既有 V5/V3 代码不自动复用或继承 | `ALIGNED BY CONTROL` |
| Phase 0–1 不建设 GPU 集群、Worker 平台、调度平台或通用 provider routing | 全部列入禁止范围 | `ALIGNED` |
| Charter 本身不启动实现 | 本记录保持实现 `NOT GRANTED` | `ALIGNED` |

### 2.2 未关闭的一致性问题

1. Charter 当前是未跟踪文件，没有本仓库内可引用的不可变修订；其声明的 Source Baseline 无法在当前仓库解析，列明的五份 informed-by 来源也无法按当前相对路径解析。其内容可作为本次对齐输入，但在正式版本化、来源核验和接受前不能作为唯一的可审计执行依据。
2. Charter 将 X2 Validation 定义为 Gen2 Phase 1，将 K2 Validation 定义为 Gen2 Phase 2；现有 [Phase 1 Production Validation Plan](phase-1-production-validation-plan.md) 则要求 K2 与 X2 分别形成 Phase 1 证据。该差异必须通过独立治理复核解决，本记录不静默改写任一文件。
3. Charter 的 Content Application、Creative Intelligence、Media Production、Infrastructure 四层是 Gen2 最小架构原则；V2.3 的 Application、V5、V4、V3、Compute 是当前冻结架构。两者之间没有获批的一一映射，本记录不创建该映射。
4. Gen2 source repository/baseline、代码提取策略和 X2 execution design 均未建立；现有 V2.3 代码不能因此被自动称为 Gen2 实现。

Gen2 战略一致性结论：`CONDITIONALLY ALIGNED`。Repository/Architecture 映射结论：`UNDECIDED`。执行效力：`NONE`。

## 3. X2 Primary Experiment Boundary

| 维度 | 边界 |
| --- | --- |
| Priority | `PRIMARY` |
| Current Authorization | 允许编制并评审 X2 execution design；不允许内容生产执行或代码实现 |
| User | Internal Content Lab |
| Hypothesis Type | 可证伪的受众或商业价值假设，不得只是技术能力陈述 |
| Resource Rule | 主要创意与工程注意力；未来最多一个 active implementation package |
| Decision | 每一阶段只能形成 `GO / HOLD / STOP` 之一 |

X2 execution design 在获批前必须冻结：

- 目标受众、明确排除的受众及预期行为；
- 稳定角色身份与个性、跨内容连续性、生产节奏、受众关系和可复用 IP 价值的验证问题；
- Audience、Production、Business 三类指标的基线、目标、证据来源、观察窗口和 owner；
- 至少包括 production time、publishable-output rate、character-consistency review、retention、follower growth、interaction quality 与 repeat engagement；
- 内容序列范围、输入来源、Rights/consent 边界和不可逆副作用；
- Creative、Production、Platform Quality 的评审方法、硬性否决条件与人类责任人；
- 停止条件、失败处理、证据位置、成本与人工纠正记录；
- `GO / HOLD / STOP` 决策人及每个决定允许的下一最小范围。

X2 不得被解释为通用 Agent、通用 Workflow、角色平台、完整内容操作系统、企业 SaaS 或基础设施计划。设计若不能说明“谁现在使用、哪个生产或商业指标改善、什么证据证实或证伪”，则保持 `HOLD`。

## 4. K2 Secondary Experiment Boundary

| 维度 | 边界 |
| --- | --- |
| Priority | `SECONDARY` |
| Current Authorization | `NOT AUTHORIZED FOR IMPLEMENTATION OR PRODUCTION` |
| Permitted Now | 记录受限实验假设、指标候选、依赖和未来进入条件；不得占用 active implementation package |
| Resource Rule | 固定、有限、不得与 X2 竞争无界工程路线 |
| Earliest Execution Condition | X2 适用证据 Gate 或独立优先级复核完成，且 K2 有单独冻结设计和授权 |

K2 未来若获独立授权，只能验证 story clarity、emotional progression、production efficiency、completion、retention、audience feedback、iteration speed 与 cost。K2 不得：

- 成为独立平台、基础设施或永久工程项目；
- 因现有 Phase 1 Plan 提到 K2 而获得自动实现许可；
- 在 X2 主线之外建立 renderer、Asset、Job、Queue、Worker 或 workflow authority；
- 未经 extraction/reuse review 自动继承 X2 或既有 V2.3 实现；
- 通过新增账号矩阵、平行内容垂类或额外平台路线扩大范围。

## 5. Vertical Slice Implementation Authorization

### 5.1 保持的 V2.3 边界

未来如获批准，生产依赖方向必须保持：

`Application Layer → V5 Core OS → V4 Platform → V3 Render Core → Compute`

这是 V2.3 Vertical Slice 边界，不是 Gen2 四层与 V2.3 层级的一一映射。结果与错误只能经相邻公开契约逐层返回，不形成反向生产依赖。

### 5.2 当前授权状态

| 范围 | 当前状态 | 说明 |
| --- | --- | --- |
| Application | `NOT GRANTED` | 不创建 UI、组件、路由、API 或 Domain 写入 |
| V5 Core OS | `NOT GRANTED` | 既有 Identity、Project、Asset、Relationship 实现不获回溯授权，也不自动成为 Gen2 能力 |
| V4 Stub | `NOT GRANTED` | 必须具有独立任务、owner、文件范围、期限、契约、停止和移除条件 |
| V3 Render MVP | `NOT GRANTED` | 必须具有独立任务、owner、输入/输出边界、测试和回退条件 |
| Compute | `NOT GRANTED` | 不创建 Worker、队列、调度、GPU 集群或通用 provider routing |
| Integration / E2E | `NOT GRANTED` | 必须等待所有相邻契约与对应候选分别获批 |

### 5.3 未来单一实现包的最低前置

未来任何 Vertical Slice 实现包提交执行授权前，至少必须：

1. 将 Gen2 Charter 纳入可追溯的版本化接受记录，并解释其 Source Baseline；
2. 批准冻结的 X2 execution design；
3. 使 P1-007 的适用范围获得正式批准并与 X2-first 顺序一致；
4. 关闭 P1-006 中适用于该实现包的 Open Questions；
5. 分别批准 Application–V5、V5–V4、V4–V3、V3–Compute 具体契约；
6. 对任何既有代码复用完成 Gen2 extraction review，记录用户需要、最小边界、依赖、维护成本、验收和移除路径；
7. 指派并接受第 9 节所需责任；
8. 形成只覆盖一个 active implementation package 的独立任务，明确文件、行为、测试、停止与退出条件；
9. 由有权责任人记录明确的 `GRANTED`，且不得将该决定扩展到 V3、V4、Release 或 Production。

## 6. Allowed Scope

### 6.1 当前立即允许

- 对 Gen2 Charter 进行版本化、来源核验和正式接受评审；
- 编制和评审 X2 execution design；
- 记录 K2 的受限次实验边界与未来进入条件；
- 指派 Phase 1、Internal Content Lab、X2、架构、契约、数据、安全、验证与验收责任；
- 解决 ACS Phase 1 Plan 与 Gen2 X2/K2 顺序差异；
- 关闭 P1-006 Open Questions；
- 编制技术中立的四条相邻契约；
- 形成数据所有权、Rights/consent、最小披露和风险评审材料；
- 为既有代码提出 extraction review；
- 准备单一最小实现包的独立授权申请。

上述动作仅产生文档、评审和决策证据，不授权实现。

### 6.2 仅在未来独立授权后可进入评审的最大包络

- 一个面向 X2 的最小 Technical Proof；
- 一次只允许一个 active implementation package；
- 只有测得人工流程瓶颈后才允许最小自动化；
- 只使用获批相邻契约和单一事实 owner；
- 风险相称的 Unit、Contract 及受控非生产验证；
- 明确可停止、可移除、可回退且不形成永久平台承诺的实现。

本节描述未来可审查的上限，不是提前授权。

## 7. Forbidden Scope

本记录明确禁止：

1. 以本任务创建或修改任何代码、测试代码、API、数据库、Schema、服务、组件、依赖、环境或基础设施。
2. 将本记录解释为 Application、V5、V4、V3、Compute、Integration、Release 或 Production 的执行许可。
3. 自动授权 V4 Stub 或 V3 Render MVP；两者必须分别获得独立授权。
4. 将 Gen2 四层自动映射、合并或替换 V2.3 的 Application/V5/V4/V3/Compute 层级。
5. 修改 V2.3 层级、责任、依赖方向、模块、数据域或权威 owner。
6. Application 绕过 V5、V5 绕过 V4、V4 绕过 V3、V3 绕过 Compute，或建立反向、循环、共享状态与私有实现依赖。
7. 自动迁移或继承 Gen1、V2.3 或现有 V5/V3 代码；代码复用必须通过 extraction review。
8. 在 X2 之前或与 X2 竞争无界资源地启动 K2 工程实现。
9. 创建通用 Agent、通用 Workflow、企业 OS、RBAC、多租户、完整权限、Billing、SSO 或通用 SaaS 平台。
10. 创建重复的 renderer、Asset authority、Job、Queue、Worker、调度器、provider routing 或隐藏状态源。
11. 建设 GPU 集群、生产级 Worker 基础设施、调度平台或因技术机会扩展 Compute。
12. 新建多账号矩阵、平行 IP 实验、额外内容垂类或基础设施驱动的内容计划。
13. 选择或绑定语言、框架、数据库、协议、模型、供应商、云平台、GPU、渲染引擎或测试框架。
14. 在结果产生后修改假设、指标、阈值、受众、比较方法或观察窗口。
15. 以 Technical Proof 宣称 Production Proof、Commercial Proof、Production Ready、Release Ready 或商业验证完成。
16. 使用本记录追认既有实现、扩大 P1-007 效力或绕过独立任务与 Gate。

## 8. Gate Authorization

### 8.1 Gate 使用授权

本记录授权 Phase 1 治理责任人使用既有 `P1-PV-G01` 至 `P1-PV-G12` 收集和评审证据，但不新建平行 Gate，也不把任何 Gate 自动标记为 `PASS`。

Gen2 证据必须嵌入适用 ACS Gate：

| Gen2 控制 | 适用 ACS Gate | 最低要求 |
| --- | --- | --- |
| 冻结实验假设、受众、指标、owner、停止条件 | `G01 / G02` | X2 execution design 与批准记录 |
| X2 主线、K2 次线、一个 active implementation package | `G01 / G02 / G05` | 优先级、资源与交付物映射 |
| Gen2 extraction review 与无自动继承 | `G03 / G05` | 复用决定、依赖和移除路径 |
| 四条相邻契约与 V2.3 方向 | `G03 / G04` | Purpose、Input、Output、Error、Ownership 和兼容性 |
| Rights/consent、数据最小化和停止条件 | `G08` | 批准记录与风险复核 |
| Technical / Production / Commercial Proof 分离 | `G06 / G10 / G12` | 各层级证据分别标注，不得推导升级 |
| Creative / Production / Platform Quality Gate | `G06 / G10 / G12` | 三份独立结果及证据，不得互相遮盖失败 |
| `GO / HOLD / STOP` | `G10 / G12` | 决策人、依据、下一授权范围与继续禁止项 |

### 8.2 当前 Gate 快照

| Gate / 条件 | 状态 | 原因 |
| --- | --- | --- |
| Phase 0 Exit prerequisite | `PASS` | ACS-P1-GOV-001 已形成正式退出记录 |
| `P1-PV-G01 Authorization` | `BLOCKED` | Scope 条件已满足，但 Operational Accountable Person、强制责任接受、风险 owner / 接受、源风险登记同步及 Charter 版本化等前置仍未闭合 |
| `P1-PV-G02 Track Definition` | `BLOCKED` | Charter 给出战略边界，但 X2 冻结设计缺失，K2 与现有 Phase 1 Plan 的顺序差异未关闭 |
| `P1-PV-G03 Architecture` | `NOT RUN` | 没有获批 Gen2/V2.3 映射或具体候选；本记录不创建映射 |
| `P1-PV-G04 Contract` | `NOT RUN` | 四条具体相邻契约尚未批准 |
| `P1-PV-G05` 至 `G12` | `NOT RUN` | 没有由本任务创建或授权的实现、候选、环境、证据或 Release |

任何一个 Gate 通过都不能自动通过另一个 Gate，不能授权下一层实现，也不能把 V4/V3、Release 或 Production 纳入范围。

## 9. Responsibility Matrix

Phase 0 中的团队标识只可作为 Phase 1 指派候选；[Phase 0 Exit Record](phase-0-exit-record.md) 已明确它们不会自动继承 Phase 1 权限。下列强制责任必须重新形成接受记录：

| 责任 | 最低职责 | 当前候选 / 状态 | 授权限制 |
| --- | --- | --- | --- |
| Phase 1 Scope Decision Function | 对本次目标、最大范围、排除项和资源上限作出一次性决定 | `ACS-PGA`；`ACS-P1-GOV-005` 已记录决定 | 仅对本次 Scope Decision 生效；不替代 Person Assignment、Implementation、Risk、Release 或专项评审 |
| Ongoing Scope Maintenance Owner | 维护获批包络、排除项、变更记录和追溯关系 | `UNASSIGNED` | 维护责任不授予实现或扩大范围的权限 |
| Phase 1 Execution Authorization Owner | 对单一实现包作出 `GRANTED / REJECTED / HOLD` | `ACS-PGA` 候选；`ACCEPTANCE PENDING` | 不得批量或回溯授权 |
| Gen2 Charter Custodian | 维护版本、来源、接受状态与变更记录 | `UNASSIGNED` | 不能单独授权实现 |
| Internal Content Lab Experiment Owner | 拥有实验 brief、运行责任和证据完整性 | `UNASSIGNED` | 不拥有架构或 Release 决策 |
| X2 Decision Owner | 冻结假设与指标并作出 `GO / HOLD / STOP` | `UNASSIGNED` | 不能事后改变成功标准 |
| K2 Decision Owner | 维护次实验边界和未来进入决定 | `UNASSIGNED` | 当前无实现授权 |
| Human Creative / Editorial Acceptance Owner | 对内容意图、质量和发布责任作出人类判断 | `UNASSIGNED` | AI 或自动化不得代替 |
| Architecture Owner | 复核 V2.3、Gen2 非映射、依赖与 ADR 触发 | `ACS-ARF` 候选；`ACCEPTANCE PENDING` | 不授权业务范围或 Release |
| Repository & Change Control Owner | 维护可重现基线、Git 证据与本记录变更 | `ACS-RGF` 候选；`ACCEPTANCE PENDING` | 不将未跟踪文件视为已接受基线 |
| 四条 Contract Owners | 分别拥有 Application–V5、V5–V4、V4–V3、V3–Compute 契约 | `UNASSIGNED — FOUR DISTINCT ACCOUNTABILITIES REQUIRED` | 不得用一个共享对象跨越边界 |
| V4 Stub Owner | 管理 Stub 范围、期限、停止、替换与移除 | `UNASSIGNED` | 必须独立授权，当前不得实现 |
| V3 Implementation Owner | 管理 V3 最小候选、验证、停止与回退 | `UNASSIGNED` | 必须独立授权，当前不得实现 |
| Asset / Data Governance Owner | 批准事实 owner、Asset Return 与最小数据边界 | `UNASSIGNED` | 不设计数据库，不因层级推断 owner |
| Rights / Security Owner | 批准 Rights/consent、输入、访问和最小披露 | `ACS-SGF` 候选；`ACCEPTANCE PENDING` | 不得以安全评审扩大功能范围 |
| Validation / Evidence Owner | 维护候选—契约—Evidence ID 映射和 Gate 状态 | `UNASSIGNED` | 不能把计划描述当作实际证据 |
| Release Decision Owner | 基于证据作出 Release 决定 | `UNASSIGNED` | 当前没有 Release 权限 |
| Acceptance Owner | 核对 DoD、风险、Gate 和最终范围结论 | `UNASSIGNED` | 不得与未经独立复核的作者自我批准混同 |

任一 `UNASSIGNED` 或 `ACCEPTANCE PENDING` 的强制责任仍保持 `P1-PV-G01` 为 `BLOCKED`。AI 助手、文档作者或自动化工具不能充当人类实验、风险接受、Release 或最终验收责任人。

## 10. Change Control

### 10.1 必须重新评审的变化

出现以下任一情况时，当前范围包络停止适用，必须先进入独立变更评审：

- X2/K2 优先级、资源上限或阶段顺序变化；
- 同时出现第二个 active implementation package；
- Gen2 四层与 V2.3 层级建立映射、合并、替换或责任迁移；
- 提取、迁移或直接复用 Gen1/V2.3 代码；
- 新增模块、数据 owner、跨层接口、API、数据库、依赖或技术绑定；
- V4 Stub 超期、拥有长期状态、扩大职责或不能移除；
- V3/Compute 增加 Job、Worker、Queue、调度、存储、供应商或生产基础设施；
- X2/K2 的假设、受众、指标、阈值、观察窗口、Rights/consent 或停止条件变化；
- 将 Scope Authorization 扩大解释为 Execution、Integration、Release 或 Production Authorization；
- 候选、契约版本、风险、停止、回退或证据前提发生实质变化；
- Gen2 Charter 的内容、状态、来源基线或接受状态变化。

### 10.2 适用流程

1. Gen2 Charter 变化必须按 Charter 的 Change Control 形成 decision record，说明证据、影响层、最小变化、风险、回退和明确接受。
2. V2.3 层级、责任、依赖、接口或数据所有权变化必须按 [Architecture Change Process](../../governance/ARCHITECTURE_CHANGE_PROCESS.md) 评估 ADR；需要 ADR 时，只有 `Accepted` 后才可继续。
3. 实验假设、指标或观察窗口在执行开始后不得为使结果成功而修改；新的问题必须建立新实验版本和新决定。
4. V4、V3、Compute 及任何具体实现包必须保留独立任务、owner、文件范围、验收、风险与停止记录。
5. 本文件的未来修订必须保留旧决定、引用不可变 Git 修订，并重新计算第 1、2、8、9 节状态；不得静默把 `BLOCKED` 或 `NOT RUN` 改为 `PASS`。

### 10.3 最终授权结论

**Phase 0 Exit Complete：`PASS`。Scope Approved：`PASS — DECISION RECORDED`。Responsibility Defined：`BLOCKED`。Gate Defined：`PASS — DEFINITION ONLY`。`P1-PV-G01` 总体仍为 `BLOCKED`。**

因此，ACS-P1-GOV-002 已建立 Phase 1 执行授权条件、X2/K2 边界、Vertical Slice 审查包络、Gate 使用规则、责任矩阵和变更控制；它当前只授权设计与治理准备。Phase 1 Implementation Authorization 保持 `BLOCKED / NOT GRANTED`，V4 与 V3 开发没有被自动授权，V2.3 架构没有改变。
