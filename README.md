# ComfyUI MiniMax H3 Motion Director

这是一个独立的 ComfyUI 自定义节点，用于编排 MiniMax H3 多段视频生成。它把分段时间轴、图片/视频/音频参考、内部或外接采样、Motion Context、Source Bridge、分段缓存与导出整合在同一个 Director 节点中。

本项目基于并大幅修改了以下上游项目：

- [AIMixer/ComfyUI_MiniMaxH3_Director](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director)
- [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)

它不是上述任一项目的官方发行版。

## 主要能力

- 支持 T2V、I2V、FL2V、R2V、V2V、RV2V。
- 在节点内编辑多段时间轴、分段提示词与参考素材。
- 支持完整序列生成、勾选分段运行、全部导出和分段导出。
- 支持模型内部采样，也支持外接标准 `SAMPLER` + `SIGMAS`。
- R2V 在“实时预览”旁提供 `Common References` 浮动素材管理器，每段再叠加自己的 Local 素材；Common 不会复制进 Local，也不会泄漏到其他任务。
- 提示词中的图片、视频、音频引用使用可视化 Prompt chip，素材勾选变化后会自动重新编号。
- 使用 latent-first Motion Context 延续上一段生成的视频状态与模型生成音频，并保留像素缓存作为兼容 fallback。
- 使用可选的 Color Re-anchor 降低长链生成中的累积性色彩漂移。
- 为 V2V/RV2V 提供固定 5 帧的 H3 原生 Source Bridge。
- External Groups 支持经过标准 Reroute、rgthree Reroute 与明确虚拟直通节点连接。
- FL2V 支持首帧、首尾帧和仅尾帧三种官方 conditioning 形式。
- 自动处理 MiniMax H3 的 `17k+5` 时间长度；所有任务统一使用 32 像素空间网格。
- 节点 ID 独立，可与 AIMixer Director 同时安装。

## 当前测试状态

仓库包含 Python 单元/运行时测试与 Node.js UI 测试，覆盖 Common/Local 有效参考集合、Prompt chip、latent-first Motion Context、Continuity UI、旧工作流迁移、全局 32 像素对齐、Source Bridge、Reroute、FL2V 仅尾帧、缓存与音频导出。提交前还会执行 Python `compileall` 和 ComfyUI loader smoke。

作者已在本地使用真实 MiniMax H3 生成测试过 T2V、I2V，以及 RV2V 基础生成和续接对比。FL2V、R2V、V2V，以及本轮新增的 Common 素材模型、latent-first handoff、全局 32 像素对齐、Reroute 与仅尾帧路径，仍需要更多真实 GPU 素材验证。自动测试通过只表示实现和回归检查完成，不代表所有素材都能获得相同的视觉改善。

现有演示视频：

| 测试 | A | B |
|---|---|---|
| T2V 测试 1 | [查看 A](demo/t2v_test_1_a.mp4) | [查看 B](demo/t2v_test_1_b.mp4) |
| T2V 测试 2 | [查看 A](demo/t2v_test_2_a.mp4) | [查看 B](demo/t2v_test_2_b.mp4) |
| I2V 测试 1 | [查看 A](demo/i2v_test_1_a.mp4) | [查看 B](demo/i2v_test_1_b.mp4) |

这些演示使用 24 fps、8 个采样步数，且没有使用 Turbo LoRA，适合观察跨段行为，不代表最高画质。当前测试环境中的 Turbo/pruned 模型组合在加入 Motion/Audio Context 后可能出现 conditioning 维度不匹配，因此不能据此断言所有 Turbo 组合都兼容或都不兼容。

## 环境要求

- 已包含官方 MiniMax H3 支持的较新版本 ComfyUI。
- MiniMax H3 diffusion model。
- MiniMax H3 video VAE 与 audio VAE。
- MiniMax 兼容的 CLIP/文本编码器。
- `requirements.txt` 中的媒体依赖。

## 安装

把仓库克隆到 ComfyUI 的 `custom_nodes`：

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/j955229/ComfyUI-MiniMax-H3-Motion-Director.git
```

使用启动 ComfyUI 的同一个 Python 环境安装依赖：

```bash
python -m pip install -r ComfyUI/custom_nodes/ComfyUI-MiniMax-H3-Motion-Director/requirements.txt
```

Windows 便携版示例：

```powershell
python\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-MiniMax-H3-Motion-Director\requirements.txt
```

重启 ComfyUI 后，在节点菜单中搜索 `MiniMax H3 Motion Director`。

> 不要在同一个 ComfyUI 环境中同时启用独立版 `ComfyUI-H3-Motion-Context`。本项目已经内置并修改了对应的 H3 runtime patch，同时加载两套 patch 可能发生冲突。

## 快速使用

1. 连接 MiniMax H3 `MODEL`、video VAE、audio VAE 和 CLIP。
2. 添加 `MiniMax H3 Motion Director`，选择任务模式。
3. 在 Director 时间轴中建立一个或多个分段，并填写全局或分段提示词。
4. R2V 可展开 `Common References` 放入重复使用的素材，再为每段添加 Local 素材；每段提示词完全独立，没有 Common Prompt。
5. 多段任务按需要选择 Motion Context 或 Source Bridge。
6. 不连接外部 `SAMPLER`/`SIGMAS` 时使用内部采样；两者都连接时自动切换到外接采样。
7. Queue 工作流。`images` 与 `audio` 可继续连接到视频保存节点。

## 节点输入

### 必需输入

| 输入 | 作用 |
|---|---|
| `model` | MiniMax H3 模型。 |
| `video_vae` | MiniMax H3 视频 VAE。 |
| `audio_vae` | MiniMax H3 音频 VAE。参考视频任务也需要它处理 Ref2VA/AV latent。 |
| `clip` | MiniMax 兼容 CLIP，通常使用 `qwen3vl`。 |
| `task_type` | T2V / I2V / FL2V / R2V / V2V / RV2V。 |
| `global_prompt` | 全局提示词；分段模式可由每段提示词覆盖。 |
| `frame_rate` | 时间轴和导出 fps。Motion Context 要求 H3 原生 24 fps。 |
| `width` / `height` | 固定输出模式的画布尺寸。 |
| `ref_max_size` | 长边模式的尺寸预算。 |
| `total_frames` | 时间轴总帧数，默认 124。 |
| `timeline_data` | UI 自动维护的内部时间轴 JSON，不建议手工编辑。 |

### 续接、采样与性能输入

| 输入 | 默认值 | 作用 |
|---|---:|---|
| `motion_context_enabled` | `true` | 多段时使用上一段最终导出帧作为 visual Motion Context。 |
| `context_length` | `22` | 请求的上下文帧数；运行时使用 H3 合法长度 `1 / 5 / 22 / 39` 中不超过可用帧数的最大值。 |
| `source_overlap_frames` | `5` | 兼容旧工作流的后端字段；UI 中表示 V2V/RV2V 的 Source Bridge。仅允许 `0` 或固定 `5`。 |
| `audio_context_enabled` | `true` | 传递上一段模型生成音频的尾部上下文。 |
| `color_reanchor_enabled` | `false` | 对传入下一段的 visual Motion Context 执行 Color Re-anchor。 |
| `steps` | `25` | 内部采样步数。 |
| `sampler_name` | `res_multistep` | 内部采样器。 |
| `scheduler` | `simple` | 内部 scheduler。 |
| `shift_video` / `shift_audio` | `12.0 / 3.0` | 内部模式的 MiniMax H3 sigma shift。 |
| `sampler` / `sigmas` | 未连接 | 两者都连接时启用外接 Advanced Sampling。 |
| `clear_vram_between_segments` | `true` | 每段结束后释放对象、卸载模型并清理 CUDA cache。 |
| `export_source_images` | `false` | 额外输出时间轴原片帧对比，会增加内存占用。 |
| `i2v_groups` / `r2v_groups` | 未连接 | 接收外部 Group 节点；连接后执行时优先于节点内卡片。 |

## 节点输出

| 输出 | 类型 | 说明 |
|---|---|---|
| `images` | `IMAGE` 列表 | 全部导出时为合并结果；分段导出时为各段结果。 |
| `audio` | `AUDIO` 列表 | 与导出视频范围和帧数对应的音频。 |
| `fps` | `FLOAT` | 导出帧率。 |
| `frame_count` | `INT` | 可见导出总帧数。 |
| `source_images` | `IMAGE` 列表 | 可选的原片对比输出。 |
| `report` | `STRING` | 任务、尺寸、采样、续接、缓存与导出诊断信息。 |

## 任务模式

| 模式 | 当前语义 | 多段续接建议 |
|---|---|---|
| T2V | 仅用文字生成视频与音频。 | 使用 Motion Context 延续生成状态。 |
| I2V | 每条连续链从一张初始图开始。 | 使用 Motion Context；后续显式新图会重置连续链。 |
| FL2V | 可使用首帧、首尾帧或仅尾帧锚点生成；仅尾帧不会伪造首图。 | 可使用 Motion Context；显式尾端 anchor 会保留在可见输出末帧。 |
| R2V | 每段有效素材按 `Common → Local` 编译成连续 Picture/Video/Audio 槽位。 | 使用 Motion Context；空 Local 组表示纯 Common 或纯场景，不表示继承上一段。 |
| V2V | 当前分段的原始源视频作为 `<Video 1>`。 | Source Bridge 是 source-motion-first 的起始方案；Motion Context 是可选 fallback。 |
| RV2V | 当前分段 `<Video 1>` 加 Picture/Audio/Video 参考。 | 与 V2V 相同，但还要遵守有效参考集合。 |

`22` 是一般 generated continuation 的基线值，不是所有任务的统一推荐值。V2V/RV2V 的动作应优先服从当前 `<Video 1>`；使用 Motion Context 时，上下文越长越可能增强上一段生成状态并干扰当前原片动作。当前可把 `1` 帧视为保守 fallback 参考，但真实效果仍依素材而异。

## R2V Common / Local 参考素材

`Common References`（Common Asset Pool）是 R2V 专用浮动素材管理器。入口位于“实时预览”旁边，点击按钮打开或收起，点击外部或按 Escape 也会关闭；浮层不会进入分段列表、推高 Batch panel 或改变 Segment index。管理器只显示已经存在的 Picture、参考视频、参考音频 card，以及每类一个“添加”入口，不会预先画出 9/3/3 个空槽。新增素材自动使用该类型第一个可用内部 slot；替换保留原 asset ID，删除后重新新增才产生新身份。Common 不含 Prompt。每段都有自己的完整 Prompt、Common 排除清单与 Local 素材区。运行时会先读取该段启用且未排除的 Common，再读取 Local，按 `Common → Local` 顺序压成没有空洞的官方槽位：`<Picture 1>`、`<Video 1>`、`<Audio 1>`……。新加入的 Common 默认对所有仍启用 Common 的分段生效；整段关闭 Common 后，后来加入的素材也不会自动开启该段。

例如 Common Pool 放入角色 A、B、C，Segment 1 的 Local 放入道具 D：

```text
Segment 1 effective refs：A、B、C、D
官方标签：<Picture 1>、<Picture 2>、<Picture 3>、<Picture 4>
```

Segment 2 若取消全部 Common 且没有 Local，就是纯场景生成；它不会继承 Segment 1 的 A、B、C、D。Segment 3 若选择 A、B、C，并上传 Local E，则有效集合是 A、B、C、E。外接 R2V Group 也使用 Director 内同一份 Common Pool，但每个外接 segment 的 Local 素材仍来自自己的 Group 节点。

每个素材都有稳定 asset ID；替换同一槽位或移动素材会保留身份，只有删除后重新新增才产生新身份。因此取消 B 后，C 的可视标签可以从 `<Picture 3>` 变成 `<Picture 2>`，但 Prompt chip 仍然指向同一个 C。chip 会明确区分绿色 `ACTIVE`、橙红色 `DISABLED` 与红色 `MISSING`；执行前对 disabled/missing 引用分别报错，不会静默删除、改绑或指向另一份素材。

参考视频自带的 soundtrack 会按官方 Ref2VA 顺序进入 Audio 槽位，再接独立参考音频。Picture、Video、Audio 的数量上限会在编译有效集合时检查，超过上限会在加载模型前报出具体分段与类型。

## Prompt chip 与素材引用

在 R2V 提示词输入框键入 `@` 会打开素材列表：包含当前分段启用与未启用的 Common，以及启用的 Local；不存在的素材不会列出。未启用 Common 会明确标记“本段未启用”，点击后会先为当前分段启用该素材、重新计算 effective mapping，再插入同一个稳定 semantic token。例如 B 原本关闭时，直接从菜单选择 B，就会自动成为当前有效的 `<Picture N>`。选中后插入不可拆开的 Prompt chip；chip 显示当前官方标签，内部保存稳定 asset ID。候选菜单挂在 Director 专用 overlay layer，位置会限制在 viewport 内，不会被 modal、滚动容器或 stacking context 遮住。切换分段会同步正确 Prompt，不会把前一段文字覆盖到后一段；在编辑器内使用 Backspace、Delete、Space、方向键、Home/End 或输入法时，也不会触发时间轴删除、播放或逐帧快捷键。

- 方向键可移动候选项目，菜单会自动滚动到当前项。
- Backspace/Delete 会一次删除整个 chip，不会把内部 token 切成残片，也不会触发节点删除快捷键。
- 在候选菜单内滚动不会关闭菜单。
- 工作流序列化保存语义 token，Queue 前才编译成 MiniMax H3 官方 `<Picture N>` / `<Video N>` / `<Audio N>` 文本。

## Director 时间轴与导出

- 可使用全局提示词，也可为每段单独编写提示词。
- `全部导出` 会按时间轴顺序合并视频和音频。
- `分段导出` 会把每个分段作为独立输出。
- `选择运行` 只采样勾选分段。未勾选部分在全部导出时优先读取有效缓存；V2V/RV2V 可在适用时使用源视频 passthrough。
- 可见分段长度、最终 `frame_count`、fps 与总时长以用户时间轴为准。内部 H3 对齐产生的额外帧不会直接暴露到导出结果。

### External Groups 与 Reroute

`i2v_groups` / `r2v_groups` 可以直接连接 Group 或 Groups Combine，也可以经过一层或多层标准 Reroute、名称包含 Reroute 的第三方节点（包括 rgthree Reroute），以及明确标记为 virtual 且只有一个已连接输入的前端直通节点。解析器最多追踪 16 层并检测循环；断链、循环或缺少上游节点会安全停止。

普通语义处理节点即使只有一个输入也不会被当作 Reroute 穿透。未知上游 packer 仍按原规则保留空 segment 槽位，让运行选择和时间轴位置不会错位。External R2V 的 Local 素材来自 Group 节点，Common 选择仍由 Director 的 `Common References` 统一管理；Prompt 始终属于各自分段。

### FL2V 仅尾帧

每个 FL2V 镜头可上传：仅首帧、首帧+尾帧，或仅尾帧。仅尾帧时，尾图只会送入官方 `last_frame` / image1；系统不会把它复制成 image0，也不会把 generation timeline 为 schema 保留的 `16×16` 灰色 placeholder 当作首帧。卡片和时间轴只显示橙色尾帧角标，尾图缩图占满该镜头，不显示绿色假首帧。

旧工作流 mirror 会用 `endOnly=true` 保存这项语义。若 FL2V 同时启用 Motion Context，传入的 visual context 会替代旧的起点 keyframe，但用户明确提供的尾端 keyframe 会重新映射到当前可见输出的最后一帧，不会被 Motion Context 合并覆盖。

## 内部与外接采样

采样模式由连接状态自动决定，没有额外模式开关：

- `sampler` 和 `sigmas` 都未连接：使用节点内部 `sampler_name`、`scheduler`、`steps`、`shift_video` 与 `shift_audio`。
- `sampler` 和 `sigmas` 都已连接：使用外接 `SAMPLER` + `SIGMAS`，不会再次应用内部 sigma shift。
- 只连接其中一个：在加载/采样前明确报错，不会静默混用。

外接 `SIGMAS` 必须是一维、有限、非负、非递增，并且来自同一个已应用 `ModelSamplingMiniMaxH3` 的 H3 模型。外接 sampler 必须能处理标准 ComfyUI `SAMPLER` 对象和 MiniMax H3 的嵌套视频/音频 latent。

## Motion Context

Motion Context 的真实数据流是：

```text
上一段采样产生的 AV latent
→ 只选择不超过可见导出终点的 H3 latent block
→ 直接写入下一段 visual / audio Motion Context
→ 写入下一段 MiniMax H3 conditioning
```

这是 latent-first handoff：正常连续运行直接使用同一次 Queue 内的内存结果，不需要依赖持久化磁盘 cache。为了支持以后只运行后续段，持久化 Motion Context cache 固定只保存上一段可见终点之前最多 39 帧的 RGB fallback、对应 waveform，以及可直接再次选取 1/5/22/39 帧的 AV latent tail；不会保存整段几百帧 RGB 或整份 sampled latent。选择运行后续段时，优先读取版本化的 AV latent tail；若 companion 不存在但有效像素 tail 存在，会明确报告 `pixels (fallback)` 并走旧的 VAE encode 路径；两者都没有则直接报错。

Color Re-anchor 是刻意的例外。它必须在 RGB 画面上计算颜色统计，所以开启后 visual 路径会使用像素缓存并报告 `pixels (Color Re-anchor)`；Audio Context 仍可独立使用 latent-first，不会因为视觉调色一起退回 waveform encode。H3 为采样网格补出的尾部帧不会被当成已导出的上下文，handoff endpoint 永远不超过用户实际可见的上一段终点。

多段 T2V/I2V/R2V/FL2V 会显示 Motion Context、上下文帧数和延续生成音频。V2V/RV2V 使用互斥的“视觉续接方式”：`Source Bridge`、`Motion Context`、`关闭`。单段任务只显示“仅多段生成可用”的提示，隐藏的控件不占节点高度。

Motion Context 只在 24 fps 下运行。请求的 `context_length` 会向下选择 `39、22、5、1` 中不超过请求值与可用帧数的最大合法长度，不会偷偷缩减空间分辨率来规避显存错误。

### I2V 图片继承与重置

- Segment 1 必须提供初始图片。
- 后续分段可留空，使用上一段 Motion Context 继续生成。
- 后续某段显式上传新图片时，该段是新的 I2V anchor：跳过传入该段的 visual MC，并按现有规则重置音频上下文。
- 新图片之后的空分段继续继承这个新的 anchor。
- Motion Context 关闭时，每个 I2V 分段仍必须有自己的图片，不会静默变成 continuation。

### 延续生成音频

- T2V、I2V、R2V、FL2V 的 MiniMax H3 路径本身生成音频，不向用户显示“原声/静音”模式。
- “延续生成音频”表示把上一段模型生成音频的尾部作为下一段 Audio Context；它不是生成声音的总开关。
- V2V/RV2V 才提供“生成音频、使用原声、静音”三种真实输出语义。只有选择模型生成音频并使用 Motion Context 时，才能延续 generated audio。
- Source Bridge v1 不运行 Motion Context 的 generated-audio continuation，也不做音频 bridge 或 crossfade；音频仍按原 nominal boundary 切分。

## Color Re-anchor

Color Re-anchor 用于降低多段链式生成中的累积性色彩漂移。漂移可能表现为白平衡、色温、色相、RGB 通道比例、亮度、饱和度或整体对比度逐段变化；它不是针对某一种颜色方向的特殊修正。

它只修改即将传入下一段的 visual Motion Context frames，不会修改：

- 已生成或已导出的视频；
- 原始图片、参考视频或源视频；
- Source Bridge 的 5 帧 conditioning、anchors 或中间 3 帧 assembly；
- 音频。

第一版固定 `COLOR_REANCHOR_STRENGTH = 0.5`，只有开/关，不提供强度、gamma 或色温滑块。算法对每个 context frame 分别计算 RGB mean/std，把统计温和地向稳定 anchor 匹配，再与原帧按 0.5 混合并 clamp 到 `[0,1]`。

支持范围与 anchor 来源：

| 任务/路径 | Color anchor |
|---|---|
| I2V + Motion Context | 当前连续链的 original/effective I2V 图片；显式新图后切换到新图片。 |
| R2V + Motion Context | 当前 effective reference set 的 Picture 1；没有 Picture 1 时安全跳过。 |
| V2V + Motion Context | 当前原始 source video 分段的起始帧。 |
| RV2V + Motion Context | 优先 effective Picture 1；没有时使用当前原始 source 分段起始帧。 |

T2V、FL2V、单段任务、视觉续接关闭，以及 Source Bridge 都不显示或不执行 Color Re-anchor。即使旧工作流残留 `color_reanchor_enabled=true`，Source Bridge runtime 也会明确跳过。

## Source Bridge（仅 V2V/RV2V）

Source Bridge v1 是固定 5 帧的 H3 原生边界重生成。后端继续使用 `source_overlap_frames` 字段保证旧工作流兼容，但它的当前语义只有 `0=关闭` 与 `5=Source Bridge`；旧的任意非零值加载后都会标准化为 5。

在 nominal boundary `B`：

```text
原始 source conditioning：B-2, B-1, B, B+1, B+2
左侧 generated anchor：  B-2
右侧 generated anchor：  B+2
最终替换：                B-1, B, B+1（三个重生成中间帧）
```

原始 source 的 5 帧只进入 `<Video 1>` conditioning，不会把原片像素直接复制到最终输出。左右两段仍按 nominal 长度生成，最终只替换 3 个对应 source-time 位置，因此没有重复帧、漏帧或总时长变化。

Source Bridge 与 visual Motion Context 互斥。选择 Source Bridge 时，即使旧工作流还保存 `motion_context_enabled=true`，runtime 也会跳过 visual MC、Audio Context 和 Color Re-anchor。Source Bridge 所需的 `<Video 1>` 会自动使用 32-safe canvas。

如果 5 帧窗口会跨越 BOF/EOF、物理源文件边界、编辑跳点，或 RV2V 的 Picture/Audio effective reference set 发生变化，该边界会明确跳过并保留 nominal hard cut；系统不会从另一支视频借帧或伪造 padding。选择运行时如果缺少相邻 nominal generated cache，也会明确报错，不会静默退化。

## V2V/RV2V `<Video 1>` 与 `17k+5`

每个 V2V/RV2V 分段只把当前 source timeline 范围作为自己的 `<Video 1>` 语义，不会重复使用整支第一段视频。MiniMax H3 ReferenceToVideo 需要合法的 `17k+5` 帧数，例如 `5、22、39、56、…、124、141`。

Director 对 reference video 执行向上对齐：

1. 保留当前分段的真实 source frames。
2. 优先从同一物理源文件读取真实 forward lookahead。
3. 只有在 EOF 或物理边界导致不足时，才对 conditioning-only 尾部复制最后一帧。
4. 不做 temporal resample，也不向下截成更短的 H3 长度。
5. 生成完成后仍按用户可见分段长度裁切，导出帧数不变。

因此 121/122 帧的 source 不会再被向下截到 107；例如 127 帧 reference base 会向上准备到 141 帧。

## 全局 32 像素空间对齐

MiniMax H3 的 visual video conditioning 在 video VAE latent 后还要进入 spatial patchify，因此相关画布必须满足：

```text
width % 32 == 0
height % 32 == 0
```

所有 MiniMax H3 任务统一使用 32 像素空间网格，包括 T2V、I2V、FL2V、R2V、V2V、RV2V，无论单段/多段、Motion Context 开/关、是否有参考视频。UI resolution、target、reference video、Motion Context、Source Bridge source 与 Color Re-anchor anchor 都使用同一个 authoritative canvas。

这不是用户选项，也不再存在运行时 16/32 分支。例如输入 `656×864` 会按现有 nearest-multiple 策略统一成为 `640×864`。这样同一工作流后来开启 Motion Context、加入参考视频或切换任务时，不会突然改变 canvas 规则，也不会重用旧的 16-grid cache。

在进入 conditioning/VAE patchify 前还有明确 preflight。非法尺寸会报告 task、path、实际宽高与 `required_stride=32`，不会等到底层才出现难以理解的 shape 错误。

## 缓存与选择运行

Director 使用版本化磁盘缓存：

- segment cache：只在“选择运行已开启 + 全部导出”或 Source Bridge 需要跨 Queue 复用相邻 anchors 时，保存完整 nominal 分段解码结果；普通完整连续生成和仅分段导出不会写入这类大型 RGB cache；
- Motion Context 像素 cache：只保存可见导出终点的最后最多 39 帧 RGB，以及按真实 fps/sample rate 精确对应的末尾 waveform，作为兼容 fallback；
- Motion Context AV latent companion：只保存最后最多 39 个可见帧对应的完整 H3 video latent blocks 与同时间窗 audio latent。H3 对齐产生、但超过可见 endpoint 的 overshoot 不会写入。

Motion Context cache fingerprint 只包含当前分段的提示词、范围、有效素材/source、生成设置，以及该分段实际使用的上游 Motion Context producer digest，不再哈希未来分段。向时间线末尾新增或修改后续分段，不会使此前未修改分段的 Motion Context 缓存失效；只有影响该分段实际生成结果或其有效上游 Motion Context 的修改才会使缓存失效。I2V 明确上传新图的 reset 会截断上游依赖。`context_length` 仍只是下一段消费 tail 时选择 1/5/22/39 帧的设置，不属于上一段生成结果身份；从 22 改成 39 不会仅因此让上一段 cache 失效。旧 V1/V2 Motion Context cache 会直接视为 miss，不会和 V3 segment-dependency 格式混用。

Source Bridge 在同一次 Queue 内会优先使用刚生成、仍在内存中的 nominal Segment，不会为了马上读取而先写入数 GB 文件；只有跨 Queue 缺少内存结果时才读取磁盘 Segment cache。所有 cache 写入仍是 best-effort：磁盘满、只读目录或发布失败不会中断当前主生成，但以后真正依赖缺失 cache 的选择运行或 Bridge 会清楚报错，不会偷偷补采样未选 Segment。

这两个目录都可以手动删除：

```text
ComfyUI/output/minimax_seg_cache
ComfyUI/output/minimax_motion_context_cache
```

删除不会损坏插件、模型或工作流，只会让旧的“选择运行 + 全部导出”、Motion Context 后续段续跑或 Source Bridge 跨 Queue 失去可复用结果；需要时重新生成前置 Segment 即可。普通完整连续生成的段间 Motion Context 仍走当前 Queue 的内存 handoff，不依赖这些目录。

单独运行后续分段时：

- Motion Context 优先需要前一段有效 AV latent companion；缺少时可使用有效 exported pixel cache；
- Source Bridge 需要边界两侧的 nominal generated-segment cache；
- 缺少或过期时会明确报错，先完整运行一次或补跑所需相邻段。

## 显存与性能

- 默认开启 `clear_vram_between_segments`，每段结束后卸载 ComfyUI 模型并清理 CUDA cache，降低长序列峰值占用。
- 关闭后会尽量保留已加载模型以减少重复加载，但更容易在 Motion Context VAE encode 或参考素材较多时耗尽显存。
- Color Re-anchor 使用纯 torch，不增加第三方依赖，但仍需要暂存当前 context 与 anchor 的同尺寸 RGB tensor。
- `export_source_images` 默认关闭，避免额外保留原片对比帧。
- Motion Context 不会为了绕过 OOM 静默减少用户选择的合法上下文长度；请降低输出尺寸或开启段间清理显存。

## 已知限制

- Motion Context 仅支持 H3 原生 24 fps。
- Source Bridge v1 只处理视觉边界，不处理音频 bridge/crossfade。
- Source Bridge 需要边界两侧各有足够的连续真实 source frame，并且不能跨物理文件或编辑跳点。
- Color Re-anchor 是基于 RGB mean/std 的温和统计匹配，不是局部曝光修复、镜头级调色或语义颜色保持模型。
- 多段续接会增加 VAE encode、缓存和显存开销。
- 不同模型、LoRA、sampler、素材运动与提示词可能显著改变续接效果；现有真实 GPU 观察不能当作普遍质量保证。
- 当前测试环境的部分 Turbo/pruned 模型组合可能与附加 Motion/Audio conditioning 不兼容。
- FL2V 仅尾帧、Common/Local 多素材重编号和 latent-first handoff 已有自动测试，但仍需用户使用自己的模型与素材做真实 GPU 质量验收。

## 开发与验证

在仓库根目录运行：

```bash
python -m compileall -q __init__.py director lib nodes patches
python -m pytest -q
node --test tests_js/*.test.mjs
```

真实 GPU 验收至少应分别检查：R2V Common A、B、C + Local D/E 的分段组合、纯场景空素材段、Prompt chip 重编号、I2V/R2V latent-first MC、Color Re-anchor 像素 fallback、FL2V 仅尾帧、V2V/RV2V Source Bridge，以及 External Groups 经一层/多层 Reroute。重点确认所有 H3 画布为 32-safe、有效素材顺序与报告一致，并且导出帧数与音频时长不变。

## 许可证与上游来源

本项目整体以 [GNU General Public License version 3](LICENSE) 发布。

其中包含并修改了 AIMixer `ComfyUI_MiniMaxH3_Director` 的 Apache-2.0 代码，以及 NikoDemon80 `ComfyUI-H3-Motion-Context` 的 GPL-3.0 代码。原始归属与许可证文本保留在 [NOTICE](NOTICE) 和 [LICENSES](LICENSES) 中。
