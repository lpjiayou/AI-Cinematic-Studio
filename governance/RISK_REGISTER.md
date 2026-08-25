# AI Cinematic Studio 风险登记册

## 1. 目的与范围

本登记册用于持续识别、评估、处置和复核 ACS 工程治理风险。第 4 节保留 Phase 0
仓库基础与治理的初始历史条目；第 5 节登记后续当前 Core 已确认的架构与治理风险。
风险条目本身不授权业务实现、数据库设计或里程碑扩展，具体缓解权限仍由当前
Source-of-Truth、Accepted ADR 与明确工作包共同决定。

风险登记不等于风险已被接受。所有开放风险都必须有责任人、缓解措施和复核状态；风险接受必须由具备相应权限的责任人明确批准。

## 2. 字段定义

以下六个字段为每条风险的最低必填项：

| 字段 | 填写规则 |
| --- | --- |
| 风险编号 | 唯一且不可复用，格式建议为 `R-P0-GOV-NNN` |
| 风险描述 | 描述“原因—事件—结果”，避免只写模糊主题 |
| 影响 | 使用 `低 / 中 / 高 / 严重`，并简述影响范围 |
| 概率 | 使用 `低 / 中 / 高`，基于当前证据评估 |
| 缓解措施 | 写明可执行动作、责任人和完成或验证条件 |
| 状态 | 使用 `开放 / 缓解中 / 监控中 / 已接受 / 已关闭` |

建议同时维护以下辅助字段，以提高可执行性和可追溯性：责任人、触发条件、目标日期、最近复核日期、关联任务或 ADR。

## 3. 评估与状态规则

### 影响等级

- `低`：局部文档或流程偏差，易于恢复且不影响关键门禁。
- `中`：影响多个工程资产或造成明显返工，但边界仍可控。
- `高`：可能破坏架构一致性、审计能力、安全基线或阶段目标。
- `严重`：可能造成不可逆损害、敏感信息暴露或全仓库治理失效。

### 概率等级

- `低`：已有有效控制，且仅在少见条件下触发。
- `中`：控制不完整或已出现先兆，存在现实发生可能。
- `高`：控制缺失、风险已重复出现或触发条件普遍存在。

### 状态转换

- `开放`：风险已确认，尚未开始执行缓解措施。
- `缓解中`：措施已有责任人并正在执行。
- `监控中`：主要措施完成，等待持续证据确认有效性。
- `已接受`：残余风险经授权责任人书面接受，包含复核日期。
- `已关闭`：风险已消除或完成验证，不再需要主动措施。

状态变更必须保留日期、依据和责任人。没有验证证据的风险不能直接从“开放”改为“已关闭”。

## 4. Phase 0 初始治理风险

| 风险编号 | 风险描述 | 影响 | 概率 | 缓解措施 | 状态 | 责任人 | 触发条件 / 验证证据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-P0-GOV-001 | 若 Phase 0 范围被扩大，可能夹带业务代码、服务实现或数据库设计，导致基础阶段目标失焦并污染架构基线。 | 高：破坏阶段边界并产生返工 | 中 | 在开发规则、评审清单与完成定义中设置硬门禁；每个变更由作者和评审者双重确认。责任人：项目负责人。完成条件：所有 Phase 0 评审均留存范围检查证据。 | 缓解中 | 项目负责人 | 发现业务文件、服务实现、数据库表或相关设计即触发 |
| R-P0-GOV-002 | 若实现或目录先于决策落地，可能隐式修改 V2.3 架构或臆造未来模块。 | 严重：权威架构失真且后续依赖错误基线 | 中 | 强制执行 ADR 与架构专项评审；未 Accepted 的提案禁止实施。责任人：架构责任人。完成条件：架构敏感变更均关联已批准 ADR。 | 缓解中 | 架构责任人（待项目负责人指定） | 出现新模块名、边界、依赖方向或与权威文档冲突即触发 |
| R-P0-GOV-003 | 若治理文档之间术语、门禁或责任定义不一致，执行者可能采用冲突规则。 | 高：评审结果不可预测并削弱审计 | 中 | 对治理文档执行交叉引用与一致性复核；变更治理规则时同步评审受影响文件。责任人：治理维护人。完成条件：关键术语和 Phase 0 禁令检查无冲突。 | 开放 | 治理维护人（待指定） | 同一事项出现不同状态、角色或强制级别即触发 |
| R-P0-GOV-004 | 若责任人和审批权限未正式指定，ADR、例外与风险接受可能停滞或被无权人员批准。 | 高：关键门禁失效或工作阻塞 | 高 | 由项目负责人书面指定架构及专项责任人，并在记录中填写实际姓名或团队标识。完成条件：不存在空缺的必需审批角色。 | 开放 | 项目负责人 | ADR 或例外出现“待指定”审批角色即触发 |
| R-P0-GOV-005 | 若为未来需求提前引入大型依赖，可能增加供应链风险、维护成本并锁定技术路线。 | 高：违反 Phase 0 边界且形成不必要约束 | 中 | Phase 0 禁止大型依赖；依赖变更必须独立说明用途、许可证、安全与体积影响。责任人：评审者。完成条件：基础初始化不含新增大型依赖。 | 缓解中 | 变更评审者 | 出现新的依赖清单、锁文件或二进制工具即触发复核 |
| R-P0-GOV-006 | 若分支保护、评审或验证门禁未实际执行，治理要求可能停留在文档层面。 | 高：未经审查的变更进入主分支 | 中 | 配置受保护主分支；要求评审和强制检查证据；定期抽查合并记录。责任人：仓库管理员。完成条件：主分支无直接推送且合并记录完整。 | 开放 | 仓库管理员（待指定） | 直接推送、强制合并或缺少评审记录即触发 |
| R-P0-GOV-007 | 若提交中包含凭据、生产数据或本地敏感信息，可能造成安全与合规事件。 | 严重：敏感信息泄露且可能需要凭据轮换 | 低 | 执行提交前自检、评审和适用的轻量扫描；发现泄露立即停止常规流程并升级处置。责任人：作者与安全责任人。完成条件：所有提交无敏感信息。 | 监控中 | 作者；安全责任人（待指定） | 检出令牌、密钥、个人信息或生产数据即触发 |
| R-P0-GOV-008 | 若风险登记册未定期复核，概率、状态和措施可能过期，开放风险将失去责任追踪。 | 中：治理决策使用失真信息 | 中 | 每个阶段关口及重大治理变更时复核；更新状态、责任人和证据。责任人：治理维护人。完成条件：所有开放风险均有当前责任人和复核记录。 | 开放 | 治理维护人（待指定） | 阶段关口前存在未复核或无责任人的开放风险即触发 |

## 5. 当前 Core 架构与治理风险

下列风险来自 `2026-08-13` 的独立只读架构、接口与测试专项复核。该复核没有修改
文件或取得实现权限。风险状态与缓解范围以
[`ADR-0006`](ADR-0006-v5-text-generation-capability-boundary.md) 和
[`ACS-ARCH-R1-V5-TEXT-GENERATION-G0`](ACS-ARCH-R1-V5-TEXT-GENERATION-G0.md)
以及后续
[`G1-R1 授权记录`](ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-AUTHORIZATION.md)
和
[`G1-R1 关账记录`](ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-CLOSEOUT-M6-P3-G0-OWNER-REVIEW.md)
为准。

| 风险编号 | 风险描述 | 影响 | 概率 | 缓解措施 | 状态 | 责任人 | 触发条件 / 验证证据 | 目标日期 / 事件 | 最近复核日期 | 关联事项 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `R-CORE-ARCH-001` | M1 AI Director、M3 Script Studio、M5 Series Director 与 Creator Server 曾直接导入 V4 public provider boundary，跳过 V5 相邻层。G1 完成四个接触面迁移；G1-R1 进一步修复持续守卫对 `importlib.import_module` / `__import__` 导入别名、简单赋值别名及常量 `getattr` 的漏检。 | 高：若持续守卫未来失效，Application→V4 违规仍可能重新进入仓库并削弱 V5 治理与替换能力 | 低：当前生产静态/程序化 V4 访问为零，alias-aware guard、正反例矩阵、完整回归和独立复核均已通过 | 保留 ADR-0006、Owner-accepted G1-R1 和全 Application 守卫；后续适用 Core checkpoint 持续执行架构合同测试。若守卫报警或出现新的程序化导入路径，立即转回 `MITIGATING` 并停止相关扩展。关闭前需跨后续里程碑的持续无回归证据及 Project Lead 决定。 | 监控中（`MONITORING`） | Project Lead / Architecture Owner `蔺鹏` | 接受证据：G1-R1 `d44f471c644e319bb4a5bf73707c3274ecbaa426`；Targeted `124/124`、Full Core `404/404`、Unit/Contract/Integration `226/81/97`、AST `63/63`、Application V4 访问 `0`、Local=Remote、独立复核 PASS、Owner Acceptance。监控触发：任一 `apps/**/*.py` 静态或程序化访问 V4，或守卫合同被删除、跳过、弱化 | 后续适用 Core checkpoint 持续监控 | `2026-08-13` | `ADR-0006`; `V5_TEXT_GENERATION_CAPABILITY_CONTRACT`; `G1-R1 AUTHORIZATION`; `G1-R1 CLOSEOUT` |
| `R-CORE-GOV-002` | Source-of-Truth 声明 `Full Core Audit Report v1.2: INDEPENDENTLY ACCEPTED`，但当前仓库及可见 Git 对象历史没有提供可定位、可校验的仓库内报告文件或 hash-addressed evidence；若原报告仅存在于外部附件或对话且无 provenance manifest，后续审计无法从仓库复核其基线、范围、作者与独立 reviewer。 | 高：削弱历史审计结论的可重复性与治理证据链；不直接证明已接受功能失效 | 高：仓库内接受声明存在，报告路径、SHA/digest 与 reviewer evidence 当前缺失 | 独立治理工作包应找回原报告并登记仓库路径或不可变外部标识、内容 digest、被审计基线 SHA、范围、作者、独立 reviewer、结论和接受记录；若无法找回，应将现有 Source-of-Truth 表述降级为“外部接受声明 / 仓库证据不可用”，不得继续把它当作仓库可复核证据。关闭必须有 Project Lead / Governance Owner 明确决定。 | 开放（`OPEN / NON-BLOCKING`） | Project Lead / Governance Owner `蔺鹏` | 触发条件：任务依赖该报告证明架构/功能完整性，或 Source-of-Truth 继续扩大其证据含义；关闭证据：可验证 provenance manifest 或经批准的状态降级同步。它不阻塞 G1，因为 G1 使用独立直接复核、专项测试与新的 Full Core 回归；G1 不得关闭本风险。 | 独立 Audit Provenance 治理 checkpoint | `2026-08-13` | `Full Core Audit Report v1.2`; `ACS-ARCH-R1-V5-TEXT-GENERATION-G0` |
| `R-CORE-SEC-003` | Creator Public HTTP/API v1 的基线曾无调用方认证并直接接受请求中的 `workspaceRef`；AUTH-W1 已增加服务端身份与凭据所属工作区边界。后续若移除鉴权、恢复客户端 scope、泄漏令牌或在非回环暴露 internal 路由，跨工作区风险将重新出现。 | 严重：控制回归仍可能造成跨工作区读取或写入，并把本地开发接口误用为可部署接口 | 低：AUTH-W1 控制、完整回归、凭据扫描、双进程 Gate C 与双仓远端树核验均已通过；残余风险是静态令牌轮换和未来用户/RBAC/生产运维尚未实现 | 持续执行全部 public endpoint 鉴权合同、客户端 scope 拒绝、非回环 public-only 规则、无 CORS/同源拓扑、服务端密钥扫描与 Gate C；未来生产部署前另行接受轮换、密钥管理、用户/RBAC 和审计合同。 | 监控中（`MONITORING`） | Project Lead / Architecture Owner `蔺鹏` | 监控基线：Core `a2297d952fa726e2d093f24869c9f0be0e417963` / tree `d52fe5b9b2f2abf577298687c97ec31537b37026`，Frontend `05c3647b1f1fa76d6d67da90cab297ea029fd27d` / tree `27a82cc0bbc3c873435a52e3a6add888982f81dc`，Core `480/480`、Frontend `112/112`、build、双进程 Gate C。触发条件：任一 public v1 匿名可用、客户端可传 `workspaceRef`、凭据进入浏览器/日志、非回环暴露 internal 路由；关闭仍需另行安全复核，AUTH-W1 不直接关闭 | 后续 public API / deployment checkpoint 持续监控 | `2026-08-17` | `ADR-0007`; `CREATOR_PUBLIC_API_AUTHENTICATION_AND_WORKSPACE_ISOLATION_CONTRACT` |
| `R-K2-EXEC-004` | 若 live provider / GPU 不可用时的本地确定性证据被描述为真实 AI/GPU 生产结果，可能造成能力、质量、成本与发布就绪度的错误结论。 | 高：误导验收与商业/发布决策，掩盖真实外部依赖 | 中：K2 必须先闭合媒体链路，而当前没有已验证的 live media provider/GPU runtime | 所有本地结果强制记录 `LOCAL_EVIDENCE`、adapter、参数、digest 与 probe facts；复用相同 V4 job/artifact contract；UI/API 明示非生产；禁用发布；live provider/GPU/rights/budget 另设门禁。责任人：K2 实现者与 Architecture Owner。 | 缓解中（`MITIGATING`） | Project Lead / Architecture Owner `蔺鹏` | 触发：出现 provider/GPU/production-ready 字样却无 live 运行证据，或本地产物可进入 publication；验证：合同测试、UI 文案测试、artifact manifest 和发布禁用测试 | K2 G4–G7 持续验证 | `2026-08-17` | `ADR-0008`; `K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT`; `REFERENCE_VIDEO_CAPABILITY_AND_WORKSPACE_MERGED_BASELINE` |
| `R-K2-LIN-005` | K2 横跨根对象、脚本、镜头、身份、资产、任务、时间线、预览、审批与成片；若稳定引用、版本、digest、staleness 或重启恢复不完整，可能把过期或异工作区对象组合成不可复现成片。 | 严重：破坏权威性、隔离性、审计和成片可复现性 | 中：当前尚无已接受的 M7–M15 端到端对象链 | 每个对象强制稳定 ref/version/digest/upstream lineage；外来、缺失、重复和 stale refs fail closed；工作区路径隔离；幂等、重启、孤儿产物与 lineage 回溯测试作为每一门禁条件。责任人：K2 实现者与 Architecture Owner。 | 缓解中（`MITIGATING`） | Project Lead / Architecture Owner `蔺鹏` | 触发：按名称重建引用、无版本覆盖、跨工作区可见、重复任务产物、stale 输入仍可 finalize；验证：G1–G7 契约/集成/失败注入测试和 master→roots 证据链 | K2 G1–G7 持续验证 | `2026-08-17` | `ADR-0008`; `K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT` |
| `R-K2-LIVE-006` | 若未通过统一 V4 job/adapter 边界记录真实 provider/model/runtime、成本、延迟与输出 provenance，可能把不可复现的外部调用或本地结果当作生产证据。 | 高：供应商替换、成本治理、质量复盘与发布证据失真 | 高：当前 G0→G7 只存在 `LOCAL_EVIDENCE`，尚无已验证 live provider/GPU 事实 | 由 P0 冻结 ProviderExecutionPolicyVersion 与 live evidence schema；所有外部调用只经 V4；保存 attempt、model、region、parameter digest、cost、latency、runtime/GPU facts、artifact digest 与 probe；缺凭据/预算即 fail closed。 | 缓解中（`MITIGATING`） | Project Lead / Architecture Owner `蔺鹏` | 触发：provider SDK 出现在 V4 之外、provider success 无 attempt/provenance、`gpuUsed=true` 无 attestation；关闭证据：P1 live image/video/audio evidence + targeted/full tests | P1 live provider gate | `2026-08-17` | `ADR-0009`; `K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT` |
| `R-K2-RIGHTS-007` | 若参考图、人物肖像/声音、音乐或生成输出的使用授权未绑定到精确版本，可能生成技术上可播放但不可合法发布的成片。 | 严重：侵权、下架、赔偿与商业发布阻断 | 高：仓库当前没有可证明真实授权的 K2 rights manifest | P0 增加 RightsManifestVersion 合同和 validator；逐输入记录 grant、用途、provider processing、地域、期限、署名和证据 ref；过期、缺项或不兼容阻止 dispatch/publication；不把用户上传等同于授权。 | 开放（`OPEN / BLOCKING P1`） | Project Lead / Rights Owner `待提供外部事实` | 触发：live dispatch 或 publication eligibility 无有效 rights manifest；关闭证据：权利责任人提供可验证 manifest/evidence 且合同检查通过 | P0→P1 hard gate | `2026-08-17` | `ADR-0009`; `REFERENCE_VIDEO_CAPABILITY_AND_WORKSPACE_MERGED_BASELINE` |
| `R-K2-PROD-008` | 若 live media 继续依赖进程内状态、本地路径、静态密钥或单机无恢复 worker，重启、并发或故障会丢失任务和产物并造成重复计费。 | 严重：数据丢失、跨租户泄漏、重复费用与不可恢复生产 | 高：当前 K2 server 为本地/测试边界，尚无生产 DB、object store、secret/runtime closeout | P2 引入已接受边界内的 durable facts/job state/object store abstractions、secret injection、lease recovery、idempotency、retention 和 observability；执行 restart、partial upload、timeout、duplicate delivery、budget exhaustion 与 isolation 测试。 | 开放（`OPEN / BLOCKING SCALE`） | Platform Owner / Architecture Owner `蔺鹏` | 触发：生产任务依赖进程内 store、本地绝对路径、提交凭据或无恢复 lease；关闭证据：P2 failure-injection and recovery suite | P2 production runtime gate | `2026-08-17` | `ADR-0009`; `K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT` |
| `R-K2-QC-009` | 若生成成功或机器 QC 通过被直接视为选片、身份一致或最终批准，低质/错误/不连续候选可能进入成片。 | 高：成片质量、角色连续性和审批责任失真 | 中：G0→G7 已分离批准事实，但 live candidate validation/selection 尚未实现 | 维持 Candidate→Validation→Selection→AssetVersion；加入图像/视频/音频专项 QC、局部重生成和 exact-version decisions；机器 QC 不写 HUMAN decision，reject/stale 继续阻止 master。 | 缓解中（`MITIGATING`） | Project Lead / Creative + Technical Approvers | 触发：job success 直接产生 accepted asset/master，或 UI 自动填充批准；关闭证据：P4–P9 candidate/selection/QC/rejection/staleness tests | P4–P9 | `2026-08-17` | `ADR-0009`; `K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT` |
| `R-K2-PUB-010` | 若 `publicationAllowed` 来自 provider、browser 或通用开关而不是精确 master 的权利、QC、批准与目的地事实，可能误发布或错误宣称可发布。 | 严重：未经授权发布与不可审计商业交付 | 中：当前值固定 false，但尚无正式 publication eligibility authority | P9 仅由 V5 对 exact master + rights + policy + QC + human decisions + destination 派生 eligibility；浏览器不得提交结果值；任一 stale/expired/rejected/unknown 均 false；真实发布另需 destination authority。 | 开放（`OPEN / BLOCKING PUBLICATION`） | Project Lead / Publication Authority `待提供外部事实` | 触发：任一路径可直接写 `publicationAllowed=true`，或无 named destination/territory；关闭证据：P9 fail-closed contract plus separate destination authorization | P9 + Gate A/B/C | `2026-08-17` | `ADR-0009`; `K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT` |
| `R-K2-BOOT-011` | 原 K2 durable lineage 未找到；若用测试 Ref、默认空库、直接 SQL、非原子部分写入或把历史技术证据挂到新 run，新的 root 将不可审计且可能被误称为恢复。 | 严重：权威血缘失真、重复 root、错误 P1/发布结论 | 低：一次性新 canonical root 已在正式主机原子创建并经独立只读扫描和 authenticated Public API exact-match；残余风险是后续误写、重复 root 或把历史证据错误接入新 lineage | ADR-0010 冻结一次性 Operator Application：显式新目录、同盘 staging、V5 public boundaries、无测试依赖、restart/read-only scan、secret-free receipt、no-replace 原子 rename、重复 apply 拒绝，并在 `ROOTS_READY` 停止；GET-only verifier 对 loopback authenticated Public API 的七个投影做 exact match。 | 监控中（`MITIGATED / MONITORING`） | Project Lead / Architecture Owner `蔺鹏` | 已有证据：实现 commit `57ce3d0…` 远端 CI 5/5；完整 Core 587/587；正式主机五库 quick-check/inventory 全通过；只读扫描为 `5 DB / 1 production DB / 1 run / FOUND_READ_ONLY`；七资源 API exact-match PASS；bootstrap receipt `94fad69a…`，API receipt `d4c2a52d…`。触发：再次创建 root、直接 SQL/测试 import、inventory/digest 漂移、历史 evidence 自动挂接、M6/P1 被越级推进 | Canonical bootstrap G0→G1 complete; downstream lineage monitoring | `2026-08-21` | `ADR-0010`; `K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21` |

## 5A. 2026-08-25 K2 转换复核

本节是第 5 节早期时点描述的当前覆盖层；发生冲突时，以本节和 ADR-0014 为准。
K2-001 已产生过受治理的自托管 GPU 技术证据；其中 M10 v1 的四个图像候选是
已选中、已准入的历史 `AssetVersion`，但不是当前 action-ready 来源。M11 v1 视频与
Shot 01 R2–R7 校准候选均未选中、未准入；当前视频媒体结论仍为失败且不可发布。
这些事实只降低“完全没有运行时证据”的不确定性，不关闭
`R-K2-EXEC-004`、`R-K2-LIVE-006`、`R-K2-QC-009` 或 `R-K2-PUB-010`。

| 风险编号 | 风险描述 | 影响 | 概率 | 缓解措施 | 状态 | 责任人 | 触发条件 / 验证证据 | 目标日期 / 事件 | 最近复核日期 | 关联事项 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `R-REPO-GOV-012` | Core 的生效 ruleset 与规范不一致，Frontend `main` 没有保护；未经两名独立批准或缺少完整检查的变更可能进入主线。 | 高：主线治理不能执行仓库声明的门禁 | 高：2026-08-25 远端快照直接观察 | 将两仓 `main` 设为两名批准、撤销旧批准、解决对话、线性历史并禁用普通 merge；按当前追踪规范仅允许 squash（若 Governance Owner 另行修订规范再改变策略）；禁止 force/delete/bypass，并绑定真实完整 Actions 检查；修复后保存精确远端配置证据。 | 开放（`OPEN / BLOCKING GOVERNANCE CLOSEOUT`） | Repository Governance Owner `蔺鹏` | Core approvals=`0`、merge/squash/rebase 均可用、缺 Integration Tests；Frontend 无规则。关闭需修复后重新读取远端配置和通过一次受保护 PR。 | 独立治理修复波次 | `2026-08-25` | `BRANCH_PROTECTION`; `ADR-0013 CLOSEOUT` |
| `R-K2-TRANS-013` | 复用 K2-001 root、数据库、refs、候选或 ADR-0011 例外会把 K2-002 错接到历史验证 lineage；把客户端声明当成 Owner approval，或在无 durable receipt/M5 binding 时执行多域注册，也会生成不可恢复的半套 roots。 | 严重：独立项目 provenance 失真并可能越权 dispatch | 中：现有多个 Operator 明确硬编码 K2-001，正式 durable registration 尚未实现 | 保留 K2-001 原路径作为只读历史；未确认 reviewed-import 必须记录上传、normalized、reviewed 与 canonical content digests，并由认证 actor 注入。正式确认须解析可信 Owner approval；Project/Series/Episode registration 必须具备 durable receipt、重启幂等、部分写入恢复和 M5 v2 EpisodePlanItem binding；在此之前不得开放 K2-002 multi-domain registration mutation endpoint。 | 缓解中（`MITIGATING`） | Project Lead / Architecture Owner `蔺鹏` | 出现 K2-001 ref、旧数据库路径、名称匹配、transferred exception、客户端自报 approval、无 receipt 多域写入或未绑定 M5 v1 source 即触发；关闭需可信 approval、durable canonical receipt、M5 consumer 成功与 authenticated exact-match。 | K2-002 roots gate | `2026-08-25` | `ADR-0014`; `K2-001 ARCHIVE` |
| `R-K2-INPUT-014` | K2-002 文稿引用的六张人物 PNG 未提供；EP01 所需 L1、主油灯 `lamp_primary_01`、远端油灯 `lamp_remote_01`、贞字、面部贴图与 postprocess manifest 也未就绪。L2 与提灯人灯笼 `lantern_entity_01` 是 EP02–03 延后需求。若生成链忽略对应集数的缺失输入，会伪造身份/资产 lineage。 | 严重：候选不可复现且引用权利未知 | 高：仓库与附件中均未发现这些 bytes/evidence | 只接受 exact AssetVersion ref+digest，并验证 requirement 的 episode applicability；EP01 缺少 12 项中的任一项即在 dispatch 前 fail closed，L2/提灯人灯笼必须在 EP02 前关闭；不得用文件名、占位 digest 或 K2-001 资产替代。 | 开放（`OPEN / BLOCKING PROVIDER DISPATCH`） | Creative Asset Owner / Rights Owner `待提供外部事实` | 当前证据：`EP01 12 BLOCKING / EP02–03 2 DEFERRED / NONE ADMITTED`；关闭需文件、来源/权利事实、内容 digest 和正式准入记录。 | K2-002 asset admission gate | `2026-08-25` | `ADR-0014`; `K2-002 v1.3` |
| `R-K2-FORMAT-015` | 旧 K2-001 链固定 16:9、四镜与固定帧预算，直接复用会错误处理 K2-002 的 9:16、EP01 十二镜和逐镜人物/对话约束。 | 高：构图、时长、身份与同步约束失真 | 高：代码审计已复现硬编码 | 以 additive v2 profile、显式 ShotGraph 和 authority-read zero-write dynamic preflight 纠正合同并保留 v1 兼容；704→720 延展必须由精确参数 digest 描述。Canonical N-slot append/V4 dispatch 尚未实现，不得声称 E2E 修复。 | 缓解中（`MITIGATING`） | K2 implementation owner / Architecture Owner `蔺鹏` | 任一 1280×720、四镜数组、每镜全人物、无 exact trim，或把 preflight 直接送往 V4 即触发；关闭需 canonical append/dispatch architecture acceptance、targeted + full Core tests。 | K2-002 pre-dispatch chain gate | `2026-08-25` | `ADR-0014`; `EpisodeProduction v2` |

## 6. 新增风险模板

复制以下表格行新增风险；不得覆盖或复用既有风险编号。

| 风险编号 | 风险描述 | 影响 | 概率 | 缓解措施 | 状态 | 责任人 | 触发条件 / 验证证据 | 目标日期 | 最近复核日期 | 关联事项 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `R-P0-GOV-NNN` | `<原因—事件—结果>` | `<低 / 中 / 高 / 严重；影响说明>` | `<低 / 中 / 高；评估依据>` | `<动作；责任人；完成条件>` | `<开放 / 缓解中 / 监控中 / 已接受 / 已关闭>` | `<待填写>` | `<触发条件或关闭证据>` | `YYYY-MM-DD` | `YYYY-MM-DD` | `<任务 / ADR / 评审记录>` |

## 7. 复核与升级

- 在每个阶段关口、重大治理变更和风险触发后复核相关条目。
- `严重` 影响风险应立即通知项目负责人及对应责任人，不等待例行评审。
- 风险概率或影响上升时，应重新评估缓解优先级和完成期限。
- 风险关闭前必须验证措施有效；残余风险需另行登记或明确接受。
- 接受 `高` 或 `严重` 影响的残余风险必须由项目负责人和对应专项责任人共同批准。

## 8. 阶段与授权限制

本登记册不独立授权任何业务实现。第 4 节 Phase 0 风险的缓解措施继续遵守 Phase 0
边界，不得包含业务代码、服务实现、数据库表、持久化设计或大型依赖。后续阶段风险
只有在当前 Source-of-Truth、Accepted ADR 与 Project Lead 明确工作包同时授权时，
才可进入对应受控实现；风险条目中的建议、目标事件或责任人不能替代该授权，也不能
改变 V2.3 架构、扩展里程碑或宣称风险已被接受。
