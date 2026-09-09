# ADR-0022 — 精确 Subject 的独立不可变 GenerationDispatchGrant 与单次消费边界

## 文档元数据

| 字段 | 值 |
| --- | --- |
| ADR ID | ADR-0022（文档提案登记；不代表 Accepted） |
| Version | 1.0 |
| Status | Proposed — 提交 Accepted 审议 |
| Design direction | Project Lead 已确认：独立、不可变 Grant；不覆盖历史五字段，不迁移历史摘要 |
| 完整 ADR 审批状态 | PENDING；设计方向批准不替代本文件批准 |
| 拟议 Decision Ref | ACS-M10-M11-IMMUTABLE-GENERATION-DISPATCH-GRANT-ADR |
| 审批人 | 蔺鹏：Project Lead / Core Architecture Owner / Generation Dispatch Authority Owner / Spike-0 Execution Gate Owner |
| 作者 | ChatGPT，架构提案编制；不担任批准人 |
| 日期 | 2026-09-09 |
| 分析基线 | Core f007ab3e93c3fb7f5e8b3b7f81c34fec28858176 |
| 分析 Tree | b5ef06d0b4557b979cd8ab4acb02790d35ec2223 |
| 提案分析唯一源码身份 | E4 冻结工具快照；完整 commit / Tree 见上两行，私有目录定位保留在交接原件 |
| Extends | ADR-0019、ADR-0021；复用 ADR-0013 的单一权威边界 |
| Narrowly amends, upon acceptance | 仅为本 ADR 定义的精确技术 subject 增加独立派发许可分支；不修改 E3H 输入权限语义 |
| Supersedes / Superseded by | 无 / 无 |
| 实现授权 | NOT_GRANTED |
| 真实 Grant 签发、消费、GPU 或 /prompt 授权 | NOT_GRANTED |

提案形成时（2026-09-09、文档入库前），main 的只读查询返回上述 f007ab3e 提交；该提交的 governance 目录已存在 ADR-0001—ADR-0021，未列出 ADR-0022。该时点本编号仅用于提案，尚未创建仓库文件。[S1]

文档登记说明：本文件分类为 DRAFT，`currentStateClaimsAllowed=false`，Status 仍为 Proposed，完整审批仍 PENDING。正文的“当前”“本轮”“本会话”保留提案编制时点含义；后续文档登记不批准实现或真实执行。[公开证据索引](../docs/status/M10_M11_SPIKE_0_E4_EVIDENCE_INDEX_2026-09-09.md)分别记录原稿与本文件摘要。

**本 ADR 即使随后被标记为 Accepted，也只表示架构合同通过；不自动允许编码、写正式数据库、签发真实 Grant、改变执行配置、产生费用或调用 /prompt。实现任务和真实执行必须分别取得后续明确批准。**本条是本 ADR 的明确批准效果，不得用 ADR 模板中泛化的“Accepted 可按范围实施”扩大范围。[S2]

## 1. Context：本决策解决什么

冻结源码中的 manifest v2 视频路由没有合法的派发许可转换分支。`route_video_methods()` 对原安全字段保持不变的 v2 Run 拒绝视频路由，对擅自改变安全字段的 v2 Run 报不一致。E3H 只允许输入准入；InputAssetVersion 的校验要求 `immutable=true` 且 `providerProcessingAuthorized=false`。这些不是可以由客户端翻转的普通开关。[S3][S4][S5]

已有 E3 InputPlan、Beat、锚帧、不可变 AssetVersion、E4 运行时证明与参数候选可以作为证据输入，但分别不等于 Project Lead 已批准实际生成。当前 E4 元数据 profile 的 false 标志保留。此前 C1/C2 审计结论不因本设计提案而自动改变。

本 ADR 采用 Project Lead 已确定的方向：另行签发一条不可变 `GenerationDispatchGrant`，独立授权一个明确的技术执行动作，而不是把历史输入记录改写成原本已经拥有生成许可。

## 2. Decision：历史事实不变，新许可按精确操作解析

### 2.1 历史五字段永久保持原值

| 既有字段 | 原值 | 本 ADR 下的处理 |
| --- | --- | --- |
| manifest.dispatchAllowed | false | 不改写，不作为本次新许可的存储位置 |
| manifest.cameraContractState | NOT_READY | 不冒充通用 camera ready |
| manifest.shotPlanApprovalState | NOT_VERIFIED | 不把局部技术批准变成完整 ShotPlan 验收 |
| InputAssetVersion.providerProcessingAuthorized | false | 不改写该不可变版本，也不重算或迁移其摘要 |
| InputAuthoritySubject.providerProcessingAuthorized | false | 不扩张 InputAppendAuthority 的 allowedOperations |

原 manifest.executionMode、publicationAllowed、Candidate、InputPlan、AssetAdmission、Selection、历史失败回执、版本号及所有 Ref/Digest 也保持不变。不得复制一份改过 false 的历史对象喂给旧验证器。

新记录中的权限是“对这一个已批准动作允许使用这些精确输入”的独立权威，不是对历史五字段的覆盖层或补丁。读取旧对象仍返回旧值；读取新 Grant 必须返回独立字段和来源。

### 2.2 有效权限的唯一计算方式

有效派发许可必须同时满足：合法且已持久化的 Grant、独立批准证据仍可信、当前输入与 subject 精确一致、执行配置及证据与批准内容一致、未过期、未被终结、唯一 Attempt/worker 的消费检查通过。

不得使用“旧 dispatchAllowed OR 任意 grant 存在”的逻辑。不得仅凭 Ref、缓存对象、`TECHNICAL_EVIDENCE_ONLY` 标签、环境变量、一个成功的元数据请求或普通认证令牌取得许可。

运行时未来必须经 V5 的新、类型化权限边界验证 Grant，再由 V4 执行。无 Grant 的旧 manifest v2 路径继续按原合同拒绝。原 E3H 的输入校验、历史读取及 replay 均保留；新的派发例外不得下放到通用输入 AssetVersion 验证器。

### 2.3 范围仅为一个技术 subject

本版本只面向 `SPIKE0-E3-SH09-VISIBLE-UPPER-BODY-HEAD-TURN-LOCKED-V2`：唯一 Run、唯一 InputPlan、唯一 Shot、唯一 Beat、唯一锚帧版本；48 帧最终输出、24 fps、2 秒、704×1280；MICRO_MOTION / SINGLE_ANCHOR_I2V；MEDIUM_CLOSE_UP / LOCKED；仅沈知微可见，裴昀画外。模型内部 length=49，不把其解释为最终输出帧数。[S9]

这些实例值只进入 Owner 管理的精确批准内容及 subject，不在通用业务代码中硬编码角色名、SH09、实例名或某个 K2 项目分支。v1 无 subject 数组、通配符、批量 grant 或“整个项目放行”。

## 3. Owner、持久化与生命周期

V5 Episode Production 是 Grant 的唯一业务权威，沿用现有 Episode Production evidence journal。V4 仍拥有 MediaJob、Attempt、worker lease 和 provider transport；不成为批准人。Operator Application 只能调用 V5 公开领域边界，不能直接使用私有 repository 或执行 SQL。

只增加两个 append-only journal record kind：

| Record kind | Payload schema | 作用 |
| --- | --- | --- |
| GenerationDispatchGrant | v5.generation-dispatch-grant.v1 | 一条不可变的精确批准记录，内嵌批准来源、权限和签发审计 |
| GenerationDispatchGrantTerminal | v5.generation-dispatch-grant-terminal.v1 | 对 Grant 的唯一终结事实：消费提交或消费前撤销 |

Terminal 是该 Grant 的不可变使用/撤销审计，不是第二个批准机制、数据库或队列。Grant 不增加可变 `used`、`remainingCount` 或 `state`。到期状态由可信时钟读取计算；撤销及消费由 Terminal 计算。消费后的执行结果归既有 MediaJob/Attempt，不改 Grant。

本 ADR 不批准新表、DDL、第二数据库、第二资产权威、独立计费账本或独立任务队列。既有 journal 的原子追加、唯一记录身份和 CAS 可以作为实现基础；它们并不是已经实现了本次业务合同。[S6]

## 4. 最终 Schema：GenerationDispatchGrant v1

以下字段集构成本提案的规范性 schema；不是已经签发的实例。每个对象均 closed-world：未列字段、重复键、缺失必填字段、未知枚举、NaN/Infinity 均拒绝。只有明确列为可空的 Terminal 分支字段允许 null；Grant 不允许用 null 或假摘要补齐未批准的运行配置。

### 4.1 通用类型与摘要

- `Ref`：非空、无控制字符的规范 Ref；沿用现有 ref 验证与作用域隔离，名称不是身份。
- `Digest`：64 位小写十六进制 SHA-256。Git commit/tree 是单独的 Git object ID 类型，不能与 SHA-256 混用。
- `Int`：严格整数，bool 不算整数。金额为币种最小单位整数，本版本为人民币分。
- `UtcTime`：带秒/必要小数位的 UTC ISO 8601，必须以 Z 结尾；有效区间采用 [notBefore, expiresAt)。
- `PinnedRef`：字段恰为 `{ref, digest}`，分别指原对象的精确版本 Ref 及其既有规范摘要；不重封装原对象来产生替代摘要。
- `H(x)`：UTF-8 canonical JSON，键排序、紧凑分隔、不做隐式 Unicode 改写、禁止非有限数字后计算 SHA-256。沿用现有合同的已签发摘要，不能另选浮点序列化去改变它们。

`subjectDigest = H({workspaceRef, projectRef, seriesRef, episodeRef, productionRunRef, subject})`。

`approvedPlanDigest = H({scope, subject, executionBinding, permissions, limits})`，其中 scope 是前述五个 scope Ref 的闭集对象。

`payloadDigest = H(Grant 去掉 payloadDigest)`。createdAt、批准的有效时间及金额都参与 Grant 完整性摘要；幂等请求摘要另行定义，不能因重试时钟变化重新签发。

### 4.2 顶层字段闭集

```text
schemaVersion = "v5.generation-dispatch-grant.v1"
generationDispatchGrantRef : Ref
version = 1
workspaceRef : Ref
projectRef : Ref
seriesRef : Ref
episodeRef : Ref
productionRunRef : Ref
subject : GenerationDispatchSubject
subjectDigest : Digest
executionBinding : ApprovedExecutionBinding
permissions : ExactSubjectPermissions
limits : SingleAttemptLimits
approval : VerifiedProjectLeadApproval
issuanceEvidence : IssuanceEvidence
publicationAllowed = false
createdAt : UtcTime
payloadDigest : Digest
```

**业务唯一槽位**：`slotDigest = H({workspaceRef, productionRunRef, creativeShotVersionRef, beatRef})`，两个后者取 subject 的精确 Ref。`generationDispatchGrantRef = "generation-dispatch-grant-" + slotDigest`，recordVersion 固定 1。唯一槽位不含 seed、批准编号、时钟或随机数，防止通过换参数、换幂等键再签一份额度。

v1 不提供续期、换参、重新签发或 version=2。旧 Grant 失效、已撤销或已消费后，不得用新 Ref 绕过同槽位限制。新的试验意图须另行评审；本 ADR 不预先批准它。

### 4.3 subject 闭集

| 字段 | 类型 / 规则 |
| --- | --- |
| technicalTargetId | Ref，仅审计标签；不能替代以下版本身份匹配 |
| productionRunPayloadDigest、manifestDigest | 各为 Digest，指未改写的原 Run/manifest |
| scriptVersion | PinnedRef |
| m6Binding | 恰为 `{m6BaselineSnapshotRef, m6BaselineCanonicalDigest, activationRevision, m6ConsumerBindingDigest}` |
| consistencyValidationVersion | PinnedRef，需重新解析其当前性及 PASS |
| executionMethodPlanVersion | PinnedRef |
| methodAwareInputPlanVersion | PinnedRef，需完整验证其 READY 绑定，而非只看字符串 READY |
| creativeShotVersion | PinnedRef |
| actionExecutionBeat | PinnedRef |
| visualExecutionRequirement | PinnedRef |
| inputAsset | 下述闭集 InputAssetBinding |
| inputAppendAuthority | 恰为 `{ref, digest, subjectDigest}`，指旧输入权威证据及旧 subject；不授予额外操作 |
| sourceAction | 恰为 `{sourceSpan, sourceTextDigest}` |
| cameraInstruction | 恰为 `{framing, movement}`，本次 MEDIUM_CLOSE_UP / LOCKED |
| frameRange | 恰为 `{startFrameInclusive, endFrameExclusive}`，本次 0 / 48 |
| outputConstraints | 恰为 `{mediaKind, mediaType, width, height, durationFrames, frameRate}` |
| executionClass | MICRO_MOTION |
| executionMethod | SINGLE_ANCHOR_I2V |

`InputAssetBinding` 字段恰为：`assetRef, assetVersionRef, assetVersionDigest, inputRole, contentDigest, mediaType, byteSize, width, height`。必须重新经既有 canonical AssetVersion authority 验证完整资产链；不是对脱敏 Public projection 直接重算 canonical asset digest。`inputRole=ACTION_READY_ANCHOR`，本次 image/png、998335 字节、704×1280。

`sourceSpan` 恰为：`scriptSceneRef, sourceField, sourceIndex, startOffsetInclusive, endOffsetExclusive`。文本必须由当前确定的 ScriptVersion 按该 span 解析并重新算摘要；不接收客户端改写的动作作为事实。

`durationFrames = endFrameExclusive - startFrameInclusive`；48 % 4 = 0；latent length=durationFrames+1。输入角色、输出画幅、动作主体、可见/画外人物约束由其所绑定的既有 Script/M6/Shot/Beat 对象验证，不新增或改写这些对象。

### 4.4 executionBinding 闭集

| 字段 | 类型 / 规则 |
| --- | --- |
| backendDecision | 原 `v4.video-execution-backend-route-decision.v1` 的完整闭集值，作为不可变快照；不是新 registry |
| backendDecisionDigest | H(backendDecision) |
| executionProfile | PinnedRef，指选定的生成 profile；不是元数据 profile，也不是未选定候选 |
| executionConfigDigest | 服务端安全配置投影的 Digest，包含执行语义、路径映射标识和超时；不含原始密钥、密码或 bearer token |
| executionCode | 恰为 `{coreCommit, coreTree, comfyuiCommit}` |
| runtimeBinding | 恰为 `{instanceRef, processIdentityDigest, attestationFileSha256}`；attestationRef/payloadDigest 取 backendDecision |
| workflowDigest | 精确 ComfyUI workflow 的 canonical 摘要 |
| costBasis | PinnedRef，指已审查的计费/估算依据；与限额不是同一概念 |

backendDecision 中的 provider/model/region/endpointClass、backendProfileRef/Digest、模型集合、adapterIdentity/capability、runtimeAttestationRef/Digest、resourceShape、币种和费用约束，必须与实时装配一致。若同一字段在两个闭集对象中出现，必须严格相等，不能择一解释。

processIdentityDigest 对实例标识、ComfyUI PID/启动身份、ComfyUI commit 及启动配置摘要的已验证投影计算，不含随时变化的空闲显存或普通观察时钟。它不是客户端自报 PID 的信任替代品。

本次 f007ab3e 是分析及 E4 工具基线，没有实现新 Grant 的消费者。未来真实 executionCode 必须另行冻结为已通过验收且包含本 ADR 实现的明确提交/tree；不得把 f007ab3e 当作已经具备这项能力，也不得自动切换浮动 main。批准未来实现任务时须单独处理这个版本迁移。

既有 E4 证明保留为历史运行时证据。若 runtimeBinding 的进程身份改变，需要新当前性证据及与批准内容一致的证明绑定；不得悄悄替换 attestationRef/Digest，或把旧进程证明当新进程实测。

workflow 在批准前由原动作、明确采样配置和确定性的 requestRef 编译为纯数据，不发送。requestRef 从 subject 和已选 profile/code/output 生成，不依赖 Grant payloadDigest；后续请求再引用 Grant，避免 Grant → workflow → request → Grant 的摘要循环。

### 4.5 permissions：恰好五项，均只属于新 Grant

```text
dispatchAllowed = true
shotPlanScopeApproval = "APPROVED_FOR_EXACT_TECHNICAL_SUBJECT"
cameraScopeApproval = "APPROVED_FOR_EXACT_TECHNICAL_SUBJECT"
inputAssetProcessingAuthorized = true
inputSubjectProcessingAuthorized = true
```

这五项不是旧字段的新值。两个 scope approval 仅认可批准记录中明确覆盖的本次镜头/固定机位技术意图，不产生全局 `shotPlanApprovalState=APPROVED` 或 `cameraContractState=READY`。inputSubjectProcessingAuthorized 指新 Grant 独立许可本次已绑定输入的处理；绝不修改旧 InputAppendAuthority 的操作集合。

Grant 不允许缺项、部分授权或授权并集。批量生成、外部 Provider fallback、输出准入、HumanSelection、Master、Export、publication、其他 Run 均不由本 schema 授权，不通过增加任意 permissions 键扩展。

### 4.6 limits 闭集

```text
maxAttempts = 1
maxPromptSubmissions = 1
retryAllowed = false
fallbackAllowed = false
costCurrency = "CNY"
maxCostMinor : 正整数
executionTimeoutSeconds : 正整数
notBefore : UtcTime
expiresAt : UtcTime
stopPolicy = "FAIL_CLOSED_NO_RESUBMISSION"
```

必须满足 `notBefore < expiresAt`，签发及消费时均满足 `notBefore <= now < expiresAt`。executionTimeoutSeconds 不能超过批准的剩余执行窗口；期限不得仅由客户端时钟判定。maxCostMinor、超时和有效期必须包含在本次独立的生成批准中。既有 E4 的人民币 1000 元累计预算不自动成为新 Grant 的额度，旧 CLI 内部 USD/0 占位也不是计费依据。缺少精确批准或可信成本上界时，拒绝真实签发，不填写 0/null 假装闭合。

任务费用上限必须明确覆盖本次获批操作的成本，并在单次执行前以 costBasis 校验最坏情形不超限；租用实例及存储继续计费的控制责任不得被遗漏。停止 ComfyUI 不等于停止平台计费。Grant 不授予平台开关机、释放或续租权限。

### 4.7 approval 闭集与信任来源

```text
approvalRef : Ref
authorityRef : Ref
authorityDecisionRef : Ref
authorityDecisionDigest : Digest
actorRef : Ref
actorKind = "HUMAN"
actorRole = "PROJECT_LEAD"
approvalKind = "EXACT_SUBJECT_GENERATION_EXECUTION"
decision = "APPROVED"
approvedPlanDigest : Digest
approvalEvidenceRef : Ref
approvalEvidenceDigest : Digest
decidedAt : UtcTime
```

`authorityDecisionDigest = H(approval 去掉 authorityDecisionDigest)`。其 approvedPlanDigest 必须等于第 4.1 节计算值。

批准来源必须由 Owner 控制的独立、可信 approval resolver 验证。设计方向批准、ADR Accepted、实现批准、普通 HTTP 认证、InputAppendAuthority 和 HumanSelection 均不能替代 `EXACT_SUBJECT_GENERATION_EXECUTION` 批准。

首版采用与 E3H 相同的信任部署形状：由 Owner 管理一个新类型、绝对路径、独立 SHA-256 pin 的只读批准 bundle。拟议外层 schema `v5.generation-dispatch-approval-bundle.v1` 字段恰为 `{schemaVersion, authorityRef, approvals}`，approvals 必须恰好一项，项为上述 approval。bundle 只表达批准来源，不直接成为数据库 Grant；每次 issue/consume 重新验证源字节、身份、范围和有效期。不得重用 E3H bundle 的类型或扩张其 operations。

SHA-256 只证明一致性，不独立证明批准者身份。批准人身份必须由外部可信流程与预配置 authority 的对应关系确立；CLI 不接受随意填写 actorRef 就认作 Project Lead。原始密码、令牌、私钥、认证头不得落入 Grant 或审计报告。

### 4.8 issuanceEvidence 闭集

```text
issuerServiceRef : Ref
requestDigest : Digest
approvalBundleSha256 : Digest
expectedRecordJournalHead : Digest
expectedWorkspaceRecordJournalHead : Digest
expectedEvidenceRevisionToken : Digest
currentSubjectReadSetDigest : Digest
```

此处 currentSubjectReadSetDigest 是服务端对本次实际读取的 source Ref/Digest 与 selector version 集合的摘要，是审计证据，不是新 currentness 权威或新数据库。journal 的 sequence、idempotencyKey、createdAt 等仍由现有 EvidenceRecord envelope 持有。

## 5. 入口与签发事务

### 5.1 首版只有 Operator Application，不做新 Frontend 页面

拟议 `GenerationDispatchGrantOperatorApplication` 提供 `prepare`（只读生成批准待核内容）和 `issue`（实际签发写入）。这是待实现接口说明，不是本轮可执行命令。Operator 调用 V5 public domain boundary；不在 Application 中打开 SQLite、不调私有存储接口。

issue 的请求字段闭集为：

```text
workspaceRef
productionRunRef
methodAwareInputPlanVersionRef
creativeShotVersionRef
beatRef
inputAssetVersionRef
backendRef
expectedSubjectDigest
expectedApprovedPlanDigest
authorityDecisionRef
idempotencyKey
expectedRecordJournalHead
expectedWorkspaceRecordJournalHead
expectedEvidenceRevisionToken
```

其余 scope Ref 从既有 Run 解析并验证。禁止客户端提交 permissions、actor/role、五个历史字段、完整 grant、生成结果或 `allowV2`。expected* 字段只是比较条件，不是事实来源。generation-specific 批准数据只由独立 resolver 返回。

prepare 可以返回待审查的精确 plan 和 digest，但不产生 Grant、不消耗额度、不认定阻塞解除，也不替用户批准 seed、费用或运行环境。

### 5.2 签发原子写入的精确范围

服务端重新核对原 Run/manifest、完整输入资产链、InputPlan、Script/M6/M7/M8/M9、实际配置及独立批准，然后在既有 evidence journal 的一次事务内：校验 CAS，检查唯一槽位及幂等冲突，追加**恰好一条 GenerationDispatchGrant**。批准投影、五项 subject 权限和 issuanceEvidence 都在该记录同一 payload 中提交，不存在部分字段先放行。

不写入旧 manifest、AssetVersion、InputAuthoritySubject、Candidate、InputPlan 或批准文件；不创建 MediaJob、Attempt、输出资产或 HTTP 请求。成功表示“记录签发已提交”，不表示已经派发或项目就绪。任一校验/提交失败回滚，本次新增 Grant 为零。

**原子性仅限这个 journal 事务。**当前 journal 采用同一 Run 批次、BEGIN IMMEDIATE、唯一记录身份、请求幂等和 journal/revision CAS。不能把它描述成同时覆盖独立 M5/M6 数据库、V4 队列与网络调用的全局事务。[S6]

## 6. CAS、重放和当前性规则

| 情形 | 规范结果 |
| --- | --- |
| 新 subject 槽位、准确批准、三项 journal/revision token 和 source 校验一致 | 单条 Grant 原子追加 |
| 相同幂等键、相同语义请求、已有完整 Grant | 返回原 Ref、原 payloadDigest、原 createdAt；新增零条 |
| 相同幂等键、不同 subject/批准/profile/限额/有效期 | IDEMPOTENCY_CONFLICT，零写入 |
| 不同幂等键命中同一 subject 槽位 | GRANT_SUBJECT_ALREADY_RECORDED，零写入；不能再发额度 |
| 首次签发时 expectedRecordJournalHead / expectedWorkspaceRecordJournalHead / expectedEvidenceRevisionToken 任一不符 | SUBJECT_SNAPSHOT_CHANGED，零写入 |
| 原输入版本、digest、current selector 或批准内容漂移 | SUBJECT_OR_APPROVAL_CHANGED，零写入；不自动重绑定 |
| Grant 已过期或存在 Terminal | 可返回历史记录，但不得返回新的可用许可 |
| 超时导致签发结果未知 | 先按精确幂等键查历史；不得生成新 Ref/新批准编号盲重试 |

requestDigest = H(issue 请求去掉 idempotencyKey 和三项 CAS token)。subject、plan 和 authorityDecisionRef 属于语义内容，不能从 requestDigest 中排除。CAS token 不参与幂等语义是为了能读取原请求的既有结果，不是允许过期请求获得新权限。重放返回必须将 `recordReplay` 与 `currentlyEligible` 分开，后者每次重新计算。

**跨权威域限制：**journal CAS 不能锁住独立 M5/M6 selector。Grant 绑定的是不可变版本，并不保证这些版本永远 CURRENT。签发前和消费前都必须重新经各 owner 的正式 reader 验证当前性；v1 的消费只允许在当前性敏感写入与校验可被现有 V5 生命周期协调域的读屏障保护的部署启用。无法提供这个协调保证时，返回 `CURRENTNESS_FENCE_UNAVAILABLE`，不得把两次散点读取包装成跨库原子快照。该要求是待实现及测试的契约，不宣称冻结代码已有此屏障；如必须新增持久化 owner/DDL 或分布式事务方可满足，实施必须另行停报。

读屏障保护“取得当前 subject → GrantTerminal 消费提交”的临界区，并以紧接提交前的校验形成决策时点；不在长时间 GPU 推理期间持有数据库事务。决策时点之后的新版本不会被改写到已批准 Attempt，也不能授权另一个 subject。显式撤销与消费的并发规则见下一节。

## 7. 不可变 Grant 的单次消费与撤销

### 7.1 Terminal schema

`v5.generation-dispatch-grant-terminal.v1` 的字段恰为：

```text
schemaVersion
grantTerminalRef
generationDispatchGrantRef
generationDispatchGrantDigest
workspaceRef
productionRunRef
kind = "CONSUMPTION_COMMITTED" | "REVOKED"
attemptBinding : AttemptConsumptionBinding | null
revocationApproval : VerifiedRevocationApproval | null
requestDigest
expectedRecordJournalHead
expectedEvidenceRevisionToken
createdAt
payloadDigest
```

`grantTerminalRef = generationDispatchGrantRef + ":terminal"`，recordVersion=1，同一 Grant 只能追加一个 Terminal。kind=CONSUMPTION_COMMITTED 时 attemptBinding 必填、revocationApproval=null；kind=REVOKED 时反之。字段不能省略；两分支同时出现或同时为 null 均拒绝。

`AttemptConsumptionBinding` 恰为 `{mediaJobRef, attemptRef, workerRef, jobRevision, leaseTokenDigest, executionEnvelopeDigest, workflowDigest, currentSubjectReadSetDigest}`。不保存原始 lease token。V5 通过正式 V4 只读端口核对真实指定 Job/Attempt、当前 revision/lease 和摘要，不能信任客户端自报。

`VerifiedRevocationApproval` 恰为 `{approvalRef, authorityRef, authorityDecisionRef, authorityDecisionDigest, actorRef, actorKind, actorRole, approvalKind, decision, grantDigest, approvalEvidenceRef, approvalEvidenceDigest, decidedAt}`；actorKind=HUMAN，actorRole=PROJECT_LEAD，approvalKind=REVOKE_EXACT_GENERATION_GRANT，decision=APPROVED，grantDigest 精确等于目标 Grant payloadDigest。authorityDecisionDigest=H(该对象去掉自身 digest)，并由独立可信 resolver 验证。不得将原签发批准重用为撤销批准。

### 7.2 消费不是把 Grant.state 改成 used

V4 先在原 MediaJob 存储通过 revision/lease CAS 获得唯一 Attempt，再请求 V5 消费该 Grant。V5 在原 evidence journal 的单事务中验证 Grant、有效期、当前性、实际 Attempt 绑定以及 Terminal 槽位为空，追加 CONSUMPTION_COMMITTED。并发撤销使用同一 Terminal 槽位；只有一个可以提交。

撤销不要求原 source 仍为 CURRENT，否则过期输入可能反而阻止 Owner 撤销；它只要求目标 Grant、撤销批准和 Terminal/CAS 条件有效。撤销先提交：消费拒绝。消费先提交：撤销返回 `ALREADY_CONSUMED`，不能声称已停止在途请求；终止运行需走另行授权的既有取消/进程处理，不退款重置消费次数。到期不写 Terminal、不删除历史，但同一 Grant 不得续期使用。

### 7.3 跨存储与网络的真实保证

V4 Job/Attempt CAS、V5 Terminal 追加、ComfyUI HTTP 请求是不同提交点，不宣称一个分布式原子事务。采用 fail-closed 的单调消费顺序：**有效 Grant → 唯一 Job/Attempt → 消费提交 → 当前活跃 worker 至多一次 POST /prompt**。不存在从只读 prepare、issue 或 replay 直接发请求的路径。

只有本次新消费提交并成功收到该结果的当前 worker 进程，可沿非恢复的执行分支继续。读取历史 Terminal 或消费幂等 replay 不返回新的发送许可。消费回执丢失、进程崩溃、lease 失效、HTTP 结果未知，即按已用掉额度处理，不转移许可，不重新提交，不因观察不到视频而“补一次”。

由此保证**至多一次提交**，不能保证“恰好成功生成一次”。允许某些崩溃窗口产生零次请求；安全性优先于自动重试的可用性。已知 providerRequestRef 的只读核对与结果恢复不增加提交额度，但可能产生费用的后续动作仍需要独立批准。frozen worker 已有 revision/lease 与不可重试失败语义，可作为基础；新的 Grant 消费接线尚未实现。[S7]

HTTP transport 禁止对 POST 自动重试、307/308 等重定向重发和 provider fallback。maxAttempts=1 不替代 maxPromptSubmissions=1；两者都必须由实际路径与测试证明。

## 8. 新 Grant 如何接到现有 v2 Run，而不改旧五字段

未来实现应按如下验证顺序建立局部例外：先完整验证原 manifest v2 和 E3H 输入安全不变量仍为原值，再解析本次精确新 Grant 和独立批准；只有获得内部类型化 VerifiedGenerationDispatchGrantContext 后才允许此 subject 的新 route/request。其余 v2 Run、旧无 Grant 请求和字段自报一律继续拒绝。

历史验证器不接收伪造的“允许版旧对象”。只新增 operation-specific 授权分支，不删除 blanket guard，也不让 V4 Worker 通过配置直接跳过 V5。

新请求中的 executionMode 可以表达本次批准的 INTERNAL_SELF_HOSTED 行为，但这是新请求的事实，不改历史 Run 的 LOCAL_EVIDENCE。输出仍为技术候选，不产生输出 AssetVersion、Master、Export 或 publication。

### Closed-world 接口的 additive 版本

为了将 Grant 身份绑定到现有 V5→V4 链而不扩张旧 schema，提案冻结下列新增版本边界：

| 对象 | 既有版本保留 | 带 Grant 的新版本 |
| --- | --- | --- |
| Video method route plan / route | v5.video-method-route-plan.v1 / v5.video-method-route.v1 | 对应 v2 |
| Method-aware generation request | v5.method-aware-video-generation-request.v1 | v5.method-aware-video-generation-request.v2 |
| Execution envelope | v4.method-aware-media-execution-envelope.v1 | v4.method-aware-media-execution-envelope.v2 |
| Method-aware media job | v4.media-job.v3 | v4.media-job.v4 |

以上新版本新增的 `dispatchGrantBinding` 闭集为 `{generationDispatchGrantRef, generationDispatchGrantDigest, subjectDigest, approvedPlanDigest}`；其余既有语义字段必须保持原义并进入各自新摘要。GrantTerminal 由正式权限端口核验，不以请求自带一个字符串作为消费证明。旧无 Grant 版本保持历史读取和准确重放，新带 Grant 请求不能降级到旧执行路径。[S8]

InputPlan、InputAssetVersion、InputAppendAuthority 和 v2 runtime attestation 不因本 ADR 升版或迁移。若执行结果 DTO 或其他闭集对象确需增加字段，也必须在单独的实现任务范围内明确版本分派，不允许无声明加键。

本版本首个执行消费者只承接本次单 Shot/Beat，不循环派发 InputPlan 中其他条目；本次原始 InputPlan 本身只有一项，也必须在边界上再次验证，不依赖偶然数量绕过作用域检查。

## 9. 明确的非目标

不赋予一般 Production Ready；不补造全局 ShotPlan/camera 验收对象；不升级输入资产许可；不改变 E3H 排除操作；不重做 Candidate/InputPlan；不开放 CONTACT/GAIT fallback；不改 Frontend 或 M12-C3；不创建第二资产、队列或批准来源；不自动签发真实 Grant、不自动申请或实施 GPU 生成；不配置 cloud power、续租或账户付费操作。

这份 ADR 的接受不等于已实施路径、不等于真实 subject Grant 已签发、不等于阻塞已解除。任何此类运行状态结论由 Project Lead 根据后续证据单独确认。

## 10. Alternatives 与 Consequences

原位覆盖五字段：不采纳。违反不可变输入资产/subject 的语义，破坏摘要引用，且旧验证器仍会拒绝。

复用 E3H grant、P1 环境变量或绕过 V5 直接向 ComfyUI 提交：不采纳。前者操作集合明确排除生成，后者不建立本次精确 subject 的 V5 派发权威。

只增加一个无持久化消费约束的 boolean：不采纳。批准不能审计到精确参数，也无法证明并发、崩溃后的单次使用。

保持当前 BLOCKED：在本 ADR 未接受、未实现或未获得真实生成批准时，仍是正确执行状态；不是要绕过的故障。

独立不可变 Grant + 唯一 Terminal：采纳的提案。收益是保存历史血缘、缩小权限、可以证明重放和消费上限；代价是新增两个 journal record kind、独立批准 reader、版本化接线及严谨的并发/崩溃测试。不存在“加一个文件就无需调整消费者”的承诺。

主要风险为：假批准、来源漂移、重复额度、CAS 检查与原子边界不一致、旧协议降级、跨库 currentness 竞争、超时后重复提交、运行成本无法准确约束。对应责任人为 Core Architecture / Generation Dispatch Authority / V4 Worker Owner；此提案不伪造已经分配的 Risk Register 编号。

## 11. 验收要求（未来实现任务的门禁，不是本轮已执行测试）

| 类别 | 必须证明 |
| --- | --- |
| 历史保持 | 五字段原值、E3 全部 Ref/Digest、InputPlan、Candidate、历史失败与 replay 字节/语义不变 |
| 批准真实性 | transport auth、伪 actorRef、ADR Accepted、InputAppendAuthority、HumanSelection、旧预算均不能代替独立生成批准 |
| schema | 所有闭集、类型、重复键、金额、时区、digest、版本与超限拒绝 |
| subject 精确性 | 外 Run/Workspace/Shot/Beat/Asset、不同动作范围、不同48帧规格均拒绝 |
| 配置完整性 | profile、code、模型、workflow、runtime 及费用依据变动不得静默更新批准 |
| 签发原子性 | 失败零记录、成功单记录；相同幂等 replay 零新增；不同键同槽位不能再签 |
| CAS/currentness | 三项 token 漂移拒绝；source selector 竞争有受控读屏障或 fail-closed，不以 mock 散点读取冒充保障 |
| 消费/撤销 | 并发同一 Grant、不同 job/worker、消费与撤销竞争最多一个 Terminal；Grant 始终不变 |
| 崩溃窗口 | Job CAS 后、消费前/后、HTTP前/后、回执丢失、lease 到期均不产生第二次 /prompt |
| 旧版兼容 | 旧 schema 继续历史 read/replay，不能携带 grant 降级执行；新版闭集与 E1/E2 接线完整 |
| 无输出升级 | 生成候选/恢复文件不自动建立输出准入、Master/Export/publication |
| 测试资源 | 所有实现期 unit/contract/integration 用 no-call/fake transport；真实 GPU 与付费运行另行批准 |

不得为了通过测试弱化精确 subject、CAS、许可或 single-submit 断言。需要新 DDL、第二权威、跨库事务层、额外依赖或超出上表版本范围时，停报范围扩张；不能由实现者默认同意。

## 12. Migration、回滚与审批次序

**无历史数据迁移。**既有 Run、manifest、AssetVersion、InputAppendAuthority 及 InputPlan 保留原样。将来的实施只增加新权限记录及消费者分支，默认关闭新写入与执行。

顺序固定为：本 ADR 完整正文审议 → 明确 Accepted（仅架构）→ 单独提出并获批实现任务 → 实现及无真实调用测试 → 仓库验收与新执行代码基线批准 → 精确生成计划审议 → Project Lead 对一次实际生成及成本明确批准 → 才可受控签发和消费真实 Grant。

任一阶段未完成，不自动开始下一阶段。移除新 authority 配置只恢复默认拒绝，不删除已持久化 Grant/Terminal；回滚不得退回能忽略 Terminal 的旧消费者继续执行。

## 13. 审批记录与本轮交付状态

本节保留提案编制时的审批与操作记录，所称“仓库修改未批准、未执行”指该次提案编制；不否定后续单独授权的文档登记，也不将文档修改解释为实现授权。

| 事项 | 状态 |
| --- | --- |
| 独立不可变 Grant、不覆盖历史五字段的方向 | 已由 Project Lead 在当前消息明确确认 |
| ADR-0022 v1.0 全文 Accepted | 待批准 |
| 实现任务授权申请 | 本轮未提出 |
| 实现、仓库修改、DDL、配置写入 | 未批准、未执行 |
| 真实 subject 批准 / Grant 签发 / 消费 / /prompt | 未批准、未执行 |
| 阻塞解除结论 | 本轮未作出 |

本轮仅查询 GitHub 冻结源码及已上传只读回执，编制本会话 Markdown 交付件；没有连接 A100、运行服务、修改仓库/数据库/执行配置或进行任何生成调用。

## 14. 证据索引

以下仓库事实以 f007ab3e93c3fb7f5e8b3b7f81c34fec28858176 为准。新对象及行为均为本提案，不能反读为这些文件已实现。

- [S1] GitHub refs/heads/main 只读查询；该提交 governance 目录列表（最后已有编号 ADR-0021）。
- [S2] governance/ADR_TEMPLATE.md，Status、Decision 与审批记录；本提案明确将 Accepted 的批准效果收窄为架构合同。
- [S3] governance/ADR-0021-manifest-v2-technical-input-append-authority.md，Decision 4—10、Scope relationship、Verification and rollback。
- [S4] services/v5_core_os/episode_production/method_aware_media.py:1632–1658，manifest v2 路由拒绝；foundation.py:1039–1045、1157–1188，历史安全字段及重解析 currentness。
- [S5] services/v5_core_os/episode_production/method_aware_input_assets.py:152–164、608–658，immutable input asset 和原子准入；input_append_authority.py:35–51、379–406，排除操作及 fixed subject 安全值。
- [S6] services/v5_core_os/episode_production/evidence.py:1794–1938，append_records 的同范围事务、唯一身份、幂等、CAS 和回滚；未覆盖其他数据库或网络。
- [S7] services/v4_platform/media_jobs.py:2590–2697、2769–2910，lease、不可重试故障、Attempt revision CAS 与调用 adapter 的顺序。
- [S8] services/v5_core_os/episode_production/method_aware_media.py:37–46；services/v4_platform/method_aware_execution.py:13–23；services/v4_platform/media_jobs.py:29–51，既有版本常量。
- [S9] 本会话已交付 e4_step1_exact_binding_20260909/BINDING_REVIEW.json；这是已封存包及已观察运行进程的只读核对，不是新 online currentness 或资产重封装验证。

## 变更历史

2026-09-09：创建 v1.0 Proposed，采纳已确认的独立不可变 Grant 方向；提出最终闭集 schema、签发事务、CAS、单次消费和撤销语义；未授予或执行实现与生成。
