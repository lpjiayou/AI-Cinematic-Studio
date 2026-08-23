# M001 — V5 Identity Engine Foundation

## 1. Milestone Overview

| 字段 | 已核对事实 |
| --- | --- |
| Milestone ID | `M001` |
| 关联任务 | `ACS-P1-002` |
| 任务名称 | V5 Identity Engine Foundation |
| 架构范围 | V5 Core OS 内部实现 |
| 目标修订 | `d439e3cd894b6f91d0f161e28b92b080e589c5f6` |
| Commit 时间 | `2026-08-06 19:59:41 +08:00` |
| 记录日期 | `2026-08-06` |
| 工程结论 | 任务授权范围已实现，所记录的 Unit 与 V5 内部包 Contract 命令执行成功；该结果仅为本地观察，不使用正式 `PASS` 状态 |
| 非结论 | 不代表 V5 Core OS、Phase 1、Release 或 Production Validation 已完成 |

目标修订实现了三个最小能力：Identity 创建与查询、Workspace 创建与查询、既有 Identity 与 Workspace 之间的基础 Ownership Reference 创建与查询。Ownership Reference 只表示引用关系，不授予权限、访问权或权威数据所有权。

本里程碑没有实现认证、授权、RBAC、OAuth、SSO、Billing、Enterprise Tenant、权限系统、数据库、持久化、网络 API、Application 集成或下层调用。

## 2. Technical Contribution

### 2.1 实现资产

| 资产 | 已实现贡献 |
| --- | --- |
| [Identity Engine](../../../services/v5_core_os/identity_engine/engine.py) | 提供进程内 Identity、Workspace 与 Ownership Reference 的创建和查询入口 |
| [Immutable Models](../../../services/v5_core_os/identity_engine/models.py) | 提供不可变的 `Identity`、`Workspace`、`OwnershipReference` 返回记录 |
| [Error Surface](../../../services/v5_core_os/identity_engine/errors.py) | 提供输入校验、重复记录和未找到记录的包内错误层次 |
| [Package Surface](../../../services/v5_core_os/identity_engine/__init__.py) | 汇总 V5 内部包可消费的类型与错误 |
| [Unit Tests](../../../tests/unit/test_identity_engine.py) | 验证正常路径、重复、缺失、校验、不变性、实例隔离、UTC 时间与并发重复创建 |
| [Package Contract Tests](../../../tests/contract/test_identity_engine_contract.py) | 验证 V5 内部包的创建、查询、返回类型和错误契约 |

### 2.2 已实现语义

- Identity 与 Workspace 使用调用方提供的不透明标识符，并返回 UTC 时间戳记录。
- Identity 和 Workspace 标识符在各自进程内状态中保持唯一。
- Ownership Reference 以 `Identity ID + Workspace ID` 组合为关联键；创建前要求两端记录均已存在。
- 重复 Ownership Reference 创建会返回明确错误，不产生第二条关联。
- 返回记录不可变；状态由单个 `IdentityEngine` 实例隔离并保存在进程内。
- 并发重复 Identity 创建通过锁保护；所覆盖测试中只有一次创建成功。
- 实现只使用 Python 标准库，没有新增第三方依赖或依赖清单。

以上语义是目标修订的包内实现事实，不是 Application → V5 的公开 API、跨层数据契约或项目级技术选型。

## 3. Architecture Impact

- 生产代码变更只位于 `services/v5_core_os/identity_engine/` 及必要的 Python 包标记文件。
- 测试变更只位于 `tests/unit/` 与 `tests/contract/`。
- 目标 Commit 未修改 Application Layer、V4 Platform、V3 Render Core、Compute、Foundation、架构文档或治理文档。
- 实现不依赖 V4、V3、Compute、Application、存储、数据库、Worker 或外部服务。
- `services/v5_core_os/` 是本任务的物理放置位置；本记录不将其外推为所有 V5 模块的永久目录规则。
- Ownership Reference 不声明 V5 自动拥有 Identity、Workspace 或任何既有数据域。
- 本里程碑没有改变 V2.3 的层级、职责、相邻依赖方向或公开边界。
- Python 仅是目标 Commit 的实际实现语言和本地验证环境；仓库尚未通过独立技术选型记录批准项目级运行时。

因此，本里程碑提供的是 V5 内部最小实现证据，不是架构变更、技术决策或跨层接口批准。

## 4. Validation Evidence

### 4.1 复验上下文

| 字段 | 记录 |
| --- | --- |
| 目标修订 | `d439e3cd894b6f91d0f161e28b92b080e589c5f6` |
| 复验时间 | `2026-08-06T20:04:12+08:00` 至 `2026-08-06T20:04:13+08:00` |
| 运行环境 | Windows 工作区；复验解释器版本 `UNVERIFIED`；仅使用 Python 标准库。2026-08-07 审计时 `python` 与 `py` 均只解析到 Python `3.12.4`，该当前观察不能回溯证明 2026-08-06 复验所用版本 |
| 前置状态 | HEAD 精确指向目标修订；工作树在文档任务开始前洁净 |
| 外部资源 | 未访问网络、数据库、外部服务或生产数据 |

### 4.2 本地执行观察

| 观察项 | 验证目标与方法 | 预期结果 | 实际观察 | 适用边界 |
| --- | --- | --- | --- | --- |
| Unit Test | 执行 `python -m unittest discover -s tests/unit -p "test_*.py" -v` | 所有 Unit Test 通过 | 命令执行成功，`16/16` 通过 | 只证明 Identity Engine 包内单元行为 |
| Package Contract Test | 执行 `python -m unittest discover -s tests/contract -p "test_*.py" -v` | 所有包契约测试通过 | 命令执行成功，`6/6` 通过 | 只证明 V5 内部 Python 包契约，不是 Application → V5 API |
| Current Test Suite | 执行 `python -m unittest discover -s tests -p "test_*.py" -v` | 当前仓库全部已存在测试通过 | 命令执行成功，`22/22` 通过 | 当前测试集合只包含上述 Unit 与 Package Contract 测试 |
| Commit Scope | 检查目标 Commit 的 name-status 与 stat | 改动仅落在获批 V5 与测试范围 | 13 个文件，`680` insertions、`3` deletions；仅涉及 `services/`、`tests/unit/`、`tests/contract/` | 证明 Commit 文件范围，不证明运行时生产行为 |
| Dependency Scope | 检查导入、依赖清单与目标 Commit 文件集 | 不新增未经批准依赖 | 仅使用 Python 标准库与包内导入；无依赖清单变更 | 不等同于项目级技术栈批准或供应链认证 |

没有执行 Integration、E2E、性能、安全、部署、Release 或 Production Validation。本节不得用于推导这些验证已经通过。

上述结果是本里程碑编制时的本地执行观察，不是具有正式状态的测试证据记录或 Phase Gate 证据包。命令输出已在文档任务中实际观察，但没有作为独立构建产物提交；仓库中也没有登记本次复验的有权人工评审人、验收责任人或保留责任人。因此，本节不使用正式 `PASS` 状态，只支持目标 Commit 的工程事实快照，不支持正式 Phase、Release 或审计结论。

## 5. Commit Information

| 字段 | 值 |
| --- | --- |
| Full SHA | `d439e3cd894b6f91d0f161e28b92b080e589c5f6` |
| Parent SHA | `5b970ae6ed7d9a30b90a882f46b3df88dbe6be10` |
| Subject | `feat(services): add V5 identity engine foundation` |
| Task Footer | `Refs: ACS-P1-002` |
| Author / Committer | `linpeng` |
| Author / Commit Date | `2026-08-06 19:59:41 +08:00` |
| Diff Summary | 13 files changed；680 insertions；3 deletions |
| Repository Reachability at Record Time | 存在于任务分支及其后继文档分支；尚未进入 `main`，没有 Release tag |
| Git Signature | 未检测到 Commit 加密签名 |

10 个文件由该 Commit 新增；3 个用于保留空目录的 `.gitkeep` 在实际实现和测试文件落位后删除。完整 SHA 是本里程碑的权威修订引用；分支名称只记录当时仓库状态，不能替代 Commit。

## 6. Investor Value Statement

M001 提供了一个可复核的工程执行信号：ACS 已把既有治理约束转化为范围受控的 V5 内部实现，并将任务、代码位置、自动化测试、限制和不可变 Commit 建立了明确追溯关系。该结果降低了“仓库治理是否能够落到可运行、可测试实现”的局部执行不确定性。

这一价值陈述仅适用于 ACS-P1-002 的交付纪律和最小技术基础。它不证明产品市场匹配、客户采用、收入能力、商业化成熟度、生产规模、可用性、安全合规、完整身份平台或完整 V5 Core OS 已经形成，也不构成投资回报承诺。

## 7. Known Limitations

1. **未进入主分支或 Release**：目标 Commit 在记录时尚未合并到 `main`，没有 Release tag，也没有部署证据。
2. **仅进程内状态**：进程重启后 Identity、Workspace 和 Ownership Reference 状态丢失；没有数据库、持久化或迁移能力。
3. **仅内部包契约**：Contract Test 验证 V5 内部 Python 包，不是 Application → V5 网络/API 契约。
4. **验证层级有限**：只有 16 项 Unit 与 6 项 Package Contract 测试；未执行 Integration、E2E、Production Validation、性能或安全验证。
5. **没有身份安全能力**：未实现认证、授权、RBAC、OAuth、SSO、Billing、Enterprise Tenant 或权限系统。
6. **没有生产运行能力证明**：未提供部署、配置、可观测性、容量、可用性、备份、恢复或故障演练证据。
7. **复验解释器版本未验证 / 技术栈尚未批准**：未版本化草案曾记录 Python `3.12.13`，但没有提交日志或构建产物支持该版本；2026-08-07 审计只观察到当前 Python `3.12.4`，该结果不能回溯证明 2026-08-06 的复验环境。因此精确复验版本为 `UNVERIFIED`，且不构成仓库级技术选型结论。
8. **Ownership 语义受限**：当前只记录 Identity 与 Workspace 的引用关联，不代表权限、访问权或权威数据所有权。
9. **记录时全局状态文档未同步；后续已关闭**：在 2026-08-06 本记录编制时，仓库根 README 仍描述 Phase 0 空服务基线；该入口文档差异已由 2026-08-07 Commit `a1a3b9a098bfd7212ec7841e6261218305308c36`（`ACS-DOC-BASELINE-001`）同步。该后续文档变更不修改 M001 目标 Commit，也不解除 Phase 1 Gate 或产生 Implementation Authorization。
10. **非独立审计意见**：本记录提供仓库内工程证据，不替代外部技术尽调、正式审计或有权责任人的 Release/Phase 批准。

## 8. Future Expansion

以下事项只是继续提高证据成熟度所需的治理候选，不是已批准范围、路线图承诺或技术决策：

- 完成评审后按仓库治理流程决定是否将目标 Commit 合并到 `main` 并建立可追溯 Release 身份；
- 通过独立技术选型记录或 ADR 决定项目级语言与运行时，再扩展实现；
- 在 Application → V5 具体契约获批后，另行实现并验证跨层入口；
- 在数据所有权、存储抽象和迁移责任获批后，另行评估持久化能力；
- 在实际相邻组件与受控环境存在后，补充 Integration、E2E、性能、安全与 Production Validation 证据；
- 仅在后续工作真实完成并绑定不可变 Commit 后，新增下一条投资者就绪里程碑记录。

任何扩展都必须遵守 V2.3 相邻依赖方向和现有治理流程。本节不批准架构变化、数据库、技术栈、API、认证系统、商业功能或 Phase 退出。
