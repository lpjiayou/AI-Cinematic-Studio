# AI Cinematic Studio Investor Readiness

## 1. 目录定位

`docs/15-investor-readiness/` 保存可追溯的工程里程碑记录，用于向投资人、治理责任人和后续维护者说明：在什么任务授权下，哪个不可变 Git 修订实际交付了什么、如何验证，以及哪些能力仍未实现。

本目录是证据索引与事实快照，不是产品功能清单、融资承诺、估值依据、审计意见、Release 批准或架构决策来源。记录必须区分已实现事实、验证范围、已知限制与待独立批准的未来事项。

## 2. 权威边界

本目录遵守以下既有权威来源：

- [V2.3 系统上下文](../../architecture/system-context.md)；
- [架构守卫](../../governance/ARCHITECTURE_GUARD.md)；
- [完成定义](../../governance/DEFINITION_OF_DONE.md)；
- [测试证据标准](../11-testing/test-evidence-standard.md)；
- [Phase 1 Production Validation Plan](../12-release/phase-1-production-validation-plan.md)；
- [风险登记册](../../governance/RISK_REGISTER.md)。

里程碑记录不得覆盖上述基线，不得通过事实描述反向批准新的层级、模块、接口、数据所有权、技术栈或依赖方向。记录与权威基线冲突时，应停止传播相关结论并按治理流程纠正；不能以投资者材料为架构例外。

## 3. 里程碑索引

| Milestone ID | 关联任务 | 标题 | 目标修订 | 记录结论 |
| --- | --- | --- | --- | --- |
| [M001](milestones/M001-v5-identity-engine-foundation.md) | `ACS-P1-002` | V5 Identity Engine Foundation | `d439e3cd894b6f91d0f161e28b92b080e589c5f6` | 已实现并完成所记录的本地验证；不构成 Phase 或 Release 结论 |
| [M002](milestones/M002-v5-project-engine-foundation.md) | `ACS-P1-003` | V5 Project Engine Foundation | `5759fc0c6dc91f43ca6cc912e8e76758dc59bd25` | 已实现并完成所记录的本地验证；不构成 Phase 或 Release 结论 |
| [M003](milestones/M003-v5-asset-registry-foundation.md) | `ACS-P1-004` | V5 Asset Registry Foundation | `e4f1a5d9247119b75e4fe863242cee9a3abe41c1` | 已实现并完成所记录的本地验证；不构成 Phase 或 Release 结论 |
| [M004](milestones/M004-v5-project-asset-relationship-foundation.md) | `ACS-P1-005` | V5 Project Asset Relationship Foundation | `139024327ea9cfcd7328f7a5b4ac385fb1e1a1ea` | 已实现并完成所记录的本地验证；不构成 Phase 或 Release 结论 |

Milestone ID 唯一且不得复用。修订后的记录必须保留原目标 Commit，并说明更正原因；不得把分支名称、工作树状态或未来计划替代为不可变修订依据。

## 4. 记录准入标准

一项工程结果进入本目录前，至少应具备：

1. 明确的获批任务编号与范围；
2. 可解析的完整 Commit SHA；
3. 精确的交付物与改动范围；
4. 与目标修订绑定的验证结果；
5. 架构、依赖和数据边界影响说明；
6. 已知限制与未实现事项；
7. 不把单项工作外推为 Phase、Release、生产或商业结果的约束声明。

正式验证状态沿用 `PASS / FAIL / BLOCKED / NOT RUN / N/A`；任务完成结论沿用 `完成 / 未完成`。缺少执行责任、审查记录、保留责任或其他必需元数据的本地复验只能记录实际观察结果，不得标记为正式 `PASS`。单项 `PASS`、单个 Commit 或一份里程碑记录都不能独立证明 Phase Gate、Production Validation 或商业化准备完成。

## 5. 投资者解读原则

本目录可以提供以下类型的工程信号：

- 任务、实现、测试和 Commit 之间存在可复核追溯链；
- 团队能够在冻结架构与明确范围内交付最小实现；
- 自动化验证覆盖已声明的局部行为；
- 未实现能力与残余限制被明确披露。

本目录不得被解读为已经证明产品市场匹配、收入、客户采用、生产规模、可用性、安全合规、完整平台能力或外部 Release 就绪。任何此类结论都需要对应范围的独立证据。

## 6. 维护规则

- 只记录已经存在并可复核的结果，不使用路线图语言替代交付证据。
- 测试复验必须绑定目标修订、运行环境、时间、实际结果和适用边界。
- 失败、未运行、未合并、未部署和未批准事项不得省略或包装为完成。
- Future Expansion 只记录可能的治理后续，不代表预算、排期、技术选择或实施授权。
- 新里程碑通过新增文件进入索引，不得改写历史 Commit 的事实含义。
