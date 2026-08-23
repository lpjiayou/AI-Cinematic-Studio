# 测试资产

本目录承载 AI Cinematic Studio 当前已跟踪的测试资产。Unit Test 与 Contract Test 已存在；Integration 与 E2E 目前仅保留目录骨架。

测试存在和本地执行结果只证明对应仓库修订的有限工程事实，不自动通过 Phase Gate，也不授予 Implementation、Integration、Release 或 Production 权限。

## 1. 目录结构

```text
tests/
├── README.md
├── unit/
│   ├── __init__.py
│   ├── test_identity_engine.py
│   ├── test_project_engine.py
│   ├── test_asset_registry.py
│   └── test_project_asset_relationship.py
├── contract/
│   ├── __init__.py
│   ├── test_identity_engine_contract.py
│   ├── test_project_engine_contract.py
│   ├── test_asset_registry_contract.py
│   └── test_project_asset_relationship_contract.py
├── integration/
│   └── .gitkeep
└── e2e/
    └── .gitkeep
```

## 2. Unit Test

`tests/unit/` 已包含四个 V5 Core OS Foundation 包的单元测试：

| 测试文件 | 当前验证范围 |
| --- | --- |
| `test_identity_engine.py` | Identity、Workspace、Ownership Reference 的创建、查询、校验、重复与缺失行为 |
| `test_project_engine.py` | Project 创建、查询、列表、引用、最小生命周期及异常行为 |
| `test_asset_registry.py` | 旧进程内 Asset Registry 的 fail-closed 退役行为；唯一 AssetVersion authority 位于 Episode Production evidence journal |
| `test_project_asset_relationship.py` | Project–Asset 关联、双向查询、重复关系和校验行为 |

Unit Test 验证包内最小行为，不证明网络 API、数据库、跨引擎协作或 Production 行为。

## 3. Contract Test

`tests/contract/` 已包含与上述四个包对应的契约测试：

| 测试文件 | 当前验证范围 |
| --- | --- |
| `test_identity_engine_contract.py` | Identity Engine 包的公开导出、创建/查询及错误层级 |
| `test_project_engine_contract.py` | Project Engine 包的公开导出、引用、生命周期及错误层级 |
| `test_asset_registry_contract.py` | 兼容包仍可导入、但所有 authority 操作均拒绝并指向 canonical authority |
| `test_project_asset_relationship_contract.py` | Relationship 包的公开导出、关联、查询及重复关系契约 |

这些 Contract Test 验证当前 Python 包边界，不等同于 Application–V5、V5–V4、V4–V3 或 V3–Compute 的跨层接口验收。

## 4. Integration 与 E2E

`tests/integration/` 与 `tests/e2e/` 包含跨边界与端到端测试；其中 K2
Creator HTTP 测试覆盖真实 public contract、BFF 所依赖的资源路径和状态投影。
真实 Chromium 的 Creator→BFF→Core HTTP gate 位于唯一 Frontend 仓库，Core
仓库不复制第二套浏览器栈。测试通过也不等同于外部系统、真实用户流量或
Production Validation。

未来新增这些测试必须具有独立授权、明确候选、受控输入、责任人和符合治理标准的证据。

## 5. 当前运行方式

当前 Unit 与 Contract 测试使用 Python 标准库测试能力，不需要安装第三方测试框架：

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

运行前应确认目标 Commit 和工作区状态。为避免本地字节码缓存，可在受控环境中禁用字节码写入；这不是测试通过的必要语义条件。

## 6. 证据边界

- 测试结果必须绑定准确 Commit、执行上下文、实际结果、时间和责任人；
- 本地命令退出成功不能单独构成正式 `PASS` Evidence；
- 强制测试缺失时应记录 `BLOCKED`、`NOT RUN` 或经批准的 `N/A`，不能静默跳过；
- Unit、Contract、Integration、E2E 和 Production Validation 不能互相替代；
- 测试不能用于追认未授权实现、修改 V2.3 架构或扩大 Phase 1 范围。

测试层级、Gate 和证据规则见：

- [测试治理总览](../docs/11-testing/README.md)
- [测试策略](../docs/11-testing/testing-strategy.md)
- [测试层级](../docs/11-testing/test-levels.md)
- [验证 Gate](../docs/11-testing/verification-gates.md)
- [测试证据标准](../docs/11-testing/test-evidence-standard.md)
- [Release 验证流程](../docs/11-testing/release-validation.md)
- [完成定义](../governance/DEFINITION_OF_DONE.md)

本文件只同步测试资产事实，不新增测试、框架、架构决策或实施授权。
