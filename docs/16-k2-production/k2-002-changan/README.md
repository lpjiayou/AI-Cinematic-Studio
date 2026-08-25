# K2-002《长安刮痕》预生产包

当前精确仓库授权见
[`ACS-K2-002-GOV-RB1`](../../../governance/ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md)。

## 接受状态

| 项目 | 状态 |
| --- | --- |
| 原始输入 | 上传 bytes `SHA-256 8dec72d6b…`；仓库 LF-normalized UTF-8 `SHA-256 77734389…` |
| 审校版本 | `v1.3 / REVIEWED CORRECTION CANDIDATE / OWNER ACCEPTANCE PENDING` |
| Canonical project | `NOT REGISTERED`；受控、durable、幂等的 Public API apply 尚未实现 |
| Local draft evidence model | `StoryboardDraft + CreativeShotDraft:* + ShotPlanDraft`；隔离验证停在 `SCRIPT_VALIDATED`，未 apply 到 live canonical host |
| ExecutableShotGraph | `NOT COMPILED` |
| Camera contract | `NOT_READY`；不得从 `editorialShotSize` 合成 lens / angle / movement |
| 必需资产 | `14 TOTAL / EP01 12 BLOCKING + EP02–03 2 DEFERRED / NONE ADMITTED` |
| Postprocess manifest | `NOT_READY` |
| Provider / GPU dispatch | `NOT STARTED / NOT AUTHORIZED` |
| Publication | `publicationAllowed=false` |

## 剧本审校结论

v1.2 的系列钩子、30 个约 30 秒竖屏单集结构，以及 EP01–03 共 36 镜的戏剧推进
可作为预生产基础，但不能原样编译。v1.3 已修正以下阻断项：

- EP01 只揭示残卷刮痕中的“贞”，不提前声称完整姓名；完整姓名仍留在 EP14–16 回收；
- 灯笼色温与实体称谓连续性被冻结，不再出现未定义的“灯焰转色”或“他/它”漂移；
- 面部 Identity Lock 与无面灯笼实体分离；
- 可见台词镜头改为画外音或不可见嘴部，未把未验证 lip-sync 写成既成能力；
- 补足故事内部的证据、追捕原因和结局事实，同时明确这是历史幻想，不声称史实准确；
- EP01 的 12 镜时长固定为 720 帧，生成与时间线帧数采用明确的
  `latent + exact trim` 合同。

## 生成链路审计

| Gate | 正确入口 | 当前结论 | 阻断条件 |
| --- | --- | --- | --- |
| Source | 声明 reviewed-source provenance 的首次整稿只能走 unconfirmed `reviewed-import`；Core 生成 scene refs 与 canonical content digest | `importedByRef` 由认证 service credential 注入，不代表已解析具体自然人或 RBAC；三个外部 document digest 仅是该凭据下未独立验证的 declarations；v1.3 未获 Owner Acceptance，未 apply | 禁止把 reviewed source 伪报为 AI generation；generic generation/manual-edit 不携带该 provenance，也不授权 K2-002 导入；generic confirm 对整条 import lineage 阻断；正式确认须有 trusted Owner approval resolver |
| Roots | 幂等创建独立 Project / Series / Episode | `NOT IMPLEMENTED FOR DURABLE APPLY` | durable receipt、可信审批、M5 v2 EpisodePlanItem binding 均缺失；禁止复用 K2-001 数据库或 refs |
| Output profiles | 生成 `704×1280`、剪辑 `720×1280`、发布 `1080×1920` | additive v2 合同候选与测试已形成；不是 live domain fact | 旧 16:9 v1 不能承载本项目 |
| ShotPlan draft | EP01 12 个显式镜头及逐镜人物/对话约束 | additive v2 repository candidate 在一个 `G3_SCRIPT_VALIDATION` 原子 append 中写入 `StoryboardDraft`、12 个 `CreativeShotDraft:*` 与 `ShotPlanDraft`，并停在 `SCRIPT_VALIDATED`；未在 live canonical host 执行 | ShotPlan approval 与 camera contract 均未验证；禁止写 `G3_SHOT_GRAPH`、生成 `ExecutableShotGraph`、进入 `SHOTS_COMPILED`，或从 editorial size 发明 lens/angle/movement |
| Image candidates (M10 preview only) | Public API → V5 current-authority read | authenticated public zero-write image-preflight implementation 已接入，server-side 绑定 current `ShotPlanDraft` / `CreativeShotDraft` refs+digests；camera 为 `NOT_READY` 且返回 `CAMERA_CONTRACT_NOT_READY` blocker；尚未在 K2-002 live canonical lineage 上执行 | canonical M10 append、V4 MediaJob/Attempt 与 dispatch 均未接入；M11/video preflight 未实现；禁止走 detached provider experiment |
| Input assets | 精确 AssetVersion refs + digests | `EP01: 12 BLOCKING NOT_READY / EP02–03: 2 DEFERRED` | EP01 缺六张人物 PNG、L1、主/远端油灯、贞字、面部贴图与 postprocess manifest；L2 与 `lantern_entity_01` 仅登记为 EP02–03 延后需求 |
| Postprocess | 704→720 左右各 8 px 受控延展；无裁切、无拉伸 | 需求已冻结，manifest 未生成 | 不得用虚构 artifact ref/digest 宣称完成 |
| Selection/admission | 人工 exact-ref/digest 决策 | `NOT STARTED` | 技术 PASS 不能自动准入 |

因此，审计结论是：原 K2-001 生成链路不能直接用于 K2-002；当前仓库形成了
additive v2 Shot/Profile 合同和非执行型 ShotPlan 草稿实现，以及能够在调用时从
current draft authority 读取 exact refs+digests 的零写 M10 image-preflight
implementation。草稿事实只通过 `G3_SCRIPT_VALIDATION` 进入隔离证据并停在
`SCRIPT_VALIDATED`；它们不是 `ExecutableShotGraph`，不会推进 `SHOTS_COMPILED`。
该实现尚未对 K2-002 live canonical lineage 执行，不是 canonical 生成主链或生成成功。
EP01 当前有 12 项硬阻断资产；L2 与 `lantern_entity_01` 是
EP02–03 延后需求。v1.3 Owner Acceptance、durable registration receipt、M5 binding、
ShotPlan/camera approval、canonical production refs、EP01 输入资产、后处理 manifest、
rights/provider/budget/runtime authority 与 canonical M10 append 任一未就绪时都必须
fail closed；即使这些条件成立，Provider/GPU dispatch 仍须单独授权。M11/video
preflight、candidate、selection 与 admission 均未实现或开始。

## 文件

- `source/K2-002-CHANGAN-SOURCE-v1.2.md`：原输入的 LF-normalized UTF-8 文本，
  仅作来源证据；原上传 bytes 的 CRLF/LF 差异已由双 digest 明确登记；
- `K2-002-CHANGAN-SERIES-AND-EP01-03-v1.3.md`：审校修订候选；只有 Project Lead
  明确接受后才能作为 reviewed-import 的正式输入。
- `experiments/k2-002-changan-preproduction/k2-002-changan-preproduction.v1.json`：
  EP01 十二镜机器可读候选与 fail-closed 准入账本；不是 domain fact、approved
  ShotPlan 或 `ExecutableShotGraph`。
