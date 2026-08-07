# Phase 1 Responsibility Assignment

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-P1-GOV-004` |
| Record Type | Draft Phase 1 Responsibility Assignment Standard |
| Record Date | `2026-08-06` |
| Architecture Baseline | AI Cinematic Studio V2.3，未修改 |
| Document Status | `DRAFT / REVIEW INPUT / NOT ACCEPTED` |
| Responsibility Model | `DEFINED IN DRAFT / NOT ACCEPTED` |
| Person Assignment | `INCOMPLETE / UNASSIGNED` |
| Assignment Acceptance | `NOT COMPLETE` |
| Document Acceptance Owner | `UNASSIGNED` |
| `P1-PV-G01 Authorization` | `BLOCKED` |
| Phase 1 Implementation | `BLOCKED / NOT AUTHORIZED` |
| Release / Production | `NOT AUTHORIZED` |
| ADR | `NOT TRIGGERED`；本记录不改变架构语义且不创建 ADR |

本草案建立 Phase 1 的责任角色、人员指派规则、证据责任和冲突处理方式。它以 [Phase 0 Exit Record](phase-0-exit-record.md)、[Phase 1 Production Validation Plan](phase-1-production-validation-plan.md)、[Verification Gates](../11-testing/verification-gates.md)、[Test Evidence Standard](../11-testing/test-evidence-standard.md)及 [Definition of Done](../../governance/DEFINITION_OF_DONE.md)为当前已跟踪治理输入；[Gen2 Charter Integration Record](../00-governance/gen2-charter-integration-record.md) 在评审时仍是未跟踪、未接受的工作树输入，只用于核对候选 Gen2 责任域，不能赋予本草案治理效力。

本记录定义“谁应对什么负责”，但不决定“工作是否可以开始”。责任不等于授权；Role 已定义、Person 被提名或接受责任，都不能单独授予代码、API、数据库、V4、V3、Compute、Integration、Release 或 Production 权限。

## 1. Responsibility Model

### 1.1 Role、Person 与 Function

| 概念 | 定义 | 生命周期 | 不得推断 |
| --- | --- | --- | --- |
| Role | 与决策或交付物绑定的稳定职责、权限上限和问责边界 | 随治理规范持续存在；可由不同 Assignee 先后承担 | Role 存在不表示已有 Assignee 或行动许可 |
| Person | 可明确识别、能够接受责任并对决定署名的自然人 | 指派有生效时间、结束时间、代理和撤销记录 | Person 参与或署名不表示拥有未授予的决策权 |
| Function / Team | 提供专项复核或执行能力的组织职能 | 可作为 Role 候选承接方或 `C/R` 支持方 | 团队名称不能替代关键决定所需的明确 Accountable Assignee |
| Assignment | 将一个 Role 在限定范围和期限内交给 Person 或获准 Function 的记录 | 必须被接受、可暂停、可撤销、可替代 | Assignment 不等于 Implementation Authorization |
| Authorization | 由有权责任人在明确范围、期限和 Gate 条件下授予的行动许可 | 只对指定工作项生效 | 不得从 Role、Assignment、计划或历史 Commit 推导 |

Phase 0 使用的 `ACS-PGA`、`ACS-ARF`、`ACS-RGF`、`ACS-SGF` 仅是 Phase 1 Role 的候选职能。它们在 Phase 0 的责任不会自动继承为 Phase 1 的 Person 指派、风险接受、实施、Release 或验收权限。

### 1.2 Assignment 状态

| 状态 | 含义 | 可执行效力 |
| --- | --- | --- |
| `UNASSIGNED` | Role 已定义但没有 Assignee | 无；相关 Gate 保持阻塞 |
| `NOMINATED` | 已提出 Person/Function 候选，尚未接受 | 无；不得作出该 Role 的正式决定 |
| `ACCEPTED` | Assignee 已接受明确范围、期限和升级义务 | 仅承担责任；仍需独立 Authorization 才能执行受限动作 |
| `DELEGATED` | 原 Accountable Role 在获准范围内指定临时代理 | 代理范围、期限和不可代理决定必须明确 |
| `SUSPENDED` | 因冲突、离岗、风险或证据问题暂停 | 不得继续作出决定 |
| `REVOKED` | 指派终止并保留历史记录 | 无未来效力，不删除既有决定记录 |

### 1.3 RACI 与决定责任

- `A — Accountable`：对一个明确决定承担最终责任；每个决定只能有一个明确的 `A`。
- `R — Responsible`：执行获批工作并形成证据；可以有多个，但范围必须互不冲突。
- `C — Consulted`：在决定前提供专项意见。
- `I — Informed`：接收决定和影响信息，不参与批准。

RACI 只描述责任关系，不授予执行权限。作者不能因同时承担 `R` 而自动成为自己的独立评审人或 `A`；架构、安全、风险接受、Release 和 Phase Exit 等决定必须满足适用的职责分离。

### 1.4 强制 Assignment 记录

每项指派至少记录：Role ID、Role 名称、Person/Function 标识、RACI 类型、适用任务或决定、文件/行为范围、权限上限、生效与结束时间、代理规则、冲突披露、接受记录、撤销条件和审批依据。缺少任一强制字段时，状态不得高于 `NOMINATED`。

### 1.5 当前核心 Assignment 快照

| Role | 候选 Function | Person | Assignment 状态 | Authorization 状态 |
| --- | --- | --- | --- | --- |
| Phase / Project Owner | `ACS-PGA` 候选 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Scope Authorization Owner | `ACS-PGA` 候选 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Execution Authorization Owner | `ACS-PGA` 候选 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Architecture Review Owner | `ACS-ARF` 候选 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Repository & Change Control Owner | `ACS-RGF` 候选 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Rights / Security Review Owner | `ACS-SGF` 候选 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Validation / Evidence Owner | 待指定 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Change Owner | 待指定 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Production Validation Owner | 待指定 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Risk Owner（每个 Risk 分别指定） | 待指定 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Risk Register Custodian | `ACS-RGF` 候选 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Risk Acceptance Authority | 待指定 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Release Decision Owner | 待指定 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Phase Exit Decision Owner | 必须由 Phase / Project Owner 在退出决定上下文中承担 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |
| Document Acceptance Owner | 待指定 | `UNASSIGNED` | `UNASSIGNED` | `NONE` |

因此，本规范完成只表示责任模型已定义，不表示责任已闭合。Person 和有权 Function 的正式指派与接受记录仍缺失，`P1-PV-G01` 继续保持 `BLOCKED`。

## 2. Architecture Review Responsibility

| Role | RACI | 最低责任 | 明确不拥有 |
| --- | --- | --- | --- |
| Architecture Review Owner | `A` | 复核 V2.3 层级、职责、依赖、公开边界、Gen2 非映射和 ADR 触发；记录 `APPROVE / REJECT / HOLD` 评审意见 | Phase Scope、实现、商业实验、Release 或风险接受授权 |
| Architecture Change Classifier | `R` | 对变更进行 `No Architecture Change / Architecture Sensitive / ADR Required` 分类并提供依据 | 自行批准存在争议的架构变化 |
| Contract Architecture Reviewers | `R/C` | 分别复核 Application–V5、V5–V4、V4–V3、V3–Compute 的边界一致性 | 具体 Contract Owner 的语义责任或实现许可 |
| Data / Ownership Reviewer | `C` | 复核事实 owner、Asset Return、Rights、最小数据与共享状态风险 | 数据库设计或从层级名称推断数据 owner |
| Repository & Change Control Owner | `C/I` | 核对受影响文档、修订、历史和可重现性 | 架构批准权 |

Architecture Review Owner 的 Person 当前为 `UNASSIGNED`。`ACS-ARF` 仅为候选 Function，必须有 Phase 1 指派与接受记录后才能承担本节责任。

架构评审负责判断候选是否符合 V2.3，不负责授权候选开始实现。即使评审结论为 `APPROVE`，仍必须等待 Scope、Execution、Risk、Contract 和 Gate 的独立决定。

本任务没有新增、删除、映射、拆分、合并或重命名层级和模块，没有改变职责、所有权、接口、依赖方向或技术边界，因此 ADR assessment 为 `NOT TRIGGERED`。

## 3. Implementation Responsibility

实现责任只在具体工作包已经获得独立 Execution Authorization 后生效。当前不存在由本规范授权的 active implementation package。

| Role | RACI | 最低责任 | 当前状态 |
| --- | --- | --- | --- |
| Work Package Owner | `A` | 维护获批文件范围、行为、非目标、停止条件、DoD 和交付决定 | `UNASSIGNED / NO AUTHORIZED PACKAGE` |
| Implementation Responsible | `R` | 只在获批范围内实现，形成 Unit/Contract 及适用证据，及时上报偏差 | `UNASSIGNED / BLOCKED` |
| Application Implementation Owner | `A/R`（仅适用包） | 保持 Application 只依赖 V5 公开边界 | `UNASSIGNED / NOT AUTHORIZED` |
| V5 Implementation Owner | `A/R`（仅适用包） | 保持 V5 范围、公开契约和无 V3 直连 | `UNASSIGNED / NOT AUTHORIZED` |
| V4 Stub Owner | `A/R`（仅适用包） | 管理 Stub 的范围、期限、停止、替换和移除 | `UNASSIGNED / NOT AUTHORIZED` |
| V3 Implementation Owner | `A/R`（仅适用包） | 管理 V3 最小候选、失败、测试、停止与回退 | `UNASSIGNED / NOT AUTHORIZED` |
| Compute Implementation Owner | `A/R`（仅适用包） | 保持最小计算边界，不创建平台化基础设施 | `UNASSIGNED / NOT AUTHORIZED` |

每个层级的 Role 必须按实际工作包分别指派；一个上层 Assignee、Vertical Slice Owner 或 Work Package Owner 不能自动承担 V4、V3 或 Compute 的独立责任和授权。

Implementation Responsible 可以对实现质量负责，但不能批准自己的 Scope、Architecture、风险例外、Release 或 Phase Exit。发现范围、契约、架构、Rights、安全或数据前置缺失时，必须停止并按第 7 节升级，不得以“由我负责”为继续执行的依据。

## 4. Validation Responsibility

### 4.1 Engineering Validation Roles

| Role | RACI | 最低责任 | 职责分离 |
| --- | --- | --- | --- |
| Validation Plan Owner | `A` | 将获批范围映射到 Unit、Contract、Integration、E2E 和 Production Validation 的适用证据 | 不授权实现或环境 |
| Evidence Producer | `R` | 执行已批准验证并记录输入、输出、时间、修订、限制和失败 | 不批准自己的高风险证据 |
| Evidence Reviewer | `A/R` | 独立核对可复现性、候选一致性、限制、`N/A` 和证据状态 | 不修改结果以满足 Gate |
| Change Owner | `A/R` | 维护候选变更、影响范围、修订—契约—证据映射和重新验证触发 | 不批准自己的 Scope、Architecture、风险例外或 Release |
| Gate Coordinator | `R` | 汇总强制证据、阻塞、风险和责任状态 | 不替代 Gate Decision Owner |
| Gate Decision Owner | `A` | 对指定 Engineering Gate 作出允许进入、暂停待决或不允许进入决定 | 不自动授权下一 Gate、Release 或商业投资 |
| Evidence Retention Owner | `R` | 管理 Evidence ID、保留位置、访问、期限和处置 | 不改变证据结论 |

### 4.2 Experiment、Risk 与 Release Roles

| Role | 决定语义 | 不得混同 |
| --- | --- | --- |
| Gen2 Experiment Decision Owner | 基于冻结实验设计作出 `GO / HOLD / STOP` | ACS Engineering Gate、Release 或 Phase Exit 决定 |
| Creative / Editorial Acceptance Owner | 对内容意图、质量和人工发布责任作出人类判断 | Technical Proof 或自动化评分 |
| Risk Owner | 跟踪具体风险、缓解、触发和复核 | Risk Acceptance Authority |
| Risk Acceptance Authority | 在权限上限内接受有期限、可追溯的残余风险 | 风险缓解执行或架构例外批准 |
| Release Decision Owner | 基于候选、工程证据和风险作出 `Proceed / Hold / Exception Approved` | `GO / HOLD / STOP` 商业实验决定 |
| Production Validation Owner | 仅在获批 Release 后执行预先批准的安全技术确认，管理停止条件并报告实际结果 | Release 决定、发布前 E2E 或商业实验 |
| Phase Exit Decision Owner | 由 Phase / Project Owner 在退出上下文中承担最终 `A`，基于全部 Gate、DoD、风险和移交决定 Phase 1 是否退出，并取得适用专项责任人的批准 | 独立于 Phase / Project Owner 的第二个 `A`、单项测试或 Release 决定 |

上述 Role 当前均未形成完整 Person 指派和接受记录。两类 `HOLD` 可能使用相同单词，但所属决定域、证据和权限不同；不得互相替代或推导。

每项 Phase 1 风险都必须单独指定 Risk Owner。Risk Register Custodian 负责同步状态、责任、最近与下次复核点，但不替代 Risk Owner 或 Risk Acceptance Authority。Phase 0 Exit Record 已要求在 `P1-PV-G01` 前同步源风险登记册；该同步责任当前仍为 `UNASSIGNED / BLOCKED`。

任何证据为 `FAIL`、`BLOCKED`、强制 `NOT RUN` 或未经批准的 `N/A` 时，Evidence Owner 必须保留原始状态并升级。责任分配不得被用于修改、隐藏或降级失败证据。

## 5. Documentation Responsibility

| Role | RACI | 最低责任 | 明确边界 |
| --- | --- | --- | --- |
| Document Owner | `A` | 确定用途、权威级别、受众、维护周期和废弃条件 | 不因拥有文档而拥有其描述的系统或业务能力 |
| Record Author | `R` | 准确区分事实、决定、提案、限制和未来事项 | 不能自我授予批准身份 |
| Technical Reviewer | `R/C` | 核对技术陈述、边界、链接和与 Repository 的一致性 | 不替代架构或专项批准 |
| Governance Reviewer | `R/C` | 核对 Role、Gate、状态、风险、授权与变更流程 | 不改写 Repository 事实 |
| Repository / Versioning Custodian | `R` | 维护路径、Git 修订、历史、索引和可重现引用 | 未跟踪文件不得标记为已发布或不可变记录 |
| Document Acceptance Owner | `A` | 基于验收标准决定文档 `ACCEPTED / REJECTED / HOLD` | 文档接受不等于实现或 Release 授权 |

每份 Phase 1 治理、架构、契约、证据和里程碑文档必须记录适用 Role、Assignee、状态、日期和依据。作者姓名、Git author、文件 owner、内容审批人和实现 owner 是不同概念，不得默认等同。

当前由本任务创建的文档只建立责任规范；它不为自身或其他未跟踪文档虚构 Document Acceptance Owner，也不把文件存在解释为已进入可复现治理基线。

## 6. Milestone Ownership

Milestone Ownership 负责陈述已发生的工程事实，不负责追认授权或夸大商业能力。

| Role | RACI | 最低责任 | 不得声明 |
| --- | --- | --- | --- |
| Milestone Owner | `A` | 确认 Milestone ID、任务、目标 Commit、事实范围、限制和更新责任 | Phase Gate、Release 或商业成功自动完成 |
| Evidence Custodian | `R` | 保留 Commit、验证上下文、输出、限制和复验记录 | 未留存证据为正式 `PASS` |
| Technical Assertion Reviewer | `R/C` | 将每项能力声明核对到 Repository 与不可变 Commit | 计划能力、未实现能力或跨 Commit 推断 |
| Investor Readiness Editor | `R` | 以克制语言说明可验证价值、限制和未来扩展 | 投资、收入、PMF、Production Ready 等无证据结论 |
| Milestone Acceptance Owner | `A` | 决定记录是否可进入里程碑索引和发布基线 | 对底层实现、风险或 Release 的独立授权 |

一个 Person 可以在低风险记录中承担多个 Role，但 Milestone Owner/Author 不能独立完成需要专项或独立性的全部评审。目标实现的作者或 Committer 不会自动成为 Milestone Owner，Milestone Owner 也不会自动成为实现 owner。

本规范不对 M001–M004 或未来里程碑作回溯 Person 指派，不改变其 Commit、验证或发布状态。缺少明确 Assignee、接受记录或版本化证据的里程碑继续按实际状态披露。

## 7. Escalation Process

### 7.1 触发条件

出现以下任一情况必须升级：

- 必需 Role 为 `UNASSIGNED`、Assignee 未接受或代理超出期限；
- Scope、Architecture、Contract、Data、Rights、安全、风险或 Gate 前置不完整；
- 两个 Person/Function 对同一决定都声称 `A`，或没有任何 `A`；
- 实际变更超出已批准文件或行为范围；
- Repository 证据与文档、计划、里程碑或声明冲突；
- 出现严重风险、不可逆副作用、敏感数据、凭据、真实用户或生产影响；
- Assignee 存在利益冲突、无法独立评审或拒绝接受责任；
- 需要 V2.3 架构变化、阶段范围扩大或新的 Implementation Authorization。

### 7.2 升级路径

1. **Work Item Level**：由 Work Package Owner 记录事实、立即停止越界动作、指定临时保护措施和解除条件。
2. **Specialist Review Level**：交由 Architecture、Contract、Data、Rights/Security、Validation 或 Documentation 的适用 Role 审查。
3. **Phase Governance Level**：Scope、责任、资源、风险接受或实施权限问题提交 Phase / Project Owner 与对应 Authorization Owner。
4. **Release / Exit Level**：候选、残余风险与 Release 提交各自 Decision Owner；Phase Exit 由 Phase / Project Owner 作为最终 `A`，并取得适用专项责任人的批准。Work Package Owner 不得代决。

每次升级必须记录 Issue ID、发现时间、当前 owner、事实、影响、临时控制、所需决定、目标复核时间、最终决定和证据引用。没有可用 Assignee 时，事项状态为 `BLOCKED`，不得跳过层级继续执行。

紧急情况可以缩短响应时间，但不能创建隐含授权、取消必要评审、允许自我批准或突破 V2.3 与安全边界。

## 8. Conflict Resolution

### 8.1 冲突类型与处理

| 冲突 | 处理原则 | 未解决状态 |
| --- | --- | --- |
| Role 与 Person 混同 | 回到 Assignment 记录，分别确认 Role、Assignee、范围、接受和 Authorization | `BLOCKED` |
| 多个 Accountable Assignee | 由 Phase / Project Owner 指定唯一 `A`，保留其他方为 `R/C/I` 或记录职责拆分 | `BLOCKED` |
| Person 利益冲突或自我评审 | 回避并指定独立 Reviewer/Decision Owner；无法分离时记录补偿控制并取得有权批准 | `BLOCKED` |
| Repository 与文档声明冲突 | Repository source、tests、Git state 与可复现输出决定当前事实；修正文档或声明 | `BLOCKED`，不得夸大 |
| Gen2 Strategy 与 V2.3 Architecture 冲突 | 两者分别保持战略和技术权威；停止实现，提交治理/架构评审，不允许一方静默覆盖另一方 | `BLOCKED` |
| ACS Engineering Gate 与 Gen2 实验决定冲突 | 分别保留两套决定、证据与 owner；任何一方不通过都不能由另一方抵消 | `BLOCKED` |
| Responsibility 与 Authorization 冲突 | Authorization 的明确范围和状态决定能否行动；有责任但无授权时不得执行 | `BLOCKED` |
| 风险 owner 与风险接受权限冲突 | Risk Owner 负责管理，Risk Acceptance Authority 负责接受；不能默认合并 | `BLOCKED` |

### 8.2 决议记录

冲突决议必须包含：争议事实、涉及 Role/Person、各自权限依据、Repository 证据、适用 Charter/V2.3/Governance 规则、备选方案、决定、决定人、日期、有效范围、到期或复核条件及后续文档同步。

若冲突要求改变 V2.3 层级、职责、所有权、接口或依赖方向，必须按 [Architecture Change Process](../../governance/ARCHITECTURE_CHANGE_PROCESS.md) 评估并在需要时创建 ADR。仅建立责任模型、记录空缺和区分权限不改变架构语义，因此本任务不创建 ADR。

### 8.3 当前结论

- Document Status：`DRAFT / REVIEW INPUT / NOT ACCEPTED`。
- Responsibility Model：`DEFINED IN DRAFT / NOT ACCEPTED`。
- Role / Person distinction：`DEFINED`。
- Person Assignment：`INCOMPLETE / UNASSIGNED`。
- Change、Production Validation、Risk、Risk Acceptance、Release、Phase Exit 与 Document Acceptance 等关键责任：`UNASSIGNED`。
- `P1-PV-G01 Authorization`：`BLOCKED`。
- Phase 1 Implementation：`BLOCKED / NOT AUTHORIZED`。

本规范不能被用于把 Role 定义视为 Person 指派、把责任接受视为执行授权、把历史实现视为已追认，或把文档完成视为 Phase 1 已启动。
