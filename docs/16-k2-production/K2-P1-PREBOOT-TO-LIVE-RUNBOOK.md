# K2 P1 从离线候选到受治理实验运行手册

> 当前状态：`PREBOOT READY / LIVE DISPATCH BLOCKED / P1 NOT PASSED`

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

## 2. 开机后的第一个动作：重建当前血缘

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
