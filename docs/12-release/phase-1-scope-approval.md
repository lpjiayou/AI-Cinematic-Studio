# Phase 1 Scope Approval

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-P1-GOV-005` |
| Record Type | Phase 1 Scope Approval Decision |
| Decision Date | `2026-08-06` |
| Approval Instrument | `ACS-P1-GOV-005` Phase Governance Directive |
| Decision Function | ACS Phase Governance Authority（`ACS-PGA`），仅限本次范围决定 |
| Scope Decision Owner | `ACS-PGA` 通过本任务承担本次决定职能；不自动获得实施或 Release 权限 |
| Accountable Function | `ACS-PGA`；当前接受基线允许明确团队职能承担本次治理决定 |
| Operational Accountable Person | `UNASSIGNED`；本记录不填补 Phase 1 实施、风险、Release 或 Exit 的 Person Assignment |
| Ongoing Scope Maintenance Owner | `UNASSIGNED` |
| Scope Acceptance Owner | `ACS-PGA`，仅接受本记录的最大范围与排除项 |
| Record Revision | `VERSIONED BY CONTAINING GIT COMMIT`；Gate Evidence 必须引用解析后的不可变 Commit |
| Architecture Baseline | AI Cinematic Studio V2.3，未修改 |
| Scope Decision | `APPROVED — MAXIMUM REVIEW ENVELOPE` |
| Immediate Execution Effect | `DOCUMENTATION / DESIGN / GOVERNANCE PREPARATION ONLY` |
| Phase 1 Implementation Authorization | `NOT GRANTED / BLOCKED` |
| V4 / V3 / Compute Implementation | `NOT GRANTED` |
| Release / Production | `NOT GRANTED` |
| `P1-PV-G01 Authorization` | `BLOCKED`；Scope 条件已由本记录满足，但责任、Person、风险与接受前置未闭合 |
| ADR | `NOT TRIGGERED`；本记录不改变 V2.3 架构且不创建 ADR |

本记录正式批准 Phase 1 可进入后续评审的最大范围包络，并对当前立即允许的非实现活动作出限定。它不创建代码、API、数据库、V4 Stub、V3 Render、Compute、环境或候选，也不追认历史实现。

`ACS-PGA` 在本记录中的职能只作出这一次 Scope Decision。后续范围维护、Person Assignment、风险接受、Implementation、Release 和 Phase Exit 仍须分别指派并授权；本决定不把 Phase 0 团队责任自动扩展为 Phase 1 实施责任。

**Scope Approval ≠ Implementation Authorization。** 范围被批准只表示某项提案具备“可以在该边界内申请后续授权”的资格，不表示工作可以开始、Gate 已通过、实现已存在或 Release 已获许可。

本记录受 [Phase 0 Exit Record](phase-0-exit-record.md)、[Phase 1 Production Validation Plan](phase-1-production-validation-plan.md)、[V2.3 System Context](../../architecture/system-context.md)、[Dependency Map](../../architecture/dependency-map.md)、[Verification Gates](../11-testing/verification-gates.md)、[Test Evidence Standard](../11-testing/test-evidence-standard.md)、[Definition of Done](../../governance/DEFINITION_OF_DONE.md)与 [Architecture Change Process](../../governance/ARCHITECTURE_CHANGE_PROCESS.md)约束。

以下工作树材料在本记录创建时未被 Git 跟踪或正式接受，只作为内容指纹固定的审查输入；它们不能替代 Repository 事实、V2.3 权威、Person Assignment 或独立批准：

| Review Input | SHA-256 | 本记录中的效力 |
| --- | --- | --- |
| `AI_CINEMATIC_STUDIO_GENERATION_2_DEVELOPMENT_CHARTER.md` | `fea4f1d57c8ac99e650714d8c644241c31f19209b88c056cf371cac994cd29ec` | Gen2 战略约束参考；不授权实现 |
| `docs/00-governance/gen2-charter-integration-record.md` | `7782bab46460211ee6c469d0a9a81ac387de119edeff14f4bbfe8d23826f433d` | 候选治理接入说明 |
| `docs/12-release/phase-1-responsibility-assignment.md` | `1c58b9e0f7d10d889b7e111b30e4ce8e1d2e77acfada492d4f292b8fc164904f` | 当前责任空缺与职责分离审查输入 |
| `docs/04-interface-contract/v5-v3-vertical-slice-review.md` | `ead91c6999bd6c878af2a45ca4c7cd51f536384932c4b393be523178fd3d9d24` | 候选 Vertical Slice 语义与 Open Questions |
| `docs/07-v3-render-core/render-core-boundary.md` | `6f42a53a72eb1265d3545a84fec73fe8101566e0ffcf6450acde3ada93b48de1` | 候选 V3 边界说明 |
| `docs/12-release/phase-1-vertical-slice-authorization.md` | `dd21f3b4ca1d4a942864c018805523979e84a2645c1825e58461859fa9a1b737` | `PROPOSED / BLOCKED` 范围草案；不构成授权 |
| `docs/12-release/phase-1-execution-authorization.md` | `2f654285266d21f53244a9d683975f9b1dbf97832bd6c90a7f2a5b90ff9eb0c4` | 相关授权审查草案；未被接受且不构成 Implementation Authorization |

## 1. Phase 1 Objective

### 1.1 批准目标

ACS Engineering Phase 1 的批准目标是：围绕 Internal Content Lab 的 X2 主实验方向，冻结可验证范围并准备一条最小、可停止、可追溯的 V2.3 Vertical Slice，使后续有权责任人能够基于明确的 Scope、Contract、Risk、Evidence 与 Stop Conditions 决定是否逐项授权实现。

该目标同时包含两个不同但不可混同的维度：

| 维度 | Phase 1 目标 | 不得推断 |
| --- | --- | --- |
| Gen2 Strategy | X2-first；验证真实内容需求、可重复生产、质量、受众和商业信号，K2 保持受限次实验 | Gen2 execution design 已完成、真实受众试验已获准或商业验证已发生 |
| V2.3 Engineering | 在 `Application → V5 → V4 → V3 → Compute` 相邻公开边界内准备最小验证闭环 | 任一层、接口、Stub、实现、环境或 Release 已获批准 |

Gen2 Phase 0/1/2 与 ACS Engineering Phase 0/1/2 是不同命名空间。一个命名空间的 Scope、Gate、进入或退出决定不会自动完成或授权另一个命名空间。

### 1.2 成功边界

Phase 1 的目标不是完成整个 ACS、完整 V5/V4/V3/Compute、企业平台、规模化内容矩阵或商业化 SaaS。即使未来 Phase 1 在获批实现和真实证据下退出，也只证明批准范围达到相应 Gate，不表示 Production Ready、Phase 2、外部 Release 或商业成功。

## 2. Allowed Scope

### 2.1 当前立即允许的非实现活动

- 将本 Scope Approval 纳入后续治理评审并维护范围—证据追溯；
- 编制并冻结 X2 experiment design，包括假设、受众、指标、阈值、观察窗口、Rights/consent、质量 Gate、停止条件、证据位置和决策 owner；
- 记录 K2 受限次实验的目的、非目标、资源上限和未来进入条件，不启动 K2 工程路线；
- 完成 Phase 1 Role/Person 指派、接受记录、职责分离与升级路径；
- 同步 Phase 0 Exit Record 指定的源风险登记册状态、责任和复核点，并正式登记 Phase 1 风险；
- 关闭适用于当前候选的 Vertical Slice Open Questions；
- 编制技术中立的 Application–V5、V5–V4、V4–V3、V3–Compute 具体契约供评审；
- 形成 Asset Return、事实 owner、Rights、安全、最小数据与错误披露的独立治理决定；
- 对任何既有代码复用提出 Gen2 extraction review；
- 准备一次只覆盖一个 active implementation package 的独立 Execution Authorization 申请；
- 规划 Unit、Contract、Integration、E2E、停止、回退和 Evidence ID，不执行尚未授权的验证。

### 2.2 未来可申请独立 Implementation Authorization 的最大包络

只有在适用前置全部通过后，以下内容才有资格被拆分为独立工作项申请授权：

- 一个面向 X2 的最小 Internal Content Lab Profile；
- Application 只向 V5 表达获批 View Request 或 Command Intent；
- V5 只保持批准的 Project、Production Intent、Shot 与 Asset 关联语义，并只依赖 V4 公开边界；
- V4 仅以可识别、可移除、无长期权威状态的受控 Stub Profile 承接两侧独立契约；
- V3 仅处理批准的最小 Render Request，并返回 Render Result 或 Error；
- Compute 仅承接 V3 通过批准契约表达的最小计算语义；
- 结果候选只沿相邻契约返回，在获批权威边界接纳前不得被称为 Asset 事实；
- 风险相称的 Unit、Contract、Integration 与受控非生产 E2E 证据。

本节是未来工作项的审查上限，不是当前实施许可。每一层、每一契约和每一验证活动仍须独立授权。

## 3. Forbidden Scope

本次 Scope Approval 明确排除：

1. 本任务创建或修改任何代码、测试代码、API、数据库、Schema、服务、组件、依赖、配置、环境、CI/CD 或基础设施。
2. 自动授权 Application、V5、V4 Stub、V3 Render、Compute、Integration、E2E、Release 或 Production Validation。
3. 修改、替代或绕过 V2.3 的层级、职责、公开边界、模块、数据 owner 或相邻依赖方向。
4. 将 Gen2 四层自动映射为 V2.3 六层、仓库目录、服务、部署单元或数据所有权。
5. V5 直连 V3、Application 绕过 V5、V4 绕过 V3、V3 绕过 Compute，以及任何反向、循环、共享状态或私有实现依赖。
6. 当前启动 K2 实现，或允许 K2 建立独立平台、基础设施、永久路线或与 X2 竞争无界资源。
7. 同时批准第二个 active implementation package、额外内容垂类、多账号矩阵或平行 IP 实验。
8. 通用 Agent、通用 Workflow、Enterprise OS、multi-tenancy、复杂 RBAC、OAuth、SSO、Billing 或完整权限平台。
9. 重复的 renderer、Asset authority、Job、Queue、Worker、scheduler、provider routing 或隐藏状态源。
10. GPU 集群、生产级 Worker 平台、通用调度、容量、弹性、供应商或基础设施扩张。
11. 选择或绑定语言、框架、协议、数据库、模型、渲染引擎、供应商、云平台、GPU 或测试框架。
12. 自动迁移、复用或追认 Gen1、V2.3、现有 V5/V3 代码或既有 Phase 1 Commit。
13. 使用真实用户流量、未授权敏感数据、不可逆业务副作用、外部客户或自动发布。
14. 在结果产生后修改假设、指标、阈值、受众、比较方法或观察窗口。
15. 用 Scope Approval、MVP、Stub、Gate、Technical Proof 或演示声明 Production、Commercial、Release Ready 或 Production Ready。

## 4. X2 Primary Experiment Boundary

| 项目 | 批准边界 |
| --- | --- |
| Priority | `PRIMARY` |
| Immediate Scope | 独立 experiment design、责任、风险、证据和契约准备 |
| Implementation | `NOT AUTHORIZED` |
| User | Internal Content Lab |
| Work-in-progress | 最多一个未来 active implementation package，且须另行授权 |
| Decision | `GO / HOLD / STOP`，与 Engineering Gate 和 Release 决定分开 |

X2 experiment design 在执行申请前必须冻结：

- 可证伪的受众或商业价值假设；
- 目标受众、明确排除受众及预期行为；
- character identity/personality、跨内容连续性、生产节奏、受众关系和可复用 IP 价值的验证问题；
- Audience、Production、Business 三类指标的基线、目标、证据来源、观察窗口和 owner；
- production time、publishable-output rate、character-consistency review、retention、follower growth、interaction quality 与 repeat engagement；
- 内容序列、输入来源、Rights/consent、质量方法、人工责任、停止条件、失败处理与证据位置；
- `GO / HOLD / STOP` Decision Owner 及每个决定允许的下一最小范围。

X2 Scope Approval 不等于 X2 内容生产、软件实现、真实受众试验或发布授权。缺少任一冻结字段时，X2 保持 `DESIGN BLOCKED`。

## 5. K2 Secondary Experiment Boundary

| 项目 | 批准边界 |
| --- | --- |
| Priority | `SECONDARY / BOUNDED` |
| Immediate Scope | 仅允许定义目的、非目标、指标候选、资源上限和未来进入条件 |
| Implementation / Production | `NOT AUTHORIZED` |
| Resource Rule | 固定、有限，不占用当前 active implementation package |
| Earliest Entry | X2 适用证据或独立优先级决定完成，且 K2 有冻结设计、责任和独立授权 |

K2 未来只可在独立批准后验证 story clarity、emotional progression、production efficiency、completion、retention、audience feedback、iteration speed 与 cost。它不得成为平台、Infrastructure 或永久工程项目。

现有 Phase 1 Production Validation Plan 要求 K2/X2 双轨定义与证据，而 Gen2 Charter 规定 X2-first、K2-later。该差异不会被本记录静默改写：在 `P1-PV-G02` 通过前，必须由有权责任人选择并记录以下一种处置：

1. 在不违反 X2 主优先级、资源和单 active package 限制的前提下，分别批准两份轨道定义；或
2. 正式修订 Phase 1 Plan、Gate、风险和退出条件，使其与获批 Gen2 阶段顺序一致。

在该决定形成前，K2 保持 `DEFINITION PENDING / IMPLEMENTATION NOT AUTHORIZED`。

## 6. Vertical Slice Scope

### 6.1 不变依赖方向

唯一允许进入后续评审的生产依赖方向保持：

`Application Layer → V5 Core OS → V4 Platform → V3 Render Core → Compute → Foundation`

Phase 1 Vertical Slice 最多覆盖 Application 至 Compute；Foundation 不在本次 Scope Approval 的实现包络内。需要 Compute–Foundation 能力时，必须形成独立范围、契约和授权。

### 6.2 分层范围状态

| 层级 | 可进入后续评审的最小范围 | 当前实现状态 |
| --- | --- | --- |
| Application | Internal Content Lab 的最小受控 Profile；只向 V5 表达意图并展示 V5 公开结果 | `NOT AUTHORIZED` |
| V5 Core OS | 保持批准的上层语义，形成最小 V5–V4 投影；不直连 V3 | `NOT AUTHORIZED` |
| V4 Platform | 可识别、可移除、无长期权威状态的 Stub Profile；只在两条独立相邻契约间验证、保持、裁剪或翻译 | `NOT AUTHORIZED` |
| V3 Render Core | 接收批准的 Render Request，返回 Render Result/Error，只通过 V3–Compute 契约依赖 Compute | `NOT AUTHORIZED` |
| Compute | 返回批准的最小接收、结果或失败语义，不拥有产品、创意、Asset 或 Render 决策 | `NOT AUTHORIZED` |
| Foundation | 不在本次 Vertical Slice 包络内 | `OUT OF SCOPE` |

V3 不得创建 Job、Worker、Queue、scheduler、database、Asset ID 或权威 Asset 事实；Render Result 在获批 Asset 权威边界接纳前只能是候选。V4 Stub 不得形成长期状态、共享 DTO、共享数据库或永久平台地位。

### 6.3 实现前阻断条件

在任何 Vertical Slice 实现申请获得评审前，至少必须：

1. `P1-PV-G01` 至 `G04` 的适用前置已经通过；
2. X2/K2 轨道定义与阶段顺序冲突已按第 5 节关闭；
3. 适用 Open Questions 已形成批准结论；
4. 四条相邻契约分别拥有 Purpose、Input、Output、Error、Ownership、Compatibility 与 owner；
5. Shot、Asset Version、内容物化、Asset Return 权威责任、Rights、最小数据、同步/异步、幂等与 V3–Compute 能力等适用问题已批准；
6. 每层 Work Package Owner、Implementation Responsible、Validation、Risk、Change 与停止/回退责任已接受指派；
7. V4 Stub、V3 与 Compute 分别拥有独立任务、文件范围、行为范围、测试和 Execution Authorization；
8. 任何既有代码复用已经通过 extraction review；
9. 源风险登记册与 Phase 1 风险已同步，并由有权责任人处理残余风险。

Scope Approval 不关闭这些条件，也不允许实现通过默认值代替答案。

## 7. Gate Definition

### 7.1 Gate 体系

本记录不创建平行 Gate。ACS Engineering Phase 1 继续使用 `P1-PV-G01` 至 `G12`。Gen2 的 Creative/Production/Platform Quality、Technical/Production/Commercial Proof 与 `GO / HOLD / STOP` 是独立的内容和投资决定记录；它们可以作为适用证据输入，但不能替代、重命名或自动通过 ACS Engineering Gate。

### 7.2 当前 Gate 快照

| Gate | 当前状态 | 当前依据 |
| --- | --- | --- |
| Phase 0 Exit prerequisite | `PASS` | Phase 0 Exit Record 已正式形成 |
| Scope Approval condition within G01 | `PASS — DECISION RECORDED` | 本记录批准最大范围与明确排除项；Gate Evidence 必须引用本文件所在的不可变 Commit |
| `P1-PV-G01 Authorization` overall | `BLOCKED` | Phase 1 operational Accountable Person、责任接受、Risk Owner/Acceptance、源风险登记同步及其他批准前置未闭合 |
| `P1-PV-G02 Track Definition` | `BLOCKED` | X2/K2 冻结定义缺失，且双轨计划与 X2-first 顺序尚未形成正式协调决定 |
| `P1-PV-G03 Architecture` | `NOT RUN` | 没有获批实现候选；本记录只保持 V2.3，不建立新映射 |
| `P1-PV-G04 Contract` | `NOT RUN` | 四条具体相邻契约尚未批准 |
| `P1-PV-G05` 至 `G09` | `NOT RUN` | 没有本记录授权的工作包、候选、分层证据、环境或恢复证据 |
| `P1-PV-G10` 至 `G12` | `NOT RUN / NOT AUTHORIZED` | 没有 Release 候选、Release 决定、Production Validation 或 Phase Exit 证据 |

任何 Gate 通过都不能自动授权下一 Gate、实现、V4/V3、Release 或 Production。Scope condition 为 `PASS` 不能把 G01 overall 改为 `PASS`。

`P1-PV-G01` 只有在下列责任均完成 Person/Function 指派、职责分离、接受记录与必要授权后才可重新评审：Phase / Project、Scope、Ongoing Scope Maintenance、Repository / Change Control、Architecture、Execution、Validation、Production Validation、Release、Phase Exit 与 Document Acceptance；独立的 Risk Owner、Risk Register Custodian 与 Risk Acceptance Authority；Application–V5、V5–V4、V4–V3、V3–Compute 四个 Contract Accountable Owner；Asset / Data Governance / Ownership Accountable Owner；Rights / Security Owner；以及 Work Package Owner 与独立的 Work Package / DoD Acceptance Owner。当前这些前置尚未全部闭合，因此 G01 保持 `BLOCKED`。

## 8. Exit Criteria

### 8.1 Scope Approval 记录完整性

| 检查项 | 当前状态 | 说明 |
| --- | --- | --- |
| Approval Instrument / Decision Function | `RECORDED` | `ACS-P1-GOV-005` 与 `ACS-PGA` 仅承担本次范围决定 |
| Allowed / Forbidden Scope | `RECORDED` | 最大包络、当前立即范围与排除项已分开 |
| X2/K2 disposition | `CONDITIONALLY RECORDED` | X2 primary、K2 bounded secondary 已明确；与现有双轨 Plan 的正式协调仍阻塞 G02 |
| Architecture impact | `NO ARCHITECTURE CHANGE` | V2.3 层级与依赖不变，不建立 Gen2 映射 |
| Operational Accountable Person / Maintenance Owner | `UNASSIGNED` | 继续阻塞 G01，不扩大本次 Scope Decision 效力 |
| Record revision | `VERSIONED BY CONTAINING GIT COMMIT` | Gate Evidence 必须引用实际解析出的不可变 Commit |
| Implementation effect | `NONE` | Scope Approval 不授权实现、集成、Release 或 Production |

本节的未完成项不允许扩大范围或开始实现。它们必须在 G01 决定前关闭并形成可追溯接受记录。

### 8.2 Phase 1 Exit

Phase 1 只有同时满足以下条件才具备退出评审资格：

1. 本 Scope Approval 已进入可追溯版本，Person/Function Assignment、Document Acceptance、Risk Owner 与风险接受权限完整。
2. X2/K2 的定义、阶段顺序和现有 Phase 1 Plan 差异已由正式决定关闭。
3. `P1-PV-G01` 至 `G11` 的全部强制项通过，`G12` 所需退出证据包完整且等待有权责任人作出退出决定；合法 `N/A` 具有客观理由和有权批准，阻塞项为零。
4. 实际交付物只包含批准范围，并对 Allowed/Forbidden Scope 形成逐项证据。
5. V2.3 Architecture、相邻依赖与四条具体 Contract 均通过适用审查；没有未批准映射、旁路或共享真源。
6. 适用 Unit、Contract、Integration 与 E2E 证据对应同一冻结候选，失败、停止、回退与恢复得到验证。
7. Gen2 内容质量、证明层级和 `GO / HOLD / STOP` 保持独立记录，没有用 Technical Proof 夸大商业或生产结论。
8. Release Decision Owner 作出合法 Release 决定；只有明确 `Proceed` 加外部授权才可 Release。
9. Production Validation 仅在获批 Release 后执行安全技术确认，并形成真实终态结论。
10. V4 Stub 的移除、隔离观察或未来替换去向具有 owner、期限、风险与独立决定。
11. DoD 的代码、测试、文档、审查和验收均有真实结论；所有残余风险已关闭、转移或由有权责任人限时接受。
12. Phase / Project Owner 作为 Phase Exit 最终 Accountable，取得适用 Architecture、Security、Validation 与其他专项批准后作出退出决定。

在 Phase 1 Plan 被正式修改前，其现有 K2/X2 双轨定义和证据要求继续有效；本 Scope Approval 不单方面移除 K2 Exit Criteria。若决定采用 X2-only Phase 1，必须先同步修改 Plan、G02、风险和 G12 Exit Criteria。

当前没有实现、候选、环境、完整责任或相应证据，Phase 1 不具备退出条件。Phase 1 Exit 也不自动批准 Gen2/ACS Phase 2、外部客户、规模化生产或商业化。

## 9. Change Control

### 9.1 必须重新进行 Scope Approval 的变化

- 改变 X2/K2 优先级、阶段顺序、资源上限或允许并行的 active package 数量；
- 新增内容垂类、账号矩阵、外部用户、真实流量、不可逆副作用或商业化活动；
- 扩大 Application、V5、V4 Stub、V3、Compute、Foundation、数据、Rights、安全或环境范围；
- 新增 API、数据库、Job、Queue、Worker、调度、供应商、基础设施或技术绑定；
- 自动复用既有代码，或改变 extraction review 的依赖、维护和移除结论；
- 修改冻结假设、指标、阈值、受众、观察窗口、停止或成功条件；
- 改变 Work Package、Contract、候选修订、证据、风险、停止、回退或 Stub 生命周期；
- 将 Scope Approval 扩展解释为 Implementation、Integration、Release 或 Production Authorization。

### 9.2 Architecture 与治理变更

- 若变化影响 V2.3 层级、职责、所有权、公开边界、接口或依赖方向，必须按 Architecture Change Process 评估 ADR；只有 Accepted ADR 才能改变架构基线。
- 只批准最大范围包络且保持现有架构语义不变，不触发 ADR。本任务因此为 `ADR NOT TRIGGERED`。
- Scope 变化本身不应通过代码、测试、Stub 或候选先行落地；必须先更新批准记录和受影响 Gate。
- Phase 1 Plan、Responsibility Assignment、Risk Register、Contract、Validation 和 Release 文档出现冲突时，必须同步审查，不能由实现自行选择有利版本。
- 本记录未来修订必须保留旧决定、说明变化原因、绑定不可变 Git 修订并重新计算 Gate；不得静默把 `BLOCKED` 或 `NOT RUN` 改为 `PASS`。

### 9.3 最终范围决定

Phase 1 最大范围包络为 `APPROVED`；立即执行效力仅限 Documentation、Design 与 Governance Preparation。Scope Approval 不构成 Implementation Authorization，`P1-PV-G01` overall 继续 `BLOCKED`，所有代码、API、数据库、V4、V3、Compute、Integration、Release 与 Production 权限继续为 `NOT GRANTED`。V2.3 架构保持不变，本任务不创建 ADR。
