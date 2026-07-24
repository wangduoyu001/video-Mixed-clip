# Video Mixed Clip

## AI 本地信息流素材理解与自动混剪器

这是一个完全独立的本地视频混剪项目，不包含短剧导演、人物资产、场景资产、分镜或生图生视频系统。

核心能力：

- 完整扫描整条本地视频，不再默认只识别前 40 秒
- 场景切分、媒体信息和多帧画面抽取
- 识别人物、动作、场景、道具、产品、包装、原字幕、水印和画面文字
- 区分客观事实、可能暗示、叙事功能和剪辑表现手法
- 任何产品包装、运输包装或疑似容器默认硬淘汰
- 根据文案匹配多来源画面并规划粗剪时间线
- 固定跑量开头，批量裂变不同后续画面
- 同一文案批量生成不同画面组合
- 检测原视频字幕冲突，优先裁切、局部模糊或小面积磨砂处理
- 支持原声、配音和混合音频模式
- Whisper 时间对齐
- SRT、ASS 和卡拉 OK 字幕
- FFmpeg 预览渲染
- 镜头锁定、替换、重规划和回滚
- 导出剪映可编辑素材包

## 仓库边界

```text
本仓库：素材理解、信息流裂变、自动粗剪、字幕、配音、返修、剪映交付
旧短剧仓库：短剧剧本、资产、分镜和导演系统
```

两个项目的代码、配置、数据库和输出目录完全分开。

## Windows 安装

```powershell
git clone https://github.com/wangduoyu001/video-Mixed-clip.git
cd video-Mixed-clip
powershell -ExecutionPolicy Bypass -File scripts/setup_jianying_windows.ps1 -InstallMissingTools
```

## 标准工作流

### 1. 扫描完整素材

```powershell
script-driven-mixer --config script_mixer.local.json scan-media "D:\视频素材"
```

扫描阶段默认识别整条原视频。成片中同一来源的使用时长限制由剪辑规则控制，不再通过截断素材识别实现。

### 2. 多帧素材理解与安全过滤

```powershell
material-intelligence --config script_mixer.local.json analyze
material-intelligence --config script_mixer.local.json status
```

分析结果写入同一个 SQLite 素材库。以下镜头自动设为不可用：

```text
产品零售包装
快递或运输包装
无法确认是道具还是包装的瓶、盒、袋
明显水印
分析失败且启用 fail-closed
```

原始视频不会被删除、移动或修改。

### 3. 生成基础粗剪

```powershell
script-driven-mixer --config script_mixer.local.json plan `
  --script "D:\文案\input.txt" `
  --voice "D:\配音\voice.wav"
```

### 4. 围绕跑量母素材裂变

固定前三秒开头，只更换后续画面：

```powershell
creative-variants --config script_mixer.local.json generate <项目目录或项目ID> `
  --mode same_hook_new_body `
  --count 8 `
  --hook-seconds 3 `
  --seed 20260724
```

固定文案和结构，整条更换画面：

```powershell
creative-variants --config script_mixer.local.json generate <项目目录或项目ID> `
  --mode same_script_new_visuals `
  --count 8
```

每个变体都会记录母素材、测试假设、替换镜头、随机种子和原字幕处理建议，避免批量生成之后没人知道到底测试了什么。

## 原字幕处理原则

原字幕与新文案不一致时，按以下顺序处理：

1. 轻微放大或上移构图，将贴近底边的旧字幕裁掉。
2. 对小区域做局部羽化模糊。
3. 复杂背景使用小面积半透明磨砂承托区。
4. 原字幕压住人物、商品或占据过大区域时，直接换镜头或重新构图。

禁止使用覆盖半个画面的纯黑、纯白或高饱和色块。

## 环境检查

```powershell
script-driven-mixer --config script_mixer.local.json doctor
script-driven-mixer --config script_mixer.local.json models
script-driven-mixer --config script_mixer.local.json jianying-status
material-intelligence --config script_mixer.local.json status
```

## 一键生成剪映项目

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_jianying_project.ps1 `
  -MediaRoot "D:\视频素材" `
  -Script "D:\文案\input.txt" `
  -Voice "D:\配音\voice.wav" `
  -DraftRoot "D:\JianyingPro Drafts"
```

没有配音时删除 `-Voice` 参数。

## CLI

```text
video-mixed-clip       主混剪命令
script-driven-mixer    兼容命令
material-intelligence  多帧素材理解、包装和原字幕识别
creative-variants      跑量母素材裂变
```

## 测试

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
video-mixed-clip --help
material-intelligence --help
creative-variants --help
```

## 重要规则

- 原始素材只读，不删除、不移动、不覆盖。
- 素材理解默认覆盖整条视频。
- 任何产品包装或疑似包装镜头默认淘汰。
- 拍摄道具只有在高置信度确认后才允许进入候选库。
- 自动裂变每轮尽量只改变一到两个测试变量。
- 原字幕遮盖不得使用又大又丑的纯色色块。
- 自动粗剪必须人工审核，模型毕竟还没有拿过投放预算，也不会替人承担烧钱责任。
