# K2 单集生产资料

本目录同时保存已冻结的验证历史和当前受控预生产包。所有媒体生产仍服从
`CURRENT_MILESTONE.md`、Accepted ADR 与既有
Creator Public API → Application → V5 → V4 → V3 → Compute 主链。

## 当前状态

| 工作项 | 仓库状态 | 媒体状态 |
| --- | --- | --- |
| K2-001 | [验证历史已归档](K2-001-HISTORICAL-VALIDATION-ARCHIVE.md) | `M10 V1 IMAGES ADMITTED AS HISTORY / M11 + R2–R7 FAILED OR UNSELECTED AND NOT_ADMITTED / NOT PUBLISHABLE / CLOSED TO NEW DISPATCH` |
| K2-002《长安刮痕》 | [v1.3 审校修订候选](k2-002-changan/README.md) | `PREPRODUCTION / SCRIPT OWNER ACCEPTANCE PENDING / GENERATION NOT STARTED / NOT_ADMITTED / NOT PUBLISHABLE` |

K2-001 与 K2-002 是两条不同 lineage。不得复用 K2-001 的 `workspaceRef`、
`productionRunRef`、生成请求、候选、AssetVersion、决策或 ADR-0011 例外。

## K2-001 历史入口

- [历史归档索引与边界](K2-001-HISTORICAL-VALIDATION-ARCHIVE.md)
- [剧本、分镜、镜头与角色多角度候选](K2-001-PREPRODUCTION-CANDIDATE.md)
- [P1 开机前到受治理实验运行手册](K2-P1-PREBOOT-TO-LIVE-RUNBOOK.md)
- [内部自托管 P1 同血缘视频运行手册](K2-INTERNAL-SELF-HOSTED-P1-RUNBOOK.md)
- [图像优先真实媒体修订合同](../../architecture/K2_INTERNAL_IMAGE_FIRST_REAL_MEDIA_REVISION_CONTRACT.md)
- [G2 M6 Authority 与 Identity Lock 准备运行手册](K2-G2-AUTHORITY-PREPARATION-RUNBOOK.md)

历史机器可读资料仍保留原路径，避免改写既有证据引用：

- `experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json`
- `experiments/k2-001-m6-draft/k2-001-m6-draft-candidate.v1.json`
- `experiments/k2-001-canonical-bootstrap/k2-001-canonical-bootstrap.v1.json`

## K2-002 当前入口

- [K2-002 状态、剧本审校与链路准入矩阵](k2-002-changan/README.md)
- [v1.2 LF-normalized 来源副本（双 digest 见说明）](k2-002-changan/source/K2-002-CHANGAN-SOURCE-v1.2.md)
- [审校修订候选 v1.3](k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.3.md)
- [ADR-0014：K2-001 归档与 K2-002 启动](../../governance/ADR-0014-k2-001-archive-k2-002-changan-start.md)

“开始 K2-002”在当前阶段只表示：来源入库、审校修订、注册要求冻结，以及
Shot/Profile 和零写 preflight 合同准备。Durable registration apply/receipt 与 Core-only
M5 binding 尚未实现。缺少精确引用、输入资产或后处理清单时必须 fail closed；不得把
文档中的提示词直接送往 Provider，也不得把技术 PASS 推导为选片、准入或发布。
