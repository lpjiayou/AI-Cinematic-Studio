# K2-001 历史验证归档

- Archive decision date: `2026-08-25`
- Disposition: `HISTORICAL VALIDATION EVIDENCE`
- New dispatch: `CLOSED`
- M10 v1 image selection/admission: `HISTORICAL / 4 IMAGE ASSETVERSIONS / NOT ACTION-READY`
- M11 v1 and Shot 01 R2–R7: `UNSELECTED / NOT_ADMITTED`
- Episode Master / export: `NOT_CREATED`
- Publication: `NOT ALLOWED`

## 归档范围

K2-001 的治理、脚本、运行手册、机器可读候选、receipt 描述和测试仍保留原路径，
以免破坏历史链接或把旧文件伪装成新 lineage。它们只证明各自明确记录的控制面、
技术验证或 M10 v1 历史图像准入事实；不证明 M11 当前视频集合通过语义视觉审阅，
也不证明任何媒体可发布。

下列历史 Operator 只能用于读取或复核 K2-001 证据，不得用于启动 K2-002：

- `scripts/k2_canonical_lineage_bootstrap.py`
- `scripts/k2_canonical_lineage_api_verify.py`
- `scripts/k2_m6_draft_operator.py`
- `scripts/k2_preboot_validate.py`

ADR-0011 的内部自托管例外只绑定原精确 K2-001 `workspaceRef` 与
`productionRunRef`；没有自动继承规则。ADR-0012 的四个技术验证视频候选仍为
`UNSELECTED / NOT_ADMITTED / publicationAllowed=false`。

## 主线接受与媒体结论

ADR-0013 的非 GPU 控制平面在 Core
`6d28a53f3a077f032e341a87412b19b37c00bb1e` / tree
`369c3b1479f3136cc32fcbc4efd0fa24e4964058` 和 Frontend
`5b36aac09fc10db04455d9ee287060232a521e5f` / tree
`fd20b7d75c5ff379842462964d4e4f1d860d334d` 上正式接受为
`OWNER ACCEPTED / COMPLETE / MAIN-VERIFIED`。该接受不改变 K2-001 媒体结论：
M10 v1 四个图像 `AssetVersion` 仅保留为历史准入事实；M11 v1 与 Shot 01 R2–R7
候选仍为失败或未选中、未准入，K2-001 整体仍不可发布。

完整事实边界与远端治理差异见
[`K2_001_ADR_0013_MAIN_CLOSEOUT_2026-08-25.md`](../../governance/K2_001_ADR_0013_MAIN_CLOSEOUT_2026-08-25.md)。

## 不可推导的历史事实

2026-08-25、K2-002 工作分支发布前的归档审计快照能证明 Core 当时有一条分支与
51 个指向一致归档对象的标签；该快照本身不能
独立还原历史起点恰为 52、全过程没有 force、上一轮临时认证清理或某次测试的原始
`665.763s` 用时。这些内容如被引用，只能标为上一轮记录，不得提升为当前快照证明。
