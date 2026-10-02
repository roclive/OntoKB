# npocut - timestamp based CLI 剪辑工具

## Windows 桌面版

在 [GitHub Releases](https://github.com/roclive/npocut/releases/latest) 下载 Windows x64 安装包（`*-setup.exe`）或免安装 ZIP。ZIP 必须完整解压，再启动 `npocut.exe`。

内置 Electron、Python、FFmpeg/FFprobe 和 faster-whisper，无需另外安装运行环境。支持 Windows 10/11 x64。加载任意目录的视频和 SRT 后点击 **Run**，可在应用中查看日志、取消任务。结果、计划和修改后的字幕保存在“文档\npocut”，点击 **Open output folder** 打开；导入的原文件不会被覆盖。首次自动生成字幕需要联网下载 Whisper 模型，后续复用缓存。

当前安装包未进行代码签名，Windows 可能显示未知发布者提示。发布页提供 SHA-256 校验值。

从源码构建（Windows x64，Node.js 22+）：

```powershell
npm ci
npm test
npm run dist:win
node scripts/smoke-electron.mjs dist/win-unpacked/npocut.exe
```

产物位于 `dist/`。`npm start` 启动开发版（先运行 `npm run prepare:runtime`）。可用 `NPOCUT_WORKSPACE` 环境变量指定输出目录。仓库的 Windows release 工作流可手动构建、测试并发布 package.json 中的版本。


`npocut` 是一个基于命令行和 timestamp 的视频剪辑工具集，适合 YouTube 长视频、单个 Shorts、字幕生成、字幕微调、字幕烧录和按 SRT 快速找剪辑点。Web UI 运行在本机浏览器里，视频不会上传。

## Quick Start on macOS

macOS 不应假设一定有可用的 Python。先检查：

```bash
python3 --version
```

如果没有 `python3`，推荐用 Homebrew 安装。顺便安装 Node.js 和 ffmpeg：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python ffmpeg-full node
```

如果已经有 Python，只需要快速安装 Node.js 和 ffmpeg：

```bash
brew install ffmpeg-full node
```

如果只缺 Node.js：

```bash
brew install node
node --version
npm --version
```

不想用 Homebrew 的话，也可以从 Node.js 官网下载安装包：`https://nodejs.org/`。安装后确认：

```bash
node --version
npm --version
```

克隆并安装 Python 依赖：

```bash
git clone https://github.com/roclive/npocut.git
cd npocut
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

启动 Web UI：

```bash
npm run dev
```

打开终端显示的地址，通常是 `http://localhost:5173/`。在页面里加载视频和 SRT 后，可以用 `Cut`、`Submod`、`Shorts`、`Adv Cut`、`SRT`、`Burn SRT`。

## 依赖

| 依赖 | 用途 | 安装 |
| --- | --- | --- |
| Python 3.10+ | 运行所有 `.py` 脚本 | `brew install python` |
| ffmpeg / ffprobe | 视频切割、拼接、转码、字幕烧录 | `brew install ffmpeg-full` |
| Node.js | 运行 Web UI | `brew install node` |
| faster-whisper | 本地生成 SRT | `pip install -r requirements.txt` |
| OpenAI API key | 可选，用 OpenAI 转写模型生成 SRT | `export OPENAI_API_KEY="..."` |

`generate_srt_openai.py` 使用标准库直接调用 OpenAI API，不需要安装 `openai` Python 包。

## Agent Skills 安装

如果你使用 Codex 或其他支持自定义 skill 的本地 coding agent，可以安装一个 `npocut` skill，让 agent 记住这个项目的视频剪辑流程。

```bash
mkdir -p ~/.codex/skills/npocut
cat > ~/.codex/skills/npocut/SKILL.md <<'EOF'
---
name: npocut
description: Use npocut to generate SRT files, edit subtitle timestamps, build cut plans, make one Short, and burn subtitles for local video editing.
---

Use the local npocut repository for video/subtitle work.
Prefer the documented CLI commands and the Web UI from README.md.
Generated videos, local SRT files, temporary plans, and large media outputs are local editing artifacts and should not be committed unless the user explicitly asks.
EOF
```

安装后，重启 agent 会话，或者让 agent 重新加载 skills。这个 skill 不会安装 Python、Node.js、ffmpeg；这些依赖仍然需要按照上面的 Quick Start 单独安装。

## Web UI

```bash
cd npocut
npm run dev
```

Web UI 会把 plan 文件直接写到 Python 脚本所在目录：

| UI 模式 | 功能 | 导出/保存文件 |
| --- | --- | --- |
| `Cut` | 手动打 IN/OUT，生成保留片段计划 | `clip_plan.csv` |
| `Submod` | 直接编辑 SRT 的 start/end 和字幕正文；改 start 同步上一条 end，改 end 同步下一条 start；`Time Nav` 可切换 timestamp 点击跳转视频；编辑后会自动保存一个备份 SRT | 当前加载的 `.srt` / `<原文件名>.submod-backup.srt` |
| `Shorts` | 在字幕行左侧点 `Add`，把字幕加入一个 short 的保留计划；导出时按选择逐行写入，不自动合并 timestamp | `shorts_plan.csv` |
| `Adv Cut` | 在字幕行左侧点 `Del` 标记要删的字幕，再导出反转后的保留计划 | `cut_plan_new.csv` |
| `SRT` | 生成 `python3 generate_srt.py ...` 命令 | 无 plan |
| `Burn SRT` | 生成 `python3 burn_existing_srt.py ...` 命令 | 无 plan |
| `Burn 9:16` | 生成 `python3 burn_vertical_srt.py ...` 命令，把现有 SRT 烧进 9:16 竖屏视频 | 无 plan |

底部命令栏右侧：

| 按钮 | 作用 |
| --- | --- |
| `Copy` | 复制当前命令 |
| `Terminal` | 先保存当前 plan，再在当前目录打开 macOS Terminal 并执行命令 |

Submod 的自动备份会写到 Python 脚本所在目录，不覆盖原始 SRT。例如加载 `meeting_01.srt` 后，编辑时会自动生成 `meeting_01.submod-backup.srt`。

## 时间格式

以下格式都支持：

```text
75.5
01:15.500
00:01:15.500
00:01:15,500
```

## 常用流程

### YouTube 长视频

```bash
python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"
npm run dev
# UI 中用 Cut 或 Adv Cut 导出 plan
python3 cut_plan.py "long.mp4" clip_plan.csv -o "long.cut.mp4" --srt "long.srt"
python3 burn_existing_srt.py "long.cut.mp4" "long.cut.srt" -o "long.final.mp4"
```

### 生成一个 YouTube Short

Web UI 的 `Shorts` 模式现在是“一次生成一个 short”的逻辑：点多个字幕行的 `Add/Keep` 后，导出时会按选择逐行写入 `shorts_plan.csv`，并把所有区间写成同一个 `output`。同一个 `output` 的多行会在生成 short 时按顺序拼接，中间未选择的时间会被跳过。

```bash
python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"
npm run dev
# UI 中切到 Shorts，点字幕左侧 Add，导出 shorts_plan.csv
python3 make_shorts.py "long.mp4" shorts_plan.csv \
  --srt "long.srt" \
  --burn-srt \
  --out-dir shorts_out \
  --vertical blur
```

示例 `shorts_plan.csv`：

```csv
output,start,end,title
short_01.mp4,00:01:10.000,00:01:58.000,hook
short_01.mp4,00:03:20.000,00:03:42.000,follow up
```

这会只生成一个 `short_01.mp4`，由 CSV 里同一个 `output` 的所有行按顺序拼接而成。

## 命令总览

| 脚本 | 作用 | 常用命令 |
| --- | --- | --- |
| `generate_srt.py` | 本地 faster-whisper 生成 SRT | `python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"` |
| `generate_srt_openai.py` | OpenAI transcription API 生成 SRT | `python3 generate_srt_openai.py "long.mp4" -l zh -o "long.srt"` |
| `burn_subs.py` | 生成 SRT 后人工确认，再烧录字幕 | `python3 burn_subs.py "long.mp4"` |
| `burn_existing_srt.py` | 把已有 SRT 烧录到视频 | `python3 burn_existing_srt.py "long.mp4" "long.srt" -o "long.subbed.mp4"` |
| `srt_find.py` | 搜索 SRT 找剪辑点 | `python3 srt_find.py "long.srt" -q "keyword" -c 2` |
| `cut_plan.py` | 按保留片段计划剪辑、重排、生成新 SRT | `python3 cut_plan.py "long.mp4" clip_plan.csv -o "long.cut.mp4" --srt "long.srt"` |
| `remove_ranges.py` | 按删除区间计划删除并拼回 | `python3 remove_ranges.py "long.mp4" --plan remove_ranges.txt -o "long.clean.mp4" --srt "long.srt"` |
| `srt_slice.py` | 只根据保留计划重新生成 SRT | `python3 srt_slice.py "long.srt" clip_plan.csv -o "long.cut.srt"` |
| `make_shorts.py` | 生成一个竖版 short，可烧录字幕 | `python3 make_shorts.py "long.mp4" shorts_plan.csv --srt "long.srt" --burn-srt --vertical blur` |
| `ffprobe_info.py` | 查看视频时长、编码、分辨率等信息 | `python3 ffprobe_info.py "long.mp4"` |

## 命令参数参考

### `generate_srt.py`

```bash
python3 generate_srt.py VIDEO [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `VIDEO` | 输入视频 | 必填 |
| `-o, --output` | 输出 SRT 路径 | `<video>.srt` |
| `-m, --model` | faster-whisper 模型，如 `tiny`、`base`、`small`、`medium`、`large-v3` | `small` |
| `-l, --language` | 强制输入语言，如 `zh`、`ja`、`en` | 自动检测 |

### `generate_srt_openai.py`

```bash
export OPENAI_API_KEY="你的 OpenAI API key"
python3 generate_srt_openai.py VIDEO [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `VIDEO` | 输入视频或音频 | 必填 |
| `-o, --output` | 输出 SRT 路径 | `<video>.srt` |
| `-m, --model` | OpenAI 转写模型；旧的 `medium` 等本地模型名会被兼容并忽略 | `gpt-4o-transcribe-diarize` |
| `-l, --language` | 输入语言，如 `zh`、`ja`、`en` | 自动检测 |
| `--prompt` | 给转写模型的上下文提示 | 无 |
| `--chunk-seconds` | 长视频临时音频切片秒数 | `300` |
| `--audio-bitrate` | 临时音频码率 | `48k` |
| `--timeout` | API 请求超时秒数 | `600` |
| `--keep-temp` | 保留临时音频切片 | 关闭 |

### `burn_subs.py`

```bash
python3 burn_subs.py INPUT [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `INPUT` | 输入 MP4 | 必填 |
| `-o, --output` | 输出视频 | `<input>.subbed.mp4` |
| `-s, --srt` | SRT 路径 | `<input>.srt` |
| `-m, --model` | faster-whisper 模型 | `small` |
| `-l, --language` | 强制输入语言 | 自动检测 |
| `--keep-srt` | 保留 SRT 文件 | 默认保留 |
| `-y, --yes` | 跳过 SRT 生成后的人工确认 | 关闭 |

### `burn_existing_srt.py`

```bash
python3 burn_existing_srt.py VIDEO SRT [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `VIDEO` | 输入 MP4 | 必填 |
| `SRT` | 已有字幕文件 | 必填 |
| `-o, --output` | 输出视频 | `<video>.subbed.mp4` |

### `cut_plan.py`

```bash
python3 cut_plan.py VIDEO PLAN [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `VIDEO` | 输入视频 | 必填 |
| `PLAN` | `start,end,title` 保留片段计划 | 必填 |
| `-o, --output` | 输出 MP4 | `<video>.cut.mp4` |
| `--srt` | 源 SRT；提供后会同步生成重新计时的 SRT | 无 |
| `--out-srt` | 指定输出 SRT 路径 | `<output>.srt` |
| `--copy` | 用 stream copy 加速，切点附近不如重编码精确 | 关闭 |
| `--crf` | x264 CRF | `18` |
| `--preset` | x264 preset | `veryfast` |
| `--dry-run` | 只打印 ffmpeg 命令，不执行 | 关闭 |
| `--keep-temp` | 保留临时片段文件 | 关闭 |

### `remove_ranges.py`

```bash
python3 remove_ranges.py VIDEO [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `VIDEO` | 输入视频 | 必填 |
| `-p, --plan` | 删除区间文件，支持 CSV、`start-end`、`start --> end` | 无 |
| `-r, --remove` | 直接传入一个删除区间，可重复 | 无 |
| `-o, --output` | 输出 MP4 | `<video>.clean.mp4` |
| `--srt` | 源 SRT；提供后会同步生成重新计时的 SRT | 无 |
| `--out-srt` | 指定输出 SRT 路径 | `<output>.srt` |
| `--write-keep-plan` | 写出自动计算的保留计划 | 无 |
| `--copy` | 用 stream copy 加速，切点附近不如重编码精确 | 关闭 |
| `--crf` | x264 CRF | `18` |
| `--preset` | x264 preset | `veryfast` |
| `--dry-run` | 只打印 ffmpeg 命令，不执行 | 关闭 |
| `--keep-temp` | 保留临时片段文件 | 关闭 |

### `make_shorts.py`

```bash
python3 make_shorts.py VIDEO PLAN [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `VIDEO` | 输入长视频 | 必填 |
| `PLAN` | `output,start,end,title` Shorts 计划 | 必填 |
| `--out-dir` | 输出目录 | `shorts_out` |
| `--srt` | 源 SRT；提供后会给 short 生成重新计时的 SRT | 无 |
| `--burn-srt` | 把重新计时的 SRT 烧录进 short | 关闭 |
| `--no-srt-output` | 不输出旁路 SRT 文件 | 关闭 |
| `--vertical` | 竖屏模式：`crop`、`blur`、`pad`、`none` | `crop` |
| `--target` | 输出尺寸 | `1080x1920` |
| `--max-seconds` | 超时提醒阈值；设为 `0` 关闭 | `180` |
| `--strict-duration` | 超过 `--max-seconds` 时直接失败 | 关闭 |
| `--crf` | x264 CRF | `19` |
| `--preset` | x264 preset | `veryfast` |
| `--font-size` | 烧录字幕字号 | `52` |
| `--margin-v` | 烧录字幕底部边距 | `220` |
| `--font-name` | 烧录字幕字体 | `Helvetica` |
| `--dry-run` | 只打印 ffmpeg 命令，不执行 | 关闭 |
| `--keep-temp` | 保留临时时间线文件 | 关闭 |

竖屏模式说明：

| 模式 | 说明 |
| --- | --- |
| `crop` | 居中裁切成 9:16，适合人物在中间 |
| `blur` | 模糊背景 + 原视频居中，适合横屏内容不想裁掉 |
| `pad` | 黑边补齐 |
| `none` | 不改比例 |

### `srt_find.py`

```bash
python3 srt_find.py SRT [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `SRT` | 输入字幕 | 必填 |
| `-q, --query` | 搜索文本或正则 | 无 |
| `-c, --context` | 显示命中项前后多少条字幕 | `1` |
| `--all` | 列出全部字幕 | 未传 `--query` 时默认 |
| `--ignore-case` | 忽略大小写 | 开启 |

### `srt_slice.py`

```bash
python3 srt_slice.py SRT PLAN [OPTIONS]
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `SRT` | 源字幕 | 必填 |
| `PLAN` | `start,end,title` 保留片段计划 | 必填 |
| `-o, --output` | 输出 SRT | `<srt>.slice.srt` |

### `ffprobe_info.py`

```bash
python3 ffprobe_info.py VIDEO
```

| 参数 | 说明 |
| --- | --- |
| `VIDEO` | 要查看信息的视频 |

## Plan 文件格式

### `clip_plan.csv` / `cut_plan_new.csv`

```csv
start,end,title
00:01:10.000,00:02:04.000,opening hook
00:08:30.000,00:09:12.000,best explanation
```

CSV 行顺序就是输出视频顺序。

### `remove_ranges.txt`

```text
00:03:12.000,00:03:28.000,dead air
00:10:00.000-00:10:20.000
00:24:15.000 --> 00:24:40.000 long pause
```

### `shorts_plan.csv`

```csv
output,start,end,title
short_01.mp4,00:01:10.000,00:01:58.000,hook
short_01.mp4,00:03:20.000,00:03:42.000,follow up
```

同一个 `output` 的多行会被拼成同一个 short。

## 示例文件

- `examples/clip_plan.csv`
- `examples/remove_ranges.txt`
- `examples/shorts_plan.csv`
