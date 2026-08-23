# ADR-0001 — Separate Commercial Experience Layer from Core Creator Runtime

## 文档元数据

| 字段 | 内容 |
| --- | --- |
| ADR ID | `ADR-0001` |
| Title | Separate Commercial Experience Layer from Core Creator Runtime |
| Status | `Accepted` — final acceptance recorded; checkpoint and implementation authorization remain pending |
| 提案执行 | Codex，依据 `PRE-M6-RB1` 任务整理 |
| 创建日期 | `2026-08-11` |
| 最后更新日期 | `2026-08-11` |
| 项目负责人 | 蔺鹏 |
| Architecture Owner | 蔺鹏 |
| Independent Interface & Testing Governance Reviewer | ChatGPT |
| Independent Review Decision | `ACCEPT` |
| Repository Governance Owner | 蔺鹏 |
| Repository Governance Decision | `ACCEPT` |
| Final Acceptance Date | `2026-08-11` |
| 关联事项 | `PRE-M6-RB1 — Core / Frontend Source-of-Truth Rebaseline` |
| Supersedes | 无既有 ADR；精确候选替代清单见“Supersession Inventory”，仅在本 ADR 后续 Accepted 且形成 remote-verified checkpoint 后生效 |
| Superseded by | 无 |

## ADR ID

`ADR-0001`

仓库此前只有 `governance/ADR_TEMPLATE.md`，没有已分配 ADR 编号，因此本记录
使用首个连续编号。

## Title

Separate Commercial Experience Layer from Core Creator Runtime

## Status

`Accepted`

Project Lead、Architecture Owner 与 Repository Governance Owner 蔺鹏已于
`2026-08-11` 接受 ADR-0001；Independent Interface & Testing Governance
Reviewer ChatGPT 的独立审查结论为 `ACCEPT`。本次接受仅适用于 ADR-0001 的
架构决策，不创建 remote-verified checkpoint，不授权 RB1.2、Legacy UI 删除、
运行时代码、跨仓库集成实现或 M6。`P3-RV1-003` 继续作为非阻塞 EOL 审计债务；
`M6 ≠ V5 Identity Lock`。

## Context

Core 仓库当前同时包含：

- Creator Server Runtime 与公开 HTTP/API；
- Creator Application、V5、V4、V3、Compute/Foundation 和持久化；
- 历史客户浏览器 UI `apps/creator-workspace-mvp`。

现有 `ONE CREATOR UI` 规则曾要求所有 Creator UI 修改进入 Core Creator Server
Runtime。这在 UI-R1、UI-R2 和 UI-R2A 阶段避免了平行静态产品，但商业客户
Project Lead 的拟议方向把现有独立仓库 `AI-Cinematic-Studio-Frontend` 指定为
未来唯一 Commercial Frontend 源码真源。该指定仍以本 ADR 后续接受为生效条件。
如果 Core 同时继续维护客户 UI，将形成第二套 Commercial SaaS 体验真源，并使
前后端职责、Browser Gate 和跨仓库合同不清晰。

本决策只改变 Experience Layer 的仓库归属和验证边界。以下保持不变：

- Project First 与 Production Spine；
- V2.3 Core 依赖方向；
- V5/V4/V3、Compute/Foundation 的所有权；
- Creator Application 的公开合同责任；
- Backend-issued Ref、Version 和 Lineage 权威；
- M1–M3 已接受 Domain/Application 能力；
- M4 — Project Context Foundation：`ACCEPTED`；
- M5 — Series Planning + Series Director：`ACCEPTED`；
- M6 `NOT STARTED / NOT AUTHORIZED`。

不在本 ADR 当前实施范围：

- 删除任何 UI 或混合 Server 文件；
- 修改运行时代码、API、数据模型或持久化；
- 修改独立 Frontend 仓库；
- 实现 Cross-Repo Integration Gate；
- 设计或实现 M6。

## Decision

### 1. Repository responsibilities

| Repository / Layer | Proposed authoritative responsibilities | Explicit exclusions |
| --- | --- | --- |
| `AI-Cinematic-Studio-Frontend` | Commercial SaaS customer pages, routes, experience adapters, presentation state, responsive/accessibility/visual behavior and customer workflow QA | Core source imports, Domain/SQL/Provider/private V5/GPU/ComfyUI access |
| Core `AI Cinematic Studio` | Creator Server Runtime, Creator Public HTTP/API, Creator Application, Domain, V5, V4, V3, Compute/Foundation integration, persistence, infrastructure and backend/application/domain tests | A second customer-facing Commercial SaaS experience layer |

### 2. ONE CREATOR UI reinterpretation

If this ADR is later accepted, there remains exactly ONE customer-facing Creator UI:

```text
AI-Cinematic-Studio-Frontend
```

Under that conditional decision, `ONE CREATOR UI` no longer means the customer UI
source must live in Core. It means
there must be one Commercial experience implementation, consuming one authoritative
Core through public contracts.

### 3. Proposed dependency boundary

```text
Commercial Frontend
↓
Frontend Experience Adapter
↓
Creator Public HTTP/API
↓
Creator Application
↓
V5
↓
V4
↓
V3
↓
Compute/Foundation
```

Canonical form:
`Commercial Frontend → Frontend Experience Adapter → Creator Public HTTP/API → Creator Application → V5 → V4 → V3 → Compute/Foundation`

The Experience Layer is outside the V2.3 Core six-layer chain. This decision does not
insert a new layer between Application and V5 and does not change any Core dependency
direction.

The Frontend Experience Adapter belongs to the Frontend repository and may consume
only Creator Public HTTP/API. Frontend must not access Creator Application, Domain,
SQL, Persistence, Provider, private V5, GPU, Worker or ComfyUI directly. Core must not
recreate a customer Commercial UI, and the repositories do not share customer UI
source code.

### 4. Creator Server responsibility

Creator Server remains the Core HTTP runtime owner. It must continue to expose stable,
testable, sanitized public HTTP/API behavior for Creator Application commands, queries,
authorization, workspace/tenant enforcement, persistence and error contracts.

If this ADR is later accepted, serving a customer-facing Commercial UI is no longer a
required Core responsibility. During migration Core may temporarily serve historical
static files, but those files do not remain an accepted customer product entry after
decommission completion.

### 5. Legacy UI decommission policy

`apps/creator-workspace-mvp` is a `DECOMMISSION CANDIDATE`, not an authorized whole-
directory deletion target.

Later decommission may remove only files proven to be UI-only, such as customer pages,
page layouts, page-only CSS/assets/tests and presentation-only client state.

It must preserve Creator Server/API handlers, Application services, commands, queries,
DTOs, auth, Domain, ports/adapters, persistence, migrations and backend tests. Mixed
files are `AMBIGUOUS_SHARED_FILE` until safely classified or mechanically separated.

### 6. Browser Gate replacement

- **Gate A — Frontend Experience Gate:** separate Frontend tests, build, real-browser
  QA, responsive, accessibility, visual quality and customer workflows.
- **Gate B — Core HTTP Runtime Gate:** Creator Server startup, public HTTP/API,
  Application behavior, authorization, tenant/workspace, persistence, idempotency,
  integration and error contracts.
- **Gate C — Cross-Repo Integration Gate:** future verification that the real Frontend
  consumes the real Creator Public HTTP/API without shared source imports.

This ADR defines Gate C's boundary only. It does not implement Gate C.

### 7. Verification of the decision

The rebaseline is correctly implemented only when:

1. active authority documents contain no unresolved old Core-customer-UI rule;
2. the later decommission inventory proves every removed file is UI-only;
3. Gate B passes after removal;
4. no second customer browser UI remains in Core;
5. public Core contracts remain available without Frontend source imports;
6. the future Gate C verifies the deployed Frontend/Core integration.

## Alternatives

### 方案 A：保持 Core 内 Creator UI 为唯一客户 UI

- 概述：继续在 Core 中开发、测试并由 Creator Server 提供客户 UI。
- 优点：单仓库本地集成简单；既有 UI-R2A 证据可直接复用。
- 缺点：与已建立的独立 Commercial Frontend 形成双重体验真源。
- 风险与约束：UI 演进分叉、Browser Gate 重复、Core 职责膨胀。
- 拟不采纳原因：违反 Project Lead 提出的仓库责任方向。

### 方案 B：将 Creator Server/Application 一并迁入 Frontend 仓库

- 概述：让独立 Frontend 同时拥有页面和后端运行时。
- 优点：表面上形成单一部署单元。
- 缺点：破坏 Core 的 Application/V5/V4/V3 责任和仓库权威。
- 风险与约束：Domain 私有依赖泄漏、密钥/持久化暴露、Production Spine
  权威分裂。
- 未采纳原因：违反 V2.3、Provider、Persistence 和 Domain ownership 规则。

### 方案 C：Experience Layer 与 Core Runtime 分仓（选择）

- 概述：Frontend 独立拥有客户体验，Core 独立拥有公开 HTTP/API 和生产事实。
- 优点：职责明确、技术可独立演进、可通过公开合同做跨仓集成。
- 缺点：需要正式 API 成熟度、跨仓版本兼容和新的 Gate C。
- 风险与约束：迁移期可能出现旧 UI 残留或隐藏源代码耦合。
- 选择原因：保持一个客户 UI，同时保护 Core Production Spine 和权威边界。

## Consequences

### 正向影响

- Commercial UX 有唯一源码真源。
- Core 专注 Creator Runtime、Application、Domain 与平台能力。
- Frontend/Core 可通过公开合同独立测试、版本化和部署。
- Legacy UI 清理可以使用显式库存，降低误删 API/Server 的风险。

### 负向影响与成本

- 需要维护公开 HTTP/API 兼容性和 Frontend/Core 版本矩阵。
- 原 Core browser tests 需要分类为 UI-only 或 API/application tests。
- 必须建立未来 Gate C，不能再把同仓源码导入视为集成。

### 风险

| Risk ID | 风险 | 触发条件 | 责任人 | 处置 |
| --- | --- | --- | --- | --- |
| `R-P0-GOV-002` | 实现或目录先于决策落地，可能隐式修改 V2.3 架构或臆造未来模块 | ADR 仍为 Proposed 时删除 UI、修改 Runtime、启动 Gate C、进入 M6，或在公开合同获批前复制 DTO/Domain、绕过公开 API；RB1.2 未证明 `UI_ONLY=YES` 即删除混合 UI/Server 文件也是该风险的具体触发场景 | Architecture Owner 蔺鹏；适用迁移/合同 Owner 在对应阶段指定 | 立即停止未授权实现或删除；恢复到只读/文档候选及公开合同边界；误删时恢复文件并复验 Gate B；重新执行架构评审 |
| `R-P0-GOV-003` | 治理文档之间术语、门禁或责任定义不一致，可能使执行者采用冲突规则 | 同一事项出现不同 Source-of-Truth 顺序、跨仓链、阶段名、角色、强制级别或 M6 状态 | 治理维护人（接受前必须指定）；Project Lead / Architecture Owner 蔺鹏协调 | 阻止 checkpoint；对受影响治理文件执行交叉引用、一致性 reconciliation 和独立复审 |
| `R-P0-GOV-004` | 责任人或审批权限未正式指定，可能导致 ADR、例外或风险接受停滞或被无权人员批准 | 审批表仍有必需角色未指定、无结论日期或无可追溯接受证据 | Project Lead 蔺鹏 | ADR 保持 Proposed；书面指定必需专项责任人并补齐身份、结论、日期和证据后重审 |
| `R-P0-GOV-006` | 分支保护、评审或验证门禁未实际执行，可能使治理要求停留在文档层面 | 缺少独立 review、required checks、受保护分支/合并证据或 remote SHA 验证 | Repository Governance Owner 蔺鹏 | 不允许把候选提交为正式基线；补齐评审、强制检查、checkpoint 与 remote verification 证据 |

上述四行只引用 `governance/RISK_REGISTER.md` 中既有中央风险语义。混合
UI/Server 误删与 Frontend 复制 DTO/Domain 均作为“实现或目录先于决策落地”
这一中央风险的具体触发场景，不创建第二条中央风险记录，不新增或复用其他
风险编号，也不表示任何中央风险已经关闭。

### 受影响资产

- 架构文档：System Master Plan、UI Master Plan、AGENTS、CURRENT_MILESTONE、
  `architecture/system-context.md`、`architecture/system-overview.md`。
- 接口或契约：当前不修改；后续 Gate C 必须以现有/新增公开合同独立评审。
- 测试与质量门禁：Browser Gate 拆为 Gate A/B/C。
- 安全、运维或发布规则：Frontend 禁止持有 Provider Secret 或绕过 Core。
- 其他：历史 UI-R1/UI-R2/UI-R2A 作为迁移前证据保留。

## Migration Plan

严格路线：

`PRE-M6-RB1.1 Source-of-Truth Rebaseline`
→ `PRE-M6-RB1.2 Legacy UI Decommission`
→ `PRE-M6-RB1.3 Full Core Current-State Audit`
→ `Architecture Review`
→ `M6 Preconditions`
→ `M6-P1`

| 阶段 | Owner | 目标时点 | 完成判据 | 沟通对象 |
| --- | --- | --- | --- | --- |
| `PRE-M6-RB1.1 Source-of-Truth Rebaseline` | Project Lead / Architecture Owner 蔺鹏；ChatGPT — Independent Interface & Testing Governance Reviewer（ChatGPT，独立接口与测试治理审查） | ADR-0001 已 Accepted；checkpoint 授权评审待进行；无日历承诺 | 七权威文件一致、接受决定已记录；后续另行取得 remote-verified checkpoint，本 ADR 不自行授权 RB1.2 | Project Lead、Architecture Owner、Repository Governance Owner、Core/Frontend leads |
| `PRE-M6-RB1.2 Legacy UI Decommission` | RB1.2 Migration Owner，进入前由 Project Lead 指定 | 仅在 RB1.1 获得接受与 remote verification 后 | 逐文件分类 `UI_ONLY`、`SERVER/API`、`SHARED`、`AMBIGUOUS`；只删除 `UI_ONLY=YES`；Gate B 通过 | Core Runtime、Application、Test、Frontend owners |
| `PRE-M6-RB1.3 Full Core Current-State Audit` | Core Audit Owner，进入前由 Project Lead 指定 | 仅在 RB1.2 关闭后 | 代码优先盘点 M1–M5、V5/V4/V3、Compute、Persistence、安全、租户与 M6 接触面；Phase 0 漂移明确处置 | Project Lead、Architecture Owner、Core owners |
| `Architecture Review` | Architecture Owner 蔺鹏及适用专项 reviewer | RB1.3 evidence 完整后 | 架构、接口、测试、安全与迁移证据形成明确结论 | Project Lead、Core/Frontend contract owners |
| `M6 Preconditions` | Project Lead 蔺鹏 | Architecture Review 通过后 | M6 owner、合同、数据 lineage、测试、回滚与非目标获得明确批准 | M6 owners、Core/Frontend owners |
| `M6-P1` | 后续授权文件指定 | 仅在新的 `CURRENT_MILESTONE.md` 明确授权后 | 不由本 ADR 或本次文档候选定义 | Project Lead 与执行团队 |

兼容策略：在 RB1.2 关闭前，Legacy UI 文件仍保留为 `DECOMMISSION CANDIDATE`，
但不得作为新客户 UI 真源。旧责任规则的停止使用和归档时点是：本 ADR 后续
成为 Accepted、权威文档形成 remote-verified checkpoint，且 RB1.2 库存给出
逐文件迁移决定之后。当前仅处于 RB1.1 修订阶段，不执行删除、Runtime 变更、
Gate C 或 M6。

## Rollback Considerations

- PRE-COMMIT 阶段：直接放弃未提交文档 diff；运行时和 Git HEAD 未改变。
- 文档 checkpoint 后、UI 删除前：恢复旧架构责任规则必须先通过新的 Accepted
  ADR。该 ADR 获得所需审批后，才可用受控 revert/new commit 执行其决定；禁止
  仅通过裸 `git revert` 恢复旧规则，也不得静默编辑 Accepted ADR。
- UI 删除后：从删除前 remote-verified commit 恢复 UI-only 文件；Server/API
  文件不应被删除，因此 Core 数据和 Application 合同无需回滚。
- 若 Gate B 失败：停止迁移，保留失败证据，恢复误删文件，不推进 Gate C/M6。
- 该决策不包含数据迁移，因此不得执行数据库 rollback 或 destructive reset。

## M6 Prerequisite Impact

M6 仍为 `NOT STARTED / NOT AUTHORIZED`。M6-P1 之前必须完成：

1. 本 ADR 和权威文档获得正式接受并 remote-verified；
2. Legacy Core customer UI 安全退役；
3. Gate B 通过；
4. 完整 Core 当前态审计；
5. Project Lead 架构评审；
6. M6 prerequisites 和 M6-P1 独立批准。

M6 Character Intelligence 至少包含 background、motivation、belief、conflict、
goal、personality、behavior rules、dialogue rules、forbidden behavior、
visual identity rules、`CharacterState`、`RelationshipContext`、timeline and
continuity。

`M6 ≠ V5 Identity Lock`。M6 不实现 M7、GPU Render、ComfyUI、Worker 或跨仓 UI。

## Supersession Inventory

下表只描述本 ADR 已 Accepted 且后续形成 remote-verified checkpoint 时的精确
替代范围；当前尚未授权 checkpoint，因此本次接受不使任何旧规则立即失效。

| 文件 | 候选替代章节/规则 | 生效条件 |
| --- | --- | --- |
| `AGENTS.md` | `# 19. UI Architecture Authority`、`# 20. One Creator UI Rule`、`# 33. Browser / Live Gate` 中 Core 作为客户 UI 源码真源的旧解释 | ADR Accepted + remote-verified authority checkpoint |
| `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md` | `# 30. Creator UI 总体结构`、`# 33. Architecture Layers`、客户 UI 仓库归属与 Gate 解释 | 同上 |
| `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md` | `# 0.1 UI Source-of-Truth Repository`、运行时/验收规则、Browser Gate 与 Legacy UI 规则 | 同上 |
| `CURRENT_MILESTONE.md` | 当前 PRE-M6 阶段、责任链、Legacy 状态、Gate A/B/C 与 M6 entry gates | 同上；且 CURRENT 只控制当前执行状态 |
| `architecture/system-context.md` | Experience Layer 与 Core 六层链的关系 | 同上 |
| `architecture/system-overview.md` | `apps/` 交付层与独立 Commercial Frontend 的仓库责任 | 同上 |

旧规则将在 RB1.2 逐文件库存完成后进入历史/归档证据；不得删除其 Git 历史或
把历史状态改写为当时已采用新架构。

## Acceptance Authority and Evidence Requirements

ADR 从 Proposed 变为 Accepted 的决策证据已记录：

1. Project Lead 蔺鹏的可识别接受结论与日期；
2. Architecture Owner 蔺鹏的架构接受结论与日期；
3. Independent Interface & Testing Governance Reviewer ChatGPT 对 Gate A/B/C、
   Creator Public HTTP/API 及相关合同与测试门禁的 `ACCEPT` 结论；
4. Repository Governance Owner 蔺鹏的 `ACCEPT` 结论与日期。

ADR 接受不等于 checkpoint 授权。候选替代规则生效、RB1.2 进入或任何
后续实施仍须另行获得 checkpoint 授权，并完成七文件稳定性证据、
accepted commit、GitHub push、fetch、local/remote SHA 相等及
Repository Governance Owner 的 checkpoint 流程确认。

## 审批记录

| 角色 | 审批人 | 结论 | 日期 | 备注 |
| --- | --- | --- | --- | --- |
| 项目负责人 | 蔺鹏 | `REVIEW COMPLETED / ACCEPT` | `2026-08-11` | 仅接受 ADR-0001；不授权 checkpoint、RB1.2 或 M6 |
| 架构责任人 | 蔺鹏 | `REVIEW COMPLETED / ACCEPT` | `2026-08-11` | Architecture Owner 接受 ADR-0001；不表示 checkpoint 或后续实施已获授权 |
| 接口/测试专项责任 | ChatGPT — Independent Interface & Testing Governance Reviewer / ChatGPT（独立接口与测试治理审查） | `REVIEW COMPLETED / ACCEPT` | `2026-08-11` | Independent Review Decision: `ACCEPT`；仅适用于 ADR-0001 与 PRE-M6-RB1.1；不拥有 Repository 写入/合并、checkpoint 或 M6 授权权 |
| Repository Governance Owner | 蔺鹏 | `REVIEW COMPLETED / ACCEPT` | `2026-08-11` | Repository Governance Decision: `ACCEPT`；仅接受 ADR-0001，checkpoint、RB1.2 与 M6 仍未授权 |

## 变更历史

| 日期 | 修改人 | 变更内容 | 审批依据 |
| --- | --- | --- | --- |
| `2026-08-11` | Codex | 创建 ADR-0001 PRE-COMMIT 候选 | `PRE-M6-RB1` Project Lead task |
| `2026-08-11` | Codex | 按独立复审 findings 修订合同、风险、迁移、supersession 与接受条件；保持 Proposed | `PRE-M6-RB1-R1`；Project Lead / Architecture Owner 身份由蔺鹏确认 |
| `2026-08-11` | Codex | 同步 M5 治理状态并按中央 Risk Register 唯一语义重整风险引用；保持 Proposed | `PRE-M6-RB1.1-R2`；RV1 P1-RV1-001 / P1-RV1-002 |
| `2026-08-11` | Codex | 依据项目负责人授权记录接口/测试专项责任人与 Repository Governance Owner；两项均为 `DESIGNATED / REVIEW PENDING`，未作审批结论，ADR 保持 Proposed | `Core PRE-M6-RB1.1 — Governance Role Designation Record` |
| `2026-08-11` | Codex | 记录 Independent Interface & Testing Governance Reviewer、Repository Governance Owner、Project Lead 与 Architecture Owner 的 `ACCEPT` 决定；ADR-0001 状态更新为 Accepted，checkpoint / RB1.2 / M6 仍未授权 | `Core PRE-M6-RB1.1 — ADR-0001 Final Acceptance Record` |
