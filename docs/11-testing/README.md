# AI Cinematic Studio 测试治理基础

## 1. 目的与范围

本目录建立 AI Cinematic Studio V2.3 的测试治理体系，用于统一测试层级、阶段 Gate、验证证据和 Release 验证流程。

这些文档定义“需要证明什么”和“何时可以通过”，不定义测试代码、业务用例、测试数据结构、框架、运行器、断言库、CI 产品或环境实现。文档中的未来要求也不授权任何模块功能开发。

## 2. 文档索引

| 文档 | 作用 |
| --- | --- |
| [测试策略](testing-strategy.md) | 定义测试目标、原则、责任和风险驱动方法 |
| [测试层级](test-levels.md) | 定义 Unit、Contract、Integration、E2E、Production Validation |
| [验证 Gate](verification-gates.md) | 定义 Phase 0、Phase 1、Phase 2 的最低验证门槛 |
| [测试证据标准](test-evidence-standard.md) | 定义证据内容、质量、状态、保留和评审规则 |
| [Release 验证](release-validation.md) | 定义发布前、发布中和发布后的验证与决策流程 |
| [Repository 测试资产](../../tests/README.md) | 记录当前已跟踪 Unit/Contract 测试与 Integration/E2E 目录状态 |

测试治理与 [层级边界](../../architecture/layer-boundaries.md)、[依赖规则](../../architecture/dependency-rules.md)、[完成定义](../../governance/DEFINITION_OF_DONE.md)、[代码评审规则](../../governance/CODE_REVIEW_RULES.md) 和 [架构变更流程](../../governance/ARCHITECTURE_CHANGE_PROCESS.md) 共同生效，不替代其中任何一项门禁。

## 3. 测试层级总览

| 层级 | 核心目标 | 当前资产位置或证据归属 |
| --- | --- | --- |
| Unit | 验证最小可隔离单元的确定性行为 | `tests/unit/`；当前存在四个 V5 Foundation 测试文件 |
| Contract | 验证公开接口、事件、错误和数据契约的兼容性 | `tests/contract/`；当前存在四个 V5 Foundation 包契约测试文件 |
| Integration | 验证获批组件或技术边界之间的真实协作 | `tests/integration/`；当前仅有 `.gitkeep` |
| E2E | 通过正式入口验证获批系统路径的整体结果 | `tests/e2e/`；当前仅有 `.gitkeep` |
| Production Validation | 发布后在受控范围内确认版本、健康状态和关键技术假设 | 当前没有 Production Validation；未来记录归入 Release 证据 |

ACS-P0-005 当时只建立目录与治理骨架；后续已跟踪任务在 Unit 和 Contract 目录中增加了 V5 Foundation 测试。该仓库事实不改写 ACS-P0-005 的历史范围，也不表示 Integration、E2E、Production Validation、Phase Gate 或 Implementation Authorization 已经完成。

## 4. 分层原则

1. 每个层级回答不同风险问题，上层验证不能代替下层验证。
2. 测试范围应与变更风险相称，不以测试数量或单一覆盖率数字替代风险说明。
3. Contract 测试只依据公开契约，不复制另一边界的内部实现。
4. Integration 与 E2E 必须使用受控环境和数据，不依赖个人机器或真实敏感信息。
5. Production Validation 是发布后的安全确认，不是首次发现基本正确性问题的主要手段。
6. 生产代码不得依赖测试代码、测试夹具或测试专属配置。
7. 失败、跳过、阻塞和不适用项都必须显式记录，不能通过遗漏制造“通过”结论。

## 5. Phase Gate 总览

| Gate | 治理目标 |
| --- | --- |
| Phase 0 | 证明仓库、治理、架构、接口和数据文档基础完整且无越界实现 |
| Phase 1 | 对获批的初始实现建立 Unit 与 Contract 为主、风险相称的验证证据 |
| Phase 2 | 对未来获批的集成与发布候选建立完整的适用分层证据和 Release 验证准备 |

Phase Gate 只定义验证成熟度，不定义 Phase 1 或 Phase 2 的产品范围、模块清单、技术栈和发布时间。任何实施仍需独立任务授权。

## 6. 测试证据最低要求

每份验证证据至少必须能够回答：

- 验证对象、范围和关联任务是什么；
- 使用了哪个测试层级以及为什么；
- 验证的是哪个候选版本或文档状态；
- 前置条件、环境边界和数据类别是什么；
- 执行了什么验证意图，而不是只给出结论；
- 结果、失败、跳过、阻塞和限制分别是什么；
- 谁执行、谁评审、何时完成；
- 证据保存在哪里、何时需要复核。

完整规则见 [测试证据标准](test-evidence-standard.md)。

## 7. 责任原则

- 变更责任人负责识别风险并提出适用测试层级。
- 验证责任人负责按批准范围执行验证并形成完整证据。
- 评审者独立检查证据是否足以支持结论。
- Gate 或 Release 决策责任人依据证据作出通过、暂停或回退决定。
- 责任人尚未指定时必须由项目负责人明确指定，不能由文档假设某个团队已经存在。

## 8. ACS-P0-005 历史非目标

ACS-P0-005 不编写测试代码、测试用例、业务场景、夹具、模拟器、配置、脚本或覆盖率规则，不选择测试框架、CI 平台、测试管理产品或发布工具，不安装任何依赖，也不实现或改变 V2.3 模块功能与架构。后续测试资产存在不改变该历史事实。
