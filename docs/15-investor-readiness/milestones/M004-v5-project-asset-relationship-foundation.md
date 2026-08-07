# M004 — V5 Project Asset Relationship Foundation

## 1. Milestone Overview

| 字段 | 已核对事实 |
| --- | --- |
| Milestone ID | `M004` |
| 关联任务 | `ACS-P1-005` |
| 任务名称 | V5 Project Asset Relationship Foundation |
| 架构范围 | V5 Core OS 内部实现 |
| 目标修订 | `139024327ea9cfcd7328f7a5b4ac385fb1e1a1ea` |
| Commit 时间 | `2026-08-06 21:43:57 +08:00` |
| 记录日期 | `2026-08-06` |
| 工程结论 | 任务授权范围已实现，所记录的 Relationship Unit 与 V5 内部包 Contract 命令执行成功 |
| 非结论 | 不代表真实跨引擎集成、完整 Project/Asset 系统、V5 Core OS、Phase 1、Release 或 Production Validation 已完成 |

目标修订形成了一个 V5 内部、进程内 Project-Asset Relationship 基础切片：使用不可变的 `project_id + asset_id` 关系记录表达“Project 使用 Asset”，支持 Attach Asset、按 Project 查询关系以及按 Asset 反向查询关系。相同 ID pair 的重复 Attach 被明确拒绝，不会覆盖既有关系。

本里程碑没有实现 Project 或 Asset 存在性校验、Ownership、Rights、Permission、Provenance、Version Selection、Render Binding、Workflow、数据库、持久化、网络 API、Application 集成或真实 Project Engine / Asset Registry 协作。

## 2. Technical Contribution

### 2.1 实现资产

| 资产 | 已实现贡献 |
| --- | --- |
| [Relationship Engine](../../../services/v5_core_os/project_asset_relationship/engine.py) | 提供进程内 Attach Asset 与两个方向的关系快照查询 |
| [Relationship Model](../../../services/v5_core_os/project_asset_relationship/models.py) | 提供只包含不透明 Project ID 与 Asset ID 的不可变关系记录 |
| [Error Surface](../../../services/v5_core_os/project_asset_relationship/errors.py) | 提供输入校验与重复 Project-Asset pair 的包内错误层次 |
| [Package Surface](../../../services/v5_core_os/project_asset_relationship/__init__.py) | 汇总 V5 内部包可消费的 Engine、模型与错误 |
| [Unit Tests](../../../tests/unit/test_project_asset_relationship.py) | 验证 Attach、双向查询、重复关系、快照、不变性、校验、实例隔离与并发重复 Attach |
| [Package Contract Tests](../../../tests/contract/test_project_asset_relationship_contract.py) | 验证 V5 内部包的 Attach、双向查询、空查询、重复和错误类型 |

### 2.2 已实现语义

- `ProjectAssetRelationship` 只包含调用方提供的 `project_id` 与 `asset_id`，两个字段均为不透明引用。
- `(project_id, asset_id)` 是单个 Engine 实例内的关系键；相同 pair 重复 Attach 返回专用错误，不覆盖或新增第二条关系。
- `attach_asset` 只登记“Project 使用 Asset”这一关系事实，不解析任一引用，也不读取或修改 Project、Asset 记录。
- `list_project_assets` 返回指定 Project ID 的关系快照；`list_asset_projects` 返回指定 Asset ID 的关系快照。
- 两类列表均不承诺排序、分页、过滤或权限隔离；无匹配关系时返回空快照。
- 不同 pair 可以同时登记，因此当前包可以观察到一个 Project 对多个 Asset、一个 Asset 对多个 Project 的关系；这不构成 V2.3 全局基数定义。
- Project ID 与 Asset ID 必须是非空、无空白且可打印的字符串；实现没有规定 ID 格式或生成方式。
- 关系记录不可变；重复检查与写入由同一进程内锁保护。所覆盖测试中，相同 pair 的八次并发 Attach 只有一次成功。
- 实现只使用 Python 标准库和本包导入，没有新增第三方依赖、依赖清单或其他 Engine import。

以上语义是目标修订的 V5 内部 Python 包事实，不是网络 API、Application → V5 契约、真实跨引擎集成或最终 Project/Asset 域关系模型。

## 3. Architecture Impact

- 生产代码变更只新增于 `services/v5_core_os/project_asset_relationship/`。
- 测试变更只新增 `tests/unit/test_project_asset_relationship.py` 与 `tests/contract/test_project_asset_relationship_contract.py`。
- 目标 Commit 未修改 Identity Engine、Project Engine、Asset Registry、Application Layer、V4 Platform、V3 Render Core、Compute、Foundation、架构文档、数据设计文档或治理文档。
- Relationship Engine 不导入 Project Engine 或 Asset Registry，也不访问 Identity、V4、V3、Compute、数据库、存储、Worker、网络或外部服务。
- V5 内部包位置只记录本任务的获批实现边界，不批准新的跨层接口、跨 Engine 依赖或永久目录规则。
- Package Contract Test 只覆盖 V5 内部 Python 包表面，不等于 Application → V5、网络或跨服务接口契约。
- Python 仅是目标 Commit 的实际实现语言和本地验证环境；本记录不形成项目级技术选型。

因此，本里程碑增加了第四个范围受控的 V5 内部基础切片，但没有改变 V2.3 的层级、职责、相邻依赖方向或公开边界，也没有把不透明关系登记提升为运行时组件集成。

## 4. Data Governance Impact

- 在单个 `ProjectAssetRelationshipEngine` 实例内，V5 只对该实例登记的 `(project_id, asset_id)` 使用关系事实执行重复裁决。
- 该局部关系事实不使 Relationship Engine 取得 Project 或 Asset 核心语义的所有权，也不建立整个 Project、Asset 数据域或跨实例关系的全局权威来源。
- 两个 ID 保持不透明；代码不验证被引用 Project 或 Asset 是否存在、处于何种状态或来自哪个实例。
- 关系只表达“Project 使用 Asset”，不表达 Ownership、Rights、Permission、Provenance、Version Selection、内容可用性或处理授权。
- 不可变关系与重复拒绝避免同一实例内相同 pair 被静默覆盖；实现没有时间戳、历史、变更原因或审计证据。
- 空查询只能说明当前实例没有匹配关系，不能区分“引用实体不存在”和“实体存在但没有关系”。
- 当前包允许多个不同 pair 并存，但这一观察结果不批准最终多对多基数、级联规则或关系生命周期。
- 目标 Commit 没有数据库、Schema、存储适配、迁移、detach、删除传播、归档或处置能力，也没有修改 V2.3 数据所有权记录。

本节只记录获批最小实现对局部关系事实的约束，不新增 Project 或 Asset 所有权决策，不宣称引用完整性，也不替代既有数据治理基线。

## 5. Validation Evidence

### 5.1 复验上下文

| 字段 | 记录 |
| --- | --- |
| 目标修订 | `139024327ea9cfcd7328f7a5b4ac385fb1e1a1ea` |
| 复验时间 | `2026-08-06T21:47:43+08:00` |
| 运行环境 | Windows 工作区；复验解释器版本 `UNVERIFIED`；仅使用 Python 标准库。2026-08-07 审计时 `python` 与 `py` 均只解析到 Python `3.12.4`，该当前观察不能回溯证明 2026-08-06 复验所用版本 |
| 前置状态 | HEAD 精确指向目标修订；跟踪代码与测试无未提交变化；存在前序未跟踪文档 |
| 外部资源 | 未访问网络、数据库、外部服务或生产数据 |

### 5.2 本地执行观察

| 观察项 | 验证目标与方法 | 预期结果 | 实际观察 | 适用边界 |
| --- | --- | --- | --- | --- |
| Relationship Unit Test | 执行 `python -m unittest tests.unit.test_project_asset_relationship -q` | Relationship Unit Test 全部通过 | 命令执行成功，`14/14` 通过 | 只证明 Relationship Engine 包内单元行为 |
| Relationship Package Contract Test | 执行 `python -m unittest tests.contract.test_project_asset_relationship_contract -q` | Relationship 包契约测试全部通过 | 命令执行成功，`6/6` 通过 | 只证明 V5 内部 Python 包契约，不是网络、Application → V5 或跨 Engine API |
| Current Repository Test Suite | 执行 `python -m unittest discover -s tests -p "test_*.py" -q` | 当前仓库全部已存在测试通过 | 命令执行成功，`86/86` 通过 | 包含 Identity、Project、Asset 与 Relationship 的 Unit/Package Contract 测试，不是 86 项 Relationship 测试 |
| Commit Scope | 检查目标 Commit 的 name-status 与 stat | 改动仅落在获批 Relationship 与测试范围 | 6 个新增文件，`432` insertions、`0` deletions | 证明 Commit 文件范围，不证明生产运行行为 |
| Dependency Scope | 检查导入、依赖清单与目标 Commit 文件集 | 不新增未经批准依赖或跨 Engine 调用 | 仅使用 Python 标准库与本包导入；无依赖清单、Project Engine 或 Asset Registry import | 不等同于项目级技术栈批准、供应链认证或跨 Engine 集成验证 |

没有执行 CI、覆盖率、Integration、E2E、性能、安全、部署、Release 或 Production Validation。没有验证引用实体存在性、跨实例一致性、权限、权利、版本、关系生命周期或真实 Application 调用，本节不得用于推导这些能力已经存在。

上述结果是本里程碑编制时的本地执行观察，不是具有正式状态的测试证据记录或 Phase Gate 证据包。命令输出已实际观察，但没有作为独立构建产物提交；仓库中也没有登记本次复验的有权人工评审人、验收责任人或保留责任人。因此，本节不使用正式 `PASS` 状态，只支持目标 Commit 的工程事实快照，不支持正式 Phase、Release 或审计结论。

## 6. Git Information

| 字段 | 值 |
| --- | --- |
| Full SHA | `139024327ea9cfcd7328f7a5b4ac385fb1e1a1ea` |
| Parent SHA | `e4f1a5d9247119b75e4fe863242cee9a3abe41c1` |
| Subject | `feat(v5): add project asset relationship foundation` |
| Task Footer | `Refs: ACS-P1-005` |
| Author / Committer | `linpeng` |
| Author / Commit Date | `2026-08-06 21:43:57 +08:00` |
| Diff Summary | 6 files changed；432 insertions；0 deletions |
| Repository Reachability at Record Time | 存在于 Relationship 任务分支及当前文档分支；尚未进入 `main`，没有 Release tag |
| Git Signature | 未检测到 Commit 加密签名 |

该 Commit 新增 4 个 Project-Asset Relationship 文件和 2 个测试文件。完整 SHA 是本里程碑的权威修订引用；分支名称只记录编制时仓库状态，不能替代 Commit，也不构成合并、发布或部署证明。目标 Commit 不包含本里程碑文档；Investor Readiness README、M001、M002、M003 与 M004 在本次验收前仍未进入 Git Commit，不能被描述为已发布或不可变的投资者记录。

## 7. Investor Value Statement

M004 提供了第四次范围受控交付的可复核工程信号：ACS 在不扩大 V2.3 层级和依赖边界的前提下，将“Project 使用 Asset”这一最小关系语义落为独立、可运行、可测试的 V5 内部基础切片。任务、实现文件、专项测试、仓库回归和不可变 Commit 之间形成了明确追溯关系。

这一结果说明既有工程治理可以支持在不合并 Project 与 Asset 核心语义、不引入跨 Engine 依赖的情况下增加显式关系登记与双向查询，进一步降低了“跨域关系基础能否按授权边界实现”的部分执行不确定性。它不证明真实 Project/Asset 集成、统一资产图谱、生产流程贯通、产品市场匹配、客户采用、收入、生产规模、安全合规、完整 V5 Core OS 或 Phase 1 已经形成，也不构成融资结果或投资回报承诺。

## 8. Known Limitations

1. **未进入主分支或 Release**：目标 Commit 在记录时尚未合并到 `main`，没有 Release tag、Commit 签名或部署证据。
2. **仅进程内状态**：进程重启后关系丢失；没有数据库、持久化、迁移、备份或恢复能力。
3. **没有跨实例一致性**：不同 Engine 实例相互隔离，不提供跨进程唯一性、复制、冲突裁决或全局关系视图。
4. **不解析引用实体**：不验证 Project 或 Asset 是否存在、是否归档、是否可用或是否属于同一运行上下文，可能登记悬空引用。
5. **空查询存在歧义**：空结果无法区分实体不存在与实体存在但没有关系。
6. **关系语义有限**：只表示“Project 使用 Asset”，不证明实际内容被访问、处理、生产使用或验证。
7. **没有所有权与访问语义**：不表达 Ownership、Rights、Permission、Provenance、授权或 Tenant 隔离。
8. **没有版本选择**：关系不包含 Asset Version，不选择或验证任何初始、当前或历史版本。
9. **没有关系生命周期**：未实现 detach、update、删除、归档、恢复、级联或处置传播。
10. **没有历史和审计时间**：模型没有时间戳、变更原因、操作身份或历史记录，不能用于审计关系何时形成。
11. **查询能力有限**：没有排序承诺、分页、复合过滤、搜索或权限范围；当前实现通过实例内关系扫描完成双向查询。
12. **标识符没有长度上限**：只校验字符串、空白与可打印性；公开暴露前需要重新评估资源与最小披露边界。
13. **重复操作不是幂等成功**：重复 Attach 返回错误，没有幂等键、结果重放或安全重试契约。
14. **局部多关系不定义全局基数**：本包允许不同 pair 并存，但不构成最终多对多关系、唯一性或级联规则。
15. **仅内部包契约**：Contract Test 验证 V5 内部 Python 包，不是网络 API、Application → V5 或跨 Engine 契约。
16. **验证层级有限**：Relationship 专项只有 14 项 Unit 与 6 项 Package Contract；未执行 CI、覆盖率、Integration、E2E、性能、安全或 Production Validation。
17. **没有权限和多租户能力**：方法没有 actor、认证、授权、RBAC、Tenant 或调用者范围参数。
18. **复验解释器版本未验证 / 技术栈尚未批准**：未版本化草案曾记录 Python `3.12.13`，但没有提交日志或构建产物支持该版本；2026-08-07 审计只观察到当前 Python `3.12.4`，该结果不能回溯证明 2026-08-06 的复验环境。因此精确复验版本为 `UNVERIFIED`，且不构成仓库级技术选型结论。
19. **非独立审计意见**：本记录提供仓库内工程事实，不替代外部技术尽调、正式审计或有权责任人的 Release/Phase 批准。
20. **里程碑文档尚未版本化**：Investor Readiness README、M001、M002、M003 与 M004 在本次验收前仍未进入 Git Commit，不能被描述为已发布或不可变记录。

## 9. Future Expansion

以下事项只是继续提高证据成熟度所需的治理候选，不是已批准范围、路线图承诺、预算、排期或技术决策：

- 完成评审后按仓库治理流程决定是否将目标 Commit 合并到 `main` 并建立可追溯 Release 身份；
- 仅在 Project、Asset 与关系事实的责任边界、引用完整性和公开查询契约独立获批后，评估存在性校验；
- 仅在跨 Engine 依赖方向和公开包面独立获批后，实施真实 Project Engine / Asset Registry 协作并增加 Integration 验证；
- 仅在关系生命周期、时间语义、历史、审计、删除传播与冲突规则获批后，扩展 Attach 之外的变化能力；
- 在关系数据责任、存储抽象、迁移、备份与恢复责任获批后，另行评估持久化能力；
- 在 Application → V5 具体契约获批后，另行实现并验证跨层入口；
- Rights、Permission、Provenance、Version Selection、Render Binding 与 Workflow 必须分别经过后续任务授权，不由本里程碑推导；
- 在真实相邻组件和受控环境存在后，补充 Integration、E2E、性能、安全与 Production Validation 证据；
- 通过独立文档提交将 Investor Readiness README 与 M001–M004 纳入版本控制，形成可追溯文档修订；
- 仅在后续工作真实完成并绑定不可变 Commit 后，新增下一条投资者就绪里程碑记录。

任何扩展都必须遵守 V2.3 相邻依赖方向和现有治理流程。本节不批准 ADR、架构变化、数据库、技术栈、API、权限系统、商业功能或 Phase 退出。
