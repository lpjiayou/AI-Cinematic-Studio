# AI Cinematic Studio

AI Cinematic Studio 是以 Project 为生产根、以可追溯版本和真实生产链为核心的
AI 影视生产系统。Core 仓库负责 Creator Server/Public API/Application、V5 Core
OS、V4 Platform、V3 Render Core、持久化与后端测试；客户 Commercial SaaS UI
由独立 `AI-Cinematic-Studio-Frontend` 仓库承载。

> 当前已验证基线：Core `main`
> `6d28a53f3a077f032e341a87412b19b37c00bb1e` / tree
> `369c3b1479f3136cc32fcbc4efd0fa24e4964058`，Frontend `main`
> `5b36aac09fc10db04455d9ee287060232a521e5f` / tree
> `fd20b7d75c5ff379842462964d4e4f1d860d334d`。ADR-0013 非 GPU 控制平面已
> 正式接受为 `OWNER ACCEPTED / COMPLETE / MAIN-VERIFIED`。K2-001 同时冻结为
> 历史验证档案；M10 v1 的四个图像 `AssetVersion` 保留为已准入历史，但不是当前
> action-ready 来源；M11 v1 与 Shot 01 R2–R7 仍为失败或
> `UNSELECTED / NOT_ADMITTED`，且整个项目不可发布。
> ADR-0014 与 `ACS-K2-002-GOV-RB1` 已启动并正式重基线独立 K2-002《长安刮痕》
> 非 GPU 预生产链：来源与 v1.3 审校候选已入库；当前候选只形成
> `StoryboardDraft / CreativeShotDraft / ShotPlanDraft`，状态停在
> `SCRIPT_VALIDATED`，不会生成 `ExecutableShotGraph` 或进入 `SHOTS_COMPILED`；
> authenticated dynamic-media preflight 只读取精确 draft refs/digests，保持零写、
> `cameraContractState=NOT_READY` 和 `dispatchAllowed=false`。canonical 注册、M10/M11
> gate append 与 V4 dispatch 尚未集成。剧本 Owner
> Acceptance、durable receipt、M5 binding、精确 camera、真实引用、EP01 输入资产、
> 后处理 manifest、rights、provider policy、budget 与 runtime authority 均是必要门禁；
> 即使全部就绪，Provider/GPU dispatch 仍须单独的 Project Lead 授权。
>
> 历史状态：M1–M5 已接受；M6-P0/P1 与 bounded M6-P2 已 Owner Accepted；
> G1-R1 `d44f471…` 已 Owner Accepted 并关闭 Architecture Remediation R1；
> M6-P3-G0 已 Owner Accepted；M6-P3-B1 原候选 `8449b521…` 的 Owner Review 为 `REVISION REQUIRED`；修正后的 B1-R1 `5c656992…` 已远端验证并于 `2026-08-14` Owner Accepted；
> M6-P3-G1 原候选 `3696d6af…` 为 `REVISION REQUIRED`；G1-R1
> `e172cc7c…` 已通过 464/464、远端验证和 Owner Review；Core `main`
> `5976263f…` 以相同 tree 完成 PR rebase 收敛并通过 post-merge CI；
> Production Ready = `NO`。

## 当前活动工作包

| 项目 | 状态 |
| --- | --- |
| ADR-0013 non-GPU control plane | `OWNER ACCEPTED / COMPLETE / MAIN-VERIFIED` |
| K2-001 | `HISTORICAL VALIDATION / M10 V1 IMAGES ADMITTED AS HISTORY / M11 + R2–R7 UNSELECTED AND NOT_ADMITTED / NOT PUBLISHABLE` |
| ADR-0014 / ACS-K2-002-GOV-RB1 / K2-002《长安刮痕》 | `GOVERNANCE REBASELINED / EXACT NON-GPU REPOSITORY WORK AUTHORIZED / SOURCE + v1.3 REVIEWED CORRECTION CANDIDATE IN REPOSITORY / SCRIPT OWNER ACCEPTANCE PENDING / TECHNICAL CANDIDATE NOT ACCEPTED / GENERATION NOT STARTED` |
| K2-002 shot authority | `LOCAL STRUCTURAL DRAFT ONLY / SCRIPT_VALIDATED / CAMERA NOT_READY / EXECUTABLE SHOT GRAPH NOT COMPILED` |
| K2-002 generation admission | `BLOCKED: SCRIPT ACCEPTANCE + DURABLE REGISTRATION + M5 BINDING + SHOT/CAMERA APPROVAL + CANONICAL REFS/ASSETS + POSTPROCESS + RIGHTS/PROVIDER/BUDGET/RUNTIME + CANONICAL M10/M11 APPEND + SEPARATE GPU AUTHORIZATION` |

## 历史治理快照（不构成当前授权）

下表保留各原始里程碑的历史措辞用于审计。其 `Current`、`AUTHORIZED` 或
`NOT STARTED` 只描述当时检查点，不覆盖 `CURRENT_MILESTONE.md` 第 0 节与
ADR-0014 的当前权威。

| 历史项目 | 当时状态 |
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
| M6-P3-G1 | `ORIGINAL 3696d6af REVISION REQUIRED / G1-R1 OWNER ACCEPTED AT e172cc7c / TREE be7447c3 / FULL CORE 464/464` |
| Core main convergence | `OWNER ACCEPTED / PR #2 REBASE AND MERGE / MAIN 5976263f / TREE be7447c3 / POST-MERGE CI PASS` |
| Accepted governance checkpoint | `ACS-GOV-POST-M6-P3-G1-CLOSEOUT / OWNER ACCEPTED AT 20207e7f / TREE e3638838` |
| Original CCV-R1 candidate | `57cbbd4959f5f3d50b4d453cb6ae96b225cb7759 / REVISION REQUIRED / NOT OWNER ACCEPTED` |
| Current checkpoint | `ACS-K2-PUBLISHABLE-P0 HOLD + P1 VIDEO SAFE PREREQUISITE / EXTERNAL AUTHORITY REQUIRED / NOT PASSED` |
| Character Consistency evidence status | `EXPERIMENT REPORTED / INDEPENDENT REPRODUCTION NOT POSSIBLE / SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION` |
| CCV-R2 / Character Visual Identity schema | `NOT AUTHORIZED / NOT STARTED` |
| M6-P3 after G1 / M6-P4+ | `NOT AUTHORIZED / NOT STARTED` |
| K2 G0→G7 | `MERGED TO CORE MAIN / LOCAL_EVIDENCE ONLY / NOT PUBLISHABLE` |
| K2 M7–M15 | `P0→P9 AUTHORIZED AS ONE PUBLISHABLE SINGLE-EPISODE SLICE / GATE-BY-GATE` |
| M16 | `P10 BOUNDED 1→3→10→30 ONLY AFTER P9 + GATE A/B/C` |
| M17–M19 | `NOT AUTHORIZED` |
| Formal port-8765 database | `UNTOUCHED / NOT DEPLOYED` |
| Frontend | `CONNECTED BASELINE + P0 PRODUCTION-READINESS MAPPING / PUBLISHABLE ACTIONS BLOCKED BY CORE FACTS` |
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
前不得修改生产或测试路径。治理检查点已远端验证；原技术候选精确修改 7 个
生产路径并新增 3 个测试路径，通过 G1 `14/14`、完整 Core `463/463`、AST
`63/63`、Markdown `88/88` 与 links `323/323`，但 Owner Review 发现其未知异常
兜底错误映射为 `m6_lineage_mismatch / 409`，因此 `3696d6af…` 保持历史
`REVISION REQUIRED`。G1-R1 仅修正该一行生产错误语义并新增一个测试文件，
在 `e172cc7c9bfca04066153d9edad70d9074bb37e5` 通过 `464/464` 并获 Owner
Acceptance。受保护的 `main` 通过 PR `#2` 以 `Rebase and merge` 收敛至
`5976263f92f7f9cbe9c091719eccb036ee8c0c2d`，tree 与 G1-R1 相同，post-merge
Repository Validation 通过。
现有 HTTP workspace versions 的 v2 响应允许透传 `episodePlanItemBindings`，但不
修改 route、handler 或外部 DTO 源文件。在该历史 M6-P3-G1 授权中，除 Owner
消歧外的 Public HTTP/API 扩张、Schema/Migration、正式数据库、Auth/RBAC、
Frontend、G1 之后的 M6 工作、M7+、V3、GPU、Worker 和 ComfyUI 均不在范围内；
其后的 K2 P0→P10 有界授权仅以 `CURRENT_MILESTONE.md` 第 16 节为准。

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
- [K2-002 Non-GPU Preproduction Governance Rebaseline](governance/ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md)
- [K2-002《长安刮痕》预生产包](docs/16-k2-production/k2-002-changan/README.md)
- [K2 Publishable Media Production Contract](architecture/K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md)
- [K2 Canonical Lineage Bootstrap Contract](architecture/K2_CANONICAL_LINEAGE_BOOTSTRAP_CONTRACT.md)
- [ADR-0010 — K2 Canonical Lineage Bootstrap](governance/ADR-0010-k2-canonical-lineage-bootstrap.md)
- [K2-001 Canonical Bootstrap Specification](experiments/k2-001-canonical-bootstrap/README.md)
- [K2 P0 External Hold](governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md)
- [K2 ComfyUI / Wan2.2 Operator Runbook](docs/08-compute/k2-comfyui-wan22-operator-runbook.md)
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
