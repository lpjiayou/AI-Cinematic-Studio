# K2-001《记忆回声》开机前创作候选包

> 归档状态：`HISTORICAL VALIDATION ONLY / CLOSED TO NEW DISPATCH`
>
> 下文“当前 / 可直接 / 后续”等措辞只描述原时点，不是当前生产授权；不得重放。
>
> 原状态：`DRAFT / CANDIDATE / NOT CONFIRMED / NOT DOMAIN FACT`
>
> Gate：`P1 NOT PASSED`
>
> 付费调用：`0`
>
> 发布：`publicationAllowed=false`

## 1. 使用边界

本文件把当前仓库已有的 K2 本地证据基线整理成一份可审阅、可直接转入后续
受治理实验的创作候选包。它不确认 M7–M12 事实，不创建 Rights、Provider、Budget、
Identity、Approval 或 Publication Authority，也不替代 Core 生成的版本化引用。

可直接复用的当前基线只有：

- 单集设计键 `K2-001`，标题《记忆回声》；
- 30 秒、16:9、24 fps、720 帧；
- 两场、四镜，场一 336 帧，场二 384 帧；
- 林澈、顾言及当前 M6 本地证据中的视觉规则；
- 两句当前剧本候选对白；
- 已核验的 Wan2.2 三个模型文件名与 SHA-256；
- `TECHNICAL_EVIDENCE_ONLY` 的 A100/ComfyUI attestation。

本文件新增的动作拆分、构图细化、表演节拍、声音方案、人物造型细节和提示词均是
创意候选。只有在对应 Core confirmation、外部 Authority、Provider 实验、候选选择与
V5 接纳完成后，才能成为生产事实。

## 2. 故事设计候选

### 核心命题

当制度可以删除一段记忆，却无法抹去其校验痕迹时，“亲眼确认”成为两个人建立有限
信任的最低条件。

### 30 秒情绪曲线

```text
0–7 秒   规则建立：顾言封锁检索，二人暂时结盟
7–14 秒  异常显形：被删除的童年影像出现
14–22 秒 证据确认：林澈指出删除不等于消失
22–30 秒 有限信任：二人各存摘要，以静默收束
```

### 人物当集目标

| 人物 | 当前基线 | 本集候选表演方向 |
| --- | --- | --- |
| 林澈 | 验证异常记忆片并保存证据；克制、敏锐 | 先观察再下结论；直到第三镜才把判断说出口 |
| 顾言 | 封锁检索通道并确认来源；审慎、果断 | 先用动作建立安全边界，再用一句短句提供有限信任 |

### 连续性硬点候选

- 林澈：黑色短发、深炭色功能风衣、右袖银灰粉尘；粉尘不得换侧或消失。
- 顾言：灰白短发、深灰监察制服、胸前琥珀身份灯；身份灯位置不得漂移。
- 道具：同一枚半透明记忆片；插入方向、编号区域和从终端回到掌心的运动连续。
- 光色：冷蓝环境光为主，琥珀实景光只用于校验台、身份灯和摘要提示。
- 雨向：外环廊桥固定为画面左上至右下。
- 轴线：场一双人站位与视线轴不跨越；场二并肩方向不反转。

## 3. 30 秒剧本候选

### 场一：中央记忆档案城·校验台 / 雨夜 / 0:00–0:14

冷蓝的档案大厅深处，校验台亮起一条克制的琥珀光。林澈将异常记忆片推入读槽，
右袖的银灰粉尘擦过台沿。顾言抬手封锁外部检索，远端接口逐个熄灭。

顾言压低声音：

> 从现在起，只相信我们亲眼看到的。

校验台投出一帧不完整的童年影像。系统将它标成“不存在”，随即发出一次短促警示。
两人没有看向警示，而是同时盯住记忆片上的校验脉冲。

### 场二：中央记忆档案城·外环廊桥 / 雨夜 / 0:14–0:30

斜雨越过外环廊桥，城市档案塔沉在冷蓝雾层里。两人把同一段异常影像分送到各自
终端；画面消失后，校验痕迹仍在。

林澈低声而坚定：

> 它被删掉了，但没有消失。

两个终端分别写入相同摘要。顾言先收回目光，林澈取回记忆片并握在掌心。最后两秒，
画面停在琥珀摘要光和冷蓝雨幕之间。

对白仍只使用当前剧本候选中的两句，未新增旁白、人物身份或世界观事实。

## 4. 分镜总表

| 镜头候选键 | 时间 / 帧 | 画面与动作 | 摄影基线 | 对白 / 声音候选 | 关键连续性 |
| --- | --- | --- | --- | --- | --- |
| K2-001-SH-010 | 0:00–0:07 / 0–167 | 校验台双人全景；林澈插片，顾言封锁通道 | wide，28mm，eye-level，slow dolly in | 顾言对白；设备底噪、远雨、锁定提示 | 右袖粉尘、身份灯、插片方向 |
| K2-001-SH-020 | 0:07–0:14 / 168–335 | 双人中近景；童年影像闪现，警示熄灭 | medium close-up，50mm，locked-off | 无对白；脉冲、警示后近静音 | 眼线、站位轴、记忆片仍在读槽 |
| K2-001-SH-030 | 0:14–0:22 / 336–527 | 廊桥远景；二人并肩查看异常影像 | wide，28mm，eye-level，slow dolly in | 林澈对白；雨、廊桥共振、远处通风 | 雨向、衣着、记忆片编号 |
| K2-001-SH-040 | 0:22–0:30 / 528–719 | 中近景；双摘要写入，林澈收片，末尾停留 | medium close-up，50mm，locked-off | 无对白；两次提示音、雨声尾音 | 手部道具、两种琥珀光、末 48 帧稳定 |

镜头时长沿用当前确定性 Shot Graph 的 `168 + 168 + 192 + 192 = 720` 帧。
摄影字段沿用当前编译器基线；本表新增的画面节拍尚未确认。

## 5. 逐镜头描述设计

### SH-010 — 共同规则

- 构图：校验台位于画面中下部，林澈偏左前景，顾言偏右后景；背景通道形成向心透视。
- 摄影：28mm 眼平缓慢前移，七秒内只完成一个轻微景别收紧，不绕轴。
- 动作：0–2 秒建立空间；2–4 秒插入记忆片；4–7 秒顾言封锁检索并完成对白。
- 表演：林澈只看校验台；顾言说话时先确认接口熄灭，再把视线移向林澈。
- 光线：冷蓝大厅为主，校验台琥珀光只勾出手、道具与下颌轮廓。
- 失败判定候选：脸部或发色漂移、粉尘换侧、身份灯缺失、插片穿模、相机突跳。

### SH-020 — 异常显形

- 构图：50mm 中近景，人物各占画面约三分之一，投影只作为两人脸部的非具象反光。
- 摄影：锁定机位，以眼神和微表情完成叙事，不使用额外推拉摇移。
- 动作：童年影像先出现、后被系统覆盖；警示熄灭时两人眼线同时落向记忆片。
- 表演：不惊叫、不大幅后退；顾言的控制感与林澈的验证欲通过呼吸和目光区分。
- 光线：投影不生成新的可识别人物脸，避免把“童年影像”升级成未经确认的身份事实。
- 失败判定候选：两张脸融合、夸张惊讶、轴线跳变、警示顺序反转、出现可读假 UI 文本。

### SH-030 — 删除不等于消失

- 构图：廊桥占下三分之一，城市档案塔提供纵深；两人并肩形成稳定双人剪影。
- 摄影：28mm 眼平缓慢前移，保持城市尺度，不做无人机式大幅运动。
- 动作：两台终端同步显示异常残影；林澈确认校验痕迹后完成对白。
- 表演：林澈由屏幕转向顾言，但顾言仍看终端，有限信任通过不同步的视线体现。
- 环境：雨向固定；冷蓝雾层与稀疏琥珀反射，不使用高饱和赛博霓虹。
- 失败判定候选：雨向反转、人物互换站位、衣着突变、城市结构融化、背景运动过快。

### SH-040 — 各持一份证据

- 构图：50mm 中近景，两个终端边缘与林澈掌心构成三角；背景雨幕虚化。
- 摄影：全镜锁定；最后 48 帧保留稳定停留，允许人物极轻微呼吸，不改变构图。
- 动作：摘要 A 写入、摘要 B 写入、顾言收回视线、林澈取片握住。
- 表演：不拥抱、不宣誓；关系只推进到“各自保存同一证据”的有限信任。
- 光线：身份灯与终端提示必须可区分；不得生成可读且未经 Core 提供的摘要字符串。
- 失败判定候选：多余手指、重复记忆片、摘要次序混乱、末尾相机漂移、身份灯消失。

## 6. 角色多角度设计

多角度图的目标是形成待审阅的 identity candidate，不是自动创建 Identity Lock。
每名人物应在同一批次输出以下八张，统一 1024×1024、中性灰背景、同一焦段感、
同一白平衡、无文字、无标志：

1. `front-full`：正面全身，中性站姿；
2. `front-close`：正面头肩，验证五官与发际；
3. `three-quarter-left`：左前 3/4 全身；
4. `profile-left`：左侧面头肩；
5. `profile-right`：右侧面头肩；
6. `rear-three-quarter`：后侧 3/4，验证服装结构；
7. `rear-full`：正后全身；
8. `expression-sheet`：同一头部的中性、警觉、克制决断三种微表情。

### 林澈多角度提示词候选

```text
production character turnaround sheet, one consistent adult character named Lin Che,
black short hair with a fixed clean silhouette, dark charcoal functional long coat in
low-reflectance technical fabric, a stable patch of silver-gray dust only on the right
sleeve, restrained observant posture, practical near-future archive engineer design,
front full body, front close-up, left three-quarter, left profile, right profile, rear
three-quarter, rear full body, restrained expression sheet, neutral gray studio
background, even soft light, realistic proportions, consistent face and wardrobe,
no text, no logo
```

禁止项：发色变化、长发、粉尘换到左袖、服装高饱和、品牌标志、武器化配件、年龄跳变、
脸型漂移、视图之间比例变化。

### 顾言多角度提示词候选

```text
production character turnaround sheet, one consistent adult character named Gu Yan,
gray-white short hair with fixed hairline and silhouette, structured dark-gray archive
inspector uniform, one small amber identity light fixed on the upper chest, cautious
reserved posture with decisive economy of movement, practical near-future inspection
design, front full body, front close-up, left three-quarter, left profile, right profile,
rear three-quarter, rear full body, restrained expression sheet, neutral gray studio
background, even soft light, realistic proportions, consistent face and wardrobe,
no text, no logo
```

禁止项：黑发或彩发、身份灯缺失/移动、军装化或礼服化、夸张肩甲、品牌标志、年龄跳变、
脸型漂移、不同视图制服灰阶变化。

### 多角度验收候选

- 八视图的人脸嵌入/人工对照必须来自同一批候选，不能用名字拼接不同人物。
- 发型轮廓、服装剪裁、固定识别点、身材比例和左右侧必须逐项打勾。
- 任何生成结果保持 `UNTRUSTED_PROVIDER_CANDIDATE / UNSELECTED / NOT_ADMITTED`。
- 只有显式人物身份决定后，所选精确文件摘要才可进入后续 Identity Lock 流程。

## 7. Wan2.2 草案

### 已核验技术组合

| 角色 | 文件 | SHA-256 |
| --- | --- | --- |
| UNET | `wan2.2_ti2v_5B_fp16.safetensors` | `456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e` |
| TEXT_ENCODER | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68` |
| VAE | `wan2.2_vae.safetensors` | `e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156` |

这些摘要只证明本地文件与 attestation 一致，不证明 Provider、region、使用条款或
商业权利已经获批。

### P1 小样参数

```text
profileId: k2.wan22-ti2v.p1-smoke.v1
size: 640 × 352
frames: 49
fps: 24
steps: 20
cfg: 5.0
sampler: uni_pc
scheduler: simple
model shift: 8.0
seed: 运行时从当前 GenerationRequest payloadDigest 前 16 个十六进制字符派生
```

49 帧约等于 2.04 秒，只用于低成本 P1 实验，不冒充 7/8 秒正式镜头。每个镜头的
完整时长仍为 168/168/192/192 帧；扩大时长必须是后续策略和成本证据支持的新版本。

### 节点草案

```text
UNETLoader + CLIPLoader + VAELoader
→ ModelSamplingSD3
→ CLIPTextEncode(positive / negative)
→ Wan22ImageToVideoLatent
→ KSampler
→ VAEDecode
→ CreateVideo(24fps / 8-bit)
→ SaveVideo(mp4 / h264)
```

该链与现有 V4 `ComfyUIWan22VideoAdapter` 一致。人物参考图尚未成为受治理输入，
所以不得偷偷增加参考图节点或把本目录的多角度草案当成已批准 Identity Lock。

### 提示词组织规则

每镜正向提示词固定按以下顺序组织：

```text
场景与时间 → 景别/机位/焦段/运动 → 人物固定识别点 → 单一动作节拍
→ 光色与材质 → 身份/服装稳定要求
```

负向提示词至少覆盖：身份漂移、换脸、发色变化、固定识别点缺失、重复人物、肢体错误、
服装变化、文字/标志/水印、过饱和霓虹、几何融化和相机突跳。四镜完整英文提示词已写入
机器可读清单，避免文档与执行候选各自漂移。

## 8. AI 音频设计候选

本集需要音频工作，但开机前只完成文本、节拍和安全边界，不生成外部音频。原因是
现有发布契约要求 image/video/audio 同源实验；完全忽略音频会让 P1 必然保持阻断。

当前建议采用最小可行音频范围：

- 两句中性 TTS，对白文字严格来自当前剧本候选；
- 不做真人声纹克隆，不模仿演员，不上传外部音频；
- P1 不配音乐，先验证对白、环境、提示音、血缘、时长与成本；
- 雨声、设备底噪、廊桥共振和提示音优先内部合成；若使用任何素材，必须先进入
  Rights Manifest 的精确摘要与用途/地域/期限范围；
- 48 kHz、双声道 WAV 候选；对白、环境和提示音保留独立 stem 血缘；
- 后续 QC 候选目标为对白可懂度、无削波、同步误差可测、结尾两秒不过度填满。

| 镜头 | 对白候选 | 环境 / 效果候选 | 音乐 |
| --- | --- | --- | --- |
| SH-010 | 顾言，低声、清晰、克制 | 设备底噪、远雨、锁定提示 | 无 |
| SH-020 | 无 | 校验脉冲、短警示、近静音 | 无 |
| SH-030 | 林澈，低声、清晰、坚定 | 斜雨、廊桥低频、远通风 | 无 |
| SH-040 | 无 | 两次摘要写入、雨声尾音 | 无 |

音频 Provider、model、region、usage terms、credential source、预算子上限与
`budgetAuthorityRef` 仍必须由外部 Provider Authority 提供；本文件不选择或猜测。

## 9. 机器可读对应关系

候选清单位于：

`experiments/k2-001-preboot/k2-001-preproduction-candidate.v1.json`

它固定并校验：

- CNY 1000 硬上限、当前承诺支出为 0、禁止立即付费调用；
- 30 秒/24 fps/720 帧与四镜连续时间轴；
- 两名人物各八种必要视图；
- 三份模型摘要与技术 attestation 摘要；
- 每镜 image preflight、49 帧 Wan2.2 小样和 text-only neutral TTS 草案；
- video/audio 必须来自当前 G4 `GenerationRequest`；当前 G4 没有 image request，
  image 保持 blocker，直到获批的同源合同扩展存在；
- 所有结果保持未选择、未接纳、不可发布；
- Rights、Provider、Budget 与三媒体真实实验仍是阻断项。

## 10. 开机前完成定义

本候选包达到“开机前可完成”，当且仅当：

1. 文档与机器清单一致；
2. 离线校验和篡改测试通过；
3. 不含 secret、凭据值、虚构引用或有效 Authority bundle；
4. 未执行 GPU、网络 Provider 或付费调用；
5. P1 仍明确为 `NOT PASSED`；
6. 开机后每个运行时引用都从当前 Core lineage 重新解析。

这不是创意验收、身份验收、P1 通过或生产授权。
