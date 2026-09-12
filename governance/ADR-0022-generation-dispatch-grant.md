# ADR-0022 — 精确 Subject 的独立不可变 GenerationDispatchGrant 与单次消费边界

## 文档元数据

| 字段 | 值 |
| --- | --- |
| ADR ID | ADR-0022 |
| 文档版本 | 1.4；保留 v1.2 控制面及 §5.6，增加 §5.7 的 R3 狭义原图/runtime/编码兼容 |
| Status | Accepted — Architecture Contract Only |
| 完整 ADR 审批状态 | ACCEPTED_ARCHITECTURE_ONLY；Project Lead 已明确接受全文，不等于实现或生成许可 |
| 已确认设计方向 | 独立、不可变 Grant；不覆盖历史五字段，不迁移历史摘要 |
| 原候选修订依据 | Project Lead 对 v1.1 N1 独立复审提出的 F01—F04 单文件文档修订回复“批准”；原修订许可不包含实现或发布 |
| 全文接受依据 | Project Lead 在 v1.2 独立复审之后回复“Accepted”；登记日期 2026-09-10，不补造精确批准时刻 |
| 本次文档发布依据 | 上述接受记录交付之后，Project Lead 对 Accepted 状态回填与文档入库另行回复“授权” |
| 接受对象原 SHA-256 | b963c12a07dea8816516752a40470df035e275714909a302ee8087963d4af75f |
| 接受决定记录 | [ADR-0022 v1.2 架构接受记录](../docs/status/ADR_0022_V1_2_ARCHITECTURE_ACCEPTANCE_2026-09-10.md) |
| Decision Ref | ACS-M10-M11-IMMUTABLE-GENERATION-DISPATCH-GRANT-ADR |
| 决策人 | 蔺鹏：Project Lead / Core Architecture Owner / Generation Dispatch Authority Owner / Spike-0 Execution Gate Owner |
| 编制人 | ChatGPT，审核窗口；不担任批准人或生产代码执行器 |
| 日期 | 2026-09-12；v1.2 接受日期仍为 2026-09-10 |
| 文档对照基线 | 3bf2e7a5152a7bd9c1087571aab6413a53a43bb6 |
| v1.0 对照 Git blob | 07e225bf3745c2e961007477a296e19a7ff07ea9 |
| v1.1 未提交候选 SHA-256 | 91d01b94cf1c1312093a612a6b3b9815dc159655e09b859681310a5a8d5e3276 |
| 已审计行为基线 | f007ab3e93c3fb7f5e8b3b7f81c34fec28858176 |
| 已审计行为 Tree | b5ef06d0b4557b979cd8ab4acb02790d35ec2223 |
| Extends | ADR-0019、ADR-0021；复用 ADR-0013 的唯一权威边界 |
| Narrowly amends, architecture only | ADR-0014 Decision 10 中完整 ShotPlan/camera 批准的技术试验前置要求，且仅限 §2.3 定义的局部例外；Decision 7 的历史事实不变 |
| Supersedes / Superseded by | 无 / 无 |
| 文档登记分类 | ACCEPTED_DECISION；currentStateClaimsAllowed=false |
| 实现、部署、真实签发、消费或生成许可 | R2 白名单本地 CPU/隔离 loopback 实现已另行授权；发布、部署、真实签发/消费/生成均 NOT_GRANTED |

本文已由 Project Lead 明确接受为架构合同，不是已实现能力或已经签发的运行授权实例。v1.2 的元数据发布不授权编码或执行。2026-09-12 Project Lead 签发 `ACS-A14B-CONTRACT-COMPATIBILITY-AND-STAGED-TRANSPORT-R2-20260912`，另行批准 §5.6 狭义设计增量及本地 CPU/夹具独占 loopback 实现。正式数据库、执行配置部署、真实费用及真实 ComfyUI `/prompt` 仍未授权；本地实现候选不等于 Owner 验收或发布。[S1][S2]

v1.2 接受对象的 SHA-256 为 `b963c12a07dea8816516752a40470df035e275714909a302ee8087963d4af75f`；其发布原文保存在 Git 基线 `ad7349ff493baaa1e0bc831810ea28b3dd2b2dce`。v1.3 仅增加 §5.6 及必要交叉引用，不改既有控制面语义；旧单模型分支仍受 v1.2 原约束。其中“本次修订”“待审议”等历史表述保留编制阶段含义。新文件摘要另行计算，不能沿用 v1.2 接受摘要或声称新增实现已验收。

v1.0 已随 PR #84 入库；v1.1 是已落稿但未提交的候选。此次在该候选原字节上只修订 F01—F04 及其直接依赖，不改写已封存的 E3/E4、v1.0/v1.1 审核或夜间回执。未变条款沿用 v1.1，不把旧纸面审查结果重新记成 v1.2 的验证结果。[S1][S9][S14]

## 1. Context 与保留边界

已审计源码没有本次精确 subject 的派发许可签发机制：manifest v2 的原安全字段合法时视频路由拒绝，擅自改成允许值时又会违反旧校验。E3H 只允许技术输入侧准入；输入 AssetVersion 明确不可变，处理权限仍为 false。[S3][S4]

本 ADR 不把“运行时存在”“InputPlan READY”“人类选中了图片”解释为输出/派发许可。采用另行签发的独立记录，允许未来系统核实一个真正的、精确的生成批准，并保持所有历史对象原样。

本次修订不声明 C1/C2 或 Spike-0 阻塞已经解除。F01—F04 的修订及 R1—R4 的整体条款是否充分，由独立复审及 Project Lead 的后续决定确定。

## 2. Decision：独立许可，不改历史

### 2.1 五个历史字段与摘要保持不变

| 历史字段 | 保留值 |
| --- | --- |
| manifest.dispatchAllowed | false |
| manifest.cameraContractState | NOT_READY |
| manifest.shotPlanApprovalState | NOT_VERIFIED |
| InputAssetVersion.providerProcessingAuthorized | false |
| InputAuthoritySubject.providerProcessingAuthorized | false |

Run.executionMode、publicationAllowed、原 Script/M6/M7/Shot/Beat、InputPlan、Candidate、Selection、Admission、AssetVersion、InputAppendAuthority、历史失败回执的内容、版本、Ref 和 Digest 均不覆盖、不回填、不迁移。禁止制作一份改过字段的历史投影传入旧验证器。

新的权限只能通过 V5 的 operation-specific Grant 验证边界使用。读取历史对象仍返回旧值；不能使用“旧 dispatchAllowed OR 任意 Grant 存在”的判断，也不能向通用输入 AssetVersion 验证器加入放宽分支。

### 2.2 唯一技术范围

本版本首个适用实例仅为 `SPIKE0-E3-SH09-VISIBLE-UPPER-BODY-HEAD-TURN-LOCKED-V2`：一个精确 Run、InputPlan、Shot、Beat 和锚帧版本；MICRO_MOTION / SINGLE_ANCHOR_I2V；MEDIUM_CLOSE_UP / LOCKED；最终 48 帧、24 fps、2 秒、704×1280，模型内部 length=49；仅沈知微可见，裴昀始终画外。[S9]

48 来自 Beat 的 [0,48)，不是 48-record 数据库投影。实例值进入经过独立批准的计划材料，不在通用业务逻辑中硬编码角色名、SH09 或 K2。首版拒绝多个目标、多个输入条目、通配符、批量授权和任意 fallback。

### 2.3 对 ADR-0014 的精确限定修订（R4）

以下条款仅在本 ADR 全文被明确 Accepted 后构成规范性例外，当前不生效。

ADR-0014 Decision 7 所述“原 ShotPlan 是本地结构表示、camera NOT_READY、不得提升合成测试 camera”为历史事实，完全保留。Decision 10 对一般生产要求完整 approved ShotPlan/camera lineage 的规则继续适用于其他 Run 和正常生产。

仅对 §2.2 的不可发布技术执行，允许 Project Lead 针对完整计划中精确 Shot/Beat、原动作、固定机位和输出规格，分别给出 `APPROVED_FOR_EXACT_TECHNICAL_SUBJECT` 的两项局部批准。这两项代替的仅是“本次技术动作必须先具有全局 ShotPlan/camera 生产验收”的前置要求，不创建全局批准对象，不将其读投影改为 READY/APPROVED，也不免除以下事实验证。

| 前置项 | 本次仍须验证的事实 | 不允许的替代方式 |
| --- | --- | --- |
| Project/Series/Episode/Plan/Script | 精确原版本、来源、Owner acceptance 和当前关系 | 技术标签、名称匹配或重建对象 |
| M6/M7/M8/M9 | 当前绑定、PASS 的一致性验证、精确 sourceSpan 和 Shot/Beat | Grant 自称全部通过 |
| 身份与参考 | 当前正式身份权威及参考版本对本次可见人物的绑定 | 仅凭图片“看起来一致” |
| 权利 | 适用的原权利事实/合法豁免事实，经原 Owner reader 判定且有证据引用 | 用新 permissions=true 补造权利 |
| Provider 策略 | 本次 SELF_HOSTED_SINGLE_GPU 的准确策略事实 | 把旧 input grant 作为 provider permit |
| 预算及成本 | 本次生成独立批准的限额、期限和可信上界 | 自动继承 E4 的 1000 元额度或 USD/0 占位 |
| runtime、模型、锚帧、workflow | 全部精确字节和版本绑定及当前性 | 只验证文件名、缓存证明或历史 PID |

`NOT_REQUIRED` 只有在适用的既有权威合同确实允许、由其正式 reader 返回且有精确范围证据时才合法；本文不创设新的 Rights/Identity/Provider 豁免。事实缺失仍拒绝。

该局部例外同时限定 ADR-0019 的 planning/dispatch 分离和 ADR-0021 对 manifest v2 的默认派发拒绝：没有满足本 ADR 的新 Grant 时仍按原合同拒绝；E3H 自己的 allowedOperations/excludedOperations 永不扩张。生成结果只是技术候选，不自动取得输出准入、Master、Export 或 publication。[S3][S10]

## 3. Owner、存储及批准材料来源（R1）

V5 Episode Production 唯一拥有 Grant/Terminal，使用现有 evidence journal。V4 唯一拥有 MediaJob/Attempt/lease/provider transport。Operator Application 只调用公开领域端口，不直接调用私有存储或执行 SQL。

只新增两个 append-only record kind：`GenerationDispatchGrant`、`GenerationDispatchGrantTerminal`。不新增数据库、表、DDL、队列、通用 RBAC、独立计费账本或第二资产权威。

### 3.1 选择：批准 bundle 内嵌完整计划包

首版不再使用“只有批准摘要、计划原文在未定义位置”的结构。Owner 管理的批准 bundle 闭集固定为：

```text
schemaVersion = v5.generation-dispatch-approval-bundle.v1
authorityRef : Ref
approvals : 恰好一个 { planPackage, approval }
```

`planPackage` 闭集恰为 `{plan, materials}`。`plan` 恰为 `{scope, subject, executionBinding, permissions, limits}`，各对象定义于 §4。`materials` 恰为 `{backendProfile, executionConfig, processIdentity, workflow, costBasis, prerequisiteEvidence}`，定义于 §5。

`approval` 定义于 §4.7，其中 `approvedPlanDigest=H(plan)`。计划中的每个材料引用必须与 materials 原文和摘要匹配；材料原文必须与重新读取的正式来源一致。缺少 plan 或 materials、只有 digest 的 bundle 必须拒绝。引用用于定位和验证，不用于推测或恢复缺失原文。

批准后的 issue 只使用选中的 bundle 元素：不能重新 prepare 后悄悄替换其 limits、profile、进程、workflow 或 costBasis。issue 可重新编译用于严格比较，但不能用新结果覆盖批准原文。

### 3.2 信任与配置边界

拟议配置对为 `CREATOR_GENERATION_DISPATCH_APPROVAL_BUNDLE_PATH` 与 `CREATOR_GENERATION_DISPATCH_APPROVAL_BUNDLE_SHA256`。配置缺失默认拒绝；部分配置、路径不安全、重复键、digest 不符或读取期间文件身份变化均拒绝。每次首次 issue、消费和发送前复核源字节；不将已持久化记录单独当成当前批准来源。[S3]

绝对路径、独立 pin、无符号链接及父路径核验沿用 E3H 的安全读取形状，但使用新类型、独立 resolver 和新操作语义。原始路径、密钥、密码及 token 不写入 Grant 的公开投影。

SHA-256 不证明人类身份。resolver 必须验证预配置 authorityRef 与外部可信流程中的 Project Lead 决定相对应；客户端不能自填 actorRef/role。设计方向批准、ADR Accepted、实现批准、普通认证、HumanSelection 和 InputAppendAuthority 都不是 `EXACT_SUBJECT_GENERATION_EXECUTION`。

本文不创建任何真实 bundle，也不确定任何真实生成额度、期限、seed 或已批准运行参数。

## 4. Grant 的完整规范性 schema

### 4.1 类型与摘要

所有以下对象均 closed-world，列出字段即为完整字段集。拒绝未知/缺失字段、重复键、非法 UTF-8、未知枚举、NaN/Infinity、bool 冒充 int、控制字符 Ref。除明确的分支 null 外，不允许空值占位。

`Ref` 使用 `[A-Za-z0-9][A-Za-z0-9._:-]{0,199}`；`Digest` 为 64 位小写 SHA-256；Git Object ID 单独为 40 位小写十六进制；`PinnedRef` 恰为 `{ref:Ref,digest:Digest}`。时间使用规范 UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`，保留六位小数；旧对象时间不因此改写。金额使用严格整数人民币分。

`H(x)` 为 UTF-8 canonical JSON 的 SHA-256：键排序、紧凑分隔、不作 Unicode 归一化、拒绝非有限数字。已存在对象继续用其原合同摘要；不得重封装或改变原浮点表示。新 plan 中的整数与浮点不得隐式相互转换；同一 profile 的 5 与 5.0 不是可以互换的已批准字节事实。[S7]

`scope` 恰为 `{workspaceRef,projectRef,seriesRef,episodeRef,productionRunRef}`。

```text
subjectDigest = H({workspaceRef,projectRef,seriesRef,episodeRef,productionRunRef,subject})
approvedPlanDigest = H(plan)
Grant.payloadDigest = H(Grant 去掉 payloadDigest)
Terminal.payloadDigest = H(Terminal 去掉 payloadDigest)
```

`plan` 的 executionBinding 绑定 materials 的全部内容摘要；materials 的顺序或展示时间不得提供替代批准。subjectDigest 保留 v1.0 的平铺 scope 写法，approvedPlanDigest 保留 H(plan)；不通过本次文档澄清变更已明确的摘要算法。

### 4.2 顶层与唯一槽位

```text
schemaVersion = v5.generation-dispatch-grant.v1
generationDispatchGrantRef : Ref
version = 1
workspaceRef, projectRef, seriesRef, episodeRef, productionRunRef : Ref
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

`slotDigest=H({workspaceRef,productionRunRef,creativeShotVersionRef,beatRef})`，后两项来自 subject；`generationDispatchGrantRef="generation-dispatch-grant-"+slotDigest`，recordVersion=1。槽位不含 seed、批准编号、幂等键、时钟或随机数。一个槽位最多一条 Grant，即使失效或被撤销也不得改 Ref 再发额度；换 Run/Shot/Beat 不是本次批准的替代入口。

### 4.3 subject

| 字段 | 类型/约束 |
| --- | --- |
| technicalTargetId | Ref，审计标签，不替代 scope 和下列身份 |
| productionRunPayloadDigest, manifestDigest | Digest，各指原对象 |
| scriptVersion | PinnedRef |
| m6Binding | 恰为 {m6BaselineSnapshotRef:Ref,m6BaselineCanonicalDigest:Digest,activationRevision:正整数,m6ConsumerBindingDigest:Digest} |
| consistencyValidationVersion | PinnedRef，原 reader 验证 CURRENT/PASS |
| executionMethodPlanVersion | PinnedRef |
| methodAwareInputPlanVersion | PinnedRef，完整 READY 链且恰好一个目标条目 |
| creativeShotVersion, actionExecutionBeat, visualExecutionRequirement | 各为 PinnedRef |
| inputAsset | 下述 InputAssetBinding |
| inputAppendAuthority | 恰为 {ref:Ref,digest:Digest,subjectDigest:Digest}，指原输入权威记录 |
| sourceAction | 恰为 {sourceSpan,sourceTextDigest:Digest} |
| cameraInstruction | 恰为 {framing:MEDIUM_CLOSE_UP,movement:LOCKED} |
| frameRange | 恰为 {startFrameInclusive:非负整数,endFrameExclusive:正整数} |
| outputConstraints | 恰为 {mediaKind:video,mediaType:video/mp4,width:正整数,height:正整数,durationFrames:正整数,frameRate:正整数} |
| executionClass, executionMethod | MICRO_MOTION / SINGLE_ANCHOR_I2V |

`InputAssetBinding` 恰为 `{assetRef,assetVersionRef,assetVersionDigest,inputRole,contentDigest,mediaType,byteSize,width,height}`；两个 Ref、两个 Digest、inputRole=ACTION_READY_ANCHOR、mediaType=image/png，其余为正整数。原 canonical authority 必须核验完整资产链，而非对脱敏 HTTP projection 重算摘要。

`sourceSpan` 恰为 `{scriptSceneRef:Ref,sourceField:ACTION,sourceIndex:非负整数,startOffsetInclusive:非负整数,endOffsetExclusive:正整数}`。从精确 ScriptVersion 解析原文本并核验长度和摘要；不得接受客户端改写动作。结束 offset/frame 必须大于起点。

输出 durationFrames 等于原帧区间差，必须为 4 的倍数，latent length=durationFrames+1；其他数值按原 output/profile 合同验证。§2.2 的实际规格是本次唯一批准候选范围，不自动放宽为所有合法数值。

### 4.4 executionBinding

```text
backendDecision : 原 v4.video-execution-backend-route-decision.v1 完整闭集
backendDecisionDigest : Digest = H(backendDecision)
executionProfile : PinnedRef
executionConfigDigest : Digest = H(materials.executionConfig)
executionCode : {coreCommit:GitId,coreTree:GitId,comfyuiCommit:GitId}
runtimeBinding : {instanceRef:Ref,processIdentityDigest:Digest,attestationFileSha256:Digest}
workflowDigest : Digest = H(materials.workflow)
costBasis : PinnedRef
prerequisiteEvidenceDigest : Digest = H(materials.prerequisiteEvidence)
```

executionProfile.ref/digest 必须等于 backendDecision.backendProfileRef/Digest，H(materials.backendProfile) 必须匹配该 digest。模型集合属于 profile.modelFiles，通过 profile 摘要绑定；不得在原 backendDecision 增加 modelFiles。[S7]

旧分支 backendDecision 的 runtimeAttestationRef/Digest 仍指原 v2 I2V attestation 的 Ref/payloadDigest；A14B 仅使用 §5.6 独立新类型。attestationFileSha256 是原文件字节摘要，三者不得混用。已有 E4 元数据 profile 不变；新的 executionProfile 必须是另行选定并批准的实际生成 profile。

executionCode 必须是将来经批准且包含新消费者的固定 commit/tree。f007ab3e 是审计基线，不具备新机制；文档 main 也不自动成为执行 pin。换代码、profile、模型、workflow、运行进程或成本依据，不得沿用不同内容的批准。

### 4.5 permissions

恰好五项，全部只属于新 Grant：

```text
dispatchAllowed = true
shotPlanScopeApproval = APPROVED_FOR_EXACT_TECHNICAL_SUBJECT
cameraScopeApproval = APPROVED_FOR_EXACT_TECHNICAL_SUBJECT
inputAssetProcessingAuthorized = true
inputSubjectProcessingAuthorized = true
```

没有部分权限并集或任意扩展键。两项局部批准须确实由 §4.7 的独立批准覆盖；它们不替代 §2.3 的事实证据，也不改变 E3H 的操作集合。

### 4.6 limits

```text
maxAttempts = 1
maxPromptSubmissions = 1
retryAllowed = false
fallbackAllowed = false
costCurrency = CNY
maxCostMinor : 正整数
executionTimeoutSeconds : 正整数
notBefore, expiresAt : UtcTime
stopPolicy = FAIL_CLOSED_NO_RESUBMISSION
```

notBefore < expiresAt；签发、消费以及 §8 定义的本地发送决策均须处于 [notBefore,expiresAt)。发送前完整 executionTimeoutSeconds 必须不超过剩余窗口。硬截止取实际开始时间加 timeout 与 expiresAt 的较早者，使用可信 UTC 与同进程单调时钟监测，时钟不可置信则停止。

这些值全部来自批准 bundle 的 plan.limits，不能由 decidedAt、backend maxCost 或旧预算推导；无默认金额或默认有效期。运行上限不等于租用账单最终上限，费用含义见 §5.4。

### 4.7 approval

```text
approvalRef, authorityRef, authorityDecisionRef, actorRef : Ref
authorityDecisionDigest : Digest
actorKind = HUMAN
actorRole = PROJECT_LEAD
approvalKind = EXACT_SUBJECT_GENERATION_EXECUTION
decision = APPROVED
approvedPlanDigest : Digest
approvalEvidenceRef : Ref
approvalEvidenceDigest : Digest
decidedAt : UtcTime
```

authorityDecisionDigest=H(approval 去掉自身 digest)。approvedPlanDigest 必须等于同一 bundle 条目 plan 的 H(plan)；approvalEvidenceRef/Digest 由独立 resolver 定位批准原件并验证来源。时间关系明确为 `approval.decidedAt <= Grant.createdAt`，且 `Grant.createdAt == EvidenceRecord.createdAt`，比较对象为 Grant 顶层与承载它的既有记录 envelope，二者取同一次服务端可信 UTC 读数并按 §4.1 编码。该读数在签发 gate 内、追加事务前取得，是签发记录时间，不冒充数据库实际 commit 时间；首次提交仍在事务临界区核对有效期。`issuanceEvidence` 不新增 createdAt。历史幂等重放保留原两处时间，不重新取 now 改写；过期或变更材料不得通过更新 decidedAt 重放获得许可。

### 4.8 issuanceEvidence

恰为 `{issuerServiceRef:Ref,requestDigest:Digest,approvalBundleSha256:Digest,snapshotTokens:SnapshotTokens,currentSubjectReadSet:CurrentSubjectReadSet,currentSubjectReadSetDigest:Digest}`。

CurrentSubjectReadSet 的原文内嵌在该不可变证据中，digest=H(readSet)，不是只保存一个无法审计前像的摘要。snapshotTokens 恰为 `{recordJournalHead:Digest,workspaceRecordJournalHead:Digest,evidenceRevisionToken:Digest}`，表示本次提交前的预期快照。现有 EvidenceRecord envelope 继续持有 sequence、idempotencyKey、recordVersion 等，不创建第二日志。

## 5. 批准材料、摘要前像与确定性编译（R3）

### 5.1 六份材料与绑定规则

| materials 字段 | 完整对象及来源 | 与 plan 的关系 |
| --- | --- | --- |
| backendProfile | 原 backend resolver.profile 返回：旧 `v4.comfyui-i2v-backend-profile.v1` 或 §5.6 独立 A14B 类型 | H(profile)=executionProfile.digest=backendDecision.backendProfileDigest |
| executionConfig | 下述 `v5.generation-dispatch-execution-config.v1`，服务端配置 reader 的安全投影 | H(config)=executionConfigDigest |
| processIdentity | 下述 `v5.generation-dispatch-runtime-process.v1`，受信任本地 runtime reader 返回 | H(identity)=runtimeBinding.processIdentityDigest |
| workflow | 固定代码纯编译出的 ComfyUI API graph，按 §5.5 验证完整精确值 | H(graph)=workflowDigest |
| costBasis | 下述 `v5.generation-dispatch-cost-basis.v1`，Owner 审查材料 | ref/digest=executionBinding.costBasis |
| prerequisiteEvidence | 下述五项固定权威引用集合 | H(set)=prerequisiteEvidenceDigest |

所有材料都在同一个 planPackage 中可取得；issue/consume/send 前须核对正式 reader 返回的实际内容，不能只相信包内自报。公开 ADR 不保存真实配置、密码或批准原件；计划包属于受控操作材料。

### 5.2 executionConfig 的闭集

`v5.generation-dispatch-execution-config.v1` 恰含：

```text
schemaVersion
configRef : Ref
configRevision : 正整数
backendRef : Ref
baseUrlDigest : Digest
credentialSourceRef : Ref
credentialBindingRevision : 正整数
sourceRoot, inputRoot, modelRoot, artifactRoot : PathBinding
launchConfiguration : LaunchConfiguration
launchConfigDigest : Digest
connectionTimeoutMs, requestTimeoutMs, historyTimeoutMs, postprocessTimeoutMs : 正整数
coordinationMode = SINGLE_HOST_SINGLE_CONTROL_PROCESS
transportPolicy : {maxPromptSubmissions:1,postRetryAllowed:false,redirectAllowed:false,fallbackAllowed:false}
```

`PathBinding` 恰为 `{locatorRef:Ref,absolutePathDigest:Digest}`。absolutePathDigest=H(正式 reader 返回的绝对规范路径字符串)；只读取得 resolved path 且无符号链接漂移，未创建目标目录。baseUrlDigest=H(已解析并规范化的 base URL 字符串)：scheme/host 小写、显式有效端口、无 userinfo/query/fragment、根路径统一为 `/`；不能从客户端给出的 URL 取得权限。连接及总请求 deadline 由 transport reader 核验。

launchConfiguration 恰为 `{argv,environmentProjection}`；argv 是实际启动的完整参数字符串数组，environmentProjection 是按 name 排序、name 不重复的 `{name,value}` 数组。name 必须匹配 `[A-Z_][A-Z0-9_]*`，value 为不含 NUL 的字符串。该数组覆盖受控 ComfyUI 启动时的完整环境，不接受隐式继承；实际有影响的参数或环境项未入包即拒绝。原始密钥不允许进入这一进程环境；V4 凭据由独立 resolver 解析，因此不能以“脱敏”为名静默删除影响运行的环境值。

launchConfigDigest=H(launchConfiguration)，与 processIdentity 中同名摘要相等。credentialSourceRef 和 credentialBindingRevision 绑定 V4 的凭据来源身份，不放入原密码/bearer token。该配置材料是私有审批材料，不原样发布 Git。

modelRoot 指模型源文件定位，inputRoot 指 ComfyUI staging 根，artifactRoot 指既有候选产物根；互换映射即配置变更。上述 timeout 覆盖的顺序阶段最坏时长不得超过 plan.limits.executionTimeoutSeconds；不得在实际执行时另用未批准的更大超时。

这是一份安全配置投影，不激活执行配置、不存储 secret。原始 argv/非敏感环境的校验材料由同一受控 reader 提供给 prepare 并留在材料保管范围，不另建持久化权威。

### 5.3 processIdentity 和 CurrentSubjectReadSet

`v5.generation-dispatch-runtime-process.v1` 恰为：

```text
schemaVersion
instanceRef : Ref
hostBootIdDigest : Digest
pidNamespaceIdDigest : Digest
comfyuiPid : 正整数
processStartTicks : 规范无前导零十进制字符串
comfyuiCommit : GitId
launchConfigDigest : Digest
```

hostBootIdDigest=H(可信本地 OS 的 boot ID 字符串)，pidNamespaceIdDigest=H(该进程 PID namespace 的稳定身份字符串)。PID 与 start ticks 共同区分复用；跨重启/namespace/进程变化均失配。reader 必须实际核对监听端口所有者及进程，不接受客户端自报。GPU idle 数、heartbeat 时间和普通观察时刻不参与此摘要。原 attestation 文件及其模型/设备事实另按原合同校验。

`CurrentSubjectReadSet` 恰为 `{schemaVersion:v5.generation-dispatch-read-set.v1,scope,phase,coordinationEpoch,objects,selectors}`。phase 关闭集为 PREPARE / ISSUE / CONSUME / SEND。coordinationEpoch 是 §8 单控制进程启动身份的 Digest，不是新的数据库版本。

objects 元素恰为 `{owner:Owner,objectKind:Ref,objectRef:Ref,objectDigest:Digest}`，按 `(owner,objectKind,objectRef)` 排序且键不重复。selectors 元素恰为 `{owner:Owner,selectorKind:SelectorKind,scopeRef:Ref,selectedRef:Ref,selectedDigest:Digest,coordinationRevision:非负整数}`，按 `(owner,selectorKind,scopeRef)` 排序且键不重复。

Owner 关闭集为 `V5_PROJECT_CONTEXT / V5_SERIES_EPISODE / V5_SERIES_PLANNING / V5_EPISODE_PRODUCTION / V5_SCRIPT / V5_M6 / V5_IDENTITY / V5_RIGHTS / V5_PROVIDER_POLICY / V4_BACKEND_CONFIG / OWNER_APPROVAL / RUNTIME_PROCESS`。新增的三个标签分别映射已有 ProjectPublicBoundary、SeriesEpisodePublicBoundary、SeriesPlanningPublicBoundary；它们是读集中的来源标识，不创建新业务 Owner、存储或 canonical selector。[S11]

SelectorKind 关闭集为下表的 16 个值。各行同时规定正式来源、scopeRef 及必须参与 gate 的最低写入范围。表中的“当前”只表示正式 reader 重新解析的事实；没有原生 selector 的对象用版本/状态观察项表示，不伪造原数据库选择指针。

| SelectorKind | Owner / scopeRef | 正式读取与 selectedRef / selectedDigest | 必须参与 gate 并失效该行计数的写入 |
| --- | --- | --- | --- |
| CURRENT_PROJECT | V5_PROJECT_CONTEXT / projectRef | ProjectPublicBoundary.get_project 与 build_context 的 project 完整原记录须一致；selectedRef=projectRef，selectedDigest=H(原 project 记录)；验证原 version/status/contentProfile/aspectRatio/series 关系 | 该 Project 的 create/archive、归属/配置/状态变化；CREATE_PROJECT_FOUNDATION 或 canonical registration 的 Project 参与写入 |
| CURRENT_SERIES | V5_SERIES_EPISODE / seriesRef | SeriesEpisodePublicBoundary.get_series，与 build_context 的 series 原记录一致；selectedRef=seriesRef，selectedDigest=H(原 series 记录)；验证原 version/status/归属 | Series create/delete、creative plan 确认及影响本 Series 的版本/状态/关系写入；foundation/registration 参与写入 |
| CURRENT_EPISODE | V5_SERIES_EPISODE / episodeRef | SeriesEpisodePublicBoundary.get_episode，与 build_context 的 episode 原记录一致；selectedRef=episodeRef，selectedDigest=H(原 episode 记录)；验证 version/episodeNumber/creativePlanRef/seriesRef | Episode create/delete、编号/creativePlan/归属/版本变化及父 Series 删除；foundation/registration 参与写入 |
| CURRENT_CONFIRMED_SERIES_PLAN | V5_SERIES_PLANNING / seriesRef | SeriesPlanningPublicBoundary.get_workspace：plan.status=confirmed，selectedRef=plan.confirmedSeriesPlanVersionRef；selectedDigest=H(versions 中唯一匹配的原完整版本) | confirm_candidate、confirm_candidate_idempotently、create_manual_version、create_episode_plan_item_binding_version、confirm_version 对该计划的实际变更；生命周期删除/失效 |
| CURRENT_EPISODE_PLAN_BINDING | V5_SERIES_PLANNING / episodeRef | 同一已确认 M5 版本内唯一 episodePlanItemBindings 与 episodePlanItems；selectedRef=episodePlanItemRef；selectedDigest=H(下述 M5BindingObservation) | 该 Episode 的绑定版本追加/确认、计划确认指针切换、对应条目或 Episode 关系变化；与上一行同时失效，不由 M6 计数代替 |
| CURRENT_CONFIRMED_SCRIPT | V5_SCRIPT / episodeRef | 原 Script reader 的已确认版本及原摘要，连同 prerequisiteEvidence.scriptOwnerAcceptance 的原 authority 校验 | Script 确认/恢复/当前选择及 acceptance 变更；原事实是否变化仍按 reader 判定 |
| ACTIVE_M6_BINDING | V5_M6 / episodeRef | 原 M6 正式 reader 解析的 active baseline/binding，与 subject.m6Binding 及其原摘要一致 | M6 activation、binding 及相依选择变更 |
| CURRENT_M7_PASS | V5_EPISODE_PRODUCTION / productionRunRef | 原 M7 validation/currentness 正式读取边界，精确版本/PASS，不从字符串自报取得权威 | 新验证/失效、相关当前选择变化 |
| CURRENT_METHOD_PLAN | V5_EPISODE_PRODUCTION / productionRunRef | 原 M8/M9 方法计划正式 reader，与 subject.executionMethodPlanVersion 及 Shot/Beat/requirement 原链一致 | M8/M9 当前计划、Shot/Beat/requirement 选择或版本变化 |
| CURRENT_INPUT_PLAN | V5_EPISODE_PRODUCTION / productionRunRef | 原 M10 InputPlan reader 与 canonical input AssetVersion/Admission/InputAppendAuthority reader 验证完整 READY 链 | InputPlan 当前选择及会影响所引用输入准入/权威有效性的变更；不修改不可变输入版本 |
| CURRENT_IDENTITY_REFERENCE | V5_IDENTITY / episodeRef | 原 identity/reference authority reader，包含 prerequisiteEvidence.identityReferenceEvaluation 及精确引用链 | 相关身份锁、参考版本/绑定、评估或 authority 来源变更 |
| CURRENT_RIGHTS_EVALUATION | V5_RIGHTS / productionRunRef | 原 Rights reader 对本 scope 的正式评估及 prerequisiteEvidence.rightsEvaluation；无合法 reader 时拒绝 | 所依赖权利/合法豁免评估、有效性或来源变更 |
| CURRENT_PROVIDER_POLICY | V5_PROVIDER_POLICY / productionRunRef | 原 policy reader 与 prerequisiteEvidence.providerPolicyEvaluation 精确匹配 | 所依赖 Provider 策略、评估或来源变化 |
| CURRENT_BACKEND_CONFIG | V4_BACKEND_CONFIG / productionRunRef | 原 backend/profile/config reader；同时验证材料 costBasis、costReview 的正式来源及有效性；全部原文进入 objects | registry/profile/config、凭据绑定版本、路径映射、成本材料/审查来源的切换；任何一个变化均失效此行 |
| CURRENT_OWNER_APPROVAL | OWNER_APPROVAL / productionRunRef | §3.2 独立批准 resolver 的精确 decision/包 pin；不等同于 Script acceptance 或成本批准 | 本次生成批准来源/pin 切换或可信性变化；消费前撤销另经 Terminal 事务 |
| CURRENT_RUNTIME_PROCESS | RUNTIME_PROCESS / productionRunRef | §5.3 可信本地 runtime reader 的实例/进程/commit/启动身份，与批准材料一致 | 受控 runtime/locator/配置切换；非受控退出、PID 复用或文件漂移由重读拒绝，不伪称 OS 事件都经 gate |

`M5BindingObservation` 是只读审计前像，闭集为 `{seriesPlanRef,seriesPlanVersionRef,planVersion,versionNumber,episodeRef,episodePlanItemRef,binding,planItem}`。前四项取同一次 get_workspace 的 plan 及已确认版本；binding、planItem 分别是该版本内唯一匹配的原完整对象。没有原生摘要的 Project/Series/Episode 或 M5 绑定仅计算此观察摘要，不写回原对象、不替代既有 canonical digest；所有原版本/状态还须通过原 Run 的完整 upstreamSnapshot/upstreamDigest 当前性验证。缺对象、重复匹配、status 不满足、上下文和正式 reader 不一致均拒绝，不填 null、伪版本或“默认 current”。[S11]

objects 必须覆盖 subject 引用的全部原对象及 profile/config/cost/证明/前置证据，并包含上述 Project、Series、Episode、原 M5 plan/已确认版本/绑定及条目；ISSUE/CONSUME/SEND 还包含选中的批准原件。PREPARE 恰含表中排除 CURRENT_OWNER_APPROVAL 的 15 行，其他三个阶段恰含 16 行，每行 scopeRef 按表定位。R1 的六材料与 plan 摘要不变，新增 readSet 观察项只进入签发/消费证据，不制造审批依赖循环。

各原 Owner 的既有 Ref/Digest 沿用原验证器；表中新定义的观察摘要只是协议前像，不给原接口增加字段。其余既有 selector 沿用 v1.1 所列原 Owner 映射，复合依赖须全部经原 reader 校验、全部计入 objects；不能仅验证代表项就忽略 Script acceptance、InputAppendAuthority、成本或其他前置证据。某一既有 authority reader 实际不存在或无法提供完整证据时拒绝，本文的枚举标签不补造该能力。

每个计数键严格为 `(workspaceRef,owner,selectorKind,scopeRef)`，coordinationRevision 在当前 epoch 内初始化为 0。表中相关写入先取得同一个 gate；成功且确认改变当前对象/选择/版本/状态，或提交结果未知时，按受影响行递增并在释放 gate 前完成失效。允许对同 workspace 的相关行保守多失效，不得漏失效；纯读及确认零写入的幂等 replay 不递增。M5 相关实际写入至少失效对应的两行；创建/删除或跨域参与写入必须由其外层 lifecycle/registration/foundation 协调调用通知全部受影响行，不能只装饰 public 单一入口而漏掉内部参与路径。[S11]

只追加不改变选择的 Grant/Terminal 历史、一般 evidence、V4 正常 heartbeat 不增加这些 source selector 计数；它们仍分别受 journal CAS 或 Job/lease 核验。未知源写入使对应 workspace fence 进入拒绝，不能通过一次“读到旧值”恢复原 capability；独立恢复确认后旧 continuation 仍作废，并重新建立受控 epoch。启动时逐个核验 source-reader / 所有 writer / 计数键的覆盖：发现表外真实依赖、缺失 writer hook 或未受控写入，返回 CURRENTNESS_FENCE_UNAVAILABLE，不允许把 M5 映射到 M6、 silently 增删枚举或继续发送。

跨控制进程重启不比较进程内计数来声称永久 CURRENT：旧 SendCapability 全部失效；未消费 Grant 可经正式 reader 重验、派发幂等恢复及新 epoch 快照继续接受检查，但不得恢复旧 Attempt 或旧发送能力。选择 A→B→A 仍递增，因此 S05 在 L1→L2 期间出现任何上述相关变更即不发送；S03 的 issue 重读到事务提交期间由同一 gate 阻止参与 writer 交错，gate 覆盖不能证明则拒绝。上述都是待实现合同，不是本次运行验证。

### 5.4 costBasis 与 prerequisiteEvidence

`v5.generation-dispatch-cost-basis.v1` 恰为：

```text
schemaVersion
costBasisRef : Ref
currency = CNY
sourceEvidence : 非空 PinnedRef 数组，按 ref 排序，无重复
reviewedByAuthorityRef : Ref
reviewDecision : PinnedRef
validFrom, validUntil : UtcTime
costScope = APPROVED_OPERATION_WINDOW_ONLY
fixedCostMinor : 非负整数
computeUnitSeconds : 正整数
computeUnitCostMinor : 非负整数
computeMinimumUnits : 非负整数
storageBoundMinor : 非负整数
transferBoundMinor : 非负整数
otherBoundMinor : 非负整数
roundingMode = CEILING_EACH_COMPONENT
billingResponsibility : {powerStopOwnerRef:Ref,dataRetentionOwnerRef:Ref,continuingChargesEvidence:PinnedRef}
payloadDigest : Digest
```

payloadDigest=H(对象去掉 payloadDigest)，executionBinding.costBasis.digest 取此值。最大批准操作费用的核算式固定为：fixedCostMinor + max(computeMinimumUnits,ceil(executionTimeoutSeconds/computeUnitSeconds))*computeUnitCostMinor + storageBoundMinor + transferBoundMinor + otherBoundMinor。须不超过 limits.maxCostMinor，也不超过 backendDecision.maxCostMinor，币种一致；validUntil 覆盖计划执行期限。

sourceEvidence 必须支撑费率、最低单位及保守存储/传输/其他费用上界；不得用显示的一笔部分账单推测完整费率。确有预付且无新增计算费时可以为 0，但必须有相应证据，不使用零成本占位。continuingChargesEvidence 明确任务窗口之外的租用/存储费用和人工停止责任；该费用不会因停止 ComfyUI 自动停止，也不宣称整个账户费用被 Grant 硬限制。无法给出可信任务上界或剩余额度时，真实签发拒绝。

prerequisiteEvidence 恰为 `{scriptOwnerAcceptance,identityReferenceEvaluation,rightsEvaluation,providerPolicyEvaluation,costReview}`，各值为 PinnedRef，由对应正式 authority reader 解析，costReview 须等于 costBasis.reviewDecision。原证据 schema 和合法状态由既有 Owner 决定，本文不新增伪造的“全部通过”证据类型。对象原文须可通过受控证据保管位置取得，引用缺失或来源无法独立核实即拒绝。

### 5.5 requestRef / workflow 的确定性有向依赖

首先从 plan 的 subject 和已选 profile/code/config 形成 `RequestIdentityMaterial`，其字段恰为：

```text
schemaVersion = v5.generation-dispatch-request-identity.v1
scope
subjectDigest
backendProfileRef
backendProfileDigest
executionConfigDigest
executionCode
outputConstraints
workflowCompilerRef
```

旧分支 workflowCompilerRef=`comfyui-i2v-api-graph-v1`，A14B 分支使用 §5.6 的独立标识；实现字节均由 executionCode 固定。`generationRequestRef="generation-request-"+H(RequestIdentityMaterial)`；`generationRequestVersionRef=generationRequestRef+":v2"`。不得使用时钟、PID、随机 UUID、Grant Ref/Digest、approvedPlanDigest 或 Terminal 生成 requestRef。

固定代码的纯 compiler 接收完整原 sourceAction 文本、cameraInstruction、source PNG contentDigest、profile.parameters、profile.modelFiles、outputConstraints、generationRequestRef。输入 staging 名称严格为 `acs-k2-m11/<contentDigest>.png`；SaveVideo 前缀严格由 generationRequestRef 构造，不依赖当前时间。正面提示词沿用确定的 sourceText 加 framing/movement 组合；负面提示词和全部采样数值来自选定 profile。length=durationFrames+1。所有其他节点参数必须由固定 compiler 原样、显式输出，不接受执行期默认值补齐。[S8]

compiler 只返回 API graph 数据，不能调用现有有写入副作用的 staging/generate 方法。graph 按固定 compiler 输出整体相等验证；没有接受额外节点/输入键的通用 graph 审批入口。图内每个模型文件、LoadImage、采样参数、尺寸、帧数、fps、codec/format 都须与计划和原节点合同匹配。

依赖顺序固定为：原事实与材料 → request identity → requestRef → workflow → workflowDigest → plan → approvedPlanDigest → 独立 approval → Grant → 带 Grant 的 request/envelope → Terminal。workflow 不包含 Grant，因而无 Grant/workflow/request 摘要循环；实际 POST 体中的 API graph 必须与批准 graph 整体相等，client correlation 元数据不进入 graph，也不能影响生成语义。

### 5.6 v1.3 狭义 A14B 兼容增量

本节来自 Project Lead 对 R2 第 3 节的明确批准。它只增加 profile、compiler、runtime 与技术结果的版本分派，不重开 Package 1/2/3，不改变 Grant/Terminal、原 request/envelope 版本、槽位、permissions、费用上限/时钟、snapshot/CAS、L1/L2、共享 gate、存储独占、一次性能力及无重试/无 fallback 合同。

#### 5.6.1 类型判别与旧分支保持

- 新 profile：`v4.comfyui-a14b-i2v-backend-profile.v1`。
- 新 backend adapter identity：`v4.comfyui-wan22-a14b-image-to-video.v1`。
- 新 compiler identity：`v4.generation-dispatch-a14b-compiler.v1`。
- 新 runtime attestation：`v4.comfyui-a14b-runtime-attestation.v1`，capabilityMode 为 `A14B_IMAGE_TO_VIDEO`。

profile 的顶层仍恰为 schemaVersion、parameters、modelFiles；新 parameters 与六角色模型项分别严格封闭。分派依据已摘要绑定的显式 schema/adapter identity，不靠模型名、模型数量或调用方 bool 推断。旧三模型 schema 不接受六模型，新 schema 不接受三模型；旧 attestation 不被重新封装为新硬件证明。旧固定输入的 request identity、graph、digest 和重放保持原值。

六角色必须唯一完整：high-noise expert、low-noise expert、text encoder、VAE、high-noise LightX2V LoRA、low-noise LightX2V LoRA；名称、摘要、字节数与 expert/LoRA 配对均有明确材料。模型只属于 profile，不复制到 backendDecision 形成第二权威。只支持单 GPU、MICRO_MOTION / SINGLE_ANCHOR_I2V。

#### 5.6.2 精确提示词、拓扑和原生输出

新 parameters 绑定 compiler/template identity、材料证明分类、固定 ComfyUI commit、完整正负 prompt、seed、总 steps、CFG、采样器/调度器、两段模型/LoRA 配对及 strength/model shift/start/end/noise/leftover 设置、输入 imageName/contentDigest、原生输出节点/前缀/规格、后处理规则和资源要求。缺少字段不补执行期默认值。

原 sourceAction/sourceSpan/sourceTextDigest 继续由 ScriptVersion 正式 reader 核对；英文 prompt 不是剧本事实。新正面 prompt 不再追加旧机位 suffix，其与 subject 的对应关系必须由独立冻结材料及实际生成批准覆盖。

编译器只返回固定拓扑的完整 API graph；验证必须与编译器预期图整体相等，而非仅计算任意输入 graph 的 hash。双专家 high→low latent 传递、各自 LoRA/conditioning/noise 语义及输出节点都受闭集约束。图中不出现 Grant/Terminal/approvedPlanDigest；新增 compiler identity、profile、模型、prompt、采样或后处理变化改变 request/plan 摘要，不允许沿用不同内容的批准。

原生输出是 49 帧 PNG 序列，独立于最终 48 帧、24fps、2 秒、704×1280 MP4。批准前像明确 `KEEP_FIRST_48_DROP_LAST`：保留原索引 0..47，排除 48。原生文件、来源顺序、派生产物各自记录摘要；有损编码输出不冒充与原 PNG 字节相同。§5.5 的旧 LoadImage 路径、sourceText suffix、SaveVideo 布局不强加给新分支；新输入定位和输出前缀必须被显式材料绑定。

原始冻结材料不足时，固定工程模板只能标记 TEST_ONLY，不能冒充 SH09 模板。它只能在绑定为 `TEST_ONLY_LOOPBACK` 的隔离工程装配中使用，不能绑定正常生产 backend。SH09 exact binding 保持缺证据，生产装配缺原件及批准则拒绝。模板测试通过不是当前硬件证明。

#### 5.6.3 运行时、请求与结果边界

新 runtime 类型必须验证完整六模型及各自来源、required nodes/inputs、设备资源、固定代码、进程/启动配置，以及与已批准 profile 的精确相等。原件 reader 的受信来源要求不变，文件原 SHA、canonical JSON digest、模型集合 digest、业务绑定 digest、包 SHA 分列；自报 pin 不能成为现场证明。

新增独立 live request/submission/result 类型不得放宽旧 TEST_ONLY schema。live 默认不装配；endpoint 只由受信内部装配提供并与原 executionConfig.baseUrlDigest/runtime/backendDecision 核对。import、构造、open_exchange 无 DNS/socket/文件读取/后台启动；唯一 commit_request_once 承担有界连接和首次写入，response/history/artifact/postprocess 在 gate 释放后进行。

写入证据区分未进入写路径、可证明零字节、可能已写、完整本地写入；partial write 或无回执不得因为本地 submission 变量尚空就推断未提交。局部 transport submission ref 与 Provider prompt ID 分开，收到 prompt ID 不等于生成完成。严禁重试 POST、跟随重定向、fallback、上传输入或管理性 POST；未知状态仍消耗原能力。

技术结果继续使用原 Job/Attempt、Candidate、artifact commit intent、durable replace、probe 与恢复路径。未知实际费用/设备/GPU 使用在独立新结果类型中保留未知，不能沿用 Fake 的 0/false；旧结果类型继续严格校验。只读结果恢复不重新 claim/consume/send，不自动接纳 AssetVersion、Master、Export 或 publication。

本节不批准任何真实配置、采集器、运行时证明、正式数据库、真实 Grant、GPU 或 /prompt。当前本地实现及证据状态由当前里程碑中的精确候选记录投影，Owner 验收与发布另行授权。

### 5.7 v1.4 R3 原图、历史前像和完整编码增量

2026-09-13 Project Lead 明确授权
`ACS-SH09-EXACT-OFFLINE-BINDING-AND-RUNTIME-SEAM-R3-20260913` A01—A06
及本节狭义规范增量。仅允许本地实现、CPU/fixture-owned loopback 验证和候选提交；
不是 Camera 候选、精确绑定或生成批准。v1.2 Grant/Terminal/CAS、readSet、L1/L2、
lease/revoke/clock、原 Job/Attempt、准入及发布权限保持不变。

- 原 v1 TEST_ONLY profile/compiler/runtime/request/编码继续闭集，不能重解释旧摘要。
  新 profile `v4.comfyui-a14b-i2v-backend-profile.v2`、compiler v2、adapter v2
  重建固定原图 16 节点，输出 41；CLIPLoader 不补写原件未填写的 device。
  不能以任意图或任意 hash 代替完整重建比较。
- 原 Camera 句到 LOCKED 的单指针变化属于待复核候选。原件不变；新 profile、workflow、
  request identity 和计划摘要重新计算，旧批准不可复用。原件来源候选被 Grant 边界拒绝，
  仅明确 TEST_ONLY 的隔离材料可进入当前 CPU 验证路径。
- Runtime v2 分离 ComfyUI 版本 0.35.0 与 commit；历史前像映射使用独立
  `v4.a14b-historical-source-map.v1`，不是当前 attestation。argv U+001F 原 hash、
  原环境字典、原模型数组顺序与新合同 canonical 前像均单独保存并验证；不将历史
  PID、启动时刻或模型元数据升级为当前进程/权重实测证据。
- request v2 绑定完整 `v4.a14b-native49-encoding.v2`：49 张原帧中保留 0—47、
  丢弃 48；704×1280、48 帧、24fps；libx264/mp4/yuv420p/CRF16。
  原命令省略的 preset/movflags 以固定工具观察解析为显式 medium/0 候选；
  显式 threads=1 是新增可复现性候选，不伪称原件指定。工具 SHA、索引映射及
  全部参数在发送前被 profile/plan/request 摘要绑定，结果 derivation v2 再验证。
  原 native 序列摘要和 MP4 摘要分开。安全临时目录、-nostdin、file/pipe、-n 保留。
- 构造/import/open 不联网；现有受控 composition 默认关闭，不创建第二队列、数据库、
  Provider 或自动启动入口。fixture 仍不得指向 8188 或真实服务。未知费用/设备不填零。
  发布、现场只读采集、配置部署、真实 Grant 和一次 /prompt 各需后续单独授权。

## 6. Operator 与内部端口闭集（R1、R3）

以下是未来实现的领域合同，不是本轮可执行命令。首版无新 Frontend 或公共 HTTP 写路由；Operator 身份来自可信本地操作边界，不能由请求 actor/role 字段自报。

### 6.1 prepare / issue / inspect

prepare 请求恰为 `{workspaceRef,productionRunRef,methodAwareInputPlanVersionRef,creativeShotVersionRef,beatRef,inputAssetVersionRef,backendRef,executionConfigRef,costBasisRef,limits}`。Ref 类型按 §4.1；limits 是明确选择的待批准候选，不含隐式默认值。其余 scope 从 Run 解析。正式 reader 取得原事实/配置/成本/前置证据/runtime，纯 compiler 建图，形成 planPackage；不得启动服务或补写任何来源。

prepare 成功返回恰为 `{schemaVersion:v5.generation-dispatch-prepare-result.v1,operation:PREPARE_ONLY,planPackage,subjectDigest,approvedPlanDigest,currentSubjectReadSet,snapshotTokens,sendPermission:NONE}`。没有 Grant、批准决定或消费额度。

issue 请求恰为 `{workspaceRef,productionRunRef,methodAwareInputPlanVersionRef,creativeShotVersionRef,beatRef,inputAssetVersionRef,backendRef,expectedSubjectDigest,expectedApprovedPlanDigest,authorityDecisionRef,idempotencyKey,snapshotTokens}`。expected* 仅作比较；通过独立 resolver 选择批准 bundle 的唯一条目，再读取其中 planPackage，不接受客户端提交 grant/permissions/actor/旧五字段。

issue 成功返回恰为 `{schemaVersion:v5.generation-dispatch-issue-result.v1,operation:ISSUE,grant,recordReplay:bool,eligibility,sendPermission:NONE}`。相同请求重放返回原记录。即使 eligibility=ELIGIBLE_FOR_CONSUMPTION，也不允许由 issue 调用链发送。

inspect 请求恰为 `{workspaceRef,productionRunRef,generationDispatchGrantRef}`；返回恰为 `{schemaVersion:v5.generation-dispatch-inspect-result.v1,operation:INSPECT,grant,terminal,eligibility,sendPermission:NONE}`，尚无 Terminal 时 terminal=null。

eligibility 关闭集为 `ELIGIBLE_FOR_CONSUMPTION / NOT_YET_VALID / EXPIRED / CONSUMED / REVOKED / SOURCE_CHANGED / APPROVAL_UNAVAILABLE / CONFIG_CHANGED / FENCE_UNAVAILABLE`。它是当前计算结果，不写回 Grant，更不是项目阻塞解除决定。

### 6.2 consume / revoke

consume 只能由 §8 的同一受控进程内 V4 worker 通过类型化端口调用。请求恰为 `{workspaceRef,productionRunRef,generationDispatchGrantRef,generationDispatchGrantDigest,mediaJobRef,attemptRef,workerRef,expectedJobRevision,expectedLeaseTokenDigest,idempotencyKey,snapshotTokens}`。实际 worker 进程/线程身份由端口上下文提供；不接受客户端自报身份当作绑定。V5 必须向正式 V4 reader 核对真实 Job/Attempt/lease。

consume 的可序列化回执恰为 `{schemaVersion:v5.generation-dispatch-consume-result.v1,operation:CONSUME,terminal,recordReplay:bool,eligibility:CONSUMED,sendPermission:NONE}`。端口的进程内返回结构恰为 `{receipt,continuation}`：只有本次新 Terminal 明确提交成功时 continuation 才是不可序列化、一次性 `SendCapability`；重放、历史 GET、超时恢复均为 null。SendCapability 不是 JSON token，不写数据库/文件，不作为 HTTP 响应或 IPC 字段返回，不允许重建。

revoke 请求恰为 `{workspaceRef,productionRunRef,generationDispatchGrantRef,generationDispatchGrantDigest,authorityDecisionRef,idempotencyKey,snapshotTokens}`；通过独立撤销 resolver 取得 §7.3 的批准。成功返回恰为 `{schemaVersion:v5.generation-dispatch-revoke-result.v1,operation:REVOKE,terminal,recordReplay:bool,eligibility:REVOKED,sendPermission:NONE}`。

上述动作失败返回统一闭集 `{schemaVersion:v5.generation-dispatch-error.v1,operation,code,writesCommitted:0,sendPermission:NONE}`。code 关闭集为 `INVALID_CLOSED_SCHEMA / APPROVAL_UNAVAILABLE / APPROVAL_PLAN_MISMATCH / SOURCE_CHANGED / CONFIG_CHANGED / RUNTIME_CHANGED / COST_BOUND_UNVERIFIED / OUTSIDE_VALIDITY_WINDOW / CURRENTNESS_FENCE_UNAVAILABLE / SNAPSHOT_CHANGED / IDEMPOTENCY_CONFLICT / GRANT_SUBJECT_ALREADY_RECORDED / TERMINAL_ALREADY_RECORDED / ALREADY_CONSUMED / ALREADY_REVOKED / ATTEMPT_OR_LEASE_CHANGED / SCOPE_MISMATCH / PERSISTENCE_UNAVAILABLE`。

写入结果未知不能返回 writesCommitted=0；必须返回独立的 `{schemaVersion:v5.generation-dispatch-indeterminate.v1,operation,code:COMMIT_OUTCOME_UNKNOWN,sendPermission:NONE}`，随后只读查原幂等记录。消费结果未知永不返回新 SendCapability。

## 7. 两个不可变记录的原子性与 CAS

### 7.1 签发事务

在 §8 的协调临界区内重新验证 source、配置、批准、期限和费用。在既有 journal 的一次事务中比较 snapshotTokens 三值、确定唯一槽位与幂等冲突，追加恰好一条 Grant。批准投影、五项局部权限和 issuanceEvidence 都在同一 payload 提交；任一检查失败零记录，不创建 Job/Attempt，不发送网络请求。[S5]

```text
issueRequestDigest = H({
  command: issue请求去掉idempotencyKey和snapshotTokens,
  resolvedApprovalDecisionDigest,
  approvedPlanDigest
})
```

相同幂等键但不同语义拒绝；不同键同槽位拒绝；首次提交任一 token 不符拒绝，不自动刷新 CAS 再试。真正相同已提交请求可返回原 Ref/createdAt/digest，重放无需制造新 record；原对象 CURRENT、批准有效及 eligibility 另行计算。查历史不能变成新签发或发送资格。

### 7.2 Terminal schema

```text
schemaVersion = v5.generation-dispatch-grant-terminal.v1
grantTerminalRef, generationDispatchGrantRef : Ref
generationDispatchGrantDigest : Digest
workspaceRef, productionRunRef : Ref
kind = CONSUMPTION_COMMITTED | REVOKED
attemptBinding : AttemptConsumptionBinding | null
revocationApproval : VerifiedRevocationApproval | null
requestDigest : Digest
snapshotTokens : SnapshotTokens
createdAt : UtcTime
payloadDigest : Digest
```

`grantTerminalRef=generationDispatchGrantRef+":terminal"`，recordVersion=1。同 Grant 最多一条 Terminal。CONSUMPTION_COMMITTED 分支 attemptBinding 非空且 revocationApproval=null；REVOKED 分支反之。Grant 永不增加 used/state/remainingCount。

AttemptConsumptionBinding 恰为 `{mediaJobRef:Ref,attemptRef:Ref,workerRef:Ref,workerProcessIdentityDigest:Digest,jobRevision:正整数,leaseTokenDigest:Digest,executionEnvelopeDigest:Digest,workflowDigest:Digest,currentSubjectReadSet:CurrentSubjectReadSet,currentSubjectReadSetDigest:Digest}`。process identity 采用 §5.3 的 OS 身份方法，但对象为可信控制进程，不是 ComfyUI 进程；其 digest 前像恰为 `{hostBootIdDigest,pidNamespaceIdDigest,pid,processStartTicks,coreCommit}`。不保存原始 lease token。

consumeRequestDigest=H({command:consume请求去掉idempotencyKey/snapshotTokens/expectedJobRevision,resolvedGrantDigest,attemptRef,workerRef,workerProcessIdentityDigest,leaseTokenDigest,executionEnvelopeDigest,workflowDigest})。普通 heartbeat revision 不形成新消费语义；实际 revision 是每次 CAS 条件及 Terminal 的观察事实。不同 Attempt/worker/lease 不能因重放规则被接纳。

### 7.3 撤销与终结唯一性

VerifiedRevocationApproval 恰为 `{approvalRef,authorityRef,authorityDecisionRef,authorityDecisionDigest,actorRef,actorKind:HUMAN,actorRole:PROJECT_LEAD,approvalKind:REVOKE_EXACT_GENERATION_GRANT,decision:APPROVED,grantDigest,approvalEvidenceRef,approvalEvidenceDigest,decidedAt}`。Ref/Digest/时间类型同 §4.7；authorityDecisionDigest=H(对象去掉自身 digest)。grantDigest 必须等于目标 Grant payloadDigest。

撤销材料使用独立 `v5.generation-dispatch-revocation-bundle.v1`，闭集 `{schemaVersion,authorityRef,revocations}`，revocations 恰好一份上述批准；独立配置 PATH/SHA256 和 reader，不复用签发批准。拟议配置名为 `CREATOR_GENERATION_DISPATCH_REVOCATION_BUNDLE_PATH` / `CREATOR_GENERATION_DISPATCH_REVOCATION_BUNDLE_SHA256`。

revokeRequestDigest=H({command:revoke请求去掉idempotencyKey和snapshotTokens,resolvedRevocationDecisionDigest})。撤销不要求原输入仍 CURRENT 或 Grant 尚未过期；只需目标、独立批准、CAS 及 Terminal 条件合法。

消费与撤销共享 Terminal 唯一身份与同一 journal 事务比较：撤销先提交，消费拒绝；消费先提交，撤销返回 ALREADY_CONSUMED。消费后取消必须走既有 V4 取消边界，不写第二 Terminal、不退还额度、不声称已取消在途 provider 请求。

Grant/Terminal 的原子性只涵盖各自 journal 事务，不涵盖独立 M5/M6 数据库、V4 队列或 ComfyUI HTTP。不能把通用 append_records 现有的幂等提前返回当成当前授权重新核验。[S5]

## 8. 首版协调模型与两个决策点（R2）

### 8.1 明确选择的部署模型

首版唯一支持 `SINGLE_HOST_SINGLE_CONTROL_PROCESS`：一个受控 composition 进程经原正式 Owner ports 访问同一工作集的各现有存储，并在该进程内承载指定的一次 V4 worker。ComfyUI 可以是独立进程，但不得写这些 canonical 数据库或批准材料。独立 `run-one` 多进程 worker、同时写相同 stores 的另一 Creator 服务、其他主机 writer、直接 SQL 工具均不属于受支持部署。

V5 生命周期协调边界拥有进程内 `GenerationDispatchCoordinationPort`，它是同步设施而非批准/存储权威。每个 workspace 一个共同的可重入互斥 gate；不是“若干无关联 reader 各自有锁”。composition 将同一 gate 实例注入全部参与方；外层先取 gate，再取某个既有 repository 的内部锁/事务，不允许反序。一次只持有一个数据库写事务，不嵌套跨库事务。

必须参与同一 gate 的写入包括 §5.3 表内全部 Project、Series/Episode、M5 Plan/绑定、Script、M6、M7/M8/M9/InputPlan、身份/参考/权利/Provider/成本前置及 approval/config/runtime locator 变化；还包括所有 Run/evidence、V4 Job 创建/lease/续租/cancel/recovery/Attempt 写入。原 lifecycle composition 的 ProjectFoundation、CanonicalRegistration、恢复/删除等复合参与路径也必须使用同一 gate，不能只覆盖普通 public 入口。具体计数按 §5.3 失效，V4 heartbeat 不伪装成源 selector 变化；unknown 写入不容许消费继续。

启动自检必须证明上述 ports 使用同一 gate，且该 scope 的存储不存在其他受支持 writer。要求部署级独占打开/锁定约定、账号/文件写权限隔离及所有受信任工具遵守独占约定；进程内 mutex 或“管理员说没人写”本身不构成跨进程保证。独占约定缺失、旁路 writer 存在、远程文件系统不能提供约定语义或不能确认覆盖范围，返回 CURRENTNESS_FENCE_UNAVAILABLE。

这些是未来实现与部署验收条件，本文不声称当前 A100 已满足。root/管理员恶意越过部署边界、停止进程后修改底层数据库或改代码，不属于此 in-process 协议可以防止的行为；不得把本设计称为对特权攻击者的 OS 安全隔离。发现任何不受控改动仍 fail-closed。

### 8.2 消费决策点 L1

正常路径先做无副作用校验，再进入下列固定顺序：

1. V4 先按 §9.1 的新服务端内部幂等合同取得同一 Grant 首次持久化的 UUID Job，再经原队列 revision CAS 取得该 Job 的唯一 Attempt；真实 request/envelope 与 Grant 绑定，maxAttempts=1。不是复用一个不存在的“旧确定性 jobRef 算法”。此处尚不能调用 adapter.generate。
2. 取得 workspace gate。通过正式 reader 重新读当前 subject、批准包、配置、runtime、成本、时钟和真实 V4 Job/Attempt；核对当前 lease 有效、无取消/恢复、caller 是原 worker。
3. consume 的 expectedJobRevision 必须匹配这次 gate 内读取。此前正常 heartbeat 导致不匹配，只返回 ATTEMPT_OR_LEASE_CHANGED、零消费记录；原活跃调用可以重新取得纯比较值后再核对，但不能更改 subject/lease 或重试任何网络提交。不能把旧 revision 当许可。
4. 在 gate 仍持有时，以同一 journal 的 snapshotTokens CAS 原子追加 Terminal。提交成功为 L1；失败或不确定都不返回 SendCapability。
5. 明确提交成功且仍为原进程原调用链时，返回仅该 worker 持有的 SendCapability，然后释放 gate。L1 后任何故障都不退还额度、不生成第二 Terminal。

L1 只线性化消费，与网络无原子事务。它绑定了当时的 Job revision/lease/读集；这些审计字段不能代替上述 gate 及再次读取。

### 8.3 本地发送决策点 L2

SendCapability 由协调器私有构造，绑定 Grant/Terminal、Job/Attempt、worker process identity、lease token digest、envelope/workflow digest、L1 的 selector 计数及有效期；不允许 pickle/JSON/文件保存、反序列化、复制生成新资格或传到另一个进程/线程。它只支持 `send_once`，一旦被使用或丢失即永久不可再次使用。

在调用 transport 前重新取得同一 workspace gate；重新读取批准源、runtime/配置身份、当前 selectors、真实 Job/Attempt/lease、取消状态及可信时钟。要求 L1→L2 所有 currentness-sensitive selector 的 coordinationRevision 均未改变，source/plan 摘要仍匹配。普通 heartbeat 可以使 jobRevision 单调增加，但必须保持同一 Job、Attempt、leaseToken、worker 和请求/配置摘要，且 lease 在 L2 尚有效；不因为“只比一个 revision 数”把合法续租随机判成冲突，也不把换 lease 视为续租。

L2 定义为：上述校验成功后，在 gate 内原子把该进程内 SendCapability 转为 spent，并进入禁重试的 transport.send_once。L2 前若被取消、lease 过期、版本/配置/批准变化、超时或线程恢复时已过期，则不进入 transport。Terminal 仍保留，配额不回退。

**初始发送边界与租约预算（F03）。** 初始写入阶段从本地 L2 开始，包含建立/复用已核对连接、请求头和请求 body 的这一次写入；结束点是全部请求字节已交给本地 socket，或者本次尝试明确中止。它不包含等响应头/body、history/queue 轮询、GPU 计算或后处理。旧同步 `json()` 不提供该分界，不能把其整个同步调用或整个 adapter.generate 塞进 gate；所需分阶段 transport 是未来新消费者的有界接线要求，不是已存在的接口。[S13]

令 `W = materials.executionConfig.requestTimeoutMs / 1000`，作为本次完整 HTTP 请求的总 deadline 预算；连接子阶段还须满足 connectionTimeoutMs <= requestTimeoutMs。L2 前 gate 内重读可信时间 `t`、原 lease 到期 `E_lease` 和 Grant 到期 `E_grant`，须满足 `t + W < E_lease`，且 `t + W <= E_grant` 及运行硬截止；§4.6 的完整 executionTimeout 剩余窗口条件仍同时成立。不能缩短 W 来绕过批准配置，也不能静默延长 lease 或批准期限。余额不足时，原 worker 可在 L2 之前通过现有正式 V4 续租端口做一次仍有效 lease 的正常续租并立即重读；仅同 leaseToken/Attempt/worker 的成功 CAS 属于续租。到期 lease 不复活；仍不满足条件就不进入 L2，已消费 Terminal 不退回。此规范不新增 lease 字段或配置项，比较使用当时真实 V4 lease。采用不满足预算的旧默认配置时应拒绝，不由执行者随意改值。

L2 的 deadline 用此可信 UTC 剩余量和同进程单调时钟同时约束；从 L2 起不得重置预算。gate 仅持有至上述初始写入结束/失败。每次进入下一用户态连接/写入步骤及暂停恢复后，transport 先检查剩余 deadline；超时不再发起后续写入，终止本次 socket 操作，不保留后台延迟补发队列。若调度暂停或不可及时中断的 OS 调用跨过 deadline/lease 到期，已交付的字节不能撤回，也不能声称物理网络从未发送：恢复后禁止下一写入/重试，将提交结果按不能独立确认的实际情况保守记录为未知。本文只约束受控应用路径，不承诺能在进程被挂起时强行保证所有内核 I/O 按时停止。

**释放与收尾顺序。** `send_once` 的正常完成、部分写入、异常、取消观察或超时退出均先在 `finally` 释放 workspace gate；调用者不得在外层保留递归持有计数。任何 heartbeat 的 stop/join、等待其他参与线程退出、响应读取、history/后处理，都必须在 gate 完全释放之后进行；不能持 gate 等待也必须取得该 gate 的 heartbeat。正常初始写入成功后先释放 gate，允许 heartbeat 按原 CAS 规则运行，再继续同一连接的响应读取，不是重新发送请求。

若初始阶段失败或恢复时 lease 已过期，先停止进一步 transport 写入并释放 gate，再通知 heartbeat 停止、有界 join，最后走既有 V4 终态/恢复边界。原 worker 只有在同 lease 仍有效且当前 revision CAS 合法时才写终态；lease 已失效时不得借旧 token 强写或续活，由既有恢复 Owner 把该唯一 Attempt 按非重试失败处理。join 超时、CAS 冲突或终态持久化失败须如实留为待恢复/未知，不伪报 cleanup=PASS。无论成功、失败或未知，Terminal 仍消费、capability 仍 spent；重启和恢复只能观察既有 Job，不建第二 Job/Attempt、不补 `/prompt`。

V4 cancel 仍按 gate 次序解释：cancel 先于 L2，则不发送；L2 先于 cancel，取消只能禁止后续动作，不能声称在途请求从未发出。S13 的租约自然过期窗口按以上规则得到固定安全结果：不复活租约、不重发；先释放 gate，再有界停止 heartbeat，再由有权 Owner 收尾。初始写入和收尾接口能否满足这些条款仍须未来实现测试证明。

expiresAt 约束的是本地 L2 授权决策，不冒充 Provider 的接受/启动时钟。无法仅凭客户端保证网络包在 expiresAt 前到达或 Provider 在该时刻前启动；本 ADR 不承诺这种跨网络硬实时性质。若具体批准要求远端接受的绝对截止，则在具有可验证服务端过期拒绝机制前必须拒绝该部署，不扩张本地保证。

### 8.4 失败、消费重放与任务终止

L1 后回执丢失、控制进程退出、lease 失效、L2 前校验失败、POST 被拒绝、响应未知，都不重新签发或补交。L2 之后，无论收到何种结果，SendCapability 都已经 spent；禁止 POST 自动重试、307/308 重发、provider fallback 或其他路径第二次调用。

发送后的历史/queue/result 只读恢复依原独立权限执行；输出 QC 失败不退还额度。运行 timeout 到达只能执行已经包含在本次执行批准中的任务级停止/收尾动作，不能擅自关机、全局清队列或续租。停止 ComfyUI 不代表停止平台计费。

此协议保证的是符合受控部署和消费者规则的应用路径至多一次提交，允许崩溃窗口零次发送，不承诺恰好一次成功生成。单次 capability 和两个决策点的实现及并发证明尚未存在；不能靠只设置 maxAttempts=1 宣布达标。

## 9. V5→V4 接线与版本边界

原 manifest v2 无 Grant 的路径继续拒绝。带 Grant 的新路线先完整验证旧对象及其 false/NOT_READY 不变量，再经 V5 验证独立权威；新的 request.executionMode 可为 INTERNAL_SELF_HOSTED，但不得更改历史 Run.executionMode。

| 对象 | 保留旧版 | 带 Grant 的新版本 |
| --- | --- | --- |
| route plan / route | v5.video-method-route-plan.v1 / v5.video-method-route.v1 | 对应 v2 |
| generation request | v5.method-aware-video-generation-request.v1 | 对应 v2 |
| execution envelope | v4.method-aware-media-execution-envelope.v1 | 对应 v2 |
| method-aware job | v4.media-job.v3 | v4.media-job.v4 |

新增 dispatchGrantBinding 恰为 `{generationDispatchGrantRef,generationDispatchGrantDigest,subjectDigest,approvedPlanDigest}`，进入各自新摘要。旧闭集不 silently 加键；旧无 Grant 记录保持历史读取与准确重放，但新请求不能降级执行。来源正是既有 profile/request/envelope 的闭集，不能误称它们已经接受上述字段。[S6][S7]

### 9.1 Job 身份与派发幂等：保留 UUID，新增服务端唯一绑定（F01）

固定源码的事实是：`MediaJobCoordinator.dispatch()` 通过 `_ref_factory("media-job")` 产生 jobRef，实际 worker 默认使用 UUID；InMemory/SQLite 依据 Workspace、Run 和调用方 idempotencyKey 重放，旧路径没有“同一 request 永远同一 Job”的确定性身份合同。[S12] UUID 本身不是缺陷；本节明确新增的仅是带 Grant 请求的内部派发键规则，不改旧 jobRef 工厂、不迁移旧 Job，也不重写所有队列。

首版对新 request v2 / Job v4 采用唯一算法：

```text
InternalDispatchIdentity = {
  schemaVersion: "v4.generation-dispatch-job-idempotency.v1",
  workspaceRef,
  productionRunRef,
  generationDispatchGrantRef
}
internalDispatchKey = "generation-dispatch-job-v1:" + H(InternalDispatchIdentity)
```

三个 Ref 必须来自经 V5 核验的同一持久化 Grant，而非原始客户端字段。键前像不含 caller route key、requestRef、Grant digest、seed、时钟、随机数或 worker；修改这些内容不能换出另一把内部键。它不是新的 jobRef：首次真正持久化时仍保存原工厂生成的 UUID Job；重放返回原 JobRef/createdAt，不采用重放过程中临时生成但未存储的另一个 UUID。

客户端 route idempotencyKey 只用于其原 V5 路由请求重放；传入 V4 创建端口的 key 必须由服务端按上述算法覆盖为 internalDispatchKey，不能拼接 caller key。`generation-dispatch-job-v1:` 是新路径保留命名空间：旧无 Grant 的新写请求不得自行使用该前缀；既有记录仍可按原语义只读/重放，不删除或改键。发现同内部键的存量异 schema/异常记录则冲突拒绝，不通过改前缀、增加 version 后缀或换数据库绕开。

新建/命中在同一现有队列 create 事务或对应 InMemory 临界区内判断；复用原 `(workspace_ref,production_run_ref,idempotency_key)` 唯一约束，不新增表/索引/队列。[S12] 命中行必须是 Job v4，且 `request.schemaVersion`、generationRequestRef/VersionRef、requestDigest、完整 dispatchGrantBinding、backendBinding 和 executionContext 均与重新核验请求逐项相等。原比较逻辑中已有 requestDigest/backendBinding/context 校验；新 Grant 语义和版本检查是将来要显式增加的合同，不声称旧代码已完成。

| 情形 | 唯一结果 |
| --- | --- |
| 同一 Grant、相同精确绑定、同或不同客户端 route key、无 Job | 内部键相同；只允许原 create 事务首次持久化一份 UUID Job |
| 同内部键且相同版本/完整绑定的 Job 已存在 | 返回首次持久化的原 Job；不新增 Job，不重置 state/attempts/lease/maxAttempts |
| 同 Grant 但 request、Grant digest、profile、backend 或上下文变化 | 仍命中同键，绑定冲突拒绝；不得签发新内部键 |
| 旧 schema 或被错误占用的内部键 | 冲突拒绝；不迁移、不覆盖、不回退到随机 caller key |
| Job 已创建但 V5 路由记录尚未返回/进程退出 | 原受控恢复重新派生同键并读取/幂等取得原 Job；不是跨 V5/V4 的全局事务，也不另建任务 |
| Grant/Terminal 已终结、Job 已失败/取消/成功或 Attempt 已存在 | 历史 Job 可以被识别和返回；返回记录本身不赋予 lease、第二 Attempt、capability 或再次发送权限 |
| 并发同键创建/结果未知 | 原数据库唯一约束或原 InMemory 锁串行化；结果未知先查原键，禁止生成另一键补建 |

唯一性在“同一经核验 Grant 的内部队列键”层成立，不要求每次尝试生成的 UUID 值相同，不改变 §5.5 的确定性 requestRef。消费前还须核对实际 Job.idempotencyKey 恰为本节的内部键，并确认当前 Job 内已有真实唯一 Attempt；不能伪造 AttemptRef 跨过 gate。生产持久化保证以原持久化队列为准，InMemory 只能作为测试环境，进程丢失不能被解释为可重新执行真实 Grant。

旧 worker CLI 在新模式下只能委托同一受控 composition 内的 worker，不允许单独进程拿 Terminal 当发送凭证。本节只是受审议的新有界合同，不是本轮 CLI 或队列代码修改许可。

InputPlan、InputAssetVersion、InputAppendAuthority 和旧 v2 runtime attestation 不因此升版；§5.6 的 A14B attestation 是独立新类型，不迁移旧原件。输出仍技术候选；不追加输出 AssetVersion/Admission/Master/Export，也不把新 Grant 作为 E2 结果准入许可。§5.6 之外确有其他闭集需要新字段，仍须逐项获得批准。

## 10. CAS 与竞争情景的唯一结果

| 场景 | 必须结果 |
| --- | --- |
| 只有批准 digest，无计划/材料原文 | prepare/issue 拒绝，不补默认值 |
| 相同批准包完整数据，重复相同 issue | 返回原记录和单独计算的 eligibility，无发送能力 |
| 更换 seed/模型/workflow/期限/额度/进程 | planDigest 不同，原批准失配；不能覆盖 Grant |
| 同槽位换幂等键、批准编号、随机 Ref | 拒绝第二 Grant |
| 同 Grant、相同绑定，调用方 route key K1/K2 不同 | 同一内部派发键，至多持久化一个 UUID Job；重放返回原 Job |
| 同 Grant 但 request/profile/Grant digest 变化 | 同内部键绑定冲突；不另建 Job |
| source 在 issue 快照之后、事务之前改变 | 共同 gate/CAS 阻止提交旧快照；否则拒绝部署 |
| source 在 L1 后、L2 前改变又改回 | coordinationRevision 已改变，不发送，额度仍消费 |
| revoke 与 consume 竞争 | 同一 Terminal 槽位只提交一个；失败者不能取得能力 |
| heartbeat 在 L1 前改变 jobRevision | 本次比较失败零消费；原调用重新只读比较，非网络重试 |
| heartbeat 在 L1 后合法续租 | 同一 lease/Attempt/worker 可经 L2 再核对，不要求 revision 仍等于历史值 |
| cancel/recovery/换 lease 在 L2 之前 | 拒绝首次发送，不返还额度 |
| 消费后在 L2 前暂停至过期 | L2 恢复检查拒绝，不发送 |
| L2 后持 gate 写入期间暂停/跨过 lease deadline | 停止后续写入，已有 I/O 不冒充可撤回；先释放 gate，再 stop/join heartbeat，既有恢复非重试收尾 |
| Terminal commit 回执丢失 | 只读历史可确认提交，不能重建 SendCapability |
| HTTP 成功/失败/响应未知 | 都不产生第二次 POST |
| 不支持单进程共同协调、存在旁路 writer | CURRENTNESS_FENCE_UNAVAILABLE，不进入消费 |

拒绝代码仅描述本次动作结果，不自动改写项目 READINESS。历史记录、重放响应、当前可消费资格、原调用的发送 continuation 是四种不同概念。

## 11. Alternatives、代价和不保证事项

原位覆盖历史五字段、扩张 E3H operations、凭环境变量直接调用 ComfyUI、仅建一个可变 used boolean、只凭 journal CAS 声称跨库原子，这些方案均不采纳。

独立 Grant + 唯一 Terminal 保留历史，批准计划可重建，权限可精确审计。代价是新批准材料 reader、两个 record kind、受限 composition、版本化消费者和无重试的故障损失；它不是“写一份 Grant JSON 就能跑”。首版为了可明确审计，不支持多进程/多主机 writer 和 worker pool。

不保证 OS 特权攻击防护、跨数据库/网络全局事务、provider exactly-once 成功、远端接受的硬实时截止、全账户最终成本封顶或自动 Production Ready。未来扩大这些保证须另立明确架构及执行授权。

## 12. 实现验收要求（本轮未执行）

| 类别 | 必须证明 |
| --- | --- |
| R1 完整性 | plan/materials/approval 一一绑定；期限/费用只能来自完整批准材料；缺原文拒绝 |
| R2 协调 | §5.3 的全部 Owner/16 行映射及复合参与 writer；gate/CAS；S03/S05/ABA；L2 预算与原 lease；S13 先释放 gate 后 heartbeat 收尾；缺任一保证即拒绝 |
| R3 规范一致性 | 原 digest/requestRef/workflow 依赖不变；§9.1 UUID 与内部 key 分离；同 Grant 不同 route key 返回原 Job、异绑定拒绝；approval.decidedAt 与 Grant/envelope.createdAt 明确相等/顺序约束 |
| R4 局部例外 | 只替代本技术 subject 的全局 ShotPlan/camera 前置；其他权威事实仍独立；其他 Run 仍拒绝 |
| 历史保持 | 原五字段、E3 Ref/Digest/版本、InputPlan/Candidate/失败/replay 不变 |
| 假批准拒绝 | 认证、设计接受、实现批准、HumanSelection、InputAppendAuthority、旧预算不能代替生成批准 |
| 事务和幂等 | 成功单 Grant、失败零记录、同键变参/同槽位不同键拒绝、未知提交不伪报零写入 |
| 消费上限 | 单 Terminal；只有新提交原调用有非序列化 capability；replay/GET/另一进程零发送能力 |
| 崩溃和网络 | L1/L2/HTTP 前后崩溃、响应丢失、重定向、lease 到期、timeout 不发生第二次 POST |
| 旧版及输出 | 不降级绕 Grant，不因候选产生输出准入、Master/Export/publication |
| 资源 | 实现期只用 no-call/fake transport；真实 GPU、付费、生成另行批准 |

不得弱化断言来适配旧代码。任何新 DDL、持久化 Owner、分布式协调、额外依赖或未声明 DTO 版本需求，须先停报；不把设计要求未实现登记为现场事故。

## 13. Migration、回滚和审批次序

无历史数据迁移。Grant/Terminal 在本提案阶段尚未真实签发；本文文档版本由未提交 v1.1 改为 v1.2，readSet 的补充枚举和 Job 内部派发键均为待审议规范，不改变任何历史数据 schema 实例。

次序为：v1.2 定向文档改稿与复审 → Project Lead 明确 Accepted（仅架构）→ 单独申请且获批实现任务 → 无真实调用实现/测试 → 验收并另定执行代码基线 → 精确生成计划和成本审议 → 独立批准实际签发/消费及最多一次 /prompt。没有一个步骤自动授权下一步。

移除新 authority 配置恢复默认拒绝，不删除已持久化 Grant/Terminal。回滚代码不得使已消费 Grant 在旧无权限消费者中重新执行。控制进程重启使所有未使用内存 continuation 失效，不进行恢复式发送。

## 14. 修订记录与源码依据

| 版本 | 内容 | 审批效果 |
| --- | --- | --- |
| 1.0 | 原独立 Grant/Terminal、签发与至多一次方向；PR #84 文档登记 | Proposed/PENDING，不是实现许可 |
| 1.1 | R1 完整批准材料；R2 单进程协调与 L1/L2；R3 规范材料/端口；R4 ADR-0014 局部例外 | 已落稿未提交；N1 与独立复审要求修订 F01—F04；不重写历史结论 |
| 1.2 | F01 保留 UUID＋新服务端幂等键；F02 原 Owner/selector 完整映射；F03 lease/deadline/释放与收尾；F04 精确时间字段 | 仅单文件文档修订获批；待独立复审，全文 Accepted/实现/生成均未批准 |
| 1.2 接受及发布元数据 | 2026-09-10 Project Lead 全文回复 Accepted；随后另行授权状态回填及文档入库；第 1—13 节原字节不变 | ACCEPTED_ARCHITECTURE_ONLY；历史行仅记录其编制阶段；实现、真实 Grant 和生成仍未批准 |
| 1.3 R2 狭义兼容 | 2026-09-12 Project Lead 明确批准 §5.6 的独立 A14B profile/compiler/runtime 与 staged transport 本地 CPU 增量；其余控制面语义保留 | 狭义设计及白名单本地实现获批；实现 Owner 验收待定，发布、真实 ComfyUI/GPU/Grant/数据库/生成未授权 |
| 1.4 R3 狭义兼容 | 2026-09-13 Project Lead 授权 A01—A06 与 §5.7 版本化原图、runtime 前像、完整编码及直接依赖接线 | 仅本地 CPU/fixture 候选；Camera/精确绑定 Owner 验收、发布与现场执行仍待后续授权 |

以下 [S] 项只支持对旧仓库行为的陈述，不表示新增规范已经实现：

- [S1] `3bf2e7a5152a7bd9c1087571aab6413a53a43bb6` 下 `governance/ADR-0022-generation-dispatch-grant.md`，Git blob `07e225bf3745c2e961007477a296e19a7ff07ea9`；PR #84 文档登记，不包含实现。
- [S2] `governance/ADR_TEMPLATE.md`；本 ADR 明确限定其 Accepted 批准效果。
- [S3] `governance/ADR-0021-manifest-v2-technical-input-append-authority.md` 及 `architecture/M10_MANIFEST_V2_TECHNICAL_INPUT_APPEND_AUTHORITY_CONTRACT.md`；E3H 输入侧权限与排除操作。
- [S4] 行为基线 f007ab3e 下 `services/v5_core_os/episode_production/method_aware_media.py:1632–1658`、`method_aware_input_assets.py:152–164,608–658`、`input_append_authority.py:35–51,379–406`；路由拒绝及 immutable 输入。
- [S5] 同基线 `services/v5_core_os/episode_production/evidence.py:1794–1938`；journal 同 scope 事务、幂等、CAS，不覆盖独立队列/网络。
- [S6] 同基线 `services/v4_platform/media_jobs.py:2590–2697,2769–2910`、`method_aware_execution.py:13–23,62–145`；旧 Job/Attempt/lease 和 envelope，不包含新消费能力。
- [S7] 同基线 `services/v4_platform/backend_registry.py:38–54,102–143,176–224`；canonical 和 backend decision/profile 闭集。
- [S8] 同基线 `services/v4_platform/comfyui.py:983–1054,1056–1192`；现有 I2V 参数、staging 与 workflow 前序；纯编译分离是待实现要求。
- [S9] 已登记 `docs/status/M10_M11_SPIKE_0_E4_EXACT_BINDING_REVIEW_2026-09-09.md`、`docs/status/M10_M11_SPIKE_0_E4_EVIDENCE_INDEX_2026-09-09.md`；本次目标及历史证据，不是新 live currentness。
- [S10] 同基线 `governance/ADR-0014-k2-001-archive-k2-002-changan-start.md:78–99`，Decision 7、10；`ADR-0019` 的 method planning 与 dispatch 分离合同。
- [S11] 同基线 `services/v5_core_os/episode_production/foundation.py:643–750,1046–1073,1157–1189`；`lifecycle_integrity/composition.py:375–438,480–503`；`project_engine/public.py:73–142`、`series_episode/public.py:75–213`、`series_planning/public.py:35–117`。分别提供实际 Project/Series/Episode/M5 reader、writer 与 composition 关系；§5.3 的协调标签/计数映射是新提案，不声称旧库已有这些 selector 表。
- [S12] 同基线 `services/v4_platform/media_jobs.py:1284–1301,1349–1442,1611–1641,2479–2520`、`method_aware_worker.py:92–95`。证明原 UUID 工厂与调用方幂等键、现有唯一约束；§9.1 的保留内部派发键是新合同。
- [S13] 同基线 `services/v4_platform/media_jobs.py:1892–1945,1947–2084`、`comfyui.py:201–246`。原 lease/heartbeat/CAS/join 与旧同步 HTTP 边界；§8.3 的初始写入分界和 gate 顺序尚待实现。
- [S14] N1 夜间审查原包 SHA-256 `091b10bd491a7e814965efd7a88275558b6444de010c352aea8a1bb9a884499c`；2026-09-10 独立复审 `ADR_0022_V1_1_N1_INDEPENDENT_REVIEW.md`。仅用于说明 F01—F04 修订依据，不代表 v1.2 已通过测试或 Owner 关闭问题。

原候选交付阶段的操作边界（历史说明）：本次修订不改 CURRENT_MILESTONE 的 BLOCKED、不将旧 C1/C2 回执改成通过、不将本文改为 Accepted、不修改执行 pin。交付本候选供执行窗口单文件落稿和独立复审后停止；此处“交付”不包含 Git commit、push、PR、CI 或合并。不自行申请实现或生成授权。

后续决定：Project Lead 已接受精确 v1.2 全文，并另外授权本次文档状态回填和入库；本次发布仅将接受决定准确登记，不改写上述历史交付事实。后续 PR、CI、合并和工作区状态以执行窗口真实回执为准，不在本文件预报成功。实现授权申请、真实 Grant 签发/消费、生成授权申请及 /prompt 均不属于本次文档任务。
