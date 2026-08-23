# M002 — V5 Project Engine Foundation

## 1. Milestone Overview

| 字段 | 已核对事实 |
| --- | --- |
| Milestone ID | `M002` |
| 关联任务 | `ACS-P1-003` |
| 任务名称 | V5 Project Engine Foundation |
| 架构范围 | V5 Core OS 内部实现 |
| 目标修订 | `5759fc0c6dc91f43ca6cc912e8e76758dc59bd25` |
| Commit 时间 | `2026-08-06 20:49:10 +08:00` |
| 记录日期 | `2026-08-06` |
| 工程结论 | 任务授权范围已实现，所记录的 Project Unit 与 V5 内部包 Contract 命令执行成功 |
| 非结论 | 不代表完整 Project 系统、V5 Core OS、Phase 1、Release 或 Production Validation 已完成 |

目标修订实现了最小 Project Engine：Project 创建、按 ID 查询、列表读取、不透明 Workspace 与 Owner 引用，以及 `ACTIVE → ARCHIVED` 生命周期变化。归档后的 Project 保持同一 Project ID 并仍可查询；归档不是删除、权限变化或完整生命周期治理。

本里程碑没有实现 Asset 绑定、Production Plan、Job、Render、Workflow、Permission、RBAC、数据库、持久化、网络 API、跨引擎集成或 Application 集成。

## 2. Technical Contribution

### 2.1 实现资产

| 资产 | 已实现贡献 |
| --- | --- |
| [Project Engine](../../../services/v5_core_os/project_engine/engine.py) | 提供进程内 Project 创建、查询、列表快照和归档入口 |
| [Project Model](../../../services/v5_core_os/project_engine/models.py) | 提供不可变 `Project` 记录与最小 `ProjectLifecycleState` |
| [Error Surface](../../../services/v5_core_os/project_engine/errors.py) | 提供输入校验、重复 Project、未找到 Project 和非法生命周期变化错误 |
| [Package Surface](../../../services/v5_core_os/project_engine/__init__.py) | 汇总 V5 内部包可消费的 Project 类型、Engine 与错误 |
| [Unit Tests](../../../tests/unit/test_project_engine.py) | 验证创建、查询、列表、引用保留、生命周期、错误、不变性、时间和实例隔离 |
| [Package Contract Tests](../../../tests/contract/test_project_engine_contract.py) | 验证 V5 内部包的稳定创建、查询、列表、引用、生命周期与错误类型 |

### 2.2 已实现语义

- `Project` 记录包含 `project_id`、`workspace_id`、`owner_identity_id`、生命周期状态以及 UTC 创建和更新时间。
- Project ID 由调用方提供，并在单个 Project Engine 实例内保持唯一。
- `workspace_id + owner_identity_id` 共同保存不透明 Owner Reference 上下文；本包不解析或验证外部对象是否存在。
- 新建 Project 的初始状态为 `ACTIVE`；该状态仅表示尚未归档，不表示任何生产、执行或业务活动。
- `archive_project` 只允许 `ACTIVE → ARCHIVED`；重复归档产生明确生命周期错误。
- 归档保留 Project ID、Workspace 引用、Owner 引用和创建时间，并更新 `updated_at`。
- `list_projects` 返回当前记录的不可变快照，不承诺排序、分页、过滤或权限隔离语义。
- 实现只使用 Python 标准库，没有新增第三方依赖或依赖清单。

以上语义是目标修订的 V5 内部包事实，不是网络 API、Application → V5 契约、跨引擎一致性证明或最终 Project 域模型。

## 3. Architecture Impact

- 生产代码变更只位于 `services/v5_core_os/project_engine/`。
- 测试变更只新增 `tests/unit/test_project_engine.py` 与 `tests/contract/test_project_engine_contract.py`。
- 目标 Commit 未修改 Application Layer、V4 Platform、V3 Render Core、Compute、Foundation、架构文档或治理文档。
- Project Engine 不导入或调用 Identity Engine，不访问 V4、V3、Compute、存储、数据库、Worker 或外部服务。
- Workspace 与 Owner 只是不透明引用；代码位置和字段名称不证明 V5 是整个 Project 数据域的权威 owner。
- Identity Engine 的 Workspace 不等于 Application Layer 页面名称 “Project Workspace”，本记录不推导二者实体同一性或基数关系。
- `ACTIVE → ARCHIVED` 是 ACS-P1-003 的局部最小授权，不改变 V2.3 数据设计基线，也不批准最终生命周期模型。
- Python 仅是目标 Commit 的实际实现语言和本地验证环境；仓库尚未批准项目级运行时。

因此，本里程碑记录的是第二个独立 V5 内部基础切片，不建立 Identity Engine 与 Project Engine 的运行时协作，也不改变 V2.3 的层级、依赖方向、公开边界或数据所有权。

## 4. Validation Evidence

### 4.1 复验上下文

| 字段 | 记录 |
| --- | --- |
| 目标修订 | `5759fc0c6dc91f43ca6cc912e8e76758dc59bd25` |
| 复验时间 | `2026-08-06T20:52:47+08:00` |
| 运行环境 | Windows 工作区；复验解释器版本 `UNVERIFIED`；仅使用 Python 标准库。2026-08-07 审计时 `python` 与 `py` 均只解析到 Python `3.12.4`，该当前观察不能回溯证明 2026-08-06 复验所用版本 |
| 前置状态 | HEAD 精确指向目标修订；源代码和测试文件与目标 Commit 一致；存在前序未跟踪文档 |
| 外部资源 | 未访问网络、数据库、外部服务或生产数据 |

### 4.2 本地执行观察

| 观察项 | 验证目标与方法 | 预期结果 | 实际观察 | 适用边界 |
| --- | --- | --- | --- | --- |
| Project Unit Test | 执行 `python -m unittest tests.unit.test_project_engine -q` | Project Unit Test 全部通过 | 命令执行成功，`15/15` 通过 | 只证明 Project Engine 包内单元行为 |
| Project Package Contract Test | 执行 `python -m unittest tests.contract.test_project_engine_contract -q` | Project 包契约测试全部通过 | 命令执行成功，`6/6` 通过 | 只证明 V5 内部 Python 包契约，不是网络或 Application → V5 API |
| Current Repository Test Suite | 执行 `python -m unittest discover -s tests -p "test_*.py" -q` | 当前仓库全部已存在测试通过 | 命令执行成功，`43/43` 通过 | 包含 Identity 与 Project 的 Unit/Package Contract 测试，不是 43 项 Project 测试 |
| Commit Scope | 检查目标 Commit 的 name-status 与 stat | 改动仅落在获批 Project Engine 与测试范围 | 6 个文件，`464` insertions、`0` deletions | 证明 Commit 文件范围，不证明生产运行行为 |
| Dependency Scope | 检查导入、依赖清单与目标 Commit 文件集 | 不新增未经批准依赖或跨引擎调用 | 仅使用 Python 标准库与 Project 包内导入；无依赖清单或 Identity Engine 依赖 | 不等同于项目级技术栈批准、供应链认证或跨引擎集成验证 |

没有执行 CI、覆盖率、Integration、E2E、性能、安全、部署、Release 或 Production Validation。Workspace 和 Owner 引用的外部存在性也没有验证，本节不得用于推导这些能力或验证已经完成。

上述结果是本里程碑编制时的本地执行观察，不是具有正式状态的测试证据记录或 Phase Gate 证据包。命令输出已实际观察，但没有作为独立构建产物提交；仓库中也没有登记本次复验的有权人工评审人、验收责任人或保留责任人。因此，本节不使用正式 `PASS` 状态，只支持目标 Commit 的工程事实快照，不支持正式 Phase、Release 或审计结论。

## 5. Git Information

| 字段 | 值 |
| --- | --- |
| Full SHA | `5759fc0c6dc91f43ca6cc912e8e76758dc59bd25` |
| Parent SHA | `d439e3cd894b6f91d0f161e28b92b080e589c5f6` |
| Subject | `feat(services): add V5 project engine foundation` |
| Task Footer | `Refs: ACS-P1-003` |
| Author / Committer | `linpeng` |
| Author / Commit Date | `2026-08-06 20:49:10 +08:00` |
| Diff Summary | 6 files changed；464 insertions；0 deletions |
| Repository Reachability at Record Time | 存在于 Project Engine 任务分支及其后继文档分支；尚未进入 `main`，没有 Release tag |
| Git Signature | 未检测到 Commit 加密签名 |

该 Commit 新增 4 个 Project Engine 文件和 2 个测试文件。完整 SHA 是本里程碑的权威修订引用；分支名称只记录编制时仓库状态，不能替代 Commit，也不构成合并、发布或部署证明。目标 Commit 不包含本里程碑文档；README、M001 与 M002 在本次验收前仍为未跟踪文件，需要通过独立文档 Commit 才能形成版本化记录。

## 6. Investor Value Statement

M002 提供了第二次范围受控交付的可复核工程信号：ACS 在不扩大 V2.3 层级和依赖边界的前提下，将 Project 创建、读取、列表和最小生命周期落为独立、可运行、可测试的 V5 内部基础切片。任务、实现文件、局部测试、仓库回归和不可变 Commit 之间形成了明确追溯关系。

这一结果说明既有工程治理能够再次转化为局部实现与自动化验证，降低了“后续核心基础能力是否能按边界递增交付”的部分执行不确定性。它不证明完整项目管理、跨引擎协作、产品市场匹配、客户采用、收入、生产规模、安全合规、完整 V5 Core OS 或 Phase 1 已经形成，也不构成投资回报承诺。

## 7. Known Limitations

1. **未进入主分支或 Release**：目标 Commit 在记录时尚未合并到 `main`，没有 Release tag、Commit 签名或部署证据。
2. **仅进程内状态**：进程重启后 Project 状态丢失；没有数据库、持久化、迁移、备份或恢复能力。
3. **引用不解析**：`workspace_id` 与 `owner_identity_id` 只做本地格式校验，不证明对应 Workspace、Identity 或 Ownership Reference 实际存在。
4. **引用不授权**：Owner Reference 不表示权限、访问权、成员关系、Tenant 或权威数据所有权。
5. **生命周期有限**：只有 `ACTIVE → ARCHIVED`；没有恢复、删除、暂停、完成、自定义状态或完整生命周期治理。
6. **列表能力有限**：没有排序承诺、分页、Workspace/Owner 过滤、搜索或权限隔离。
7. **仅内部包契约**：Contract Test 验证 V5 内部 Python 包，不是网络 API、Application → V5 或跨引擎契约。
8. **验证层级有限**：Project 专项只有 15 项 Unit 与 6 项 Package Contract；未执行 Integration、E2E、性能、安全或 Production Validation。
9. **没有业务扩展**：未实现 Asset、Production Plan、Job、Render、Workflow 或相关跨域关系。
10. **没有权限和多租户能力**：未实现 Permission、RBAC、认证、授权或 Enterprise Tenant。
11. **复验解释器版本未验证 / 技术栈尚未批准**：未版本化草案曾记录 Python `3.12.13`，但没有提交日志或构建产物支持该版本；2026-08-07 审计只观察到当前 Python `3.12.4`，该结果不能回溯证明 2026-08-06 的复验环境。因此精确复验版本为 `UNVERIFIED`，且不构成仓库级技术选型结论。
12. **记录时全局状态文档未同步；后续已关闭**：在 2026-08-06 本记录编制时，仓库根 README 仍描述 Phase 0 空服务基线；该入口文档差异已由 2026-08-07 Commit `a1a3b9a098bfd7212ec7841e6261218305308c36`（`ACS-DOC-BASELINE-001`）同步。该后续文档变更不修改 M002 目标 Commit，也不解除 Phase 1 Gate 或产生 Implementation Authorization。
13. **非独立审计意见**：本记录提供仓库内工程事实，不替代外部技术尽调、正式审计或有权责任人的 Release/Phase 批准。
14. **没有调用者范围控制**：`list_projects` 返回当前 Engine 实例中的全部记录；创建、查询、列表和归档都没有 actor 或授权参数。
15. **没有版本或审计历史**：模型没有 revision、转换历史或归档时间字段；时钟单调性也未验证，时间戳不能充当完整审计记录。
16. **公开暴露前仍需输入与错误评审**：标识符没有长度上限，部分包内错误文本包含 Project ID；当前没有网络 API，但未来对外暴露前必须重新评估最小披露和输入边界。
17. **归档不是幂等操作**：重复归档会产生生命周期错误，不会返回已有归档结果。
18. **里程碑文档尚未版本化**：Investor Readiness README、M001 与 M002 在本次验收前仍未进入 Git Commit，不能被描述为已发布或不可变的投资者记录。

## 8. Future Expansion

以下事项只是继续提高证据成熟度所需的治理候选，不是已批准范围、路线图承诺、预算、排期或技术决策：

- 完成评审后按仓库治理流程决定是否将目标 Commit 合并到 `main` 并建立可追溯 Release 身份；
- 仅在层内协作边界独立获批后，验证 Workspace、Identity 与 Owner Reference 的真实跨引擎一致性；
- 在 Project 数据责任、存储抽象、迁移和恢复责任获批后，另行评估持久化能力；
- 在 Application → V5 具体契约获批后，另行实现并验证跨层入口；
- 只有在新的生命周期语义、所有者和转换规则获批后，才扩展 `ACTIVE → ARCHIVED` 之外的状态；
- 在真实相邻组件和受控环境存在后，补充 Integration、E2E、性能、安全与 Production Validation 证据；
- 仅在后续工作真实完成并绑定不可变 Commit 后，新增下一条投资者就绪里程碑记录。

任何扩展都必须遵守 V2.3 相邻依赖方向和现有治理流程。本节不批准 ADR、架构变化、数据库、技术栈、API、权限系统、商业功能或 Phase 退出。
