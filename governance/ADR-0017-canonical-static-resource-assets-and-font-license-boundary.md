# ADR-0017 — Canonical Static Resource Assets and Font License Boundary

## 文档元数据

| 字段 | 填写内容 |
| --- | --- |
| ADR ID | `ADR-0017` |
| Title | Canonical Static Resource Assets and Font License Boundary |
| Status | `Accepted` |
| 创建日期 | `2026-08-31` |
| 审批人 | Project Lead / Architecture Owner / V5 Asset Domain Owner / M13 Domain Owner / Rights/License Boundary Owner |
| Decision Ref | `ACS-V5-FONT-AUTHORITY-AND-M13-E3-UNBLOCK` |

## Context

M13-E3 的名牌文字需要摘要钉扎、可复现且具备明确许可证边界的字体输入。既有
canonical AssetVersion authority 能读取历史媒体资产，但 AssetVersion v1 不能被
静默重解释为字体权威。恢复 deprecated `services/v5_core_os/asset_registry` 或创建
FontRegistry、sidecar database、第二 AssetVersion store 都会形成并行权威。

## Decision

### 唯一资产权威与持久化

```text
FONT_ASSET_AUTHORITY_OWNER=EXISTING_CANONICAL_ASSET_VERSION_AUTHORITY
FONT_ASSET_PERSISTENCE=EXISTING_V5_EPISODE_PRODUCTION_EVIDENCE_JOURNAL
DEPRECATED_ASSET_REGISTRY_REACTIVATED=false
SECOND_ASSET_AUTHORITY=false
SECOND_ASSET_DATABASE=false
FONT_SIDECAR_REGISTRY=false
```

`FontAssetVersionProjection` 只是 canonical AssetVersion v2 的强类型只读投影，
不是资产根、Repository 或持久化 owner。deprecated AssetRegistry 继续作为
fail-closed compatibility tombstone。

### Additive AssetVersion v2

AssetVersion v1 保持历史可读、digest 不变且不可重解释。AssetVersion v2 首版只允许
`assetClass=STATIC_RESOURCE` 与 `resourceKind=FONT`。`GRAPHIC`、`LUT`、
`ALPHA_MATTE`、`PARTICLE_SPRITE`、`SMOKE_LAYER`、`UI_PLATE` 及其他类型均保持关闭。
首版沿用 Episode Production 的 workspace/run/project/series/episode scope，不创建
workspace-global store、跨租户字体市场或全局字体库。

### 唯一 Font 准入链

```text
StaticResourceCandidate
→ FontTechnicalValidation
→ ResourceLicenseBindingVersion
→ StaticResourceAdmissionDecision
→ canonical AssetVersion v2
→ FontAssetVersionProjection
→ M13 read-only consumption
```

所有对象只引用既存上游 ref/version/digest，禁止摘要环。Candidate 不能自报 font
family、license、admission state 或 AssetVersion，也不能把文件名、扩展名或路径
当作字体 authority。

### FontTechnicalValidation

首版只接受服务器侧从 held descriptor 或受控 storage binding 验证的 TTF/OTF。
TTC、WOFF、WOFF2、Type1、未知格式、扩展名伪装、损坏 SFNT、symlink 和非 regular
file 必须 fail closed。验证记录绑定文件 digest、size、SFNT signature、name-table、
variable-font facts，以及固定 FFmpeg/FreeType renderer identity。

验证器必须明确指定 font file，禁止 system/network fallback，并以确定性 renderer
probe 证明同一字体与测试文本产生相同 decoded pixel digest。不得新增第三方 Python
依赖；固定 renderer 缺少文字能力时停止实施。

### ResourceLicenseBindingVersion

许可证决策是独立、不可变、版本化的权威对象，不得退化为 AssetVersion 中的自由
字符串。首版关闭式支持 `OFL-1.1`，其他 SPDX ID 默认拒绝。每个版本绑定 candidate、
字体 digest、license text/evidence digest、用途许可、嵌入/再分发/修改/署名条件、
保留字体名、地域、有效期、撤销状态和 decision authority。默认 License Authority
拒绝；缺失、过期、撤销、用途不足或摘要漂移全部 fail closed。

### StaticResourceAdmissionDecision 与 AssetVersion v2

默认 Admission Authority 拒绝。只有 technical validation PASS、license binding
ACTIVE、`technicalPreviewAllowed=true`、`renderCandidateUseAllowed=true`，且所有
candidate/artifact/file/license/authority digests current 时，才可创建
`v5.asset-version.v2`。字体准入不得伪装成媒体候选或复用媒体视觉 QC。

AssetVersion v2 固定 `state=REGISTERED`、`admissionState=ADMITTED`、
`publicationAllowed=false`。Public/read projection 不返回绝对路径、storage path、
font local path、license source path 或 renderer argv。

### 技术 fixture 与 live 边界

测试可以携带 exact SHA-256、可审计 OFL-1.1 文本和可再分发字体 fixture，并在隔离
test authority 中执行 representative admission。fixture 必须标记
`TECHNICAL_FIXTURE_ONLY`、`NOT_LIVE_ASSET`、`NOT_SELECTED_FOR_PRODUCTION`、
`NOT_PUBLICATION_ASSET` 和 `publicationAllowed=false`。生产 builder 必须拒绝调用方
提交这些 markers；fixture 不进入 live canonical store。

本实施波保持 `LIVE_ASSET_ADMISSIONS=0`、`CANONICAL_MUTATIONS=0`、
`GPU_OR_PROVIDER_CALLS=0`、`PUBLICATION_ALLOWED=false`。

### M13-E3 消费边界

M13-E3 只能只读消费 canonical AssetVersion v2 中 admitted FONT，并重读确认
FontTechnicalValidation PASS、ResourceLicenseBindingVersion ACTIVE、preview/render
用途允许、字体文件和许可证摘要 current。M13 不创建 Candidate、Validation、
LicenseBinding、Admission 或 AssetVersion。

Face Mark Compensation 继续复用 existing Identity authority 与 canonical image/layer
AssetVersion；首版仅允许 explicit deterministic keyframes，不新增 AI tracker 或
tracking authority。

## Alternatives

- 恢复 deprecated AssetRegistry：拒绝，会形成平行资产权威。
- 新建 FontRegistry 或字体数据库：拒绝，会复制 scope、version、digest 和 replay。
- 使用系统或网络字体：拒绝，工具链和许可证不可复现。
- 原地扩写 AssetVersion v1：拒绝，会重解释历史 digest。
- M13 内注入测试字体：拒绝，会绕过 canonical admission 与 rights boundary。

## Consequences

字体成为 existing canonical AssetVersion authority 的关闭式静态资源，许可证和
技术验证可独立版本化、重放和 fail closed；M13 可在不拥有字体事实的前提下完成
确定性文字合成。成本是 additive schemas、服务端 SFNT/renderer 验证、许可证权威、
admission 负例和 SQLite replay 覆盖。

## Implementation sequence

1. 本 ADR 与上位规范同步先以 governance-only PR squash merge；
2. 从最新 main 实现 V5 FONT capability，不创建 live Font AssetVersion；
3. 从最新 main 恢复 M13-E3，只读消费 admitted Font AssetVersion v2；
4. Frontend 仅更新 Core pin；
5. 完成跨仓只读核验后停止。

## Stop conditions

若实现必须启用 deprecated AssetRegistry、创建第二 store、使用系统/网络字体、接受
自由字符串许可证、重解释 v1、让测试 fixture 进入 production builder、让 M13 创建
Admission，或 renderer probe 无法稳定复现，则立即停止。

## Change log

| 日期 | 决策方 | 变更 | Decision Ref |
| --- | --- | --- | --- |
| `2026-08-31` | Project Lead / Architecture Owner / V5 Asset Domain Owner / M13 Domain Owner / Rights/License Boundary Owner | 创建并接受 ADR-0017；冻结 static FONT AssetVersion v2、许可证绑定与 M13 只读边界 | `ACS-V5-FONT-AUTHORITY-AND-M13-E3-UNBLOCK` |
