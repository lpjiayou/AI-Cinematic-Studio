# K2-002《长安刮痕》机器可读预生产候选

> 状态：`REVIEWED CORRECTION CANDIDATE / OWNER ACCEPTANCE PENDING / NOT DOMAIN
> FACT / GENERATION NOT ALLOWED / publicationAllowed=false`

`k2-002-changan-preproduction.v1.json` 把 v1.3 审校稿中的 EP01 十二镜、画幅、
身份可见性、对白同步和未就绪后期需求冻结为机器可校验的候选账本。它不是
`ExecutableShotGraph`，不含 canonical refs，不允许 Provider/GPU dispatch。

该文件故意保留以下阻断状态：

- Project Lead 尚未明确接受 v1.3；
- durable project-registration receipt 尚未实现；
- EpisodePlanItemBinding 仍待既有 Core-only 步骤；
- 每镜精确 camera contract 尚未冻结；
- EP01 的 12 项输入资产均未准入；L2 与 `lantern_entity_01` 是 EP02–03 的
  2 项延后需求，也未准入。

合同测试会核对来源 digest、720 帧总时长、连续 ordinal、三层画幅、逐镜动作/声音
以及所有禁用执行、候选准入与发布的状态。逐镜后期 operation requirement 通过
`inputAssetRequirementKeys` 显式引用顶层资产需求，不能按相似名称猜测。当前逐镜预算只是本地结构表达，没有已接受的
ShotPlan ref/version/digest/approval lineage。未来任何外部 import/registration 写入都必须
从 authenticated Public API 注入 workspace；M5 EpisodePlanItemBinding 只能使用既有
Core-only operation，不得新增 HTTP route。两者都必须把缺失项替换成同一 authority
中的 exact refs+digests。
