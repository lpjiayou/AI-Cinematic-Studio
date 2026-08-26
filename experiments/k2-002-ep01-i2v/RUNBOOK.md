# K2-002 EP01 Wan2.2 I2V 技术验证运行手册

## 1. 边界

本目录只准备一次自托管 A100 技术验证：用 `final-assets-v1.2.zip` 内 12 张
`704×1280` EP01 候选关键帧作为起锚帧，逐镜生成一个原生
`704×1280（竖屏 9:16） / 49 帧 / 24 fps` Wan2.2 I2V 片段。

固定状态：

```text
authorityState=TECHNICAL_EVIDENCE_ONLY
publicationAllowed=false
canonicalMutationCount=0
AssetVersion / Admission / Master / Export=NONE
```

这里的 `ingest_ep01.py` 只把摘要锁定的 PNG 写入本机 ComfyUI `input/`，不调用
Creator API、V5、canonical database、Asset Registry 或发布接口。每镜只提交一个
`Wan22ImageToVideoLatent(length=49)`；没有多段、续写、拼接、补帧或自动重试。

## 2. 固定配置

| 项目 | 固定值 |
| --- | --- |
| UNET | `wan2.2_ti2v_5B_fp16.safetensors` |
| Text encoder | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` |
| VAE | `wan2.2_vae.safetensors` |
| 输出 | `704×1280（竖屏 9:16）` |
| 原生帧数 | `49` |
| 帧率 | `24 fps` |
| Steps / CFG | `20 / 5.0` |
| Sampler / Scheduler | `uni_pc / simple` |
| Model shift / Denoise | `8.0 / 1.0` |
| 并行度 / 自动重试 | `1 / 0` |
| 运动策略 | 缓推、呼吸、轻微手部或头部动作；禁止大幅运镜 |

`workflow.json` 是 ComfyUI API-format workflow，内容是可直接提交或导入的 SH01
实例。批处理程序只替换节点 5/6/8/11/12 的正向提示词、负向提示词、seed、输出前缀
和起锚帧；其他参数全部锁死。

## 3. A100 开机前准备

在持久盘准备：

```text
/data/coding/AI-Cinematic-Studio/          本仓库
/data/coding/final-assets-v1.2.zip         原始资产包
/data/coding/apps/ComfyUI/                 已验证的 ComfyUI
/data/coding/apps/ComfyUI/models/          三份摘要锁定模型
/data/k2-technical-evidence/               技术证据目录
```

不要把资产包解压后改名覆盖；脚本可直接从 ZIP 读取 12 个精确成员，并先验证整个 ZIP
的 SHA-256 `532765d91b56692e611cabb9fcbd3d8ecc916f169f5c4e2b3b9e82a56bbe99c6`。

## 4. GPU 会话顺序

### 4.1 设置本机路径，约 1 分钟

```bash
cd /data/coding/AI-Cinematic-Studio
export PYTHON_BIN=/path/to/the/python-used-by-comfyui
export ASSET_PACKAGE=/data/coding/final-assets-v1.2.zip
export MODEL_ROOT=/data/coding/apps/ComfyUI/models
export COMFYUI_ROOT=/data/coding/apps/ComfyUI
export COMFYUI_BASE_URL=http://127.0.0.1:8188
export EVIDENCE_ROOT=/data/k2-technical-evidence/k2-002-ep01-i2v-v1
```

`PYTHON_BIN` 必须是启动 ComfyUI 的同一个绝对解释器，不能根据另一个 Conda 环境
推断。

### 4.2 离线预检，预计 3–6 分钟

```bash
experiments/k2-002-ep01-i2v/run_ep01.sh preflight
```

预期末尾：

```text
VALIDATION=PASS
SHOT_COUNT=12
OUTPUT_PROFILE=704x1280/49f/24fps/ONE_SEGMENT
GPU_OR_PROVIDER_CALLS=0
CANONICAL_MUTATIONS=0
```

这一步验证五个交付文件、12 张锚帧尺寸/摘要、资产包摘要及三份模型摘要；不访问
ComfyUI，不使用 GPU。

### 4.3 启动既有 ComfyUI，预计 3–8 分钟

使用该 A100 主机已经验证过的本地启动方式，只监听 `127.0.0.1:8188`。本包不会替你
启动进程，也不会开放公网端口。确认：

```bash
curl -fsS http://127.0.0.1:8188/system_stats >/tmp/k2-002-system-stats.json
curl -fsS http://127.0.0.1:8188/object_info >/tmp/k2-002-object-info.json
```

执行脚本仍会独立验证：唯一 CUDA 设备包含 `A100`、原生 I2V 节点存在、
`Wan22ImageToVideoLatent.start_image` 可用、三份模型名称可被 ComfyUI 识别。

如需要保存本次启动的 runtime attestation，可另行运行现有
`scripts/k2_comfyui_runtime_attestation.py --require-start-image`；它仍只是技术证据，
不是 Rights、Provider、Budget 或 canonical authority。

### 4.4 必须先跑单镜探针 SH06，预计冷启动 8–15 分钟

```bash
export K2_EP01_I2V_ACK=TECHNICAL_EVIDENCE_ONLY
experiments/k2-002-ep01-i2v/run_ep01.sh shot EP01_SH06
```

脚本顺序执行：锚帧摘要复核 → 本机 input staging → `/prompt` 单次提交 → 单次 history
等待 → MP4 下载 → `ffprobe`。只有输出同时满足
`704×1280（竖屏 9:16） / 49 帧 / 24 fps / 无音轨` 才写入技术证据记录。没有隐式重试。

必须先由人工查看 SH06，确认画面方向、构图、主体一致性、形变与运镜符合技术验证预期；
只有人工确认后，才可执行 `run_ep01.sh batch`。该查看不是 Human Selection，也不产生
Admission。

### 4.5 顺序执行其余镜头，预计 45–90 分钟

```bash
experiments/k2-002-ep01-i2v/run_ep01.sh batch
```

`batch` 固定串行，自动跳过同一 `EVIDENCE_ROOT` 下已通过摘要验证的 SH06；不会并发占用
显存，也不会拼接镜头。任一镜头失败即停止，修复原因后由操作员决定是否再次执行；脚本
不会自动消费第二次 GPU 尝试。

### 4.6 核对并关机，预计 5–10 分钟

```bash
find "$EVIDENCE_ROOT" -maxdepth 2 -type f -print | sort
sha256sum "$EVIDENCE_ROOT"/media/*.mp4
```

完整批次应包含：

- `media/EP01_SH01.mp4` 至 `media/EP01_SH12.mp4`；
- `records/EP01_SH01.json` 至 `records/EP01_SH12.json`；
- `session-manifest.json`；
- 可选的单镜校准 `session-manifest-EP01_SH06.json`。

将整个 `EVIDENCE_ROOT` 保存在持久盘后关闭 GPU。不要把 MP4 或 runtime evidence 提交到
Git，也不要调用任何 canonical、Admission、Master、Export 或 Publication 操作。

## 5. 时间与开机时长估算

仓库没有 `704×1280（竖屏 9:16） / 49 帧 / 20 steps` 在当前 A100 40GB 上的实测时延，
因此以下是排期估算，不是已验证性能结论：

| 阶段 | 估算 |
| --- | ---: |
| 环境变量与离线预检 | 4–7 分钟 |
| ComfyUI 启动与首次模型装载 | 3–8 分钟 |
| 首镜冷启动生成、下载和 probe | 8–15 分钟 |
| 后续单镜暖态生成、下载和 probe | 每镜 4–8 分钟 |
| 12 镜无重试合计 | 55–105 分钟 |
| 最终摘要核对与持久化 | 5–10 分钟 |

建议一次预留 **2 小时 A100 开机窗口**。该窗口包含冷启动和小量故障处置余量，不包含
任何重生成、调参或第二轮实验。首镜实测完成后，应以其 `latencyMs` 修正剩余 11 镜的
估算；不得把上述范围冒充实测耗时。

## 6. 停止条件

出现以下任一情况立即停止，不继续消耗 GPU：

- 资产包、锚帧或模型 SHA-256 不匹配；
- 输出不是 `704×1280（竖屏 9:16） / 49 帧 / 24 fps`；
- ComfyUI 缺少原生 I2V 节点或 `start_image`；
- 运行设备不是唯一 A100 CUDA 设备；
- 单镜超过 60 分钟超时；
- 已有证据与同镜新配置冲突；
- 需要多段续写、拼接、自动重试或修改 canonical 状态才能继续。
