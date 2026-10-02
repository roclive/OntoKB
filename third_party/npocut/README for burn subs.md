# Burn Subs - MP4 字幕烧录工具

自动为 MP4 视频生成带时间戳的字幕文件，并将其烧录（硬编码）到视频中，输出为单个 MP4 文件。

## 功能

- ✅ 自动语音识别 (ASR) — 基于 OpenAI Whisper，支持多语言自动检测
- ✅ 生成 SRT 字幕文件（含精确时间戳）
- ✅ **支持只生成 SRT** — `generate_srt.py` 只转录，不烧录视频
- ✅ **支持 OpenAI API 转写** — `generate_srt_openai.py` 使用 OpenAI transcription API，不用本地 Whisper
- ✅ **人工确认/编辑环节** — 转录完成后暂停，可手动校对/修改 SRT，再继续烧录
- ✅ 硬编码字幕到视频 — 字幕成为视频的一部分（单文件）
- ✅ 自定义字幕样式 — 字体、大小、颜色、位置
- ✅ **支持烧录已有 SRT** — `burn_existing_srt.py` 跳过转录，直接烧录

## 依赖

### 系统要求
- macOS / Linux / Windows（有 ffmpeg）
- Python 3.7+

### 安装

#### 1. 安装 Python 依赖
```bash
pip install faster-whisper
```

#### 2. 安装 ffmpeg（需要 libass 支持）

**macOS（推荐）：**
```bash
brew install ffmpeg-full
```
> ⚠️ Homebrew 的默认 `ffmpeg` 缺少 libass（字幕滤镜）。必须用 `ffmpeg-full`。

**Ubuntu/Debian：**
```bash
sudo apt install ffmpeg
```

**其他系统：** 从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载（确保编译时启用 `--enable-libass`）

#### 3. 复制脚本
```bash
cp burn_subs.py <your-project-dir>/
```

## 快速开始

### 完整流程（转录 + 人工确认 + 烧录）
```bash
python3 burn_subs.py "input.mp4"
```

执行过程：
1. **转录** — Whisper 生成 `input.srt`
2. **暂停等待确认** — 终端会提示：
   ```
   [REVIEW] SRT file generated: input.srt
     - Open the file in your editor and fix any errors.
     - Save your changes before continuing.
   Proceed to burn subtitles? [y/N/r=re-show path]:
   ```
   - 输入 `y` 继续烧录
   - 输入 `n` 或回车 取消
   - 输入 `r` 再次显示 SRT 文件绝对路径
   - 这时可以打开 `input.srt`、手工修改文本/时间戳、保存
3. **烧录** — 输出 `input.subbed.mp4`

### 跳过确认（自动化场景）
```bash
python3 burn_subs.py "input.mp4" -y
```

### 只生成 SRT 字幕文件（不烧录视频）
```bash
python3 generate_srt.py "input.mp4"
```

使用较大模型、指定语言、自定义输出路径：
```bash
python3 generate_srt.py "input.mp4" -m medium -l ja -o "input.srt"
```

使用 OpenAI API 生成 SRT，不用本地 Whisper：
```bash
export OPENAI_API_KEY="你的 OpenAI API key"
python3 generate_srt_openai.py "input.mp4" -l zh -o "input.srt"
```

### 只烧录已有 SRT（不转录）
```bash
python3 burn_existing_srt.py "input.mp4" "input.srt"
```

输出文件：
- `input.srt` — 字幕文件（可手工编辑）
- `input.subbed.mp4` — 带字幕的视频（输出）

## 详细用法

### `burn_subs.py` — 完整流程

```bash
python3 burn_subs.py INPUT_FILE [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `INPUT_FILE` | 源 MP4 文件 | **必需** |
| `-o, --output` | 输出 MP4 路径 | `<input>.subbed.mp4` |
| `-s, --srt` | SRT 字幕文件路径 | `<input>.srt` |
| `-m, --model` | Whisper 模型大小 | `small` |
| `-l, --language` | 强制语言代码（如 `en`, `ja`, `zh`） | 自动检测 |
| `--keep-srt` | 处理后保留 SRT 文件 | 默认保留 |
| `-y, --yes` | 跳过 SRT 生成后的人工确认 | 默认需确认 |

### `burn_existing_srt.py` — 仅烧录已有 SRT

```bash
python3 burn_existing_srt.py VIDEO_FILE SRT_FILE [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `VIDEO_FILE` | 源 MP4 文件 | **必需** |
| `SRT_FILE` | 已存在的 SRT 字幕文件 | **必需** |
| `-o, --output` | 输出 MP4 路径 | `<video>.subbed.mp4` |

### `generate_srt.py` — 仅生成 SRT

```bash
python3 generate_srt.py VIDEO_FILE [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `VIDEO_FILE` | 源视频文件 | **必需** |
| `-o, --output` | 输出 SRT 路径 | `<video>.srt` |
| `-m, --model` | Whisper 模型大小 | `small` |
| `-l, --language` | 强制语言代码（如 `en`, `ja`, `zh`） | 自动检测 |

### `generate_srt_openai.py` — 使用 OpenAI API 仅生成 SRT

```bash
python3 generate_srt_openai.py VIDEO_FILE [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `VIDEO_FILE` | 源视频文件 | **必需** |
| `-o, --output` | 输出 SRT 路径 | `<video>.srt` |
| `-m, --model` | OpenAI transcription 模型；旧的 `medium` 等本地模型名会被忽略 | `gpt-4o-transcribe-diarize` |
| `-l, --language` | 强制输入语言代码（如 `en`, `ja`, `zh`） | 自动检测 |
| `--chunk-seconds` | 长视频临时切片秒数 | `300` |

适用场景：
- 已用 `burn_subs.py` 生成 SRT 但取消了烧录，想之后重新跑
- 字幕由其他工具/人工翻译生成
- 反复调整字幕样式重新烧录

### 示例

**使用较大模型获得更准确的转录：**
```bash
python3 burn_subs.py "video.mp4" -m medium
```

**指定语言（加快识别，提高准确度）：**
```bash
python3 burn_subs.py "video.mp4" -l ja  # 日语
python3 burn_subs.py "video.mp4" -l en  # 英语
python3 burn_subs.py "video.mp4" -l zh  # 中文
```

**自定义输出路径：**
```bash
python3 burn_subs.py "video.mp4" -o "output/video_with_subs.mp4" -s "output/subs.srt"
```

**组合使用：**
```bash
python3 burn_subs.py "shorts.mp4" -m large -l ja -o "finals/shorts_subbed.mp4"
```

**自动化模式（CI/批处理，跳过确认）：**
```bash
python3 burn_subs.py "shorts.mp4" -m medium -l ja -y
```

**编辑 SRT 后再烧录：**
```bash
# 第一步：转录后取消（输入 n）
python3 burn_subs.py "shorts.mp4"
# 第二步：手工编辑 shorts.srt
# 第三步：用已有 SRT 烧录
python3 burn_existing_srt.py "shorts.mp4" "shorts.srt"
```

## 自定义字幕样式

编辑 `burn_subs.py` 中的字幕样式配置（第 73-75 行）：

```python
style = (
    "FontName=Helvetica,"           # 字体名
    "FontSize=18,"                  # 字号
    "PrimaryColour=&H00FFFFFF,"     # 主颜色（白色）BGR 格式
    "OutlineColour=&H00000000,"     # 描边颜色（黑色）
    "BorderStyle=1,"                # 边框样式（1=有描边和阴影）
    "Outline=2,"                    # 描边粗细
    "Shadow=0,"                     # 阴影
    "Alignment=2,"                  # 对齐方式（2=底部中心）
    "MarginV=40"                    # 距底部距离（像素）
)
```

### 颜色格式（BGR 十六进制）
- `&H00FFFFFF` = 白色
- `&H000000FF` = 红色
- `&H0000FF00` = 绿色
- `&H00FF0000` = 蓝色
- `&H00FFFF00` = 青色

### 对齐方式（Alignment）
```
7 8 9  (左上、中上、右上)
4 5 6  (左中、中心、右中)
1 2 3  (左下、中下、右下)  ← 2 是底部中心（推荐）
```

**修改后重新运行：**
```bash
python3 burn_subs.py "input.mp4"
```

## Whisper 模型选择

| 模型 | 大小 | 速度 | 准确度 | 显存 |
|------|------|------|--------|------|
| `tiny` | 39M | ⚡⚡⚡ | ⭐ | 1GB |
| `base` | 140M | ⚡⚡ | ⭐⭐ | 1GB |
| `small` | 466M | ⚡ | ⭐⭐⭐ | 2GB |
| `medium` | 1.5G | 中速 | ⭐⭐⭐⭐ | 5GB |
| `large-v3` | 3.1G | 慢 | ⭐⭐⭐⭐⭐ | 10GB |

**推荐：** YouTube Shorts/TikTok 用 `small`，长视频用 `medium`。

## 工作流程

```
input.mp4
   ↓
[1] Whisper 转录音频  (burn_subs.py)
   ↓
input.srt (带时间戳)
   ↓
[2] ⏸  人工确认/编辑     ← 可在此手动校对
   ↓
[3] ffmpeg subtitles 滤镜烧录
   ↓
input.subbed.mp4 ✓
```

**只烧录已有 SRT：**
```
input.mp4 + input.srt
   ↓
ffmpeg subtitles 滤镜烧录   (burn_existing_srt.py)
   ↓
input.subbed.mp4 ✓
```

## 故障排除

### 错误：`ModuleNotFoundError: No module named 'faster_whisper'`
```bash
pip install faster-whisper
```

### 错误：`ffmpeg: subtitles filter not found`

**macOS：**
```bash
# 检查当前 ffmpeg 版本
ffmpeg -version

# 卸载并重装 ffmpeg-full
brew uninstall ffmpeg
brew install ffmpeg-full

# 验证 libass 支持
/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg -hide_banner -filters | grep subtitles
```

**Linux：** 确保编译了 libass 支持：
```bash
ffmpeg -version | grep libass
```

### 转录很慢

- 使用较小模型：`-m small` 或 `tiny`
- 指定语言加快处理：`-l ja`（日语例子）
- 若有 GPU，修改代码 device 参数（需装 torch + cuda）

### 输出文件很大

默认编码使用 H.264 + CRF 20。要压缩更多：
```python
# 在 burn_subs.py 中改第 85 行的 CRF 值（范围 0-51，数字越大越低质量）
"-crf", "28",  # 更高压缩率（但质量会下降）
```

### 字幕位置/样式不对

编辑 `burn_subs.py` 中的 `style` 字符串，参考"自定义字幕样式"部分。

## 许可证

MIT

## 相关资源

- [Whisper 文档](https://github.com/openai/whisper)
- [faster-whisper](https://github.com/guillaumekln/faster-whisper)
- [FFmpeg 文档](https://ffmpeg.org/documentation.html)
- [ASS 字幕格式](https://en.wikipedia.org/wiki/SubStation_Alpha)
