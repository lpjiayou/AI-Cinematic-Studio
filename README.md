# AI Cinematic Studio

AI Cinematic Studio 是以 Project 为生产根、以可追溯版本和真实生产链为核心的
AI 影视生产系统。Core 仓库负责 Creator Server/Public API/Application、V5 Core
OS、V4 Platform、V3 Render Core、持久化与后端测试；客户 Commercial SaaS UI
由独立 `AI-Cinematic-Studio-Frontend` 仓库承载。

> 当前状态：M1–M5 已接受；M6-P0/P1 与 bounded M6-P2 已 Owner Accepted；
> 当前执行 `ACS-ARCH-R1-V5-TEXT-GENERATION-G0 → G1`；M6-P3-G0 candidate
> 保持 HOLD；Production Ready = `NO`。

## 当前活动工作包

| 项目 | 状态 |
| --- | --- |
| Accepted M6-P0/P1 baseline | `e38c75aa4ff26bdea80c82d8a24096f799dad860` |
| M6-P0/P1 | `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED` |
| ADR-0004 / M6-P2-G0 | `ACCEPTED / COMPLETE` |
| M6-P2-G1 | `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 8227c6c616140824fd70de920dc6fcf459bb734d` |
| Architecture remediation wave | `ACS-ARCH-R1-V5-TEXT-GENERATION-G0 → G1 / AUTO-SEQUENTIAL BOUNDED` |
| ADR-0006 / V5 Text Generation Contract | `ACCEPTED FOR BOUNDED G1` |
| G0 | `GOVERNANCE / ARCHITECTURE SYNCHRONIZATION IN PROGRESS` |
| G1 | `AUTHORIZED ONLY AFTER G0 REMOTE VERIFICATION / NOT STARTED` |
| R-CORE-ARCH-001 | `CONFIRMED / HIGH / MITIGATING` |
| R-CORE-GOV-002 | `OPEN / NON-BLOCKING` |
| M6-P3-G0 | `REMOTE-VERIFIED CANDIDATE AT c524486c05c21b270a7dd75e89fae4312430736a / OWNER REVIEW PENDING / HOLD` |
| ADR-0005 / M6 Consumer Contract | `PROPOSED / NO IMPLEMENTATION AUTHORITY` |
| M6-P3-B1 EpisodePlanItemBinding | `PROPOSED / NOT AUTHORIZED / NOT STARTED / BLOCKS M6-P3-G1` |
| M6-P3-G1+ | `NOT AUTHORIZED / NOT STARTED` |
| M7-M19 | `NOT STARTED / NOT AUTHORIZED` |
| Formal port-8765 database | `UNTOUCHED / NOT DEPLOYED` |
| Frontend | `FROZEN / UNTOUCHED` |
| Production Ready | `NO` |

当前修复恢复既有 V2.3 相邻层方向：

```text
Creator Application
→ V5 Text Generation Capability
→ V4 TextGenerationPort
→ Provider Adapter
```

G0 只同步 ADR-0006、规范合同、风险及 Source-of-Truth；G0 commit、push 和 remote
verification 全部通过后，才自动进入 G1。G1 迁移 AI Director、Script Studio、
Series Director 与 Creator Server composition 的四个直接 V4 接触面，并增加禁止
`apps → V4` 的自动化守卫。G1 完成远端验证后必须 STOP 等待 Project Lead review。

G3/P3-G0 在 `c524486c05c21b270a7dd75e89fae4312430736a` 的内容保持
remote-verified candidate / HOLD；ADR-0005 仍为 Proposed，M6-P3-B1/G1 均不授权。
Schema/Migration、正式数据库、Public HTTP/API 扩张、Auth/RBAC、Frontend、M6-P3、
M7+、V3、GPU、Worker 和 ComfyUI 不在当前授权范围内。

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
  生产事实，以及 Creator Application 消费的 public Text Generation Capability
  boundary。
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
- M6-P2 — bounded local-development durable SQLite adapter

M6-P0/P1 已实现两个不可变版本根和一个原子基线：

```text
M5 Confirmed SeriesPlanVersion + Digest
→ SeriesBible / SeriesBibleVersion
→ CharacterContinuity / CharacterContinuityVersion
→ M6BaselineSnapshot
→ ordered Outbox
```

M6-P2 已将相同领域语义接入 LifecycleAssembly 的本地开发 SQLite Adapter，
覆盖原子 Migration、完整 Scope/FK、持久化幂等、持久化 Outbox、重启一致性和
删除完整性；它不是正式数据库或 Production 部署。

完整 Scope 为：

```text
businessDomain + tenantId + workspaceRef + projectRef + seriesRef
```

## 仓库结构

| 路径 | 责任 |
| --- | --- |
| `apps/creator_workspace_mvp/` | Creator Server、Public HTTP/API 与 Application runtime；只消费 V5 公开边界 |
| `services/v5_core_os/` | V5 Domain、Application-facing capability boundary 与 persistence adapters |
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
- [V5 Text Generation Capability Contract](architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md)
- [ADR-0006 — V5 Text Generation Capability Boundary](governance/ADR-0006-v5-text-generation-capability-boundary.md)
- [ACS-ARCH-R1 G0 Record](governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G0.md)
- [M6 Domain Contract](architecture/M6_SERIES_INTELLIGENCE_DOMAIN_CONTRACT.md)
- [M6 Durable SQLite Contract](architecture/M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md)
- [M6 Consumer Contract — Proposed](architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md)
- [ADR-0003 — M6 InMemory baseline](governance/ADR-0003-m6-series-intelligence-baseline.md)
- [ADR-0004 — M6 Durable SQLite boundary](governance/ADR-0004-m6-series-intelligence-durable-sqlite-boundary.md)
- [ADR-0005 — M6 consumer boundary — Proposed](governance/ADR-0005-m6-series-intelligence-consumer-boundary.md)
- [Agent Constitution](AGENTS.md)

## 安全与发布边界

禁止提交 API key、Token、密码、Authorization 值、私钥、生产数据或正式数据库
文件。当前 SQLite 仅是本地开发 Durable Adapter，不是 Production Database。

测试通过、分支存在或远端同步都不等于 Production Ready、Release Authorized
或后续里程碑自动接受。
