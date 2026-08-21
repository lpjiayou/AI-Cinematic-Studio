# K2 P1 从离线候选到受治理实验运行手册

> 当前状态：`CANONICAL ROOT G1 HOST-VERIFIED / M6 + IDENTITY NOT CREATED / P1 NOT PASSED`

本手册把已完成的开机前资料接回现有主链。它不绕过
`docs/08-compute/k2-comfyui-wan22-operator-runbook.md`，也不把 image/audio 缺口
伪装成可执行能力。

## 1. 现在即可执行：离线总检

```bash
set -o pipefail
cd /absolute/path/to/AI-Cinematic-Studio

python scripts/k2_preboot_validate.py \
  --manifest "$PWD/experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json"

python -m unittest tests.unit.test_k2_preboot_package -v
```

期望输出至少包含：

```text
K2_PREBOOT_PACKAGE=PASS
BUDGET_HARD_CAP=CNY_1000
PAID_CALLS_EXECUTED=0
P1_GATE=NOT_PASSED
PUBLICATION_ALLOWED=false
```

这一步不需要网络、GPU、Provider 凭据或外部音频。

## 2. 开机后的第一个动作：只读定位当前血缘

不要沿用文档中的 `K2-001-SH-*` 候选键作为 Core ref。先确认：

```bash
cd /absolute/path/to/AI-Cinematic-Studio

python scripts/k2_readonly_lineage_scan.py \
  --root /data \
  --max-depth 6 \
  --max-rows 200 \
  | tee /data/k2-authority/k2-readonly-lineage-scan.txt
```

该工具只以 SQLite `mode=ro + query_only` 打开既有文件，只输出已知表的计数、稳定
Ref、version、state 和 digest。它不选择 payload JSON、创作正文、idempotency key 或
credential 字段，也不会初始化数据库。期望最终输出
`K2_CURRENT_LINEAGE_STATUS=FOUND_READ_ONLY`；如果是 `NOT_FOUND`，不得启动 Creator
server，因为默认路径可能创建一套新的空数据库。

`2026-08-21` 的扩展只读定位已经覆盖 `/data`、`/root`、`/home` 与 `/tmp`：

- 只发现两个 ComfyUI 自身 SQLite 文件；它们不包含已知 K2 Core 表；
- 15 个归档中没有数据库成员；
- `K2_PRODUCTION_DATABASES_FOUND=0`、`K2_PRODUCTION_RUNS_FOUND=0`；
- 定位审计文件 SHA-256 为
  `7aaa36333f08be3bdfd09c6b4632804f3b7bf14a0bd1bc35f359df0391fa167b`。

因此当前状态是 `K2_CURRENT_LINEAGE_STATUS=NOT_FOUND`，不是待修复的路径问题，也
不能用测试中的固定 Ref、文档候选键或文件名重建。后续只能二选一：

1. 从当前存储之外取得可校验的原始 K2 Core 数据库或受控快照，并再次只读扫描；
2. 由 Project Lead 明确批准建立一条新的 canonical K2 lineage。

第二种路径属于重新引导，不是恢复。它必须经现有 Creator Public API 和已接受的
Application → V5 边界创建，使用显式持久化路径、初始化前空目录检查、初始化后只读
复核与数据库摘要；不得直接写 SQLite，也不得把旧的技术证据描述成新血缘上的生产
事实。在作出该决定之前保持 Creator 停止、`P1 NOT PASSED` 和
`publicationAllowed=false`。

Project Lead 已于 `2026-08-21` 选择并授权第二种路径。ADR-0010 冻结的引导上限是
新建一个 `ROOTS_READY` root；M6 Authority、Identity Lock、Rights/Provider/budget、
live media 与 publication 均不随该授权产生。治理检查点已在 PR #9 的
`976416bdd1a5a93001e1f271d406ed41e1415208` 通过 Repository Validation #43 的
5/5 作业。正式 apply 只能在本轮实现 checkpoint 也完成远端验证后执行。

### 2.1 无写 dry-run

以下命令不需要 GPU、模型加载、Provider 凭据或外部音频。它会校验精确规范、目标
安全性和 fail-closed 退出状态，但不会创建 canonical 目录：

```bash
set -euo pipefail
cd /data/coding/AI-Cinematic-Studio

SPEC="$PWD/experiments/k2-001-canonical-bootstrap/k2-001-canonical-bootstrap.v1.json"
CANONICAL_PARENT=/data/k2-core
CANONICAL_TARGET="$CANONICAL_PARENT/k2-001-canonical-v1"

test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$CANONICAL_TARGET"
install -d -m 700 "$CANONICAL_PARENT"

python scripts/k2_canonical_lineage_bootstrap.py \
  --spec "$SPEC" \
  --target-dir "$CANONICAL_TARGET" \
  | tee /data/k2-authority/k2-canonical-bootstrap-dry-run.txt

test ! -e "$CANONICAL_TARGET"
```

期望摘要：

```text
K2_CANONICAL_BOOTSTRAP_VALIDATION=PASS
SPECIFICATION_SHA256=3b4d77b371cb23e2acf5420d74ded9d890a877f9555d781bc7842d0b715eb0ee
PAYLOAD_SHA256=0dfa64aa23e7120415a58b48eb00bb5d92274518d16051f2cb419525ea3b364c
K2_CANONICAL_BOOTSTRAP_MODE=DRY_RUN_NO_WRITE
K2_CANONICAL_ROOT_STATUS=NOT_CREATED
P1_GATE=NOT_PASSED
PUBLICATION_ALLOWED=false
```

### 2.2 唯一正式 apply

只在实现 commit、远端 tree 与 CI 已由本工作包复核后执行一次。不要提供
`--repository-commit`；脚本会从干净 checkout 解析真实 HEAD 并写入 receipt：

```bash
python scripts/k2_canonical_lineage_bootstrap.py \
  --spec "$SPEC" \
  --target-dir "$CANONICAL_TARGET" \
  --apply \
  --acknowledge-new-lineage NEW_CANONICAL_K2_LINEAGE_NOT_RECOVERY \
  | tee /data/k2-authority/k2-canonical-bootstrap-apply.txt
```

期望最终状态只能是：

```text
K2_CANONICAL_BOOTSTRAP=PASS
K2_CANONICAL_ROOT_STATUS=ROOTS_READY
M6_AUTHORITY_STATUS=NOT_CREATED
IDENTITY_LOCK_STATUS=NOT_CREATED
P1_GATE=NOT_PASSED
PUBLICATION_ALLOWED=false
```

脚本在同盘私有 staging 中通过 V5 创建根链，重启并调用现有 read-only scanner，要求
恰好一个 production run，然后以 no-replace 原子 rename 发布。失败会清除 staging；
目标已存在、确认短语不精确、checkout 非干净或扫描不一致都会停止。不要自动重试或
删除目标。

### 2.3 apply 后的独立文件与只读复核

```bash
(
  cd "$CANONICAL_TARGET"
  sha256sum -c k2-canonical-bootstrap-inventory.sha256
)

python scripts/k2_readonly_lineage_scan.py \
  --root "$CANONICAL_TARGET" \
  --max-depth 1 \
  --max-rows 20 \
  | tee /data/k2-authority/k2-canonical-bootstrap-readonly-scan.txt
```

必须得到 `K2_PRODUCTION_DATABASES_FOUND=1`、
`K2_PRODUCTION_RUNS_FOUND=1` 和
`K2_CURRENT_LINEAGE_STATUS=FOUND_READ_ONLY`。将 apply 输出、receipt、inventory 和
独立 scan 的 SHA-256 保存到 `/data/k2-authority`，但不要把数据库、创作正文或宿主
绝对路径提交到 Git。

### 2.4 authenticated Public API exact-match

Creator authenticated API 核对时必须显式注入固定数据库路径；不要让 Creator 回退到
默认空库：

```bash
export CREATOR_DATA_PATH="$CANONICAL_TARGET/creator-workspace.sqlite3"
export CREATOR_EPISODE_PRODUCTION_DATA_PATH="$CANONICAL_TARGET/episode-production.sqlite3"
export CREATOR_PRODUCTION_POLICY_DATA_PATH="$CANONICAL_TARGET/episode-production.sqlite3.production-policy.sqlite3"
export CREATOR_MEDIA_JOB_DATA_PATH=/data/k2-runtime/k2-001/media-jobs.sqlite3
export CREATOR_MEDIA_ARTIFACT_ROOT=/data/k2-runtime/k2-001/artifacts
```

使用一次性随机 server-to-server bearer。原始值只保留在当前 shell 环境，配置文件只写
SHA-256；不要把原始值粘贴到命令行参数、日志、Git 或证据文件：

```bash
set -euo pipefail
install -d -m 700 /data/k2-runtime/k2-001 /data/k2-authority/evidence

export K2_WORKSPACE_REF="$(
  python - "$CANONICAL_TARGET/k2-canonical-bootstrap-receipt.v1.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["lineage"]["workspaceRef"])
PY
)"
export K2_CREATOR_API_BEARER_TOKEN="$(
  python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
export K2_CREATOR_API_TOKEN_SHA256="$(
  printf '%s' "$K2_CREATOR_API_BEARER_TOKEN" | sha256sum | awk '{print $1}'
)"
export CREATOR_PUBLIC_API_TOKEN_CONFIG=/data/k2-runtime/k2-001/creator-public-auth.v1.json

python - <<'PY'
import json
import os
from pathlib import Path
import tempfile

target = Path(os.environ["CREATOR_PUBLIC_API_TOKEN_CONFIG"])
value = {
    "schemaVersion": "creator.public-auth.v1",
    "credentials": [
        {
            "credentialRef": "k2-canonical-verifier-v1",
            "workspaceRef": os.environ["K2_WORKSPACE_REF"],
            "tokenSha256": os.environ["K2_CREATOR_API_TOKEN_SHA256"],
            "enabled": True,
        }
    ],
}
descriptor, temporary = tempfile.mkstemp(prefix=".creator-auth-", dir=target.parent)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

unset K2_CREATOR_API_TOKEN_SHA256
export CREATOR_PUBLIC_API_HOST=127.0.0.1
export CREATOR_PUBLIC_API_PORT=8765

while IFS= read -r NAME; do unset "$NAME"; done < <(compgen -A variable COMFYUI_)
unset CREATOR_RIGHTS_AUTHORITY_BUNDLE_PATH \
  CREATOR_RIGHTS_AUTHORITY_BUNDLE_SHA256 \
  CREATOR_PROVIDER_AUTHORITY_BUNDLE_PATH \
  CREATOR_PROVIDER_AUTHORITY_BUNDLE_SHA256
```

短暂启动 loopback Creator，仅执行认证 GET 核对。清理函数会停止进程并清除当前 shell
中的原始 bearer：

```bash
CREATOR_LOG=/data/k2-authority/k2-canonical-creator-readonly-verification.log
CREATOR_PID=""
cleanup_k2_api_verify() {
  if [ -n "$CREATOR_PID" ]; then
    kill "$CREATOR_PID" 2>/dev/null || true
    wait "$CREATOR_PID" 2>/dev/null || true
  fi
  unset K2_CREATOR_API_BEARER_TOKEN K2_WORKSPACE_REF
}
trap cleanup_k2_api_verify EXIT

python -m apps.creator_workspace_mvp.server >"$CREATOR_LOG" 2>&1 &
CREATOR_PID=$!

CREATOR_READY=0
for _ in $(seq 1 30); do
  if ! kill -0 "$CREATOR_PID" 2>/dev/null; then
    break
  fi
  if curl -fsS --max-time 2 http://127.0.0.1:8765/health >/dev/null; then
    CREATOR_READY=1
    break
  fi
  sleep 1
done
test "$CREATOR_READY" = 1

VERIFY_TIME="$(date -u +%Y%m%dT%H%M%SZ)"
VERIFY_OUTPUT="/data/k2-authority/evidence/k2-canonical-public-api-verification-$VERIFY_TIME.json"
python scripts/k2_canonical_lineage_api_verify.py \
  --canonical-root "$CANONICAL_TARGET" \
  --base-url http://127.0.0.1:8765 \
  --output "$VERIFY_OUTPUT" \
  | tee /data/k2-authority/k2-canonical-public-api-verification.txt

sha256sum "$VERIFY_OUTPUT" | tee "$VERIFY_OUTPUT.sha256"
(
  cd "$CANONICAL_TARGET"
  sha256sum -c k2-canonical-bootstrap-inventory.sha256
)

cleanup_k2_api_verify
trap - EXIT
```

必须得到 `K2_CANONICAL_PUBLIC_API_VERIFICATION=PASS`、
`VERIFIED_RESOURCE_COUNT=7`、`CANONICAL_ROOT_STATUS=ROOTS_READY`、
`P1_GATE=NOT_PASSED` 和 `PUBLICATION_ALLOWED=false`。核验器不跟随 redirect；Series、
Project、Episode、Series Plan workspace、Script workspace、run detail 与 run list 的
任一 ref/version/digest 不一致、run 数量不是 1 或 API 非 loopback 都会 fail closed。

不要设置任何 `COMFYUI_*` 或外部 Authority 环境变量，直到该 exact-match receipt 已
生成。runtime job/artifact 路径放在 canonical 目录之外，避免把后续运行文件混入根
数据库 inventory。

### 2.5 正式主机 G1 收口记录

`2026-08-21T15:24:43Z`，正式主机在实现 commit
`57ce3d0bf3e5772f57cea7a8a79726237ef366ba` 上完成唯一一次 acknowledged apply。
独立只读扫描得到五个数据库、一个 production database、一个 production run；七个
authenticated Public API 投影全部 exact-match。bootstrap receipt SHA-256 为
`94fad69a2fdffe50e599c08fdc0e7c94aa3a381a30d1515b126a1f8b88076234`，API verification
receipt SHA-256 为
`d4c2a52d1c141ed5f0b8b24a13a985e47e38b3b78eac27eb5d59b452c18ca8a6`。

G1 的正式状态为 `ROOTS_READY / COMPLETE`；M6 Authority、Identity Lock、P1 与发布
均未随 bootstrap 自动推进。完整记录见
[`K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21.md`](../../governance/K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21.md)。

仅当结果为 `FOUND_READ_ONLY` 时，才继续核对：

1. 当前仓库分支、commit 与干净工作树；
2. authenticated Creator Public API 可达；
3. 当前 K2 `projectRef`、`episodeProductionRunRef`、M6 Authority、Identity Lock、
   ExecutableShotGraph 与 M9 Asset Plan 未变 stale；
4. 从当前 G4/M9 重新读取每镜已有 video/audio 的真实 `GenerationRequestRef`、version
   和 digest；确认 current G4 image request 仍缺失并保持 blocker；
5. 当前生产策略仍为 30 秒、24 fps、四镜，预算 hard cap 不超过 CNY 1000。

任何引用缺失、摘要变化、workspace 不一致或上游版本变更都应停止并重新生成候选映射，
不得按人物名、镜头序号或文件名猜测。

## 3. 激活外部 Authority

Rights 与 Provider bundle 必须由外部权威提供，先在受控主机计算精确 SHA-256，再运行：

```bash
cd /absolute/path/to/AI-Cinematic-Studio

python scripts/k2_external_authority_activate.py \
  --rights-bundle /absolute/operator/path/rights-authority.json \
  --provider-bundle /absolute/operator/path/provider-authority.json
```

只把脚本打印的四个 digest-pinned 环境赋值注入 Creator server。实际 worker secret 由
`credentialSourceRef` 指向的秘密系统提供，不复制进命令历史、Git、浏览器或证据包。

激活后重新读取 production readiness，必须验证：

- 所有输入摘要有 exact rights decision；
- image/video/audio 各有精确 provider/model/region/endpoint execution；
- Provider 子上限之和不超过 `100000` minor CNY；
- current attestation 的精确 ref/digest 已被 Provider Authority 接受；
- `region=provider-not-disclosed` 被显式接受或被真实 region 取代；
- expiry、usage terms、safety/privacy、retention 与 release territories 相容。

如果任一项缺失，保持 `BLOCKED_EXTERNAL_EVIDENCE`，不要启动模型。

## 4. 启动视频技术运行时

视频路径严格按现有
`docs/08-compute/k2-comfyui-wan22-operator-runbook.md` 执行。安装、启动、取证必须使用
同一个 Python 解释器，并在 dispatch 前重新生成 runtime attestation。

最小核验：

```text
ComfyUI /system_stats reachable
exactly one CUDA device
10/10 required native nodes
exact UNET / TEXT_ENCODER / VAE names and SHA-256
runtime attestation ref/digest equals approved Provider Policy
```

`2026-08-21` 当前启动已重新生成并独立验证 attestation
`technical-k2-funhpc-a100-20260821T130634Z`，payload digest 为
`be03a079d17cad524b5e2e061e0c651a8f41f6f5221dfe80a8244398817ded53`。它仍必须被
Provider Authority 精确接受；`2026-08-20` 记录只保留为历史技术证据。

## 5. 三媒体实验顺序

### 5.1 Image

当前 G4 只有四个 video 和四个 audio `GenerationRequest`，没有 image request；仓库也
尚无获批 image live adapter 与同源 image dispatch 入口。在获批的同源合同扩展、精确
Provider 决定和 V4 adapter 完成前，停止在 `NOT_SELECTED`。不得把 ChatGPT 图片、网页
素材、手工上传或本目录提示词直接写成 M10 AssetVersion。

adapter 就绪后，先对林澈/顾言各做一组低成本八视图 identity candidate，再为四镜各做
一张构图 preflight。每张保持 unselected/not admitted，并记录精确输入/输出摘要和成本。

### 5.2 Video

视频使用现有受控 endpoint：

```text
POST /creator/api/v1/episode-production-runs/{productionRunRef}/provider-experiments
```

每次只提交当前 M9 video `sourceGenerationRequestRef`、外部权威返回的
`providerCapabilityRef` 与新的 idempotency key。V5 会生成固定 49-frame profile；不要把
文档提示词、seed、workspace 或 run ref直接塞进请求体绕过派生逻辑。

建议先只运行 SH-010 的一个 49-frame attempt。确认 cost、latency、probe、digest、runtime
与 lineage 完整后，再决定是否继续另外三镜；总承诺费用始终不得超过硬上限。

### 5.3 Audio

当前仓库尚无获批 neutral-TTS live adapter。adapter 和 Authority 未完成前停止在
`NOT_SELECTED`。后续只允许两句现有剧本文字作为输入：

```text
顾言：从现在起，只相信我们亲眼看到的。
林澈：它被删掉了，但没有消失。
```

不上传外部音频，不启用 voice cloning，不模仿真人，P1 不生成音乐。对白、环境和提示音
分别记录 stem lineage，并在合成前独立 probe 48 kHz/双声道/时长/削波/同步。

## 6. 每次调用前预算熔断

对每个 attempt，先读取服务器当前已提交成本，再验证：

```text
committed_total_minor + next_attempt_max_minor <= 100000
provider_subcap_remaining >= next_attempt_max_minor
currency == CNY
budgetAuthorityRef == current approved policy value
```

未知成本、币种换算缺失、Provider 报价变化、子上限缺失或并发保留不确定时，全部视为
不可调用。失败 attempt 的计费也必须计入 committed total；不能只统计成功文件。

## 7. 证据收口

每个 real attempt 完成后立即保存 secret-free 证据：

- 请求/镜头/策略/权利 lineage；
- adapter/job/attempt/provider request refs；
- provider/model/region/endpoint/runtime facts；
- 精确 cost、currency、latency；
- 文件 SHA-256、bytes 与独立 media probe；
- candidate state 与 blocker；
- `publicationAllowed=false`。

运行时 attestation 使用现有归档工具：

```bash
python scripts/k2_comfyui_runtime_evidence_archive.py --help
```

只归档工具声明的 safe payload；模型本体、secret、本地主机绝对路径和浏览器凭据不得进入
Git 或审核包。

## 8. 自动停止条件

出现以下任一情况立即停止：

- 离线清单校验失败；
- Rights/Provider/Budget Authority 缺失或摘要不匹配；
- 当前 run/G4 request stale 或 workspace 不一致；
- 任一媒体没有 V4 adapter 与受治理入口；
- image/video/audio 任一结果无法 probe、超预算、超时或 identity/continuity 失败；
- 输出被错误标成 selected/admitted/publishable；
- 需要人工创意、身份、技术或 master 决定。

停止后只记录 blocker。P1 只有在三媒体同源真实实验均存在且后续条件满足时才可能通过；
视频成功不能替代 image/audio。
