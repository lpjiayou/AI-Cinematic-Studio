# Baseline Asset Acceptance Decision Record

| 项目 | 内容 |
| --- | --- |
| Task ID | `ACS-GOV-BASELINE-001` |
| Record Type | `Repository Asset Acceptance Decision Record` |
| Decision Date | `2026-08-07` |
| Review Population | ACS-GIT-003 识别的 13 个既有未跟踪 Markdown 资产 |
| Decision Function | ACS Baseline Governance Review；仅限本次资产处置 |
| Architecture Impact | `NONE`；不修改 AI Cinematic Studio V2.3 Architecture |
| Phase Impact | `NONE`；不修改 Phase 范围或实施授权 |
| Baseline Effect | `NONE / NO AUTOMATIC INCLUSION` |
| Tag / Release | `NOT CREATED BY THIS TASK`；本地 Tag 仍不存在，外部 Release 状态无法从无 remote 的本地仓库核验 |
| ADR | `NOT TRIGGERED`；本记录不改变架构语义 |

## 1. Decision Scope

本记录对 [Baseline v0.1.0 Candidate Manifest](baseline-v0.1.0-candidate-manifest.md) 审计时存在的 13 个未跟踪 Markdown 资产作出内容处置决定。审查依据包括 Repository source、tests、Git history、可复现本地检查、[Phase 0 Exit Record](phase-0-exit-record.md)、[Phase 1 Scope Approval](phase-1-scope-approval.md)、[Baseline Release Process](../../governance/BASELINE_RELEASE_PROCESS.md)及 V2.3 架构规则。

以下两个文件不属于该 13 个资产：

- `docs/12-release/baseline-v0.1.0-candidate-manifest.md`：由 ACS-GIT-003 在 13 个资产审计后创建；
- `docs/12-release/baseline-asset-acceptance-decision-record.md`：本任务的新增记录。

Decision 只绑定第 2 节列出的文件内容指纹。文件内容变化后，旧决定不得自动继承。`ACCEPT` 只表示内容可以进入后续独立版本化与 Baseline Review 包，不表示本任务已经暂存、提交、合并或纳入 Baseline，也不构成 Implementation、Integration、Release、Production 或 Phase 授权。

## 2. Reviewed Asset Identity

| # | 文件 | Reviewed SHA-256 |
| ---: | --- | --- |
| 1 | `AI_CINEMATIC_STUDIO_GENERATION_2_DEVELOPMENT_CHARTER.md` | `fea4f1d57c8ac99e650714d8c644241c31f19209b88c056cf371cac994cd29ec` |
| 2 | `docs/00-governance/gen2-charter-integration-record.md` | `7782bab46460211ee6c469d0a9a81ac387de119edeff14f4bbfe8d23826f433d` |
| 3 | `docs/04-interface-contract/v5-v3-vertical-slice-review.md` | `ead91c6999bd6c878af2a45ca4c7cd51f536384932c4b393be523178fd3d9d24` |
| 4 | `docs/07-v3-render-core/README.md` | `8ac509f4c368013f0b03d9e8ec7a1e5479125475a52ddc9512785c6b8a6c5080` |
| 5 | `docs/07-v3-render-core/render-core-boundary.md` | `6f42a53a72eb1265d3545a84fec73fe8101566e0ffcf6450acde3ada93b48de1` |
| 6 | `docs/12-release/phase-1-execution-authorization.md` | `2f654285266d21f53244a9d683975f9b1dbf97832bd6c90a7f2a5b90ff9eb0c4` |
| 7 | `docs/12-release/phase-1-responsibility-assignment.md` | `1c58b9e0f7d10d889b7e111b30e4ce8e1d2e77acfada492d4f292b8fc164904f` |
| 8 | `docs/12-release/phase-1-vertical-slice-authorization.md` | `dd21f3b4ca1d4a942864c018805523979e84a2645c1825e58461859fa9a1b737` |
| 9 | `docs/15-investor-readiness/README.md` | `871be6ba8e109f74f699e89bb2e61cc596754522f80e7269eb049efde484e48a` |
| 10 | `docs/15-investor-readiness/milestones/M001-v5-identity-engine-foundation.md` | `884583b81e0fae27055636a3b5e1223bb536d22abf4cb2657b799299ff52dcd6` |
| 11 | `docs/15-investor-readiness/milestones/M002-v5-project-engine-foundation.md` | `0dc15e5d88d18ebb453e216afd0af48605444b373f93ad0652f7f73825807fd6` |
| 12 | `docs/15-investor-readiness/milestones/M003-v5-asset-registry-foundation.md` | `699b9770df3f6743be53b32f1693760afe8fab09d14648c3a2cc74f1ae40f6ba` |
| 13 | `docs/15-investor-readiness/milestones/M004-v5-project-asset-relationship-foundation.md` | `082f99ea750aa1317261b734a86d14c18da69961979049e615bfb32819722a40` |

## 3. Decision Semantics

| Decision | 含义 | Baseline 行为 |
| --- | --- | --- |
| `ACCEPT` | 审查内容在其明确边界内准确，可以进入独立版本化评审 | 仍不自动暂存、提交、合并或纳入 Baseline |
| `REVISE` | 已识别可修正的事实、状态或证据问题 | 修订后产生新指纹并重新审查；当前内容不得纳入 |
| `DEFER` | 内容可能有价值，但依赖、来源、责任或接受条件尚未闭合 | 保持在候选之外，前置关闭后重新决定 |
| `REJECT` | 内容不适合作为 Repository 治理资产，且没有保留为待修订候选的依据 | 明确排除；删除或归档仍需独立授权 |

## 4. Decision Matrix

| # | 文件名称 | 分类 | 当前状态 | Decision | 原因 |
| ---: | --- | --- | --- | --- | --- |
| 1 | `AI_CINEMATIC_STUDIO_GENERATION_2_DEVELOPMENT_CHARTER.md` | Strategic Governance Charter | `UNTRACKED / FINAL CLAIM / SOURCE NOT REPRODUCIBLE` | `DEFER` | 内容指纹稳定且未授权实现，但当前仓库不能解析 Source Baseline，5 个 informed-by 链接全部失效；外部来源副本及其依据也未被声明 Commit 跟踪，来源链尚不能复现 |
| 2 | `docs/00-governance/gen2-charter-integration-record.md` | Strategic Governance Integration Record | `UNTRACKED / INTEGRATED CLAIM / DEPENDENCY DEFERRED` | `DEFER` | 指纹和边界陈述准确，但 `INTEGRATED` 状态依赖尚未接受的 Charter；必须与 Charter 来源和版本化决定成组复核 |
| 3 | `docs/04-interface-contract/v5-v3-vertical-slice-review.md` | Interface / Architecture Review | `UNTRACKED / REVIEW COMPLETE / OPEN QUESTIONS` | `ACCEPT` | 明确 V5–V3 只是端到端语义血缘，强制 V4 中介，保留 V2.3 依赖方向，并明确未达到实现就绪 |
| 4 | `docs/07-v3-render-core/README.md` | V3 Documentation Index | `UNTRACKED / DOCUMENTATION ONLY / NO IMPLEMENTATION` | `ACCEPT` | 明确目录不是代码或部署单元，V3 未实现、未授权；相邻依赖和禁止项准确 |
| 5 | `docs/07-v3-render-core/render-core-boundary.md` | V3 Boundary Specification | `UNTRACKED / TECHNOLOGY-NEUTRAL REVIEW / NO IMPLEMENTATION` | `ACCEPT` | 只定义候选边界，V3 唯一上游为 V4、下游为 Compute；禁止 Job、Worker、API、数据库和 V3 直接写入 V5/Asset Registry |
| 6 | `docs/12-release/phase-1-execution-authorization.md` | Phase Governance Authorization Record | `UNTRACKED / IMPLEMENTATION BLOCKED / SCOPE SNAPSHOT STALE` | `REVISE` | Phase 0 与 Implementation 状态正确，但 Scope Approved 仍被写为 `BLOCKED`；必须改为 Scope Decision 已记录，同时保持 G01 overall `BLOCKED` |
| 7 | `docs/12-release/phase-1-responsibility-assignment.md` | Phase Responsibility Draft | `UNTRACKED / DRAFT / NOT ACCEPTED / UNASSIGNED` | `DEFER` | 文件自身准确声明 Draft；核心 Person、Document Acceptance Owner、Risk 和 Release 责任未指派，不能由 Baseline 审查追认 |
| 8 | `docs/12-release/phase-1-vertical-slice-authorization.md` | Vertical Slice Authorization Draft | `UNTRACKED / PROPOSED / BLOCKED / PHASE SNAPSHOT STALE` | `REVISE` | 两处错误声明 Phase 0 尚未正式退出，Scope 仍仅标为 Proposed；需要与 Phase 0 Exit 和 Phase 1 Scope Approval 协调，同时保持 Implementation `NOT GRANTED` |
| 9 | `docs/15-investor-readiness/README.md` | Investor Readiness Index | `UNTRACKED / INDEX CANDIDATE / CHILD RECORDS REQUIRE REVISION` | `DEFER` | 索引自身边界准确，但应等待 M001–M004 修订后作为原子文档组接受，避免索引指向未接受记录 |
| 10 | `docs/15-investor-readiness/milestones/M001-v5-identity-engine-foundation.md` | Investor Milestone Record | `UNTRACKED / TARGET COMMIT VERIFIED / FACT CORRECTIONS REQUIRED` | `REVISE` | Commit、能力、测试数量和限制准确；Python `3.12.13` 无证据支持，README 状态已过期，Overview 的“验证通过”与正文非正式本地观察边界不一致 |
| 11 | `docs/15-investor-readiness/milestones/M002-v5-project-engine-foundation.md` | Investor Milestone Record | `UNTRACKED / TARGET COMMIT VERIFIED / FACT CORRECTIONS REQUIRED` | `REVISE` | Commit、能力、测试数量和限制准确；Python 版本无法证实，且 README 未同步与 Future Expansion 陈述已被后续事实关闭 |
| 12 | `docs/15-investor-readiness/milestones/M003-v5-asset-registry-foundation.md` | Investor Milestone Record | `UNTRACKED / TARGET COMMIT VERIFIED / FACT CORRECTIONS REQUIRED` | `REVISE` | Commit、能力、测试数量和限制准确；Python 版本无法证实，“全局状态文档尚未同步”需要改为日期化历史说明 |
| 13 | `docs/15-investor-readiness/milestones/M004-v5-project-asset-relationship-foundation.md` | Investor Milestone Record | `UNTRACKED / TARGET COMMIT VERIFIED / ENVIRONMENT CLAIM UNVERIFIED` | `REVISE` | 实现、Git、测试和价值陈述准确，但 Python `3.12.13` 环境声明没有可复核证据，必须更正或标为 `UNVERIFIED` |

Decision 汇总：

| Decision | 数量 | 文件组 |
| --- | ---: | --- |
| `ACCEPT` | 3 | V5–V3 Vertical Slice Review、V3 README、V3 Render Core Boundary |
| `REVISE` | 6 | Phase 1 Execution Authorization、Vertical Slice Authorization、M001–M004 |
| `DEFER` | 4 | Gen2 Charter、Charter Integration Record、Responsibility Assignment、Investor Readiness README |
| `REJECT` | 0 | 无 |

## 5. Priority Review Findings

### 5.1 Gen2 Charter 来源完整性

- 当前仓库无法解析 Charter 声明的 Source Baseline `9da3835c3bf7f69ed4085fa28d6206fa3f84ed25`。
- 在另一份本地来源 Repository 中可以解析该 Commit，且存在与本资产 SHA-256 完全一致的 Charter 副本。
- 但是 Charter 和其列出的五份 informed-by 文档均不属于该 Commit，并且在该来源工作树中仍为未跟踪文件；该 Commit 只能说明环境基线，不能证明 Charter 的版本化来源。
- Charter 的 5 个相对 informed-by 链接在当前仓库全部失效。
- `FINAL FOUNDING CHARTER` 是文件自声明；在来源身份、依赖材料、接受责任和可复现版本闭合前，本次决定为 `DEFER`，不是 `REJECT`。
- Integration Record 准确披露上述问题，但其 `INTEGRATED` 状态不能先于 Charter 接受，因此一并 `DEFER`。

### 5.2 Phase 文档状态一致性

当前权威状态保持：

| 状态维度 | 当前结论 |
| --- | --- |
| Phase 0 | `COMPLETED / CLOSED` |
| Phase 1 Scope | `APPROVED — MAXIMUM REVIEW ENVELOPE` |
| `P1-PV-G01` | `BLOCKED` |
| Phase 1 Implementation | `NOT GRANTED / BLOCKED` |
| V4 / V3 / Compute Implementation | `NOT GRANTED` |

据此：

- `phase-1-execution-authorization.md:59,242,304` 必须把 Scope Decision 与 G01 overall 分开；Scope 已记录为 Approved，但责任、Person、风险与其他前置仍阻塞 G01；
- `phase-1-execution-authorization.md:256` 必须区分已经完成的一次性 Scope Decision 与尚未指派的持续 Scope Maintenance；
- `phase-1-vertical-slice-authorization.md:10,224` 的 Phase 0 状态已过期，`:9,223,305` 需要与正式 Scope Approval 协调；
- `phase-1-responsibility-assignment.md` 的 Draft、Unassigned 和 Not Accepted 状态仍准确，因此 `DEFER`，不回溯赋予 Person 或责任授权。

### 5.3 Investor Milestone 事实准确性

以下 Git 与测试结构事实已经核对：

| Milestone | Target Commit | Commit Scope | 专项测试 | 目标 tree 中完整测试数 |
| --- | --- | --- | ---: | ---: |
| M001 | `d439e3cd894b6f91d0f161e28b92b080e589c5f6` | 13 files，`+680/-3` | 16 Unit + 6 Contract | 22 |
| M002 | `5759fc0c6dc91f43ca6cc912e8e76758dc59bd25` | 6 files，`+464/-0` | 15 Unit + 6 Contract | 43 |
| M003 | `e4f1a5d9247119b75e4fe863242cee9a3abe41c1` | 6 files，`+489/-0` | 17 Unit + 6 Contract | 66 |
| M004 | `139024327ea9cfcd7328f7a5b4ac385fb1e1a1ea` | 6 files，`+432/-0` | 14 Unit + 6 Contract | 86 |

四个 Commit 均可解析，是当前 HEAD 的祖先，但不是当前 `main` 的祖先；Commit metadata、文件范围、实现能力、无第三方依赖、局部测试数量和已知限制均与 Repository 事实一致。当前完整 Unit/Contract Suite 重新执行结果为 86/86 成功。

阻塞接受的共同问题是：四份记录都声称复验环境为 Python `3.12.13`，但当前 `python` 与 `py` 唯一可解析解释器为 Python `3.12.4`，Repository 没有提交的日志或构建产物证明记录时曾使用另一解释器。修订时必须使用可证明版本，或把环境版本标为 `UNVERIFIED`。

此外，M001–M003 中部分 README/全局状态同步描述已被后续 Commit `a1a3b9a098bfd7212ec7841e6261218305308c36` 改变；这些内容应明确标为记录时快照或更新为后续已关闭事项。Investor Value Statement 的局部工程价值边界和未实现能力披露本身没有商业、Phase、Release 或 Production 夸大。

### 5.4 V3 文档实现表述

接受的三份文档必须作为一个原子文档组解释：

- 完整 V2.3 依赖仍为 `Application → V5 → V4 → V3 → Compute → Foundation`；本组文档只审查其中至 Compute 的范围，所展示的 `V5 → V4 → V3 → Compute` 是该范围的链路后缀；
- V4 被明确规定为不可跳过的相邻中介，不存在 V5 直连 V3 或 V3 回调 V5；
- V3 只被描述为技术无关的候选责任边界，没有被声明为已实现、已部署或已授权；
- Render Request、Render Result 与 Asset Return 是语义概念，不是 API、Job、队列消息、文件或已登记 Asset；
- Job、Worker、Queue、API、Database、Storage 与 Compute 实现只出现在禁止项、非目标或未来独立 Gate 条件中。

因此三份文件获得 `ACCEPT AS DOCUMENTATION ASSET SET`。该决定不能外推为 V3 Implementation、V4 Stub、Compute、Vertical Slice 或 Production Authorization；`P1-PV-G01` 继续为 `BLOCKED`。

## 6. Baseline Impact

| 影响项 | 结论 |
| --- | --- |
| 自动纳入 Baseline | `NO` |
| Content Candidate SHA / Tree | `UNCHANGED`；本记录不修改 `a1a3b9a098bfd7212ec7841e6261218305308c36` |
| Accepted Asset Set | 3 个 V3/Vertical Slice 文档；仍须独立版本化、评审与合并 |
| Revision Queue | 6 个资产；修订后必须形成新 SHA-256 并重新审查 |
| Deferred Queue | 4 个资产；前置闭合前保持在 Baseline 外 |
| Rejected Assets | 0 |
| Candidate Readiness | `HOLD / NOT READY FOR TAG` |
| Architecture | V2.3 `UNCHANGED` |
| Phase / Implementation | `UNCHANGED / NOT AUTHORIZED` |
| Tag / Release / `main` Merge | `NOT PERFORMED` |

`ACCEPT` 不会把未跟踪文件变成 Git 历史。三份已接受内容需要通过后续独立 docs 版本化任务原子提交；任何内容变化都会使本决定所绑定的指纹失效。`REVISE` 与 `DEFER` 资产在新决定形成前不得进入 Baseline Candidate。

## 7. Validation and Final Decision

| 检查 | 结果 |
| --- | --- |
| Reviewed assets | `13 / 13` |
| Content fingerprints | `13 / 13` 已记录 |
| Relative Markdown links | 90 个；5 个缺失目标全部来自 Gen2 Charter |
| Markdown encoding / tables / trailing whitespace | 13 个资产均无 UTF-8 替换字符、表格列数错误或尾随空白 |
| Target milestone Commits | `4 / 4` 可解析，metadata、范围和测试结构已核对 |
| Current Unit / Contract Suite | `86 / 86` 命令执行成功；仅作为本地观察 |
| V3 implementation claim | 未发现已实现、已部署或已授权的错误声明 |
| Phase status | 已识别需修订快照；当前 Implementation 仍为 `NOT AUTHORIZED` |
| Code / Architecture / Phase Scope changes | `NONE` |
| Tag / Release / Baseline creation | `NONE` |

最终资产处置结论：`3 ACCEPT / 6 REVISE / 4 DEFER / 0 REJECT`。

本任务完成资产接受决策记录，但没有创建 Repository Baseline。由于 Revision Queue、Deferred Queue、现有 GitHub/责任/验证阻塞及未版本化资产仍然存在，`acs-baseline-v0.1.0-candidate` 继续保持 `HOLD / NOT READY FOR TAG`。
