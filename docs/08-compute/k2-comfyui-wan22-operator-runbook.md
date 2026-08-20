# K2 ComfyUI / Wan2.2 受控候选实验运行手册

> 状态：`P1 SAFE IMPLEMENTATION / EXTERNAL AUTHORITY REQUIRED`
>
> 范围：现有 K2 `EpisodeProductionRun` 的视频候选实验；不是独立生成工具。

## 1. 接入位置

唯一合法链路是：

```text
Commercial Frontend
→ Frontend Experience Adapter
→ authenticated Creator Public API
→ Creator Application
→ V5 K2 Provider Experiment Service
→ V4 MediaJobCoordinator
→ ComfyUIWan22VideoAdapter
→ approved ComfyUI / GPU runtime
```

ComfyUI 的成功结果仍是 `UNTRUSTED_PROVIDER_CANDIDATE / UNSELECTED /
NOT_ADMITTED`。本工作包不会创建 `AssetVersion`、推进现有 G5 `MEDIA_READY`、
代替人工选择或把 `publicationAllowed` 改为 `true`。

## 2. 开始前必须具备的外部事实

同一 K2 lineage 必须先存在当前有效的：

- `ProductionPolicyVersion`；
- `RightsManifestVersion`，状态为 `RIGHTS_CLEARED`；
- `ProviderExecutionPolicyVersion`，含唯一的视频 provider/model/region/capability；
- 可解析但不含秘密值的 `credentialSourceRef`、`usageTermsRef`、
  `budgetAuthorityRef`；
- 明确的币种、单次成本上限、总预算与超时；
- 要求 GPU attestation 的 provider policy，并由外部权威写入精确的
  `runtimeAttestationRef + runtimeAttestationDigest`。

这些事实只能由已注入的 Rights/Provider Authority 产生。环境变量、浏览器请求、
文件名、一次成功生成或本手册都不能授予版权、预算或生产权限。

## 3. 在 GPU 主机生成技术运行证明

在实际运行 ComfyUI 的主机上，从本仓库根目录执行。脚本会读取三份真实模型文件、
计算 SHA-256，并通过 ComfyUI API 核对节点、模型名称和唯一 CUDA 设备。输出不包含
Base URL、Bearer Token 或模型本地路径。

安装依赖、启动 ComfyUI 和运行操作脚本必须使用同一个绝对 Python 解释器。另一个
Conda/venv 中的 `pip check` 或导入成功不能证明 ComfyUI 进程使用了相同依赖。可从
ComfyUI PID 的 `/proc/<pid>/cmdline` 第一项复核实际解释器，再用该路径运行以下脚本。

先设置非秘密配置；秘密仅允许通过进程环境注入，禁止写入 Git：

```bash
export COMFYUI_BASE_URL=http://127.0.0.1:8188
export COMFYUI_PROVIDER_ID=self-hosted-comfyui
export COMFYUI_MODEL_ID=wan2.2-ti2v-5b-fp16
export COMFYUI_REGION=<approved-region>
export COMFYUI_ENDPOINT_CLASS=<approved-endpoint-class>
export COMFYUI_UNET_NAME=wan2.2_ti2v_5B_fp16.safetensors
export COMFYUI_UNET_SHA256=<verified-sha256>
export COMFYUI_CLIP_NAME=umt5_xxl_fp8_e4m3fn_scaled.safetensors
export COMFYUI_CLIP_SHA256=<verified-sha256>
export COMFYUI_VAE_NAME=wan2.2_vae.safetensors
export COMFYUI_VAE_SHA256=<verified-sha256>
export COMFYUI_RUNTIME_ATTESTATION_REF=<approved-attestation-ref>
```

然后生成证明：

```bash
PYTHONPATH=. python scripts/k2_comfyui_runtime_attestation.py \
  --model-root /data/coding/apps/ComfyUI/models \
  --output /secure/evidence/k2-comfyui-runtime-attestation.json
```

只有脚本退出码为 `0` 时才可使用输出中的 `attestationRef` 和 `payloadDigest`。
`authorityState=TECHNICAL_EVIDENCE_ONLY` 与 `publicationAllowed=false` 是固定事实；
该文件还必须由外部 provider-policy authority 审核后，才能把这两个精确值写入
生产策略。Core、V5 请求、V4 配置和运行回传任一处不一致都会 fail closed。

若算力平台没有披露实例地域，不得根据公司地址、域名或机型猜测地域。操作员可以
使用明确的 `provider-not-disclosed` 生成一份仅供外部审核的技术记录，但该值不能
自行解除 P0→P1 的 region/provider-policy 门禁；外部 authority 必须明确接受该值，
或在取得真实地域后重新生成证明。

证明生成后，先保存同一运行时返回的 `/system_stats` 与 `/object_info`，再使用仓库
工具交叉验证并生成确定性归档：

```bash
PYTHONPATH=. python scripts/k2_comfyui_runtime_evidence_archive.py \
  --attestation /absolute/evidence/runtime-attestation.json \
  --model-digests /absolute/evidence/model-files.sha256 \
  --system-stats /absolute/evidence/comfyui-system-stats.json \
  --object-info /absolute/evidence/comfyui-object-info.json \
  --output /absolute/evidence/k2-runtime-evidence.tar.gz
```

归档工具会复核 attestation 的 `factsDigest/payloadDigest`、三份模型摘要、Python /
PyTorch / CUDA 设备事实与完整 `objectInfoDigest`，然后输出归档 SHA-256 sidecar。
它拒绝相对路径、跨文件篡改、非技术证明、`publicationAllowed=true` 和覆盖已有归档；
归档成功仍不构成 Rights、Provider、Budget 或 Publication Authority。

## 4. 配置 Creator Core 的 V4 Worker

Core 进程需要以下完整配置。若任何必填项缺失，启动会 fail closed；若本地成本高于
已批准请求上限，适配器会在向 ComfyUI 提交任务之前拒绝执行。

```text
COMFYUI_BASE_URL
COMFYUI_PROVIDER_ID
COMFYUI_MODEL_ID
COMFYUI_REGION
COMFYUI_ENDPOINT_CLASS
COMFYUI_UNET_NAME
COMFYUI_UNET_SHA256
COMFYUI_CLIP_NAME
COMFYUI_CLIP_SHA256
COMFYUI_VAE_NAME
COMFYUI_VAE_SHA256
COMFYUI_RUNTIME_ATTESTATION_REF
COMFYUI_RUNTIME_ATTESTATION_DIGEST
COMFYUI_COST_CURRENCY
COMFYUI_COST_MINOR_PER_ATTEMPT
```

可选项：

```text
COMFYUI_BEARER_TOKEN
CREATOR_PROVIDER_EXPERIMENT_JOB_DATA_PATH
CREATOR_PROVIDER_EXPERIMENT_ARTIFACT_ROOT
```

`COMFYUI_BASE_URL` 只允许 loopback HTTP，或无嵌入凭据的 HTTPS。Core 在本地、GPU
在远端时，先建立受控 SSH tunnel，再使用 `http://127.0.0.1:8188`；不要把远端
ComfyUI 的明文 HTTP 端口直接暴露到公网。

## 5. 从现有 K2 GenerationRequest 发起实验

公开入口为：

```text
POST /creator/api/v1/episode-production-runs/{productionRunRef}/provider-experiments
GET  /creator/api/v1/episode-production-runs/{productionRunRef}/provider-experiments
```

POST 只接受三个业务字段：

```json
{
  "idempotencyKey": "k2-video-p1-shot-01-v1",
  "sourceGenerationRequestRef": "<existing-M9-video-generation-request-ref>",
  "providerCapabilityRef": "<exact-approved-video-capability-ref>"
}
```

Workspace 由 Bearer credential 选择，run ref 由路径注入；调用方不能在 JSON 中
提交二者。V5 会重新读取当前 M9 Asset Plan、Production Policy、Rights Manifest、
Provider Policy 与 CreativeShotVersion，并由这些事实生成固定 49-frame 小规格实验。

## 6. 成功与失败判定

一次技术成功至少同时具备：

- V4 `Job + Attempt + providerRequestRef`；
- provider/model/region/endpoint 与策略完全一致；
- seed、latency、cost、GPU/device、runtime facts 与 digest；
- 受控 artifact key、SHA-256、byte size 和独立 ffprobe 结果；
- V5 exact request/shot/policy/rights lineage；
- `publicationAllowed=false`。

常见 fail-closed 状态：

- `production_policy_required`：同一 run 没有当前有效且由外部权威确认的策略包；
- `worker_unavailable`：V4/ComfyUI 未配置、不可达、超时或任务未成功；
- `artifact_verification_failed`：产物、费用、延迟、probe、路径或 lineage 不一致；
- `stale_input`：上游 run、M6、Shot Graph、M9 或策略版本已变化；
- `idempotency_conflict`：同一 key 被用于不同请求事实。

## 7. 当前边界

本实现只闭合 P1 的视频候选实验入口。P1 仍不能通过，直到同一 K2 lineage 至少有
真实 image/video/audio 实验事实，并完成后续候选校验、显式选择和 V5 AssetVersion
接纳。P2 的生产数据库、对象存储、秘密注入、恢复和故障演练也尚未由本手册建立。
