# AI Cinematic Studio

AI Cinematic Studio 是以 Project 为生产根、以可追溯版本和真实生产链为核心的
AI 影视生产系统。Core 仓库负责 Creator Server/Public API/Application、V5 Core
OS、V4 Platform、V3 Render Core、持久化与后端测试；客户 Commercial SaaS UI
由独立 `AI-Cinematic-Studio-Frontend` 仓库承载。

> 当前状态：M1–M5 已接受；M6-P0/P1 已 Owner Accepted；M6-P2 本地开发
> Durable SQLite Slice 已授权；Production Ready = `NO`。

## 当前活动工作包

| 项目 | 状态 |
| --- | --- |
| Accepted M6-P0/P1 baseline | `e38c75aa4ff26bdea80c82d8a24096f799dad860` |
| M6-P0/P1 | `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED` |
| ADR-0004 / M6-P2-G0 | `ACCEPTED / COMPLETE` |
| M6-P2-G1 | `AUTHORIZED / NOT STARTED` |
| M6-P3+ | `NOT AUTHORIZED / NOT STARTED` |
| M7-M19 | `NOT STARTED / NOT AUTHORIZED` |
| Formal port-8765 database | `UNTOUCHED / NOT DEPLOYED` |
| Frontend | `FROZEN / UNTOUCHED` |
| Production Ready | `NO` |

当前执行范围只允许 M6 local-development SQLite 持久化、Migration、完整 Scope
约束、删除完整性、持久化幂等与持久化 Outbox。正式数据库、Public HTTP/API
扩展、Auth/RBAC、Frontend、M6-P3+ 和 M7+ 不在授权范围内。

权威执行状态见 [CURRENT_MILESTONE.md](CURRENT_MILESTONE.md)。

## 产品生产主链

```text
Workspace
→ Content Profile
→ Project
→ AI Director
→ Series
→ Series Planning
→ Series Bible / Character Intelligence
→ Episode
→ CreativePlan / Story / Script
→ Consistency
→ Storyboard / Shot
→ Asset Requirement / AssetVersion
→ Video + Audio
→ Timeline / V3 Render
→ Preview / QC / Approval
→ Episode Master
→ Release
→ Performance Feedback
```

每项新能力必须明确上游、输入合同、输出合同、直接下游、Ref/Version 血缘和
最终可追溯路径。孤立工具、复制 JSON 和名称匹配不构成集成。

## 架构边界

```text
Commercial Frontend
→ Frontend Experience Adapter
→ Creator Public HTTP/API
→ Creator Application
→ V5 Core OS
→ V4 Platform
→ V3 Render Core
→ Compute/Foundation
```

- V5 拥有 Project、Series、Episode、Bible、Character、Script、Asset、版本和
  生产事实。
- V4 执行 Provider、Job、Queue、Worker 和 Compute 调度，不拥有 V5 业务事实。
- V3 负责确定性时间线、合成和渲染。
- Frontend 只能通过公开 HTTP/API 使用 Core，不导入 Core 源码或访问 SQL。
- Provider 只生成 Candidate，不拥有确认、权利或发布事实。

## 当前已接受能力

- M1 — AI Director Core
- M2 — Series + Episode Foundation
- M3 — Script Studio
- M3-H — Script Candidate Robustness
- Story Projection
- M4 — Project Context Foundation
- M5 — Series Planning + Series Director
- M6-P0/P1 — Series Bible + Character Intelligence InMemory baseline

M6-P0/P1 已实现两个不可变版本根和一个原子基线：

```text
M5 Confirmed SeriesPlanVersion + Digest
→ SeriesBible / SeriesBibleVersion
→ CharacterContinuity / CharacterContinuityVersion
→ M6BaselineSnapshot
→ ordered Outbox
```

完整 Scope 为：

```text
businessDomain + tenantId + workspaceRef + projectRef + seriesRef
```

## 仓库结构

| 路径 | 责任 |
| --- | --- |
| `apps/creator_workspace_mvp/` | Creator Server、Public HTTP/API 与 Application runtime |
| `services/v5_core_os/` | V5 Domain、Application boundary 与 persistence adapters |
| `services/v4_platform/` | V4 execution/provider boundary |
| `services/v3_render_core/` | V3 deterministic render boundary |
| `architecture/` | 架构合同、层级边界与 M6 规范 |
| `governance/` | ADR、开发、评审、Git、风险与 checkpoint 决策 |
| `tests/unit/` | Unit tests |
| `tests/contract/` | Public/domain contract tests |
| `tests/integration/` | 跨边界、SQLite 与 lifecycle integration tests |

历史 Core 客户浏览器 UI `apps/creator-workspace-mvp` 已退役，不得与下划线路径
`apps/creator_workspace_mvp` 的 Server/API runtime 混淆。

## 验证

运行完整 Core 测试：

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_*.py' -q
```

仓库 CI 还验证：

- tracked Markdown 结构与 UTF-8；
- local documentation links；
- Unit tests；
- Contract tests。

正式 checkpoint 还必须通过适用 Integration、Python AST、architecture、secret、
`git diff --check`、commit、GitHub push、Remote SHA equality 和 clean status。

## 关键文档

- [System Master Plan](AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md)
- [UI Master Plan](AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md)
- [Current Milestone](CURRENT_MILESTONE.md)
- [M6 Domain Contract](architecture/M6_SERIES_INTELLIGENCE_DOMAIN_CONTRACT.md)
- [M6 Durable SQLite Contract](architecture/M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md)
- [ADR-0003 — M6 InMemory baseline](governance/ADR-0003-m6-series-intelligence-baseline.md)
- [ADR-0004 — M6 Durable SQLite boundary](governance/ADR-0004-m6-series-intelligence-durable-sqlite-boundary.md)
- [Agent Constitution](AGENTS.md)

## 安全与发布边界

禁止提交 API key、Token、密码、Authorization 值、私钥、生产数据或正式数据库
文件。当前 SQLite 仅是本地开发 Durable Adapter，不是 Production Database。

测试通过、分支存在或远端同步都不等于 Production Ready、Release Authorized
或后续里程碑自动接受。
