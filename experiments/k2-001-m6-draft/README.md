# K2-001 M6 分阶段草稿候选

> 状态：`OPERATOR INPUT / NOT DOMAIN FACT / HUMAN REVIEW REQUIRED`

本目录把已审阅的 K2-001《记忆回声》创作候选整理为现有 M6 合同可以接收的
Series Bible 与 Character Continuity 输入。它不创建审批、确认版本、激活 baseline、
建立 Identity Lock 或推进 G2/P1。

## 固定血缘

- `tenantId=tenant-k2-001-canonical`
- `workspaceRef=workspace-6c2c70926cf64cd68435537ffd4de92d`
- `projectRef=project-00482509a3a14837be7f29f1467c0ced`
- `seriesRef=series-c0a74d5580b44aeea75747ad1d33438a`
- `authorityRef=m6-scope-authority-k2-001-v1`
- scope-only bundle SHA-256：
  `d4f4fcb0a71cc734c06478e80ef8ce09c188d5be46a9e741472b7673959554e7`

## 必须分阶段执行的原因

现有 M6 合同要求 Character Continuity 引用一个已经确认的
`SeriesBibleVersion`。空审批的 scope-only bundle 只能创建 Bible 候选，不能确认
Bible，因此也不能在同一阶段创建 Character 候选。

正确顺序固定为：

1. 部署精确 scope-only bundle，只创建 Bible candidate；
2. 人工审阅该不可变 Bible version，外部 Authority 签发精确 Bible approval；
3. 用含该项批准的新 bundle 重启 Creator 并确认该 Bible version；
4. GET-only 复核后停止进程，重新部署原始 scope-only bundle，再运行本工具，只创建
   Character Continuity candidate；
5. 人工审阅 Character version，分别取得 Character 与 baseline approval；
6. 确认 Character、激活 baseline，之后才准备 Identity reference authority。

## Operator 工具

工具只访问现有 Creator Public API。它永远不会调用 Bible/Character confirmation、
baseline activation 或 G2 authorize-and-lock 接口。Bearer token 只从
`K2_CREATOR_API_BEARER_TOKEN` 读取，不接受命令行 token，也不写入 receipt。

Bible 候选预检：

```bash
cd /data/coding/AI-Cinematic-Studio

python scripts/k2_m6_draft_operator.py \
  --phase bible-candidate \
  --base-url http://127.0.0.1:8765 \
  --m6-bundle /data/k2-authority/k2-g2-scope-authority-20260822/k2-m6-scope-authority-k2-001-v1.json
```

预检通过后才显式执行：

```bash
EVIDENCE_DIR=/data/k2-authority/evidence
NOW_UTC="$(date -u +%Y%m%dT%H%M%SZ)"

python scripts/k2_m6_draft_operator.py \
  --phase bible-candidate \
  --base-url http://127.0.0.1:8765 \
  --m6-bundle /data/k2-authority/k2-g2-scope-authority-20260822/k2-m6-scope-authority-k2-001-v1.json \
  --output "$EVIDENCE_DIR/k2-m6-bible-candidate-$NOW_UTC.json" \
  --apply
```

Bible 经真实人工批准并通过现有确认接口成为 `CONFIRMED` 后，GET-only 复核并重新以
原始 scope-only bundle 启动 Creator，再使用同样方式把 `--phase` 改为
`character-candidate`。工具会从 authenticated M5 bootstrap 动态解析真实
`episodePlanItemRef`，不会使用文档中的 `K2-001-SH-*` 候选键或按名称推断 Ref。

## 硬边界

- 输入文件中的 Character Ref 是待写入 M6 candidate 的显式结构化身份，不是从名称
  推断出的历史事实；
- `identityBindings` 必须为空；
- 每次 `--apply` 都输出一个 secret-free receipt，且拒绝覆盖已有文件；
- Bible 未确认时，Character 阶段必须失败且不得发送写请求；
- 任一阶段结束后仍保持 `G2 NOT PASSED / P1 NOT PASSED /
  publicationAllowed=false`。
