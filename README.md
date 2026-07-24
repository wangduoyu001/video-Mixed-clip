# Video Mixed Clip

## AI 本地视频混剪器

这是一个完全独立的本地视频混剪项目，不包含短剧导演、人物资产、场景资产、分镜或生图生视频系统。

核心能力：

- 扫描本地视频素材并建立 SQLite 索引
- 每个原视频默认只处理前 40 秒
- 场景切分、缩略图和媒体信息提取
- 根据文案检索并规划多来源粗剪时间线
- 支持原声、配音和混合音频模式
- Whisper 时间对齐
- SRT、ASS 和卡拉 OK 字幕
- FFmpeg 预览渲染
- 镜头锁定、替换、重规划和回滚
- 导出剪映可编辑素材包
- 可选生成剪映草稿

## 仓库边界

```text
本仓库：素材扫描、自动粗剪、字幕、配音、返修、剪映交付
旧短剧仓库：短剧剧本、资产、分镜和导演系统
```

两个项目代码、配置、数据库和输出目录完全分开。

## Windows 安装

```powershell
git clone https://github.com/wangduoyu001/video-Mixed-clip.git
cd video-Mixed-clip
powershell -ExecutionPolicy Bypass -File scripts/setup_jianying_windows.ps1 -InstallMissingTools
```

## 环境检查

```powershell
script-driven-mixer --config script_mixer.local.json doctor
script-driven-mixer --config script_mixer.local.json models
script-driven-mixer --config script_mixer.local.json jianying-status
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

以下命令等价：

```text
video-mixed-clip
ai-local-video-mixer
script-driven-mixer
```

## 测试

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
video-mixed-clip --help
```

## 重要规则

- 原始素材只读，不删除、不移动、不覆盖。
- 每个原视频默认最多处理前 40 秒。
- Whisper 只用于时间证据，不覆盖用户原文。
- 剪映草稿失败时，标准 MP4、WAV、SRT 和 CSV 编辑包仍需保留。
- 自动粗剪必须人工审核，算法并不会因为文件夹改了名字就突然懂导演艺术。
