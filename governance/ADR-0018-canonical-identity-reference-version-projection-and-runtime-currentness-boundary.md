# ADR-0018 — Canonical Identity Reference Version Projection and Runtime Currentness Boundary

## 文档元数据

| 字段 | 填写内容 |
| --- | --- |
| ADR ID | `ADR-0018` |
| Title | Canonical Identity Reference Version Projection and Runtime Currentness Boundary |
| Status | `Accepted` |
| 创建日期 | `2026-08-31` |
| 审批人 | Project Lead / Architecture Owner / V5 Identity Domain Owner / M13 Domain Owner / Security / External Authority Boundary Owner |
| Decision Ref | `ACS-V5-IDENTITY-REFERENCE-PROJECTION-AND-M13-E3-UNBLOCK` |

## Context

现有 V5 Episode Production 已由 `K2AuthorityIdentityService` 创建并持久化
`IdentityLock`，且锁中的视觉身份引用来自 existing external identity-reference
authority。锁定事实包含 `referenceRef`、`referenceVersionRef`、`contentDigest`、
`mediaType`、`rightsState`、`provenance` 和 `approvalRef`，但持久化历史锁本身不能证明
外部决定在后续消费时仍然 current。

M13-E3 Face Mark Compensation 必须在 Requirement 创建、确定性执行和 SQLite restart
后恢复时使用当前且权威的身份引用。允许调用方自报身份版本、只信任历史
`IdentityLock`，或创建新的 IdentityVersion root/repository/sidecar store，都会绕过既有
外部决定、形成第二身份权威，或把已经漂移的 rights/provenance/approval 误认为有效。

`services/v5_core_os/identity_engine` 当前只拥有基础 Identity/Workspace 模型，不自动
获得视觉身份版本语义。本 ADR 不提升该模块为视觉身份权威，也不修改 existing
`IdentityLock` 的 schema、payload 或 digest。

## Decision

### 唯一身份权威与持久化边界

```text
IDENTITY_REFERENCE_AUTHORITY_OWNER=EXISTING_K2_AUTHORITY_IDENTITY_SERVICE
IDENTITY_LOCK_OWNER=EXISTING_V5_EPISODE_PRODUCTION_IDENTITY_LOCK
IDENTITY_REFERENCE_DECISION_SOURCE=EXISTING_EXTERNAL_IDENTITY_REFERENCE_AUTHORITY
IDENTITY_REFERENCE_PERSISTENCE=EXISTING_IDENTITY_LOCK_FACT_PLUS_EXTERNAL_AUTHORITY_SNAPSHOT

SECOND_IDENTITY_AUTHORITY=false
SECOND_IDENTITY_DATABASE=false
IDENTITY_VERSION_REGISTRY=false
IDENTITY_SIDECAR_STORE=false
```

`K2AuthorityIdentityService` 继续负责 IdentityLock 谱系和对外部身份引用决定的受控消费；
existing external identity-reference authority 继续是 `referenceRef` 及其版本、内容、
rights、provenance 与 approval 的唯一决定来源。不得把
`services/v5_core_os/identity_engine` 扩展成并行视觉身份权威，不得新增 Identity
repository、IdentityVersion repository、registry、database 或 sidecar store。

### IdentityReferenceVersionProjection 是只读投影

冻结唯一 canonical projection type：

```text
CANONICAL_PROJECTION_TYPE=v5.identity-reference-version-projection.v1
```

`IdentityReferenceVersionProjection` 是以下两个既有事实的强类型只读投影：

```text
existing IdentityLock
+ fresh external identity-reference decision
```

它不是 Identity root、IdentityVersion root、repository、persistent owner、approval
authority、AssetVersion 或 IdentityLock successor。投影不得创建、修改或批准身份事实，
也不得成为外部 authority 的缓存替代品。

正式字段映射固定为：

| 投影字段 | 既有 external decision 字段 |
| --- | --- |
| `identityReferenceRef` | `referenceRef` |
| `identityReferenceVersionRef` | `referenceVersionRef` |
| `identityReferenceContentDigest` | `contentDigest` |

`contentDigest` 保留外部 authority 的既有内容摘要语义；不得将其重命名或解释为
`identityPayloadDigest`、`identityVersionPayloadDigest`、IdentityLock payload digest，
或投影对象摘要。投影自身独立使用 `projectionDigest`。

首版投影至少包含：

- `schemaVersion`、`workspaceRef`、`productionRunRef`；
- `characterRef`、`scriptCharacterName`；
- `identityLockRef`、`identityLockVersionRef`、`identityLockDigest`；
- `referenceRef`、`referenceVersionRef`、`contentDigest`；
- `mediaType`、`rightsState`、`provenance`、`approvalRef`；
- `externalDecisionDigest`、`projectionCheckedAt`、`projectionDigest`。

`externalDecisionDigest` 对规范化的七个 external decision 字段计算；
`projectionDigest` 对 schema、scope、character、IdentityLock ref/version/digest、全部
external decision 字段及 `externalDecisionDigest` 计算。`projectionCheckedAt` 不得进入
可重复内容摘要，普通时钟值不得使相同权威事实产生不同 `projectionDigest`。

### Runtime currentness 必须重新调用外部 authority

每次消费身份引用前必须按以下顺序 fail closed：

1. 重新读取 current Root；
2. 重新读取 current M6 baseline；
3. 重新读取 existing IdentityLock 并验证其谱系与摘要；
4. 调用 existing external identity-reference current reader；
5. 对同一 `workspaceRef`、`productionRunRef` 和 `characterRef` 重新解析当前决定；
6. 对 `referenceRef`、`referenceVersionRef`、`contentDigest`、`mediaType`、
   `rightsState`、`provenance`、`approvalRef` 逐字段精确比较；
7. 任一字段变化、缺失、类型不符或摘要不符均判定 stale；
8. current reader 或 external authority 缺失、拒绝或不可验证时立即拒绝；
9. 返回 digest-sealed `IdentityReferenceVersionProjection`，不得改写 IdentityLock。

```text
IDENTITY_CURRENTNESS_REQUIRES_EXTERNAL_REVALIDATION=true
```

首次 authorize-and-lock 继续使用现有 `authorize_reference()` port。运行时 currentness
必须通过独立、只读、默认拒绝的 current reader port 完成；environment-backed
external authority 可以同时实现首次授权和 current read，但两个动作的语义不得合并。
测试用 static reader 只可作为受限 evidence reader，不得成为生产持久化 owner。

### Restart 与 external authority bundle

SQLite restart 后可以从 existing Episode Production evidence journal 恢复历史
IdentityLock，但恢复锁不等于 currentness 已证明。每次恢复后的消费必须重新装载并验证
digest-pinned external authority bundle，再重新调用 current reader。以下任一情况均须
拒绝：

- external authority/current reader 未配置；
- bundle digest 改变或无法验证；
- `referenceRef`、`referenceVersionRef` 或 `contentDigest` 漂移；
- `mediaType`、`rightsState`、`provenance` 或 `approvalRef` 漂移；
- Root、M6 baseline、IdentityLock scope/lineage/digest stale。

不得在 restart 后仅返回 SQLite 中的历史锁并声明身份引用仍 current，也不得持久化投影
作为跳过后续外部复核的依据。

### M13 Face Mark 请求与服务端解析边界

Creator Public API、浏览器或其他公共 M13 Face Mark 请求不得提交：

- `identityVersionRef` 或 `identityVersionDigest`；
- `identityReferenceVersionRef` 或 `identityReferenceContentDigest`；
- `identityProjectionDigest` / `identityReferenceProjectionDigest`；
- raw `IdentityLock`；
- raw external authority decision。

公共请求只允许提交服务器可解析的 `characterRef`、精确 target Shot
ref/version/digest、mark canonical AssetVersion ref/digest、explicit deterministic
keyframes 和 closed effect parameters。不得新增 Creator Public HTTP route，也不得允许
客户端选择或覆盖外部身份引用决定。

服务端在 Requirement 创建和每次执行前都必须调用只读 current projection boundary，
并将下列已解析事实写入内部 Requirement：

- `identityReferenceRef`；
- `identityReferenceVersionRef`；
- `identityReferenceContentDigest`；
- `identityReferenceProjectionDigest`；
- `identityLockRef`；
- `identityLockVersionRef`；
- `identityLockDigest`。

服务端还必须证明 character 属于 target Shot、projection scope 与 run 一致、IdentityLock
current、外部引用的 rights/provenance/approval current、mark AssetVersion current，且
explicit keyframes 与 sealed request 一致。M13 只读消费这些事实，不写 Identity，
不接受 AI face tracking，不创建 tracking authority。

允许 existing internal typed public boundary 提供按 workspace/run/character 获取当前投影
的操作；该操作必须由服务器端调用，不能成为接收 raw external decision 的浏览器入口。

### Additive migration 与历史兼容

本决策采用 additive、read-only migration：

1. 保留现有 `IdentityReferenceAuthorityPort.authorize_reference()` 用于首次 lock；
2. 在 existing authority service 增加独立的 fail-closed current reader port；
3. 增加 `v5.identity-reference-version-projection.v1` schema 与内部 typed projection；
4. 增强 current verification，使其对锁内每个 identity 重新调用 external authority；
5. current verification 返回 `identityReferenceVersions[]`，供受控服务端消费者使用；
6. M13-E3 只通过该边界解析身份引用，不再接受请求体自报版本或摘要；
7. restart/replay 测试必须证明 external current reader 被重新调用。

无需且禁止数据回填、IdentityLock migration、新 table、新 repository 或历史摘要重算。
既有 IdentityLock v1 payload/digest 必须逐字节保持不变；历史锁只有在 fresh external
decision 与其七个字段精确一致时才可继续消费。若任何已有锁无法通过复核，系统应将其
视为 stale 并要求现有权威流程处理，不得静默修补或提升为 IdentityVersion。

### 实施波边界

本实施波保持：

```text
AUTHORITY_STATE=TECHNICAL_EVIDENCE_ONLY
A100_START_AUTHORIZED=false
GPU_CALLS_ALLOWED=false
PROVIDER_CALLS_ALLOWED=false
CANONICAL_MUTATIONS=0
LIVE_IDENTITY_WRITES=0
LIVE_FONT_ADMISSIONS=0
LIVE_ASSET_ADMISSIONS=0
PUBLICATION_ALLOWED=false
LEGACY_MEDIA_WRITES=0
```

不得创建 RenderCandidate、EpisodeMaster、ExportArtifact 或 ExportCandidate，不得进入
M14/M15。本 ADR 只授权先实现 V5 read-only projection/currentness boundary，合入后
才能从最新 main 恢复 M13-E3；它本身不表示 M13-E3 已实现或获得发布资格。

## Risks and controls

| 风险 | 强制控制 |
| --- | --- |
| 外部身份引用静默漂移 | 每次消费与 restart 后重新调用 current reader，逐字段比较七个决定字段 |
| IdentityLock 与当前外部决定不一致 | 任一字段或摘要不一致即 `StaleInputError`，禁止自动修补锁 |
| restart 后只信任持久锁 | 必须重新验证 digest-pinned external authority bundle；authority 缺失即拒绝 |
| 把 `contentDigest` 误当对象 payload digest | 保留正式字段映射，并用独立 `externalDecisionDigest` 与 `projectionDigest` |
| 创建第二 Identity authority/store | 只在 existing `K2AuthorityIdentityService` 增加只读 port/projection；禁止新 root、repository、database 和 registry |
| 请求体自报身份版本或决定 | 公共 schema 关闭这些字段，服务端按 character/scope 解析 |
| rights/provenance/approval 漂移 | 三者与 reference/media 字段同等逐项复核，任何漂移均 fail closed |
| 测试 reader 被误作生产 owner | static reader 保持受限 evidence reader；生产默认 reader 拒绝 |
| 时间戳污染确定性摘要 | `projectionCheckedAt` 不进入 `projectionDigest` |
| 投影被误解为持久身份版本 | 投影不持久化、不批准、不继承 IdentityVersion 语义，每次消费重新生成 |

## Alternatives

- 创建 canonical IdentityVersion root/repository：拒绝，会与 existing IdentityLock 和
  external decision source 形成并行身份权威。
- 仅依赖 SQLite 中的 IdentityLock：拒绝，无法证明引用、rights、provenance 与
  approval 在消费时仍 current。
- 在 M13 Requirement 或公共请求中提交 identity version/digest：拒绝，调用方自报
  不能替代服务器端权威解析。
- 把 `contentDigest` 重命名为 payload digest：拒绝，会改变既有 external authority
  语义并掩盖不同对象摘要边界。
- 扩展基础 `identity_engine` 为视觉版本 authority：拒绝，该模块不拥有 Episode
  Production IdentityLock 或 external identity-reference decision。
- 采用 existing service 内的 read-only projection/current reader：采纳，不产生第二
  authority，并能在每次执行和 restart 后 fail closed 地证明 currentness。

## Consequences

M13 及其他服务器端消费者可以获得摘要钉扎、scope-bound 且在使用时重新验证的身份
引用投影，同时保持 existing IdentityLock 和 external authority 的唯一权威地位。历史
IdentityLock v1 不需要迁移或重算，调用方也不能伪造身份版本。

代价是每次身份引用消费都必须访问 current external authority 并逐字段验证；外部 reader
不可用、bundle 不匹配或任一决定漂移时，即使历史锁仍可读取，操作也会 fail closed。
实现还必须增加 restart、漂移、authority absence、digest repeatability 和历史锁不变性
测试。

## Implementation sequence

1. 本 ADR 与上位规范同步以 governance-only PR squash merge；
2. 从最新 main 在 existing `K2AuthorityIdentityService` 实现 read-only projection、
   current reader、restart revalidation 和聚焦测试，不修改 M13；
3. 从该实现的最新 main 重放并完成 M13-E3，只读消费 identity projection；
4. Frontend 仅更新 Core pin；
5. 完成跨仓只读核验后停止。

## Stop conditions

若实现必须创建新的 Identity root、IdentityVersion repository、第二 Identity authority、
Identity sidecar database，无法在执行时或 restart 后重新调用 current reader，无法逐字段
复核 external decision，必须接受请求体 identity version，必须把 `contentDigest` 伪装成
payload digest，或必须让 M13 写 Identity，则立即停止。

## Change log

| 日期 | 决策方 | 变更 | Decision Ref |
| --- | --- | --- | --- |
| `2026-08-31` | Project Lead / Architecture Owner / V5 Identity Domain Owner / M13 Domain Owner / Security / External Authority Boundary Owner | 创建并接受 ADR-0018；冻结 existing IdentityLock + fresh external decision 的只读 projection、runtime currentness 和 M13 服务端解析边界 | `ACS-V5-IDENTITY-REFERENCE-PROJECTION-AND-M13-E3-UNBLOCK` |
