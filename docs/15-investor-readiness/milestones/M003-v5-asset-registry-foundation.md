# M003 — V5 Asset Registry Foundation

## 1. Milestone Overview

| 字段 | 已核对事实 |
| --- | --- |
| Milestone ID | `M003` |
| 关联任务 | `ACS-P1-004` |
| 任务名称 | V5 Asset Registry Foundation |
| 架构范围 | V5 Core OS 内部实现 |
| 目标修订 | `e4f1a5d9247119b75e4fe863242cee9a3abe41c1` |
| Commit 时间 | `2026-08-06 21:20:08 +08:00` |
| 记录日期 | `2026-08-06` |
| 工程结论 | 任务授权范围已实现，所记录的 Asset Unit 与 V5 内部包 Contract 命令执行成功 |
| 非结论 | 不代表完整资产管理平台、V5 Core OS、Phase 1、Release 或 Production Validation 已完成 |

目标修订形成了一个 V5 内部、进程内 Asset Registry 基础切片：支持创建 Asset、按 Asset ID 查询、读取 Asset 列表快照、保存宽泛 Asset Type，并在创建时登记一个不可变的初始 Asset Version。该版本能力仅表示初始版本身份登记，不包含后续版本、版本顺序、版本链、latest 或回滚。

本里程碑没有实现 Rights Engine、Provenance Ledger、Vector Search、Embedding、Storage Adapter、Media Processing、Recommendation、文件路径、对象存储、数据库、持久化、网络 API、Application 集成或 Project/Identity Engine 集成。

## 2. Technical Contribution

### 2.1 实现资产

| 资产 | 已实现贡献 |
| --- | --- |
| [Asset Registry](../../../services/v5_core_os/asset_registry/engine.py) | 提供进程内 Asset 创建、按 ID 查询和无排序承诺的列表快照入口 |
| [Asset Models](../../../services/v5_core_os/asset_registry/models.py) | 提供不可变 `Asset`、`AssetVersion` 记录与宽泛 `AssetType` 分类 |
| [Error Surface](../../../services/v5_core_os/asset_registry/errors.py) | 提供输入校验、重复 Asset 和未找到 Asset 的包内错误层次 |
| [Package Surface](../../../services/v5_core_os/asset_registry/__init__.py) | 汇总 V5 内部包可消费的 Registry、模型、分类与错误 |
| [Unit Tests](../../../tests/unit/test_asset_registry.py) | 验证创建、查询、列表、类型、初始版本、不变性、校验、UTC 时间、实例隔离和并发重复创建 |
| [Package Contract Tests](../../../tests/contract/test_asset_registry_contract.py) | 验证 V5 内部包的创建、查询、列表、类型、初始版本身份和错误类型 |

### 2.2 已实现语义

- `Asset` 记录包含调用方提供的 `asset_id`、`asset_type`、`initial_version` 和 UTC `created_at`。
- `AssetVersion` 记录包含调用方提供的不透明 `version_id`、所属 `asset_id` 和 UTC `registered_at`。
- `AssetType` 提供 `IMAGE`、`VIDEO`、`AUDIO`、`TEXT` 与 `OTHER` 五个宽泛分类；它们不表示文件格式、MIME、编码、用途或处理能力。
- Asset ID 在单个 `AssetRegistry` 实例内保持唯一；重复创建返回明确错误，不覆盖既有记录。
- Asset ID 与 Version ID 必须是非空、无空白、可打印且不超过 128 个字符的字符串。
- `get_asset` 对缺失记录返回明确错误；`list_assets` 返回当前实例内容的不可变快照，不承诺排序、分页或过滤。
- Asset 与初始 AssetVersion 均为不可变返回记录；创建时间统一转换为 UTC。
- 重复检查和写入由同一进程内锁保护；所覆盖的并发测试中，同一 Asset ID 的八次并发创建只有一次成功。
- 实现只使用 Python 标准库，没有新增第三方依赖或依赖清单。

以上语义是目标修订的 V5 内部 Python 包事实，不是网络 API、Application → V5 契约、跨引擎一致性证明或最终 Asset 域模型。

## 3. Architecture Impact

- 生产代码变更只新增于 `services/v5_core_os/asset_registry/`。
- 测试变更只新增 `tests/unit/test_asset_registry.py` 与 `tests/contract/test_asset_registry_contract.py`。
- 目标 Commit 未修改 Application Layer、V4 Platform、V3 Render Core、Compute、Foundation、架构文档、数据设计文档或治理文档。
- Asset Registry 不导入 Identity Engine 或 Project Engine，也不访问 V4、V3、Compute、数据库、存储、Worker、网络或外部服务。
- V5 内部包位置只记录本任务的获批实现边界，不批准新的跨层接口、模块依赖或永久目录规则。
- Package Contract Test 只覆盖 V5 内部 Python 包表面，不等于 Application → V5 接口契约或外部服务 API。
- Python 仅是目标 Commit 的实际实现语言和本地验证环境；本记录不形成项目级技术选型。

因此，本里程碑增加了第三个独立 V5 内部基础切片，但没有建立 Identity、Project 与 Asset Registry 的运行时协作，也没有改变 V2.3 的层级、职责、依赖方向或公开边界。

## 4. Data Governance Impact

- 在单个 `AssetRegistry` 实例内，V5 对该实例创建的 Asset ID、宽泛 Asset Type 和初始版本登记事实执行唯一写入裁决。
- 上述权威范围仅存在于当前进程和 Registry 实例，不代表 V5 已成为整个 Asset 数据域、媒体内容或跨实例数据的全局权威来源。
- Asset 与初始 AssetVersion 使用不可变记录；重复 Asset ID 被拒绝，既有登记不会被同 ID 创建静默覆盖。
- Asset ID 与 Version ID 保持不透明，不编码文件路径、存储位置、格式、业务状态、Project、Owner 或权限语义。
- 初始版本记录只保存版本身份、所属 Asset 和登记时间；没有内容绑定、校验和、形成原因、直接前序、版本历史或血缘证据。
- Asset Type 只表达宽泛分类，不能据此推导内容已经存储、可访问、通过验证、拥有使用权或适合任何生产用途。
- 本实现没有定义 Asset 与 Project、Workspace、Identity、Owner、Production、Render 或 Business 数据之间的关系。
- 目标 Commit 没有创建数据库、Schema、存储适配器、数据迁移或数据生命周期状态，也没有修改 V2.3 数据设计文档。

本节记录实际实现对局部数据事实的约束，不新增数据所有权决策，不替代既有数据治理基线，也不批准完整 Asset 生命周期或存储方案。

## 5. Validation Evidence

### 5.1 复验上下文

| 字段 | 记录 |
| --- | --- |
| 目标修订 | `e4f1a5d9247119b75e4fe863242cee9a3abe41c1` |
| 复验时间 | `2026-08-06T21:26:05+08:00` |
| 运行环境 | Windows 工作区；复验解释器版本 `UNVERIFIED`；仅使用 Python 标准库。2026-08-07 审计时 `python` 与 `py` 均只解析到 Python `3.12.4`，该当前观察不能回溯证明 2026-08-06 复验所用版本 |
| 前置状态 | HEAD 精确指向目标修订；跟踪代码与测试无未提交变化；存在前序未跟踪文档 |
| 外部资源 | 未访问网络、数据库、外部服务或生产数据 |

### 5.2 本地执行观察

| 观察项 | 验证目标与方法 | 预期结果 | 实际观察 | 适用边界 |
| --- | --- | --- | --- | --- |
| Asset Unit Test | 执行 `python -m unittest tests.unit.test_asset_registry -q` | Asset Unit Test 全部通过 | 命令执行成功，`17/17` 通过 | 只证明 Asset Registry 包内单元行为 |
| Asset Package Contract Test | 执行 `python -m unittest tests.contract.test_asset_registry_contract -q` | Asset 包契约测试全部通过 | 命令执行成功，`6/6` 通过 | 只证明 V5 内部 Python 包契约，不是网络或 Application → V5 API |
| Current Repository Test Suite | 执行 `python -m unittest discover -s tests -p "test_*.py" -q` | 当前仓库全部已存在测试通过 | 命令执行成功，`66/66` 通过 | 包含 Identity、Project 与 Asset 的 Unit/Package Contract 测试，不是 66 项 Asset 测试 |
| Commit Scope | 检查目标 Commit 的 name-status 与 stat | 改动仅落在获批 Asset Registry 与测试范围 | 6 个新增文件，`489` insertions、`0` deletions | 证明 Commit 文件范围，不证明生产运行行为 |
| Dependency Scope | 检查导入、依赖清单与目标 Commit 文件集 | 不新增未经批准依赖或跨引擎调用 | 仅使用 Python 标准库与 Asset Registry 包内导入；无依赖清单或其他 Engine 依赖 | 不等同于项目级技术栈批准、供应链认证或跨引擎集成验证 |

没有执行 CI、覆盖率、Integration、E2E、性能、安全、部署、Release 或 Production Validation。没有验证媒体内容、持久化、跨实例一致性、Project/Owner 关系、权利、血缘或真实 Application 调用，本节不得用于推导这些能力已经存在。

上述结果是本里程碑编制时的本地执行观察，不是具有正式状态的测试证据记录或 Phase Gate 证据包。命令输出已实际观察，但没有作为独立构建产物提交；仓库中也没有登记本次复验的有权人工评审人、验收责任人或保留责任人。因此，本节不使用正式 `PASS` 状态，只支持目标 Commit 的工程事实快照，不支持正式 Phase、Release 或审计结论。

## 6. Git Information

| 字段 | 值 |
| --- | --- |
| Full SHA | `e4f1a5d9247119b75e4fe863242cee9a3abe41c1` |
| Parent SHA | `5759fc0c6dc91f43ca6cc912e8e76758dc59bd25` |
| Subject | `feat(v5): add asset registry foundation` |
| Task Footer | `Refs: ACS-P1-004` |
| Author / Committer | `linpeng` |
| Author / Commit Date | `2026-08-06 21:20:08 +08:00` |
| Diff Summary | 6 files changed；489 insertions；0 deletions |
| Repository Reachability at Record Time | 存在于 Asset Registry 任务分支及当前文档分支；尚未进入 `main`，没有 Release tag |
| Git Signature | 未检测到 Commit 加密签名 |

该 Commit 新增 4 个 Asset Registry 文件和 2 个测试文件。完整 SHA 是本里程碑的权威修订引用；分支名称只记录编制时仓库状态，不能替代 Commit，也不构成合并、发布或部署证明。目标 Commit 不包含本里程碑文档；Investor Readiness README、M001、M002 与 M003 在本次验收前仍未进入 Git Commit，不能被描述为已发布或不可变的投资者记录。

## 7. Investor Value Statement

M003 提供了第三次范围受控交付的可复核工程信号：ACS 在不扩大 V2.3 层级和依赖边界的前提下，将 Asset 身份、宽泛分类和单个初始版本身份登记落为独立、可运行、可测试的 V5 内部基础切片。任务、实现文件、专项测试、仓库回归和不可变 Commit 之间形成了明确追溯关系。

这一结果进一步说明既有工程治理能够支持连续、小步、边界明确的基础能力交付，降低了“核心基础切片能否继续按授权范围实现并验证”的部分执行不确定性。它不证明完整数字资产管理、媒体生产、跨引擎协作、产品市场匹配、客户采用、收入、生产规模、安全合规、完整 V5 Core OS 或 Phase 1 已经形成，也不构成融资结果或投资回报承诺。

## 8. Known Limitations

1. **未进入主分支或 Release**：目标 Commit 在记录时尚未合并到 `main`，没有 Release tag、Commit 签名或部署证据。
2. **仅进程内状态**：进程重启后 Asset 登记丢失；没有数据库、持久化、迁移、备份或恢复能力。
3. **没有跨实例权威性**：不同 Registry 实例相互隔离，不提供跨进程唯一性、复制、一致性或冲突裁决。
4. **仅登记初始版本**：没有新增后续版本、版本顺序、版本历史、latest、回滚、合并或分支语义。
5. **版本不绑定内容**：没有内容指纹、校验和、形成原因、直接前序或媒体对象引用，不能证明两个版本的内容差异或来源。
6. **分类能力有限**：五个 Asset Type 只是宽泛标签，不包含 MIME、格式、编码、用途、质量或处理路由。
7. **没有内容或存储能力**：未实现上传、下载、文件路径、对象存储、Storage Adapter、媒体解析、处理或可用性验证。
8. **没有跨域关联**：未实现 Project、Workspace、Identity、Owner、Production、Render 或 Business 关系与存在性校验。
9. **没有权利与血缘能力**：未实现 Rights Engine、Provenance Ledger、血缘、保留、归档或处置治理。
10. **没有搜索或智能能力**：未实现 Vector Search、Embedding、Recommendation 或内容相似性能力。
11. **列表能力有限**：没有排序承诺、分页、过滤、搜索、调用者范围或权限隔离。
12. **仅内部包契约**：Contract Test 验证 V5 内部 Python 包，不是网络 API、Application → V5 或跨引擎契约。
13. **验证层级有限**：Asset 专项只有 17 项 Unit 与 6 项 Package Contract；未执行 CI、覆盖率、Integration、E2E、性能、安全或 Production Validation。
14. **没有权限和多租户能力**：未实现认证、授权、Permission、RBAC、Tenant 或 Enterprise 隔离。
15. **复验解释器版本未验证 / 技术栈尚未批准**：未版本化草案曾记录 Python `3.12.13`，但没有提交日志或构建产物支持该版本；2026-08-07 审计只观察到当前 Python `3.12.4`，该结果不能回溯证明 2026-08-06 的复验环境。因此精确复验版本为 `UNVERIFIED`，且不构成仓库级技术选型结论。
16. **非独立审计意见**：本记录提供仓库内工程事实，不替代外部技术尽调、正式审计或有权责任人的 Release/Phase 批准。
17. **记录时未修改全局状态文档；后续一致性同步已完成**：M003 任务未修改仓库根 README；后续 Commit `a1a3b9a098bfd7212ec7841e6261218305308c36`（`ACS-DOC-BASELINE-001`）已同步入口文档与当前仓库事实。该后续文档变更不修改 M003 目标 Commit，也不解除 Phase 1 Gate 或产生 Implementation Authorization。
18. **里程碑文档尚未版本化**：Investor Readiness README、M001、M002 与 M003 在本次验收前仍未进入 Git Commit，不能被描述为已发布或不可变记录。

## 9. Future Expansion

以下事项只是继续提高证据成熟度所需的治理候选，不是已批准范围、路线图承诺、预算、排期或技术决策：

- 完成评审后按仓库治理流程决定是否将目标 Commit 合并到 `main` 并建立可追溯 Release 身份；
- 仅在 Asset 数据责任、存储抽象、迁移、备份与恢复责任独立获批后，另行评估持久化能力；
- 仅在版本身份、内容绑定、变化原因、前序关系和并发规则独立获批后，扩展初始版本登记之外的版本能力；
- 在 Asset 与 Project、Workspace、Identity 或 Owner 的关系契约获批后，另行实现并验证跨引擎一致性；
- 在 Application → V5 具体契约获批后，另行实现并验证跨层入口；
- Rights、Provenance、Storage、媒体处理、搜索与智能能力必须分别经过后续任务授权，不由本里程碑推导；
- 在真实相邻组件和受控环境存在后，补充 Integration、E2E、性能、安全与 Production Validation 证据；
- 通过独立文档提交将 Investor Readiness README 与 M001–M003 纳入版本控制，形成可追溯文档修订；
- 仅在后续工作真实完成并绑定不可变 Commit 后，新增下一条投资者就绪里程碑记录。

任何扩展都必须遵守 V2.3 相邻依赖方向和现有治理流程。本节不批准 ADR、架构变化、数据库、技术栈、API、权限系统、商业功能或 Phase 退出。
