# M10/M11 Spike-0 E4 — Evidence Index

Status: `GENERATED_REFERENCE`; reviewed: `2026-09-09`.
Owner: Project Lead / Documentation Governance Owner.
`currentStateClaimsAllowed=false`; this index grants no execution or architecture authority.

## 1. Identity and custody rules

分析基线为 Core `f007ab3e93c3fb7f5e8b3b7f81c34fec28858176`，Tree
`b5ef06d0b4557b979cd8ab4acb02790d35ec2223`。新 docs tip 不改变 E4 执行代码 pin。

本次实际收到交接 ZIP 后，先将外部独立保存的 SHA-256 文件与 ZIP 字节比对，再安全解包：53 个普通文件，CRC/路径/类型检查通过，内部清单覆盖其余 52 文件且全部相符；43 份 source_readonly 副本逐一匹配 SOURCE_INVENTORY 中的字节数与 SHA-256。上传任务正文与包内 EXECUTOR_TASK 字节相同。文件名后缀不参与身份判断。

保护/保管分类如下；表中仅给非敏感名称和字节身份，不提供私有目录、主机端点、会话、凭据或下载入口。

- `HANDOFF_FULL`：本次收到的完整交接包；不等于完整 E4 raw 证据备份。
- `REVIEW_COPY`：43 份审核副本中的原始回执或报告，原字节保留在私有交接包；不整体入 Git。
- `ARCHIVE_MEMBER`：从指定审核 ZIP 提取的成员副本，本次校验其字节；不表示本次收到该 ZIP 原体或远端完整 raw 包。
- `LATER_SUMMARY`：事后编写的审核/文档化总结，不能冒充最初终端采集。
- `SEALED_ORIGINAL_COPY`：证明/profile/绑定原始 JSON 的精确副本，保持只读、不改写、不重签。公开文档只作非可加载摘录。
- `REMOTE_CUSTODY_RECORD`：审核窗口于 13:05 UTC 在既在线 A100 上重算的大小与摘要。本次 docs 执行未重连该主机，记录不保证跨停机永久保存。
- `REFERENCE_ONLY`：只有参考身份或记录，不能声称获得原件。
- `PUBLIC_DERIVATIVE`：经脱敏的新 Markdown；摘要属于派生字节，不沿用原件摘要。

以下行的阶段代号明确所引源观察时点与采集基线；它不是推测文件创建时间。未记录精确时间的项标为未记录，不使用文件 mtime 充当采集时间。

## 2. Observation groups

| 代号 | 所引观察或编制时点（UTC，2026-09-09，另注明者除外） | 采集/分析基线与边界 |
| --- | --- | --- |
| G1 | 07:47:22.089–07:48:16.150；后写审核具体编制时间未记录 | 新实例现场旧 Core 0a6962be；审核参考 f007ab3e；142 份源码解析/147 项清单为前次包审核，不是本次运行 |
| G2 | 07:07:04 连接器核验；报告编制时间未记录 | 接入观察；E4 参考 f007ab3e；不授予运行权限 |
| G3 | 08:31:16.959911–08:31:26.814347；08:38:27 清理 | ComfyUI feca51a8；新实例驱动 560.35.03；当时未使用完整 f007 工具生成证明 |
| G4 | 08:45:19–08:57:18.859758 | 对 G3 JSON 作 61 项复核；对照 f007 与现场旧工具；无新服务 |
| G5 | 09:07:15.602176 装配；09:09:14.200816 导入；09:11:35.110749 收口 | f007ab3e / b5ef06d0 完整 632 文件工具快照 |
| G6 | 09:39:31.208414–09:40:20.297120；证明 observedAt 09:39:37.515060Z；09:44:33.327132 封包 | 原版 f007 工具、同一正式证明服务进程；历史技术证明 |
| G7 | 10:46:47.891084 收口；子检查开始精确时间见原件或未记录 | f007；30/30 较早离线适配；精确 E3 绑定当时未完成 |
| G8 | 11:22:23.568870 | f007；三项只读核对；所读 E3 认证记录为 2026-09-08 历史记录 |
| G9 | 11:59:18.809084 现场身份；12:05:01.775152 绑定报告 | f007；E3 原包相同字节与历史 G6 证明；69/69，不是新 currentness |
| G10 | 2026-09-09 提案编制；具体时分未记录 | f007；ADR 完整审批 PENDING；后写设计稿 |
| G11 | 2026-09-09 交接整理；A100 清单 observedAt 13:05:05.003319+00:00 | f007；文件保管清点，不重做 runtime/数据库/模型 |
| G12 | 2026-09-09 13:45:25.320373+00:00 | 本次 CPU 固定源码补核；44/8/54 为独立新观察 |

## 3. Received handoff and supporting inventories

所有下列原件均留仓库外；只发布索引。交接包不是模型、数据库或所有远端日志的完整保全。

| 类别 / 原文件名 | 字节数 | SHA-256 | 阶段 / 覆盖 |
| --- | ---: | --- | --- |
| HANDOFF_FULL / `ACS_E4_BASELINE_DOCS_HANDOFF_20260909.zip` | 146553 | `286e4c5fe6334adf95bfb0341c39e452a04fa8edd3726742e16662c95336291f` | G11；本次实际收件，53 文件 |
| LATER_SUMMARY / `EXECUTOR_TASK.md` | 17108 | `06028adebe75bd28acd438b49c91179b7e7e09d8d2dd03b5f08ca90d8649514c` | G11；私有清单/汇总原件 |
| LATER_SUMMARY / `SOURCE_INVENTORY.json` | 42155 | `a63ea1e9fc4eff2f469ffe4321b749411672719de5acd913689d74d4399bf333` | G11；私有清单/汇总原件 |
| LATER_SUMMARY / `A100_SOURCE_INVENTORY.json` | 7117 | `280780253d25edc408cede49c253364d1dea425e3b0935c46e658eac9570ae87` | G11；私有清单/汇总原件 |
| LATER_SUMMARY / `ARCHIVE_INSPECTION.json` | 2946 | `56d7f9cf390cce8ba56e225667d6aeff1c6b8746a5d7d2e6188ee2bb77622dcc` | G11；私有清单/汇总原件 |
| LATER_SUMMARY / `REPOSITORY_FILE_PLAN.md` | 4797 | `0a0f341986a012abd4cefd1d14bb45d628217fef8d735f57704ab3a7d42c8bf9` | G11；私有清单/汇总原件 |
| LATER_SUMMARY / `DISPATCH_AUDIT_HANDOFF.md` | 5410 | `6118cbe21dff3bd5ef9d8737126138a42a15d02eaed8ed7d033649b08ec39e5c` | G11；私有清单/汇总原件 |
| LATER_SUMMARY / `REFERENCE_ONLY_HISTORY.md` | 1746 | `aa8bd2d523e31011634687e15450b5bab28c47529a3760ec39431d2c418a8200` | G11；私有清单/汇总原件 |
| HANDOFF_MANIFEST / `HANDOFF_SHA256SUMS.txt` | 7101 | `942832c81d8b8ee55c2241eb84e073c7c838c9ddf67d47875158be2352e6c9f7` | G11；私有清单/汇总原件 |

SOURCE_INVENTORY 原清点 72 项，选入本交接 43 份审核副本，另有 17 个原归档成员来源映射（包含在这 43 份中）。未提供的操作脚本、预算原文及原归档不能因列在库存中而被声称已经收件。

## 4. Forty-three exact review copies

每行保护状态均为私有原字节只读副本；保管于完整交接包，不公开原始 JSON。名称前的来源组用于区分同名 REPORT/RECEIPT；不是当前机器路径。

| 原文件 / 审核来源组 | 字节数 | 原字节 SHA-256 | 阶段 | 类别 |
| --- | ---: | --- | --- | --- |
| `E4_CURRENT_INSTANCE_AUDIT.json` | 4561 | `1fb8113ac9fcce48b6239ec7d369716d13b2ca63674b7eaede8f832c85a553cd` | G1 | LATER_SUMMARY |
| `E4_CURRENT_INSTANCE_AUDIT.md` | 7262 | `0d9296ec771eda1de6433fb78feba5bfc0f5a4308787d2719539ce898d0e4c18` | G1 | LATER_SUMMARY |
| `E4_THREE_CHECKS_FRAME_EVIDENCE.json` | 4519 | `d5d58ab2ec1da9c8142627e14bb991c873bcb462ebe11a7f5fedaf4948bf0888` | G8 | REVIEW_COPY |
| `E4_THREE_CHECKS_READ_ONLY_AUDIT.json` | 3611 | `df2a50b57fbb7eaf974240d4cd8b19d3ce0c0011f1d3b603b2409f134f40c8a9` | G8 | LATER_SUMMARY |
| `adr_0022_design_review/ADR-0022-generation-dispatch-grant-v1.0-PROPOSED.md` | 36889 | `23455b3d4a211f5e28b3563703c94551699e379a5b08f01034967b234065bac6` | G10 | LATER_SUMMARY |
| `e4_contract_audit_20260909/E4_CONTRACT_CLOSEOUT_REPORT.md` | 7921 | `d289f04fcf5699056fae7e3ccca7482e5362ad4582160d9914bd279e4153e825` | G4 | LATER_SUMMARY |
| `e4_contract_audit_20260909/NODE_CONTRACT_REVIEW.json` | 6031 | `efb7570888f3d62a65f2b43382ce08fc52963124c73c40c014735f6fd53c30dd` | G4 | REVIEW_COPY |
| `e4_contract_audit_20260909/TOOL_CONTRACT_AUDIT.json` | 2179 | `991ff7bd58cc416124ad3f556b5725a48d6f9f5eb56c62452a99d982e23537c1` | G4 | LATER_SUMMARY |
| `e4_frozen_tool_snapshot_20260909/E4_FROZEN_TOOL_SNAPSHOT_REPORT.md` | 6402 | `22d09e9af8fcd97199c3c69a7eb43b55ed06624bc8c85851bcf1b328e95357ef` | G5 | LATER_SUMMARY |
| `e4_frozen_tool_snapshot_20260909/IMPORT_CHECK_RECEIPT.json` | 1292 | `defd4e568b5968ae8e2ef8da6c1398f85a6a36e7c6a3d7b6df814ce516c67871` | G5 | REVIEW_COPY |
| `e4_frozen_tool_snapshot_20260909/SNAPSHOT_RECEIPT.json` | 1176 | `7a22b4ef41fc0955fc275b8087c79f5bb1ec1ff78d3fce1bdcd530e609f9a4e1` | G5 | REVIEW_COPY |
| `e4_plan_runtime_20260909/REPORT.md` | 6046 | `8ec7cacca190692d05ed4caa7b6a5995b1bcc1075dd30030073aaf9f0a35df3c` | G7 | LATER_SUMMARY |
| `e4_profile_attestation_20260909/I2V_ATTESTATION.json` | 2002 | `c58d70cfcf6dfd77ae7c25b9d789e9f133b7e6a759730a8947cf6eed9de1516c` | G6 | SEALED_ORIGINAL_COPY |
| `e4_profile_attestation_20260909/LOCAL_BILLING_REVIEW.json` | 824 | `f04bdf6f46e63324c000d7d84dfb7cdadb82cc580b06ed7e723a567ac782524f` | G6 | REVIEW_COPY |
| `e4_profile_attestation_20260909/OPERATOR_PROFILE.json` | 1917 | `04fc2cbad12c43ee8cc93c91bdfced8a4e2962d314cf54ac051255178ef784cb` | G6 | SEALED_ORIGINAL_COPY |
| `e4_profile_attestation_20260909/PROFILE_ATTESTATION_BINDING.json` | 805 | `5ba3c89375b163ce439175d24e23a2f13b144fdfc6214e04189fd5537fe30ae0` | G6 | SEALED_ORIGINAL_COPY |
| `e4_profile_attestation_20260909/REPORT.md` | 8094 | `7bbc656c1d77afa6eb0c7a7e4f004d42df43a93718c461f7177a43be22ce3479` | G6 | LATER_SUMMARY |
| `e4_r5_live_verified/E4_R5_LIVE_METADATA_REPORT.md` | 7143 | `5c79cb40fe6fb3276354c4b0cebbc5123dadea1c9beb398fbbb98005909fe568` | G3 | LATER_SUMMARY |
| `e4_r5_live_verified/LIVE_RECEIPT.json` | 8214 | `badc2d72d40ae1c1088e242042ed31e85bdfd478f664096dd92666fe2add8ca3` | G3 | REVIEW_COPY |
| `e4_r5_r2_connector_verified/CONNECTOR_VERIFICATION_20260909T070704Z.json` | 1587 | `6da6fe3a2de05235f34d634f0850f9bb9e173890e11cf19f532456692198de41` | G2 | REVIEW_COPY |
| `e4_r5_r2_connector_verified/E4_R5_R2_CONNECTOR_VERIFIED_REPORT.md` | 4526 | `fbf9b03a9fc35d6fc0cc6ffb495948c76ec57ba49aafff00f5f7d3c25c43850e` | G2 | LATER_SUMMARY |
| `e4_step1_exact_binding_20260909/BINDING_REVIEW.json` | 3805 | `0a39b3e4bc1d34cb31193c24a2510ec0a0e6f1ead717f90580ad05209ce67f50` | G9 | REVIEW_COPY |
| `e4_step1_exact_binding_20260909/CONFLICTS_AND_UNRESOLVED_ITEMS.json` | 2281 | `0b5a42ce974a0812a8bfca77b22f11dac2b5ceadacbff631907dd9f699c3b504` | G9 | REVIEW_COPY |
| `e4_step1_exact_binding_20260909/COST_UNVERIFIED_ITEMS.json` | 1449 | `a2aace4ca929dac8dce707b62fc7e4dfc8d08078cae3dd92c7fb47fbb8602422` | G9 | REVIEW_COPY |
| `e4_step1_exact_binding_20260909/E3_ORIGINAL_SOURCE_EXCERPTS.json` | 49560 | `a41e60a7167fc8d8bbc0235e48f7b74eb19cc517bdedee51cd9a2a1f3ddb5dc9` | G9 | REVIEW_COPY |
| `e4_step1_exact_binding_20260909/REPORT.md` | 8916 | `3fa7550d36d22ecafb93c9b417aa2e125db0af986023ff6dea6069460fa74bcb` | G9 | LATER_SUMMARY |
| `E4_CURRENT_INSTANCE_20260909T074722Z_kdu9r91x/REPORT.json` | 59452 | `ba716f1e22317553fdc0387aaf90df3198394404b11c95206af3b4bf04d68308` | G1 | ARCHIVE_MEMBER |
| `E4_CURRENT_INSTANCE_20260909T074722Z_kdu9r91x/model-text_encoder.json` | 690 | `9a69047e030e15a547494f1b9dcab28294d6c25cbf898329007f9e97c709b245` | G1 | ARCHIVE_MEMBER |
| `E4_CURRENT_INSTANCE_20260909T074722Z_kdu9r91x/model-unet.json` | 678 | `488bd6e0e3dd348af5ccb8eef7abbc6d1fef8df73af25177205ac886cc489580` | G1 | ARCHIVE_MEMBER |
| `E4_CURRENT_INSTANCE_20260909T074722Z_kdu9r91x/model-vae.json` | 654 | `cde0e9599c89ad756564b3efd8dd6cd0b97e19dadad26a481bfd1d05f4f7af66` | G1 | ARCHIVE_MEMBER |
| `E4_FROZEN_TOOL_SNAPSHOT_REVIEW_20260909/FINAL_RECEIPT.json` | 1717 | `bfe3334b116119c4c9abbf1de69c1e48c4f606b87e31d8371fd2fddf0cb12c8e` | G5 | ARCHIVE_MEMBER |
| `E4_FROZEN_TOOL_SNAPSHOT_REVIEW_20260909/TRANSFER_VERIFICATION.json` | 884 | `ddb12d5b0230f35d5d63d9723f9f2b2666f96d0b3c485faea6343d3ae2294972` | G5 | ARCHIVE_MEMBER |
| `E4_PLAN_RUNTIME_COMPATIBILITY_REVIEW_20260909/OFFLINE_COMPATIBILITY_REVIEW.json` | 4312 | `86497502d6e505affd8b0f2096ad80f96b0394762058e6a1635622934d9ec504` | G7 | ARCHIVE_MEMBER |
| `E4_PLAN_RUNTIME_COMPATIBILITY_REVIEW_20260909/PARAMETER_PROPOSAL_NOT_EXECUTABLE.json` | 1606 | `a2a35263354d705f5339ba55a49d797a6c4ea720ddc72bf6d1438ea6d15d3bd6` | G7 | ARCHIVE_MEMBER |
| `E4_PLAN_RUNTIME_COMPATIBILITY_REVIEW_20260909/FINAL_OBSERVATION.json` | 535 | `ea6b78a66fcdd54dbcbf959607ed7dea17fe997312325ca7f464309e7a0126e6` | G7 | ARCHIVE_MEMBER |
| `E4_PROFILE_AND_V2_I2V_ATTESTATION_REVIEW_20260909/LOCAL_REVIEW.json` | 1121 | `e1ca5222a68825b680507efde2e0779fe595bc88e3ea3b8d7911503c65296c28` | G6 | ARCHIVE_MEMBER |
| `E4_R5_LIVE_METADATA_REVIEW_SUBSET_20260909/I2V_METADATA_CHECK.json` | 626 | `6b8cf23e73bd18790c86da1bedf9891620817bb21010966abda85c469a1c0d62` | G3 | ARCHIVE_MEMBER |
| `E4_R5_LIVE_METADATA_REVIEW_SUBSET_20260909/MODEL_NAME_CHECK.json` | 1280 | `721233949577985bcbe9bd7d3515d788fe7ba0e33d39f60a0fa3e9d2d20eb34a` | G3 | ARCHIVE_MEMBER |
| `E4_R5_LIVE_METADATA_REVIEW_SUBSET_20260909/queue-after-summary.json` | 35 | `91405b067fdbb70b17da56962d8176f2ddd1fd7357d8e5a06860bd30524b79e9` | G3 | ARCHIVE_MEMBER |
| `E4_R5_LIVE_METADATA_REVIEW_SUBSET_20260909/queue-before-summary.json` | 35 | `91405b067fdbb70b17da56962d8176f2ddd1fd7357d8e5a06860bd30524b79e9` | G3 | ARCHIVE_MEMBER |
| `E4_STEP1_EXACT_BINDING_REVIEW_20260909/CHECKS.json` | 9484 | `f98f759b7c44d42711068c9de4ea93e7d966fe88b52bfb09f9f19c93ae14654a` | G9 | ARCHIVE_MEMBER |
| `E4_STEP1_EXACT_BINDING_REVIEW_20260909/STEP1_RECEIPT.json` | 1744 | `1b785e32b8ad0b563431734caf405e0135712ba97f32102c5da8ef071d8cce74` | G9 | ARCHIVE_MEMBER |
| `E4_STEP1_EXACT_BINDING_REVIEW_20260909/A100_READ_ONLY_OBSERVATION.json` | 2857 | `fc249bb9f01517f99de13e675dd265bbc9b52f7864d861df199f7b06d1d04e5b` | G9 | ARCHIVE_MEMBER |

表中 E3 原始摘录是既有认证记录的解析副本，不是新的数据库读取。AssetVersion/Authority 原始对象未改动。账单审核 JSON 的存在只证明该私有材料被交接；账户费率、取整、持续费用及余额仍未核实。

## 5. Archive custody — bodies are not implied by filenames

以下 7 份 ZIP 由审核窗口按 ARCHIVE_INSPECTION 完成 CRC、安全路径和内部摘要核对；本次交接只带审核副本及检查记录，未包含这 7 份 ZIP 本体。每行是 `REVIEW_ARCHIVE_RECORD`，保护状态为私有，保管证明限定 G11 清点及其所引阶段。

| 审核 ZIP 原名 | 字节数 | 原归档 SHA-256 | 前次条目数 / 内部摘要数 |
| --- | ---: | --- | --- |
| `E4_CONTRACT_CLOSEOUT_REVIEW_20260909.zip` | 12283 | `5a502a0d57206a6343be135030daa45c1ef34204fb215e124b639cc27d014f2a` | 7 / 6 |
| `E4_CURRENT_INSTANCE_20260909T074722Z_kdu9r91x.zip` | 514625 | `49a25dfa7ca8019df1aefcd4a27714b54705ade343857041bc509717f5c0f66e` | 148 / 147 |
| `E4_FROZEN_TOOL_SNAPSHOT_REVIEW_20260909.zip` | 9176 | `1b0ca3ea72f968e866b01e32fc066b72bf39aee0e1adb4700c9b9d3a45ac3768` | 9 / 8 |
| `E4_PLAN_RUNTIME_COMPATIBILITY_REVIEW_20260909.zip` | 14445 | `e3ef4092d3b1dfcce3c60447027b306f77e24780c5ef8a8a3418e3419ff10bf0` | 9 / 8 |
| `E4_PROFILE_AND_V2_I2V_ATTESTATION_REVIEW_20260909.zip` | 44900 | `9cbb35e1572df4e1672699033af2ce767140012069ea73608d26f2c4b10c8364` | 11 / 10 |
| `E4_R5_LIVE_METADATA_REVIEW_SUBSET_20260909.zip` | 16671 | `bb269887d34c6533a1311764fbfa629cc8e958c9c7583d89842b4de1c8e578dd` | 11 / 10 |
| `E4_STEP1_EXACT_BINDING_REVIEW_20260909.zip` | 29734 | `057b8bd0dda0d2cfe10a4236c0c80b9e32ef580578d5ef4342e216ef33d19b18` | 13 / 12 |

A100 清单的 21 个精确文件于 G11 只读重算大小和 SHA；该轮没有下载文件，也没有重新解包全体远端归档。本次 docs 任务完全使用已提供副本，`REMOTE_EVIDENCE_RECHECK_SCOPE=NONE_THIS_DOCS_TASK`。以下归档行均为 `REMOTE_CUSTODY_RECORD`，不可加载、不得公开原包，也不声称仍在线或已有持久备份。

| 远端原归档名（省略目录） | 字节数 | 原字节 SHA-256 | 角色 / 源观察阶段 |
| --- | ---: | --- | --- |
| `E4_CURRENT_INSTANCE_20260909T074722Z_kdu9r91x.zip` | 514625 | `49a25dfa7ca8019df1aefcd4a27714b54705ade343857041bc509717f5c0f66e` | CURRENT_INSTANCE_ORIGINAL_ARCHIVE；G1 |
| `acs-e4-frozen-tools-ep3anxz3-evidence.tar.gz` | 56562 | `39cb40f5431be1919cf828fdcc3452f4db7e195457688128bb71c21bffcb05c4` | FROZEN_TOOL_EVIDENCE_ARCHIVE；G5 |
| `acs-e4-plan-runtime-20260909-r1.tar.gz` | 12252 | `9372dcf4af46fad0d995ecb58ca4656ab28cacdba25e6f364167a7b016df20af` | EARLIER_OFFLINE_PARAMETER_REVIEW；G7 |
| `acs-e4-r5-contract-phvr34ec.tar.gz` | 16490 | `de117aae828ed850b06ef81796c94049c9cd906a6518b92c48f4cff66eac30f3` | NODE_AND_OLD_TOOL_CONTRACT_AUDIT；G4 |
| `acs-e4-r5-live-20260909T083116Z-310c7bc4-closeout.tar.gz` | 112393 | `bc565102cea506cb684e40888b23967ea6b73f966d6b1ce466bd87a3a270c8a4` | LIVE_METADATA_CLOSEOUT_ARCHIVE；G3 |
| `acs-e4-r5-live-20260909T083116Z-310c7bc4-full.tar.gz` | 107678 | `104034ef3b3274d8da3641b5b85da1c6993ae7f0a33534bbdaa98033f418446c` | LIVE_METADATA_EARLIER_ARCHIVE_DISTINCT；G3 |
| `acs-e4-v2-20260909T093931Z-2267a946-evidence.tar.gz` | 94121 | `2127a60dd43672e969d11817447d36535b4ebf5a6d6c7149883a0e5174499bd8` | FORMAL_V2_ATTESTATION_FULL_ARCHIVE；G6 |
| `SPIKE_0_E3_R6_POST_E3H_ELIGIBLE_INPUT_LINEAGE_BUNDLE.tar(4).gz` | 1428336 | `ab4399d2ad769a8f8a9fc8ca0368a2e6d8f721ab76d6499a077d0a1a586dcfc2` | EXISTING_E3_INPUT_BUNDLE_PRIVATE_NO_GIT；G8/G9；E3 本体属 2026-09-08 |

其余 13 项远端清单为快照、实时服务、正式证明、模型合同及计划审核回执；本次已提供的副本见第 4 节。未提供的完整 raw object_info、服务日志、完整执行回执及全源码清单不能从审核子集重建。当前实例原 ZIP 的内部一致性检查不等于最初上传时有独立来源认证；本次交接包外部 SHA 的通过不追溯改变该事实。

## 6. R3/R4 custody distinction

REFERENCE_ONLY_HISTORY 描述审核窗口没有恢复旧归档本体。这个历史缺口原样保留，不能由检索文本另存同名文件冒充原件。本 docs 执行窗口另行枚举到此前已保存的两个实际归档，外层字节数与 SHA 实测如下；这是独立新增的本地保管观察，没有重做 runtime、内部成员核验或模型测试。

| 原名 | 字节数 | 本次外层 SHA-256 | 保管与观察 |
| --- | ---: | --- | --- |
| `E4_R3_INCREMENTAL_EVIDENCE_2026-09-08.tar.gz` | 34480 | `46ec2516784439fa7229b227cf82b955ed43b93dffa59977b66cb55540c68c51` | 私有本地原归档实际存在；2026-09-09T13:43:28.316337+00:00；匹配历史预期值 |
| `E4_R4_INCREMENTAL_EVIDENCE_2026-09-08.tar.gz` | 154806 | `c4be8688d63556f4abea0677735092a1e2882d944a1c723dc6b531517bdf8441` | 私有本地原归档实际存在；2026-09-09T13:43:28.316337+00:00；匹配历史预期值 |

对应 R3/R4 报告在本交接中仍属 REFERENCE_ONLY：交接记录没有提供该两份报告的原字节数和 SHA（UNKNOWN）；源观察为 2026-09-08 旧实例，不用来声明新实例驱动/服务状态。发现上述两个归档不等于审核窗口此前已获得本体，更不等于所有 A100 证据均已安全备份。

## 7. Public derivatives and ADR transformation

本节为 PR #84 在 `3bf2e7a5152a7bd9c1087571aab6413a53a43bb6` 发布的 2026-09-09 历史派生记录。ADR 行的 37611 字节及 `ee2ff93f…` 摘要只指该提交内的 v1.0 对象，不是当前 ADR 链接内容的摘要；当前 v1.2 接受与发布身份见第 9 节。三份 E4 派生报告的字节及摘要保持不变。

下列 Markdown 由本次文档执行在 2026-09-09 编制，采集/分析基线仍为 f007。保护方式为限定字段公开派生，原始 JSON、账单、端点、完整 argv/环境字典、主机和会话标识留仓库外。所有摘要按最终派生字节计算，不能用来加载或校验密封原件。

| 派生文档 | 字节数 | 派生 SHA-256 | 转换 |
| --- | ---: | --- | --- |
| [M10_M11_SPIKE_0_E4_RUNTIME_PREFLIGHT_2026-09-09.md](M10_M11_SPIKE_0_E4_RUNTIME_PREFLIGHT_2026-09-09.md) | 8894 | `be2512ac0502d10727ef59e17afb0fa12f182703535ddc3a6dab56ebca426ed3` | 多份原件的脱敏、有时点限定的文档化 |
| [M10_M11_SPIKE_0_E4_EXACT_BINDING_REVIEW_2026-09-09.md](M10_M11_SPIKE_0_E4_EXACT_BINDING_REVIEW_2026-09-09.md) | 6968 | `e8049055d5da9259a56d87d655e73b7177d0d0e520b81967f8fb8a17242585b5` | 多份原件的脱敏、有时点限定的文档化 |
| [M10_M11_GENERATION_DISPATCH_AUTHORITY_AUDIT_2026-09-09.md](M10_M11_GENERATION_DISPATCH_AUTHORITY_AUDIT_2026-09-09.md) | 7915 | `edafa9cfed4f5e18028f80cdd022ff580913081cbdf25358b6b630c97473ff0c` | 多份原件的脱敏、有时点限定的文档化 |
| [ADR-0022-generation-dispatch-grant.md](../../governance/ADR-0022-generation-dispatch-grant.md) | 37611 | `ee2ff93f2e5477c00de6b5492ea0ea4aa4b42b3ea63de18a3d365da584a2ee16` | 原审议稿的登记/时点/私有定位元数据/相对链接修正；方案正文保持 |

本历史检查点的 ADR v1.0 原稿为 36889 字节，SHA-256 `23455b3d4a211f5e28b3563703c94551699e379a5b08f01034967b234065bac6`；原件见第 4 节。入库候选为 37611 字节，SHA-256 `ee2ff93f2e5477c00de6b5492ea0ea4aa4b42b3ea63de18a3d365da584a2ee16`。转换仅包括提案编号登记说明、提案形成时点限定、用相同 commit/Tree 表示私有源码定位和添加相对证据链接；第 1–12 节方案正文逐字节相同，第 13 节只添加历史时点说明。schema、Terminal、CAS、签发及消费边界未重新设计。该 v1.0 历史发布时点 Status=Proposed；完整审批 PENDING；当时不 supersede 任何 Accepted ADR。此句不描述 v1.2 的当前接受状态。

本索引以及 CURRENT_MILESTONE、registry、authority map 的最终摘要由仓库外执行回执记录，避免自包含摘要循环。最终 PR、CI、merge commit/Tree 只记入该执行回执，不在文档中预报或触发第二次自引用 PR。

## 8. Historical boundary — 2026-09-09

本节保留 2026-09-09 文档检查点的边界；下述“本次”和“ADR 提案登记”仅指该历史动作。v1.2 后续架构接受另见第 9 节，原运行观察和限制不因接受而改写。

E3 PREPARED_AND_VERIFIED 保留；E4_RUNTIME_EVIDENCE=VERIFIED_TECHNICAL_ONLY；正式 v2 证明已创建并验证。C1/C2、派发机制缺失、未来服务 currentness、费用与完整执行绑定仍限制后续执行。ADR 提案登记不批准实现、真实 Grant、生成、输出准入或发布；Spike-0 仍 BLOCKED，本次不提出生成授权申请、不启动下一任务。

## 9. ADR-0022 v1.2 接受与发布（2026-09-10）

Project Lead 已接受精确 v1.2 全文，并另行授权 Accepted 元数据回填及文档入库。架构状态为 ACCEPTED_ARCHITECTURE_ONLY；规范以 [ADR-0022](../../governance/ADR-0022-generation-dispatch-grant.md) 为准，人工决定及来源映射见 [v1.2 架构接受记录](ADR_0022_V1_2_ARCHITECTURE_ACCEPTANCE_2026-09-10.md)。本节为可重建导航增补，不是新 runtime 采集、第二批准机制或真实 Grant。

| 对象 | 字节数 | SHA-256 | 来源与转换 |
| --- | ---: | --- | --- |
| 原接受 v1.2 候选 | 72590 | `b963c12a07dea8816516752a40470df035e275714909a302ee8087963d4af75f` | Project Lead 接受的精确原字节，仓库外保全；原 Proposed 元数据属于候选时点 |
| [ADR-0022 Accepted 发布版](../../governance/ADR-0022-generation-dispatch-grant.md) | 74503 | `ecb896012ec1a501b1883d6239ba22514c07d61adab06062d453f441c1573f60` | 原接受对象的元数据派生，仅回填接受/发布依据和历史语境 |
| [公开接受记录](ADR_0022_V1_2_ARCHITECTURE_ACCEPTANCE_2026-09-10.md) | 4275 | `9b0c40a2618918a7f4476becaa502caec4ea7f13575b61b0d13fd1642d929137` | 原人工接受记录与回执的公开历史登记，包含原接受对象和发布对象的准确映射 |

ADR 第 1—13 节从 `## 1. Context 与保留边界` 到 `## 14. 修订记录与源码依据` 之前，含段间全部空白，共 66124 字节，两版完全相同，SHA-256 为 `b63c0a588de2ae4f4085fa0b80fc69889d6a9836d29f133c9de5c8b8d960b7d1`。未更改规范 schema、权限、摘要、CAS、消费、幂等、时序或费用语义；原 v1.0/v1.1 及 E3/E4 记录仍按各自历史时点解释。

SPIKE_0_READINESS=BLOCKED；GENERATION_DISPATCH_MECHANISM_AT_AUDITED_COMMIT=NOT_IMPLEMENTED；GENERATION_DISPATCH_IMPLEMENTATION_AUTHORIZED=false；GENERATION_AUTHORIZATION_APPLICATION_SUBMITTED=false。架构接受不授权实现、正式数据库/配置写入、真实 Grant 签发/消费、费用、A100/ComfyUI、prompt、输出准入或发布。E4 执行 pin 仍为 `f007ab3e93c3fb7f5e8b3b7f81c34fec28858176`；Frontend pin 和既有 tag 不变。

本索引、registry、authority map、CURRENT_MILESTONE 及最终 commit/tree 的摘要只由仓库外执行回执记录。本节不预报 PR/CI/合并通过，不修改原件摘要，不解除运行阻塞，也不自动开启实现或生成申请。
