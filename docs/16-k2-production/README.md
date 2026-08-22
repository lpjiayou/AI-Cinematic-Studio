# K2 单集生产候选资料

本目录保存 K2 单集在正式 Provider 调用前可离线完成的创作与操作候选资料。
它们服从根目录 `AGENTS.md`、`CURRENT_MILESTONE.md`、ADR-0009、ADR-0010、
ADR-0011 与现有
Creator Public API → Application → V5 → V4 → V3 → Compute 主链。

当前所有文件均为：

`DRAFT / CANDIDATE / NOT DOMAIN FACT / P1 NOT PASSED / publicationAllowed=false`

目录内的镜头号、人物设计键和提示词是便于审阅的候选标识，不是 Core 生成的
`projectRef`、`characterRef`、`creativeShotRef` 或 `GenerationRequestRef`。开机后必须从
经 ADR-0010 受控引导生成并只读验证的新 canonical K2 run 解析真实引用和摘要，
不得按名称重建血缘，也不得复用历史测试 Ref。

- [K2-001 剧本、分镜、镜头、Wan2.2 与角色多角度候选](K2-001-PREPRODUCTION-CANDIDATE.md)
- [P1 开机前到受治理实验运行手册](K2-P1-PREBOOT-TO-LIVE-RUNBOOK.md)
- [K2 内部自托管 P1 同血缘视频运行手册](K2-INTERNAL-SELF-HOSTED-P1-RUNBOOK.md)
- [G2 M6 Authority 与 Identity Lock 准备运行手册](K2-G2-AUTHORITY-PREPARATION-RUNBOOK.md)
- [K2-001 M6 分阶段候选与 Operator 说明](../../experiments/k2-001-m6-draft/README.md)

对应机器可读清单：

`experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json`

M6 的机器可读候选输入位于：

`experiments/k2-001-m6-draft/k2-001-m6-draft-candidate.v1.json`

它固定为 `NOT DOMAIN FACT`，只允许先创建 Bible candidate；Character candidate 必须
等待该 Bible 经真实人工批准并确认后，再使用同一精确 scope-only 输入执行。

新的 canonical root 规范与 Operator Application 分别位于：

- `experiments/k2-001-canonical-bootstrap/k2-001-canonical-bootstrap.v1.json`；
- `scripts/k2_canonical_lineage_bootstrap.py`；
- `scripts/k2_canonical_lineage_api_verify.py`（apply 后的 authenticated GET-only
  exact-match 与 secret-free receipt）；
- [`K2 Canonical Lineage G1 正式主机收口记录`](../../governance/K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21.md)。

它们只允许建立一个 `ROOTS_READY` 根。正式主机已在实现 commit `57ce3d0b…` 上完成
唯一一次 apply、独立只读扫描和七资源 authenticated API exact-match；该 root 的真实
Ref 只能从 secret-free receipt 或 authenticated API 读取。M6 Authority、Identity Lock、
P1 与发布均未随 bootstrap 自动推进。

离线校验：

```bash
python scripts/k2_preboot_validate.py \
  --manifest "$PWD/experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json"
```
