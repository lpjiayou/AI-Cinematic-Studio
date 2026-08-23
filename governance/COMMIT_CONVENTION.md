# AI Cinematic Studio 提交约定

## 1. 目的

统一提交信息用于准确表达变更意图、支持审计与回滚，并为后续自动化提供稳定输入。每个提交应是单一、完整、可理解的工程变更，不应混入无关内容。

## 2. 提交信息格式

采用以下格式：

```text
<type>(<scope>): <subject>

<body>

<footer>
```

- `type`：必填，表示变更类别。
- `scope`：可选，表示受影响的已存在工程范围；不得用它发明未来模块。
- `subject`：必填，用祈使式简洁描述结果，不加句号。
- `body`：可选，说明原因、约束、取舍和验证方式。
- `footer`：可选，记录任务、决策、破坏性变化或关联事项。

标题建议不超过 72 个字符；正文每段聚焦一个主题。

## 3. 允许的类型

- `feat`：已获授权的功能变更；**Phase 0 禁止使用**。
- `fix`：缺陷修复。
- `docs`：仅文档变更。
- `test`：新增或调整测试。
- `refactor`：不改变外部行为的结构调整。
- `perf`：性能改进。
- `build`：构建系统或依赖变更。
- `ci`：持续集成配置变更。
- `chore`：不属于上述类别的维护变更。
- `revert`：撤销先前提交。

Phase 0 应优先使用 `docs`、`test`、`build`、`ci` 或 `chore`，且内容仍须满足当前阶段边界。类型名称不能为越界内容提供授权。

## 4. Scope 规则

Scope 应使用稳定、已存在且可识别的工程范围，例如：

```text
docs
governance
architecture
tests
repo
```

不得使用未经批准的产品域、服务名或未来模块名作为 scope；不得因提交约定反向建立模块边界。

## 5. 任务与破坏性变化

提交应在 footer 中关联任务，例如：

```text
Refs: ACS-P0-001
```

破坏性变化使用：

```text
BREAKING CHANGE: <影响、原因和迁移方式>
```

任何破坏性变化都必须事先获得授权并更新相关文档。Phase 0 不允许借助 `BREAKING CHANGE` 标记修改未来模块架构。

## 6. 示例

合规示例：

```text
docs(governance): define repository development rules

Document Phase 0 boundaries and review requirements.

Refs: ACS-P0-001
```

```text
chore(repo): initialize engineering foundation directories

Refs: ACS-P0-001
```

不合规示例及原因：

```text
update files
```

原因：缺少类型、范围和可审计意图。

```text
feat(render-service): add placeholder service
```

原因：Phase 0 禁止业务功能和占位业务代码，且不得臆造未来模块。

```text
build(db): install database stack for later
```

原因：Phase 0 禁止数据库设计和为未来用途引入大型依赖。

## 7. 提交组织

- 一个提交只表达一个逻辑目的。
- 纯格式化、机械重命名与语义变更应尽量分开。
- 不提交临时调试内容、生成物、凭据或本地环境文件。
- 修正评审意见时可在工作分支使用小提交；合并前应按仓库策略保持最终历史清晰。
- 不使用含糊信息，如 `misc`、`changes`、`fix stuff` 或仅写任务编号。

## 8. Revert 约定

撤销提交使用 `revert` 类型，正文注明被撤销的提交标识、撤销原因和后续计划。撤销不应删除审计线索，也不能用于掩盖未经批准的变更。
