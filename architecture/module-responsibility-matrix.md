# 模块责任矩阵

## 1. 使用方式

本矩阵登记当前已接受的仓库级责任域及其物理位置。业务模块只有在关联
Accepted ADR、获批任务和明确公开契约后才可加入；目录存在本身不构成授权。

## 2. 当前责任矩阵

| 责任域 | 位置 | 主要责任 | 可公开的资产 | 不承担的责任 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| Creator Application | `apps/creator_workspace_mvp/` | Creator Server、公开 HTTP/API、Application orchestration 与 composition entry | Public HTTP/API、Application command/query/DTO/error contract | V5 authoritative facts、V4 Provider execution、对 V4/V3/Compute 的直接生产依赖 | 运行中；`R-CORE-ARCH-001` 的直接 V4 依赖偏差已由 G1-R1 纠正并完成 owner acceptance |
| V5 Core OS | `services/v5_core_os/` | authoritative production facts、公开 capability boundary、版本/血缘及适用治理语义；拥有 ADR-0015 单向声音克隆血缘与 ADR-0016 唯一 Timeline/TimelineVersion 权威及持久化 | V5 public contracts；包括 ADR-0006 Text Generation、ADR-0015 M12 lineage 与 ADR-0016 M13 Timeline/RenderCandidate domain contracts | Provider adapter、V4 execution ownership、V3 render execution、Application presentation/HTTP | 运行中；M12 domain/runtime protocol 与 M13 base backend 已合入，M12 Runtime G0 未完成，M13 产品能力仍不完整 |
| V4 Platform | `services/v4_platform/` | AI/Provider execution boundary、公开 `TextGenerationPort`、隔离音频运行时的 closed-process execution boundary 与 M13 sealed deterministic-post orchestration | provider-neutral V4 execution contracts、封闭执行请求与结果证据 | V5 Domain Fact、Timeline/RenderCandidate authority、Application workflow、HTTP/UI、ML 包直接导入或运行时内部实现 | 运行中；M12 隔离 runtime protocol 与 M13 base sealed orchestration 已合入；Provider/GPU、M12 runtime install 与 Extension G0 均未授权完成 |
| V3 Render Core | `services/v3_render_core/` | deterministic audiovisual composition/render，以及 M13 CPU/FFmpeg deterministic-post execution | V3 public render contracts、确定性执行结果与 artifact evidence | V5 creative/Timeline facts、RenderCandidate persistence、Application workflow、EpisodeMaster、ExportArtifact 或 publication authority | 运行中；M13 八项 deterministic post、renderer v3 与完整 CPU vertical slice 已验证；不产生 Master/Export/publication authority |
| 共享能力 | `packages/` | 经验证、稳定且不承载产品工作流的复用能力 | 版本化包接口、类型与工具 | 应用专属流程、服务私有逻辑 | 按获批任务启用 |
| 平台基础设施 | `infrastructure/` | 构建、部署和运行环境声明 | 环境契约、资源声明、策略 | 业务规则、领域模型 | 基线已建立 |
| 工程自动化 | `scripts/` | 可重复的仓库操作 | 命令入口及其使用说明 | 业务逻辑、常驻运行时 | 基线已建立 |
| 质量保障 | `tests/` | 分层验证公开行为与集成质量 | 测试规范、夹具、报告 | 生产运行时能力 | 已启用 |
| 知识体系 | `docs/` | 保存主题化、版本化工程知识 | 说明、决策背景、运行手册 | 强制规则的重复真源 | 已启用 |
| 架构治理 | `architecture/` | 维护当前架构基线与规范契约 | 系统总览、边界、矩阵、规则、规范合同 | 生产运行时实现 | 基线已建立 |
| 工程治理 | `governance/` | 维护 ADR、协作、评审和变更规则 | ADR、风险、开发、评审、Git 规则 | 产品运行时代码 | 基线已建立 |

当前相邻依赖方向保持：

`Creator Application → V5 Core OS → V4 Platform → V3 Render Core → Compute → Foundation`

ADR-0006 接受的 Text Generation 目标路径为：

`Creator Application → V5 Text Generation Capability → V4 TextGenerationPort → Provider Adapter`

ADR-0015 与 ADR-0016 保持同一相邻依赖方向：V5 持有事实与血缘，V4 只接收
closed/sealed execution request 并编排独立进程，V3 只执行确定性合成与渲染。
这两份 Accepted ADR 仍是实现边界；上表仅陈述已有合入证据，不把未安装的
M12 runtime、未实现的 Frontend 产品面或未授权的 M13 Extension 视为已交付。

G1-R1 已关闭原 `apps/` 直接依赖 V4 的架构偏差。历史偏差记录仍保留，但不得
作为新实现先例。

## 3. 责任判定问题

新增资产前必须回答：

1. 谁是该资产的直接消费者？
2. 它是可交付入口、独立运行单元、共享能力，还是平台声明？
3. 它是否包含业务语义？若包含，不得放入 `scripts/` 或 `infrastructure/`。
4. 它是否确有复用证据？若没有，不得提前放入 `packages/`。
5. 它暴露哪些稳定契约，哪些细节必须保持私有？
6. 它是否要求新增跨层依赖？若要求，是否完成架构评审？

## 4. 未来模块登记模板

未来新增模块时，责任记录至少包括：模块标识、所属目录、责任描述、明确非责任、所有者、公开契约、允许依赖、受影响测试层级、关联架构决策和生命周期状态。

模块条目不得仅凭目录创建而视为批准；必须关联已批准的工程任务。处于 Phase 0
时不得填写未来业务模块条目；后续阶段也不得借本模板提前创建未授权模块。
