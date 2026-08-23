# AI Cinematic Studio 阶段性资产盘点与审核报告

> 状态：`STAGE SNAPSHOT / NOT FEATURE ACCEPTANCE / NOT PRODUCTION AUTHORITY`
>
> 盘点日期：`2026-08-21`
>
> 本次更新：`K2 P1 PREBOOT + RUNTIME EVIDENCE + CANONICAL ROOT G1 HOST CLOSEOUT`

## 1. 报告边界

本报告记录可从 Git 对象、上传证据、当前代码与可重复校验中核对的阶段
资产。它不替代 `AGENTS.md`、`CURRENT_MILESTONE.md`、ADR、Project Lead 验收、
外部权利决定或发布授权。

严格区分：

- 默认分支已存在资产；
- PR #9 的 publishable-production 候选；
- 本次新增的开机前创作/操作候选；
- 外部 Authority 或受治理实验才能提供的生产事实。

## 2. 仓库快照

| 仓库 | 默认分支事实快照 | 阶段候选 |
| --- | --- | --- |
| Core | `origin/main` @ `8d9ce52166cec27d2fefaa86548016130babdfff` | `feature/k2-publishable-production`，PR #9；canonical bootstrap G1 实现 `57ce3d0bf3e5772f57cea7a8a79726237ef366ba`，tree `a3eece796fafcaeead8b525cbe039a69782602c3`；Repository Validation #44 为 5/5 jobs 成功；正式主机 G1 已收口 |
| Frontend | `origin/main` @ `277754a6e61e86bb1ed8109570aa19e4214f0d60` | `feature/k2-publishable-production-ui` @ `23d5df154053c486863a18cf902f714d45801f24`，PR #8；本次未改动 |

本报告不把候选分支写成默认分支能力。最终远端 commit 由 GitHub PR 记录；
不在同一 commit 内嵌入自身 SHA 制造循环事实。

## 3. 已有真实资产

### 3.1 Core 默认分支

已核对的主要工程资产：

- Creator Public HTTP/API、Bearer 服务凭据与 principal-derived workspace 隔离；
- Project、Series、Episode、Script、Series Planning、Series Intelligence 等 V5 事实；
- SQLite 本地持久化适配器；
- K2 `EpisodeProductionRun`、M6 Authority、Identity Lock、Shot Graph、
  AssetRequirement、GenerationRequest、媒体作业、Timeline、QC、四类独立审批、
  EpisodeMaster 与 ExportArtifact；
- V4 本地媒体作业与 V3 FFmpeg 确定性合成；
- 单元、契约、集成和架构守卫测试。

默认分支 G5/G6 的视频和音频是明确标注的 `LOCAL_EVIDENCE`，用于验证作业、
probe、摘要、血缘、合成与审批边界，不是真实生成模型质量或商业权利证据。

### 3.2 Frontend 默认分支

已核对的主要资产：

- server-only Experience Adapter 和路径/方法白名单；
- 12 个产品页面、生产工作区、设计令牌与明暗主题；
- 24 个测试文件与 Gate C 浏览器编排资产；
- `public/assets/` 中 33 个 WebP、16 个 SVG、0 个 PNG；
- Script Studio 验收截图与 Logo 资产。

`ASSET_PROVENANCE.md` 是来源记录，不等于外部许可、Rights Authority 或
publication rights。

## 4. PR #9 候选资产

Core 候选已增加：

- `ProductionPolicyVersion + RightsManifestVersion + ProviderExecutionPolicyVersion`；
- 外部 Rights/Provider bundle 的摘要钉扎、封闭 schema 和原子激活；
- V4 `ComfyUIWan22VideoAdapter` 与 V5 bounded provider experiment；
- runtime attestation 与确定性 runtime evidence archive 工具；
- 固定 49-frame、640×352、24 fps 的 Wan2.2 P1 小样配置；
- `UNTRUSTED_PROVIDER_CANDIDATE / UNSELECTED / NOT_ADMITTED /
  publicationAllowed=false` 的 fail-closed 候选边界。

本轮输入基线的可重复验证为：Core `566 / 566`、开机前聚焦测试 `12 / 12`、
Python compile、Markdown、本地链接、diff 和 secret 检查全部通过；
Repository Validation #41 为 5/5 jobs 通过。

本次当前启动证据刷新及只读血缘工具完成后，证据/开机前/操作工具聚焦测试为
`23 / 23 PASS`，完整 Core 回归为 `569 / 569 PASS`。

原 durable lineage 的扩展位置审计结论为 `NOT_FOUND`。Project Lead 随后授权新的
canonical bootstrap；其 G0 治理检查点在 Repository Validation #43 获得 5/5 jobs
成功。G1 实现 commit `57ce3d0…` 在 Repository Validation #44 获得 5/5 jobs
成功，聚焦测试为 `18 / 18 PASS`。正式主机随后完成一次 dry-run、一次 acknowledged
apply、五库 quick-check/inventory、独立只读扫描和七资源 authenticated API
exact-match。新的 canonical root 现为可审计的 `ROOTS_READY` 资产，但仍不是 M6、
Identity、P1 或发布资产。

## 5. A100 / ComfyUI 技术证据

### 5.1 当前启动归档

| 项目 | 核对结果 |
| --- | --- |
| 归档 | `k2-runtime-evidence-20260821T130634Z.tar.gz` |
| 外层 SHA-256 | `77348f23aebcd2f4029c20f4d05cb910c726dbfbb7eaf9757ac44c4cf6a2e24a` |
| sidecar | 与重算摘要完全一致 |
| tar 安全性 | 5 个相对路径普通文件；无绝对路径、`..`、链接或设备项 |
| 内部 manifest | 4 个 payload 全部 SHA-256 校验通过 |
| 确定性重建 | 与上传归档逐字节一致，SHA-256 相同 |
| 敏感信息扫描 | 29,573 个 JSON 字符串值；已识别凭据、敏感 URL/查询、宿主绝对路径和非空敏感字段均为 0 |

### 5.2 语义事实

- schema：`v4.comfyui-runtime-attestation.v1`；
- attestation ref：`technical-k2-funhpc-a100-20260821T130634Z`；
- observed at：`2026-08-21T13:07:19.528120Z`；
- provider/model：`self-hosted-comfyui / wan2.2-ti2v-5b-fp16`；
- region/endpoint：`provider-not-disclosed / local-loopback`；
- Python/PyTorch：`3.12.7 / 2.11.0+cu126`；
- device：1 × `NVIDIA A100-PCIE-40GB`，42,409,000,960 VRAM bytes；
- 必需原生节点：10/10；
- attestation payload digest：
  `be03a079d17cad524b5e2e061e0c651a8f41f6f5221dfe80a8244398817ded53`；
- 权威状态：`TECHNICAL_EVIDENCE_ONLY / publicationAllowed=false`。

模型摘要：

| 角色 | 文件 | SHA-256 |
| --- | --- | --- |
| UNET | `wan2.2_ti2v_5B_fp16.safetensors` | `456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e` |
| TEXT_ENCODER | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68` |
| VAE | `wan2.2_vae.safetensors` | `e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156` |

### 5.3 摘要链与历史证据

当前事实摘要为
`d845c4c24fa0108f7574a028cce40eb6253c68c078b6cb99c4c82c6d201b8fba`，
object-info 规范摘要为
`df3dace362f18e7b35fdea119959cc12e879d9535844cba3d926624e3ecf988a`，
attestation 文件 SHA-256 为
`bd6ee9390e9733b68722ca19895836e823e264c9d9ab867ed78cc7c3ffe31fed`。

`2026-08-20` 的 attestation
`technical-k2-funhpc-a100-20260820T141317Z`、payload digest
`3a0ad8e839545390b3baaf3de57903f57f0c40c5bcaa117cd9990cd616c1bec2` 和归档
SHA-256 `c3701a1877cd9e715dcadbca93fc24eb38221f8e2c7a9f758cd978308c0b9f09`
保留为历史证据，不再作为当前启动钉扎值。所有归档仍是外部审计资产，不进入
Git，也不授予 Rights、Provider、Budget 或 Publication Authority。

## 6. 本次开机前新增资产

### 6.1 创作候选

- K2-001《记忆回声》30 秒剧本候选；
- 0–7、7–14、14–22、22–30 秒四镜分镜；
- 逐镜构图、焦段、运动、动作、表演、光色、连续性和失败判定；
- 林澈、顾言各八个必要视图的 turnaround 设计；
- 四镜 Wan2.2 正/负提示词与 49-frame 小样映射；
- 两句中性 TTS、环境声和提示音 cue sheet，无外部音频、无声纹克隆、
  P1 无音乐。

全部创作内容标记为 `DRAFT / CANDIDATE / NOT DOMAIN FACT`。候选键
`K2-001-SH-*` 不是 Core ref。

### 6.2 机器可读与治理资产

- `k2.preboot-candidate.v1` 清单；
- 当前清单规范 SHA-256
  `ca79c442f9d9998c8a214412bc78a09650e6585f955eda22ea9c9ca209947cca`；
- CNY `100000` minor 的硬上限、已承诺支出 `0`、禁止当前付费调用；
- video/audio 从当前 G4 `GenerationRequest` 解析，image 因当前 G4 不存在对应 request
  而保持 blocker 的同源实验矩阵；
- Rights/Provider 字段检查模板，故意不是可激活 Authority bundle；
- 从离线总检、重建当前血缘、Authority 激活、runtime 核验、预算熔断到
  secret-free 证据收口的运行手册；
- SQLite `mode=ro + query_only` 的 K2 血缘定位工具；只输出安全 Ref、version、state、
  digest 和计数，不选择 payload、创作正文、idempotency key 或 credential 字段；
- fail-closed 校验器与 12 个篡改/越权测试，以及 3 个只读/脱敏/行数边界测试。

新的 canonical bootstrap 资产包括：

- ADR-0010 与 `K2_CANONICAL_LINEAGE_BOOTSTRAP_CONTRACT.md`；
- 精确 `k2.canonical-lineage-bootstrap.v1` 规范，payload SHA-256
  `0dfa64aa23e7120415a58b48eb00bb5d92274518d16051f2cb419525ea3b364c`，完整规范
  SHA-256
  `3b4d77b371cb23e2acf5420d74ded9d890a877f9555d781bc7842d0b715eb0ee`；
- 默认无写、显式确认后才 apply 的 V5-only Operator Application；
- 同盘私有 staging、重启、只读 scanner、secret-free receipt、相对数据库
  inventory、no-replace 原子发布与重复 apply 拒绝；
- authenticated GET-only Public API exact-match verifier；只允许 loopback，凭据只从
  环境变量读取，不跟随 redirect，并生成 canonical root 之外的 secret-free receipt；
- 18 个规范、dry-run、权限、失败清理、并发目标、重复 apply、篡改、真实 loopback
  authenticated HTTP/API exact-match、多 run/API digest/落盘数据库篡改拒绝、
  GET-only、凭据非披露与依赖边界测试。

临时目录测试建立的 run 会随测试目录删除，仅证明工具行为，不是正式 K2 lineage。
正式 host closeout 另行建立了唯一 canonical run；其 bootstrap receipt SHA-256 为
`94fad69a2fdffe50e599c08fdc0e7c94aa3a381a30d1515b126a1f8b88076234`，API verification
receipt SHA-256 为
`d4c2a52d1c141ed5f0b8b24a13a985e47e38b3b78eac27eb5d59b452c18ca8a6`。独立扫描
得到 `5 DB / 1 production DB / 1 production run / FOUND_READ_ONLY`，authenticated
API verifier 对七个资源 exact-match PASS。

本次 canonical bootstrap G1 候选树的完整 Core 回归为 `587 / 587 PASS`：Unit
`356 / 356`、Contract `91 / 91`、Integration `140 / 140`；bootstrap/API 聚焦测试
为 `18 / 18 PASS`。早先开机前候选包的独立聚焦基线仍为 `12 / 12 PASS`。

### 6.3 离线工作包内没有发生的事项

- GPU/ComfyUI 启动：0；
- Provider 网络调用：0；
- 付费调用与已承诺成本：0；
- 外部音频导入：0；
- 真人声纹克隆：0；
- 生成图片/视频/音频：0；
- 新 Identity Lock、AssetVersion、Approval、Master 或 Export：0；
- 离线工作包本身创建正式 canonical `EpisodeProductionRun`：0；后续受控 G1 host
  apply 创建 1 个并停在 `ROOTS_READY`；
- P1/P2/P3 门禁推进：0。

## 7. 预算与 AI 音频决定

Project Lead 给定的总预算硬上限为人民币 1000 元。本轮只记录上限，没有自行分配
Provider 子预算，也没有制造 `budgetAuthorityRef`。

AI 音频工作需要保留，但限定为最小范围：

- 原因：P1 退出条件要求同一 K2 lineage 下 image/video/audio 实验，取消音频会
  使发布持续阻断；
- 范围：仅两句中性 TTS + 可内部合成的环境/提示音；
- 不做：外部音频、真人克隆、演员模仿、P1 音乐；
- 启动条件：精确 Provider/model/region、usage terms、Rights、credential source、
  `budgetAuthorityRef` 和 V4 adapter 全部存在。

## 8. 未关闭缺口

### P1 阻断项

1. M6 Authority 与 Identity Lock；
2. Rights Authority bundle；
3. image/video/audio 的 Provider Authority bundle；
4. 真实 region，或对 `provider-not-disclosed` 的外部显式接受；
5. `budgetAuthorityRef` 与三媒体子上限；
6. 当前 attestation ref/digest 的 Provider Authority 接受；
7. 获批的同源 image GenerationRequest 合同扩展与 V4 image/audio live adapters；
8. 当前 K2 lineage 下的受治理 image/video/audio 真实尝试；
9. 候选验证、显式选择与 V5 admission。

P1 依然是 `NOT PASSED`。视频技术证据或离线创作完成不能替代上述任一项。

### 后续但不得提前开始

- P2 的生产数据库、对象存储、secret injection、observability、restart/retry/recovery；
- P3 之后的 M7–M15 正式事实闭环；
- P9 发布资格与独立 destination/publication authority；
- P10 的 1 → 3 → 10 → 30 有界扩展。

## 9. 阶段结论

方向需要按新证据收窄：当前工作没有继续“为运行而修依赖”，而是把已证明的技术
运行时、创作候选、预算约束和三媒体退出条件收进同一个 fail-closed 工作包；但
`2026-08-21` 对 `/data`、`/root`、`/home`、`/tmp` 及 15 个归档的只读定位没有找到
可恢复的 K2 Core 生产血缘。两个 SQLite 候选均为 ComfyUI 自身数据库，归档中没有
数据库成员。定位审计 SHA-256 为
`7aaa36333f08be3bdfd09c6b4632804f3b7bf14a0bd1bc35f359df0391fa167b`。

当前运行时已经完成技术证据刷新；新的 canonical K2 lineage 也已按 ADR-0010 在正式
主机建立并通过独立只读扫描和 authenticated API exact-match。该路径是重新引导，
不是原 durable lineage 的恢复。测试夹具、`K2-001-SH-*` 文档键和历史技术证明仍不能
替代新 lineage 中任何正式 Ref、version 或 digest，也不能自动挂接到新 run。

当前正确的下一步是使用现有 G2 公共边界，为同一 production run 分别建立 M6 Authority
与 V5 Identity Lock；两者必须由精确 authority/reference facts 支撑，不能按人物名或
文件名推断。完成 G2 前不执行 image/video/audio live provider 实验；Rights/Provider/
budget authority、P1 与发布仍保持 fail closed。

## 10. 可复核入口

```bash
python scripts/k2_preboot_validate.py \
  --manifest "$PWD/experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json"

python scripts/k2_canonical_lineage_bootstrap.py \
  --spec "$PWD/experiments/k2-001-canonical-bootstrap/k2-001-canonical-bootstrap.v1.json" \
  --target-dir /absolute/nonexistent/canonical-target

python -m unittest \
  tests.unit.test_k2_canonical_lineage_bootstrap \
  tests.unit.test_k2_canonical_lineage_api_verify -v
python -m unittest tests.unit.test_k2_preboot_package -v
python -m unittest discover -s tests -p 'test_*.py' -q
python -m compileall -q apps services scripts tests
git diff --check
```

上传证据的复核另包括外层 SHA-256、sidecar 比对、tar 安全成员、内部 manifest、
语义校验、两次确定性重建和主机绝对路径扫描。
