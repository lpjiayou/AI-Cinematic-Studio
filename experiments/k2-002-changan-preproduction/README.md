# K2-002《长安刮痕》机器可读预生产候选

当前精确仓库授权见
[`ACS-K2-002-GOV-RB1`](../../governance/ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md)
与 [`ACS-K2-002-SCRIPT-RB2`](../../governance/ACS-K2-002-SCRIPT-V1-4-EXACT-DIGEST-REBASELINE.md)。

> 状态：`V1.4 REPOSITORY-REVIEWED REBASE CANDIDATE / OWNER ACCEPTANCE PENDING / NOT DOMAIN
> FACT / GENERATION NOT ALLOWED / publicationAllowed=false`

`k2-002-changan-preproduction.v1.json` 原样保存 v1.3 历史映射。
`k2-002-changan-preproduction.v2.json` 把当前仓库审校 v1.4 中的 EP01 十二镜、
画幅、身份可见性、对白同步、空白名牌和未就绪后期需求冻结为机器可校验的候选账本。它不是
`ExecutableShotGraph`，不含 canonical refs，不允许 Provider/GPU dispatch。

在隔离验证边界中，该账本只可驱动非执行型草稿语义：一个原子的
`G3_SCRIPT_VALIDATION` append 产生 `StoryboardDraft`、12 个
`CreativeShotDraft:*` 与 `ShotPlanDraft`，状态停在 `SCRIPT_VALIDATED`。它不会写入
`G3_SHOT_GRAPH`，不会产生或投影 `ExecutableShotGraph`，也不会进入
`SHOTS_COMPILED`。`editorialShotSize` 不是 camera authority；camera contract 始终为
`NOT_READY`，不得合成 lens、angle 或 movement。

该文件故意保留以下阻断状态：

- Project Lead 已授权把 exact v1.4 source 和 Core rebase 写入仓库，但尚未明确接受剧本内容；
- durable project-registration receipt 尚未实现；
- EpisodePlanItemBinding 仍待既有 Core-only 步骤；
- 每镜精确 camera contract 尚未冻结；
- EP01 的 16 项输入资产均未准入；EP02–03 的 L2、提灯人、铜镜、腕疤、
  “观/十”字形与分集 postprocess manifest 共 8 项延后需求也未准入。

外部 `final-assets-v1.2.zip@532765d9…` 仅登记为候选证据：其 bytes 存在，但仍绑定
v1.3，rights、exact requirement mapping、v1.4 重基线和 AssetVersion admission 均未完成。

合同测试会核对来源 digest、720 帧总时长、连续 ordinal、三层画幅、逐镜动作/声音
以及所有禁用执行、候选准入与发布的状态。逐镜后期 operation requirement 通过
`inputAssetRequirementKeys` 显式引用顶层资产需求，不能按相似名称猜测。当前逐镜预算
只是本地结构表达，没有已接受的 ShotPlan ref/version/digest/approval lineage；隔离证据
中的 draft ref/revision/digest 不能冒充该 lineage。

authenticated zero-write dynamic-media preflight 只能 server-side 读取 current
`ShotPlanDraft` / `CreativeShotDraft` refs+digests，返回
`CAMERA_CONTRACT_NOT_READY` 等 blocker；它不写 evidence，不创建 candidate，不准入或
dispatch。未来任何外部 import/registration 写入都必须从 authenticated Public API
注入 workspace；M5 EpisodePlanItemBinding 只能使用既有 Core-only operation，不得新增
HTTP route。两者都必须把缺失项替换成同一 authority 中的 exact refs+digests。
