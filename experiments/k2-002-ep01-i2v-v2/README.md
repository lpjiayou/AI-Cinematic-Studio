# K2-002 EP01 18 镜精确源归档

## 1. 归档目的

本目录把 EP01 18 镜技术实验的精确语义源从 A100 持久盘和非祖先分支恢复到
`main` 可达历史，消除主机释放或分支删除后源数据丢失的风险。

归档源根为 `/data/coding/k2-002-ep01-i2v-v2`。三个源文件由远端关机归档
`46bc8f0fc71970c136996cc30282759d964437fd` 恢复；其中 `shots.json`、
`camera_contract.json` 与 14 张批次锚帧另由非祖先收敛提交
`2a07118fbe962a6a073e62a05a8c70fac583cd66` 的摘要交叉核验。`anchor_manifest.json`
本体由关机归档根清单、R1 source manifest 以及 `shots.designInputs.anchorManifestSha256`
三处证据钉扎。

## 2. 内容

| 文件 | 字节数 | SHA-256 | 说明 |
| --- | ---: | --- | --- |
| `shots.json` | 35,140 | `52e24c8c781f2c729239d6152246677c8eb633d43d17463550c22bb91c8fd9c9` | 18 镜精确技术实验定义 |
| `camera_contract.json` | 20,922 | `b83967cd56dc22681b6b0271cae03a5aae9f3f328a5dbb9ff209e15544104a3a` | 18 镜技术设计源文件 |
| `anchor_manifest.json` | 7,424 | `70bdc61408123381b448cc9732840197632ad5523283681a15c38ff85f47fbb3` | 18 张起锚帧的路径、尺寸、字节数、SHA-256 与起始动作状态 |
| `archive_manifest.json` | 见文件本身 | 由 Git 对象钉扎 | 归档来源、18 个视频的字节数、SHA-256、probe、选择和 QC 状态 |

18 张起锚帧和 18 个视频的二进制本体不进入 Git。锚帧由
`anchor_manifest.json` 保存完整摘要清单；视频由 `archive_manifest.json` 保存完整
外部媒体清单。

## 3. 权力与生产边界

固定状态：

```text
authorityState=TECHNICAL_EVIDENCE_ONLY
canonicalMutationCount=0
publicationAllowed=false
AssetVersion / Admission / Master / Export=NONE
```

本目录是纯资产归档，不是 V5 Domain fact，也不创建或改变 ShotPlan、Camera
authority、ExecutableShotGraph、AssetVersion、Selection、Admission、Master、Export
或 Publication 状态。

文件名 `camera_contract.json` 沿用精确源名称；其中的
`TECHNICAL_DESIGN_READY` 只描述当时的技术实验设计，不等于当前治理语义中的已批准
Camera Contract。`shots.json` 的 18 镜结构同样不覆盖 `main` 中现有的 12 镜编辑候选 /
ShotPlanDraft，也不改变任何 Script、ShotPlan 或 Camera authority 状态。

## 4. 视频状态口径

`archive_manifest.json` 登记在证据生成 / 导出时存在的 18 个媒体对象，但只有 11 镜
具有非 `NONE` 的技术选择状态。SH08、SH12、SH13、SH15、SH16、SH17、SH18 均保持
`selection.status=NONE`；它们只作为外部技术证据记录，不得被解释为已选素材。

所有媒体的机器 probe 均为 H.264 High、`yuv420p`、`704×1280`、49 帧、
24 fps、2.041667 秒和零音轨。该一致性只证明技术规格，不推导视觉通过、生产准入
或发布资格。EP01 的归档视觉完成状态仍为 `INCOMPLETE`。

## 5. 来源钉扎

- 非祖先收敛提交：`2a07118fbe962a6a073e62a05a8c70fac583cd66`
- A100 关机归档提交：`46bc8f0fc71970c136996cc30282759d964437fd`
- A100 关机归档 tag：`k2-002-ep01-a100-shutdown-20260828`
- 压缩归档 Git blob：`60f183cdee5163ccc9de903d244a3b0639686f07`
- 压缩归档 SHA-256：`30fd28beb8c641672da2e07f63810c12e3e72d0624854a2fd9908d9d1794ea01`

SH01、SH02 视频未包含在关机归档内；其外部路径、字节数、SHA-256 与 ffprobe
结果于 2026-08-29 从已登录 A100 只读导出，并记录在 `archive_manifest.json`。
