# K2 单集生产候选资料

本目录保存 K2 单集在正式 Provider 调用前可离线完成的创作与操作候选资料。
它们服从根目录 `AGENTS.md`、`CURRENT_MILESTONE.md`、ADR-0009、ADR-0010 与现有
Creator Public API → Application → V5 → V4 → V3 → Compute 主链。

当前所有文件均为：

`DRAFT / CANDIDATE / NOT DOMAIN FACT / P1 NOT PASSED / publicationAllowed=false`

目录内的镜头号、人物设计键和提示词是便于审阅的候选标识，不是 Core 生成的
`projectRef`、`characterRef`、`creativeShotRef` 或 `GenerationRequestRef`。开机后必须从
经 ADR-0010 受控引导生成并只读验证的新 canonical K2 run 解析真实引用和摘要，
不得按名称重建血缘，也不得复用历史测试 Ref。

- [K2-001 剧本、分镜、镜头、Wan2.2 与角色多角度候选](K2-001-PREPRODUCTION-CANDIDATE.md)
- [P1 开机前到受治理实验运行手册](K2-P1-PREBOOT-TO-LIVE-RUNBOOK.md)

对应机器可读清单：

`experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json`

离线校验：

```bash
python scripts/k2_preboot_validate.py \
  --manifest "$PWD/experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json"
```
