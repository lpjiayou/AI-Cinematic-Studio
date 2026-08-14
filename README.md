# AI Cinematic Studio

AI Cinematic Studio 是以 Project 为生产根、以可追溯版本和真实生产链为核心的
AI 影视生产系统。Core 仓库负责 Creator Server/Public API/Application、V5 Core
OS、V4 Platform、V3 Render Core、持久化与后端测试；客户 Commercial SaaS UI
由独立 `AI-Cinematic-Studio-Frontend` 仓库承载。

> 当前状态：M1–M5 已接受；M6-P0/P1 与 bounded M6-P2 已 Owner Accepted；
> G1-R1 `d44f471…` 已 Owner Accepted 并关闭 Architecture Remediation R1；
> M6-P3-G0 已 Owner Accepted；M6-P3-B1 原候选 `8449b521…` 的 Owner Review 为 `REVISION REQUIRED`；修正后的 B1-R1 `5c656992…` 已远端验证并于 `2026-08-14` Owner Accepted；
> M6-P3-G1 已获独立有界授权，须先远端验证 governance-only checkpoint；技术候选完成后停止等待 Owner Review；
> Production Ready = `NO`。

## 当前活动工作包

| 项目 | 状态 |
| --- | --- |
| Accepted M6-P0/P1 baseline | `e38c75aa4ff26bdea80c82d8a24096f799dad860` |
| M6-P0/P1 | `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED` |
| ADR-0004 / M6-P2-G0 | `ACCEPTED / COMPLETE` |
| M6-P2-G1 | `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 8227c6c616140824fd70de920dc6fcf459bb734d` |
| Architecture remediation wave | `CLOSED AT OWNER-ACCEPTED G1-R1 d44f471c644e319bb4a5bf73707c3274ecbaa426` |
| ADR-0006 / V5 Text Generation Contract | `ACCEPTED FOR BOUNDED G1` |
| G0 | `COMPLETE / REMOTE-VERIFIED AT 92d1f3ac9e08c71458af04514baa659555fc55a7` |
| G1 | `REMOTE-VERIFIED CANDIDATE AT 0c283eb653e74784301620bdaf64bf451bb687dd / REVISION REQUIRED / NOT OWNER ACCEPTED / SUPERSEDED BY G1-R1` |
| G1-R1 | `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT d44f471c644e319bb4a5bf73707c3274ecbaa426` |
| R-CORE-ARCH-001 | `CONFIRMED / HIGH / MONITORING` |
| R-CORE-GOV-002 | `OPEN / NON-BLOCKING` |
| M6-P3-G0 | `OWNER ACCEPTED / COMPLETE AS GOVERNANCE-ARCHITECTURE / NO IMPLEMENTATION AUTHORITY` |
| ADR-0005 / M6 Consumer Contract | `ACCEPTED AS ARCHITECTURE / B1 OWNER ACCEPTED THROUGH B1-R1 / G1 BOUNDED IMPLEMENTATION AUTHORIZED` |
| M6-P3-B1 EpisodePlanItemBinding | `ORIGINAL CANDIDATE 8449b521c96bb8340806ecda8649698f4771914a REVISION REQUIRED / CORRECTED AND OWNER ACCEPTED THROUGH B1-R1 AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` |
| B1 authorized base | `6bb9d165a693057f38e5789c408293ff0eaf5bcc` |
| B1 scope | `8 GOVERNANCE → 6 PRODUCTION + 9 TESTS → REMOTE VERIFY → STOP FOR OWNER REVIEW` |
| B1 version policy | `INITIAL V1 / V1→V1 / EXPLICIT V1→V2 / V2→V2 / NO V2→V1 / UNBIND VIA NEW V2` |
| B1 Core operation | `create_episode_plan_item_binding_version / NO ROUTE, HANDLER OR EXTERNAL DTO SOURCE CHANGE` |
| B1 Owner HTTP clarification | `EXISTING WORKSPACE VERSIONS V2 RESPONSE PASSES THROUGH episodePlanItemBindings / NO OTHER HTTP EXPANSION` |
| M6-P3-B1-F001 | `CLOSED BY OWNER-ACCEPTED B1-R1 / SQLITE SAME-PROJECT CROSS-SERIES FALSE DEPENDENCY` |
| M6-P3-B1-R1 | `OWNER ACCEPTED / COMPLETE / REMOTE-VERIFIED AT 5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` |
| B1-R1 base | `8449b521c96bb8340806ecda8649698f4771914a` |
| B1-R1 scope | `8 GOVERNANCE → 1 PRODUCTION + 1 TEST → REMOTE VERIFY → STOP FOR OWNER REVIEW` |
| B1-R1 evidence | `PRE-FIX 409 REPRODUCED / SQLITE 30/30 / ORIGINAL B1 174/174 / FULL CORE 449/449 / AST 63/63` |
| M6-P3-G1 | `BOUNDED IMPLEMENTATION AUTHORIZED / GOVERNANCE REMOTE VERIFICATION REQUIRED BEFORE CODE / NOT OWNER ACCEPTED` |
| M6-P3 after G1 / M6-P4+ | `NOT AUTHORIZED / NOT STARTED` |
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

G0 已完成 ADR-0006、规范合同、风险及 Source-of-Truth 同步。G1 已迁移 AI
Director、Script Studio、Series Director 与 Creator Server composition 的四个直接
V4 接触面，且当前生产树 `apps → V4` 为零。原 G1 的持续守卫存在动态导入别名
缺口，因此保留历史 `REVISION REQUIRED`。G1-R1 已补齐 binding-aware AST 守卫、
通过完整回归并在 `d44f471c644e319bb4a5bf73707c3274ecbaa426` 获得 Owner
Acceptance。

G3/P3-G0 在 `c524486c05c21b270a7dd75e89fae4312430736a` 的架构内容已通过 Owner
Review；ADR-0005 与 M6 Consumer Contract 已作为架构规范接受，其 consumer
行为仍未实施且不授予普遍实现权限。Project Lead、Architecture Owner、Repository Governance Owner 与
M2/M4/M5/M6 Domain Owners 已批准精确 B1；其实现候选已在
`8449b521c96bb8340806ecda8649698f4771914a` 远端验证，但 Owner Review 复现 SQLite
同一 Project 下跨 Series 的错误依赖并判定 `REVISION REQUIRED`。Project Lead、
Architecture Owner、Repository Governance Owner 与 affected M2/M5 Domain Owners
现有 B1-R1 的 8 路径治理检查点已在
`716b4d298173f8123cafd93114dfc67339943ff3` 远端验证，随后只修改了
`services/v5_core_os/series_planning/foundation.py` 和
`tests/integration/test_creator_lifecycle_sqlite_p2.py`。修订已通过 SQLite `30/30`、
原 B1 `174/174`、完整 Core `449/449` 与 AST `63/63`；技术提交
`5c656992d9fade3683b70e3c57f8b8ba7d26c7f7` 已远端验证并通过 Owner Review。
M6-P3-G1 前置条件已满足，Project Lead 于 `2026-08-14` 单独授权有界 Core-only
只读 consumer。授权顺序、7 个生产路径、3 个新增测试路径与禁止项冻结于
`governance/ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER.md`；在治理检查点远端验证
前不得修改生产或测试路径，技术候选远端验证后必须停止等待 Owner Review。
现有 HTTP workspace versions 的 v2 响应允许透传 `episodePlanItemBindings`，但不
修改 route、handler 或外部 DTO 源文件。除该 Owner 消歧外的 Public HTTP/API 扩张、
Schema/Migration、正式数据库、Auth/RBAC、Frontend、G1 之后的 M6 工作、
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
- [ACS-ARCH-R1 G1-R1 Authorization](governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-AUTHORIZATION.md)
- [ACS-ARCH-R1 G1-R1 Closeout / M6-P3-G0 Owner Review](governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-CLOSEOUT-M6-P3-G0-OWNER-REVIEW.md)
- [M6-P3-G0 Owner Acceptance](governance/ACS-M6-P3-G0-OWNER-ACCEPTANCE.md)
- [M6-P3-B1 EpisodePlanItemBinding Authorization](governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md)
- [M6 Domain Contract](architecture/M6_SERIES_INTELLIGENCE_DOMAIN_CONTRACT.md)
- [M6 Durable SQLite Contract](architecture/M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md)
- [M6 Consumer Contract — Accepted Architecture](architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md)
- [ADR-0003 — M6 InMemory baseline](governance/ADR-0003-m6-series-intelligence-baseline.md)
- [ADR-0004 — M6 Durable SQLite boundary](governance/ADR-0004-m6-series-intelligence-durable-sqlite-boundary.md)
- [ADR-0005 — M6 consumer boundary — Accepted Architecture](governance/ADR-0005-m6-series-intelligence-consumer-boundary.md)
- [Agent Constitution](AGENTS.md)

## 安全与发布边界

禁止提交 API key、Token、密码、Authorization 值、私钥、生产数据或正式数据库
文件。当前 SQLite 仅是本地开发 Durable Adapter，不是 Production Database。

测试通过、分支存在或远端同步都不等于 Production Ready、Release Authorized
或后续里程碑自动接受。
