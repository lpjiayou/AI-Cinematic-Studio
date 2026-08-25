# K2 G2 M6 Authority 与 Identity Lock 准备运行手册

> `2026-08-25`：K2-001 历史运行手册，`CLOSED TO NEW DISPATCH`；不得用于 K2-002。
>
> 下文“当前 / 必须 / 执行”等措辞只描述原时点，不是当前授权；不得重放任何命令或
> authority apply。
>
> 当前上限：`VALIDATED EXTERNAL INPUTS / G2 NOT PASSED / publicationAllowed=false`

本手册只准备现有 G2 主链需要的两类外部输入：M6 scope/approval authority 与
V5 identity-reference authority。它不创建 M6 领域事实，不替人选择角色身份，不调用
Creator 写接口，也不推进 `EpisodeProductionRun`。

## 1. 不可推断的输入

以下值必须从 canonical K2 的 authenticated API、受控 receipt 或实际人类决定取得，
不得从名字、测试夹具、旧数据库或模型输出猜测：

- `workspaceRef / projectRef / seriesRef / productionRunRef`；
- 三个独立 M6 action 的 `approvalRef / actorRef / actorKind`；
- 林澈、顾言对应的真实 M6 `characterRef`；
- 每个角色经选择和批准的 `referenceRef / referenceVersionRef / contentDigest`；
- Identity reference 的权利状态、来源与 `approvalRef`。

没有这些事实时保持 bundle 不存在。服务会继续使用 rejecting authority，G2 不会通过。

## 2. M6 authority bundle

文件必须是 UTF-8 JSON，使用精确 schema `v5.external-m6-authority-bundle.v1`。字段是
closed-world；一个 approval 只能绑定一个精确 scope 和一个精确 action。当前三个 action
只能是：

- `confirm-series-bible-version`；
- `confirm-character-continuity-version`；
- `activate-m6-baseline`。

```json
{
  "schemaVersion": "v5.external-m6-authority-bundle.v1",
  "authorityRef": "<EXTERNAL_M6_AUTHORITY_REF>",
  "scopes": [
    {
      "businessDomain": "series-production",
      "tenantId": "<TENANT_REF>",
      "workspaceRef": "<CANONICAL_WORKSPACE_REF>",
      "projectRef": "<CANONICAL_PROJECT_REF>",
      "seriesRef": "<CANONICAL_SERIES_REF>"
    }
  ],
  "approvals": [
    {
      "workspaceRef": "<CANONICAL_WORKSPACE_REF>",
      "projectRef": "<CANONICAL_PROJECT_REF>",
      "seriesRef": "<CANONICAL_SERIES_REF>",
      "approvalRef": "<BIBLE_HUMAN_APPROVAL_REF>",
      "action": "confirm-series-bible-version",
      "actorRef": "<VERIFIED_HUMAN_ACTOR_REF>",
      "actorKind": "human"
    },
    {
      "workspaceRef": "<CANONICAL_WORKSPACE_REF>",
      "projectRef": "<CANONICAL_PROJECT_REF>",
      "seriesRef": "<CANONICAL_SERIES_REF>",
      "approvalRef": "<CHARACTER_HUMAN_APPROVAL_REF>",
      "action": "confirm-character-continuity-version",
      "actorRef": "<VERIFIED_HUMAN_ACTOR_REF>",
      "actorKind": "human"
    },
    {
      "workspaceRef": "<CANONICAL_WORKSPACE_REF>",
      "projectRef": "<CANONICAL_PROJECT_REF>",
      "seriesRef": "<CANONICAL_SERIES_REF>",
      "approvalRef": "<BASELINE_HUMAN_APPROVAL_REF>",
      "action": "activate-m6-baseline",
      "actorRef": "<VERIFIED_HUMAN_ACTOR_REF>",
      "actorKind": "human"
    }
  ]
}
```

`ai / model / provider / ai-provider / automation-provider` 不能成为 M6 批准者。
`actorKind` 的外部 bundle 只接受 `human`（大小写不敏感）。在任何具体版本进入人类
审阅前，`approvals` 可以暂时是空数组；这只开放同一 trusted scope 下的草案创建，所有
确认和 baseline 激活仍会因 approval authority 不可用而 fail-closed。

## 3. Identity reference authority bundle

文件使用精确 schema `v5.external-identity-reference-authority-bundle.v1`。每项决定绑定
一个精确 `workspaceRef + productionRunRef + characterRef`，因此不能跨 run 或跨角色复用。
林澈与顾言各需要一项；下方只展示一项结构。

```json
{
  "schemaVersion": "v5.external-identity-reference-authority-bundle.v1",
  "authorityRef": "<EXTERNAL_IDENTITY_AUTHORITY_REF>",
  "references": [
    {
      "workspaceRef": "<CANONICAL_WORKSPACE_REF>",
      "productionRunRef": "<CANONICAL_PRODUCTION_RUN_REF>",
      "characterRef": "<EXACT_M6_CHARACTER_REF>",
      "referenceRef": "<APPROVED_REFERENCE_REF>",
      "referenceVersionRef": "<IMMUTABLE_REFERENCE_VERSION_REF>",
      "contentDigest": "<64_LOWERCASE_HEX_SHA256>",
      "mediaType": "image",
      "rightsState": "APPROVED",
      "provenance": "AUTHORITY_APPROVED",
      "approvalRef": "<IDENTITY_HUMAN_APPROVAL_REF>"
    }
  ]
}
```

允许的决定组合仅为：

- `APPROVED + AUTHORITY_APPROVED`；
- `LOCAL_EVIDENCE_ONLY + LOCAL_EVIDENCE`。

`mediaType` 只能是 `image / video / identity-direction`。bundle 不保存 token、Cookie、
Provider 凭据或图像二进制，只保存不可变引用和内容摘要。

## 4. 分阶段只验证并生成摘要绑定环境

### 4.1 Scope-only Bible 候选阶段

先使用只含 trusted scope、`approvals: []` 的 M6 bundle。此阶段脚本输出两项 M6 环境
绑定，Creator 只能创建 Series Bible 候选，不能确认版本、创建 Character Continuity
候选或激活 baseline：

```bash
cd /data/coding/AI-Cinematic-Studio
umask 077

M6_ENV_FILE=/data/k2-authority/k2-m6-scope.env
python scripts/k2_g2_external_authority_activate.py \
  --m6-bundle /absolute/path/m6-authority-scope-only.json \
  > "$M6_ENV_FILE"

chmod 600 "$M6_ENV_FILE"
. "$M6_ENV_FILE"
```

现有 M6 合同要求每个 Character Continuity version 引用一个已经 `CONFIRMED` 的
SeriesBibleVersion；scope-only bundle 的空 approval 集合不可能满足这个条件。因此本阶段
只能先创建 Bible candidate，不能把两个候选合并成一次写入。

K2-001 使用受控 Operator 输入和 authenticated loopback Creator Public API。先执行只读
预检；它会验证精确 scope bundle 摘要、M5 bootstrap 和空 M6 workspace：

```bash
export K2_CREATOR_API_BEARER_TOKEN='<CURRENT_CREATOR_BEARER_TOKEN>'

python scripts/k2_m6_draft_operator.py \
  --phase bible-candidate \
  --base-url http://127.0.0.1:8765 \
  --m6-bundle /absolute/path/m6-authority-scope-only.json
```

预检通过后才显式 `--apply`；receipt 路径必须不存在：

```bash
NOW_UTC="$(date -u +%Y%m%dT%H%M%SZ)"

python scripts/k2_m6_draft_operator.py \
  --phase bible-candidate \
  --base-url http://127.0.0.1:8765 \
  --m6-bundle /absolute/path/m6-authority-scope-only.json \
  --output "/data/k2-authority/evidence/k2-m6-bible-candidate-$NOW_UTC.json" \
  --apply
```

工具不会调用确认、baseline、Identity 或 Provider 端点；Bearer token 只从环境读取，
不会写入 receipt。实际人类必须先审阅这个不可变 Bible version，外部 Authority 才能为
精确 `confirm-series-bible-version` 动作签发 approval ref；不得提前填写占位批准。

### 4.2 Bible 确认后 Character 候选阶段

把真实 Bible approval 写入新的 digest-pinned M6 bundle，重启 Creator，并通过现有
Bible confirmation 端点确认精确 version。GET-only 复核其状态为 `CONFIRMED` 且
`approvalRef` 精确命中后，停止该进程并重新部署原始 scope-only bundle。这个回退会移除
确认 authority，但保留已经持久化的 Bible 事实。此时才允许创建 Character Continuity
candidate：

```bash
python scripts/k2_m6_draft_operator.py \
  --phase character-candidate \
  --base-url http://127.0.0.1:8765 \
  --m6-bundle /absolute/path/m6-authority-scope-only.json
```

当前 K2-001 checked-in Operator 输入固定绑定原始 scope-only bundle 摘要，工具也拒绝
任何含 approvals 的输入 bundle。它只能在 GET 复核已经确认的 Bible 后创建 Character
candidate，不能复用之前的批准执行新确认。Character 候选写入后仍然没有 baseline、
Identity Lock、G2 或 P1。

### 4.3 完整 M6 + Identity 阶段

把三个真实 M6 approvals 写入同一个 M6 bundle，先再次省略 `--identity-bundle` 运行
4.1 的环境绑定命令（但改用完整 M6 文件），让重启后的 Creator 只在精确 approval
命中时确认 Character version 并激活 M6 baseline。随后依据 baseline 的真实
`characterRef` 形成每个角色的
immutable identity reference 决定。将最终两个文件保存在受控主机的绝对路径，限制
读取权限，然后运行：

```bash
cd /data/coding/AI-Cinematic-Studio
umask 077

G2_ENV_FILE=/data/k2-authority/k2-g2-authority.env
python scripts/k2_g2_external_authority_activate.py \
  --m6-bundle /absolute/path/m6-authority.json \
  --identity-bundle /absolute/path/identity-reference-authority.json \
  > "$G2_ENV_FILE"

chmod 600 "$G2_ENV_FILE"
. "$G2_ENV_FILE"
```

完整调用只输出以下四项，不输出 bundle 内容；省略 `--identity-bundle` 时只输出前两项：

```text
CREATOR_M6_AUTHORITY_BUNDLE_PATH
CREATOR_M6_AUTHORITY_BUNDLE_SHA256
CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_PATH
CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256
```

路径必须是绝对路径，文件不得为空或超过 512,000 bytes。任一配置缺项、JSON 重复键、
未知字段、摘要不符、scope/action 不匹配或权利来源冲突都会失败。

## 5. 启动与边界

scope-only Bible 候选阶段的 Creator 进程只继承前两项：Lifecycle composition 解析
M6 scope，空 approval 集合继续拒绝所有确认。后续每次批准变更都必须使用新的外部文件
和独立摘要重启，不能把运行中修改文件视为 authority 更新。最终 G2 进程必须同时继承
上述四项：Lifecycle composition 用前
两项解析完整 M6 scope/approval，EpisodeProduction composition 用后两项解析 Identity
reference。没有配置时两边均 fail-closed；任一 bundle 的 path/digest 配置不完整时进程
必须拒绝启动。

通过本手册的 validator 只表示相应阶段的外部文件和摘要绑定有效。草案阶段不得标记
`G2_EXTERNAL_INPUTS_VALIDATED`；完整 M6 approvals、激活的 baseline 和 Identity bundle
均存在后，才可记录该验证状态。随后仍需在 authenticated Creator Public API 上用真实
一对一 character mapping 调用现有 G2 `authorize-and-lock`。完成后必须 GET-only 复核：

- 同一 canonical root 与 `productionRunRef`；
- 当前 M5/M6 lineage 与 canonical digest；
- 两个角色均有一个 immutable identity decision；
- 状态仅从 `ROOTS_READY` 变为 `AUTHORITY_READY`；
- `publicationAllowed=false`；
- P1 仍为 `NOT_PASSED`。

在上述写入和复核完成前，不得宣称 M6、Identity Lock 或 G2 已通过，也不得开始 Provider
dispatch。
