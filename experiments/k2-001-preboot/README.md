# K2-001 开机前候选清单

本目录只有离线创作与实验计划，不含生成媒体、Provider 响应、secret、Authority bundle、
Core domain ref、candidate selection 或 production admission。

`k2-001-preproduction-candidate.v1.json` 的状态固定为：

`DRAFT_CANDIDATE_NOT_DOMAIN_FACT / P1_NOT_PASSED / publicationAllowed=false`

校验：

```bash
python scripts/k2_preboot_validate.py \
  --manifest "$PWD/experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json"
```

开机后必须从当前 K2 G4/M9 重新解析已有 video/audio 的真实
`GenerationRequestRef`；当前 G4 没有 image request，该缺口必须保持 blocker，直到有
获批的同源合同扩展。本目录中的 `K2-001-SH-*` 只是创作候选键，不能升级为 Core ref。
