# npocut - timestamp based CLI 剪辑工具

## Windows desktop app

Download the x64 installer (`*-setup.exe`) or portable ZIP from [GitHub Releases](https://github.com/roclive/npocut/releases/latest). Extract the entire ZIP before running `npocut.exe`.

Windows 10/11 x64 is supported. Electron, Python, FFmpeg/FFprobe, and faster-whisper are bundled. Load media from any folder and click **Run** to process it with in-app logs and cancellation. Outputs, plans, and subtitle edits go to **Documents\npocut**; imported originals are preserved. First transcription needs internet access to download Whisper weights; subsequent runs reuse the cache.

The app is unsigned. Windows may display an unknown-publisher prompt. SHA-256 checksums are supplied with the release.

Build on Windows x64 with Node.js 22+: `npm ci`, `npm test`, then `npm run dist:win`. Verify the built executable with `node scripts/smoke-electron.mjs dist/win-unpacked/npocut.exe`. Artifacts are in `dist/`. For development run `npm run prepare:runtime` then `npm start`. Set `NPOCUT_WORKSPACE` to customize the output folder. The manually dispatched Windows release workflow builds, tests, and publishes the version in package.json.


## English Version

`npocut` is a timestamp-first video editing toolkit for long YouTube videos, single Shorts, subtitle generation, subtitle cleanup, subtitle burn-in, and SRT-based edit planning. It provides both practical Python CLI scripts and a local Web UI. Media files stay on your machine and are not uploaded.

### macOS Quick Start

Do not assume macOS already has a usable Python. Check first:

```bash
python3 --version
```

If `python3` is missing, install Homebrew first, then install Python, Node.js, and ffmpeg:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python ffmpeg-full node
```

If Python is already installed, install only ffmpeg and Node.js:

```bash
brew install ffmpeg-full node
```

If only Node.js is missing:

```bash
brew install node
node --version
npm --version
```

You can also install Node.js from the official macOS installer at `https://nodejs.org/`. After installing, verify:

```bash
node --version
npm --version
```

Clone the repository and install Python dependencies:

```bash
git clone https://github.com/roclive/npocut.git
cd npocut
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

Start the Web UI:

```bash
npm run dev
```

Open the URL printed in the terminal, usually `http://localhost:5173/`. Load a video and an SRT file to use `Cut`, `Submod`, `Shorts`, `Adv Cut`, `SRT`, `Burn SRT`, and `Burn 9:16`.

### Dependencies

| Dependency | Purpose | Install |
| --- | --- | --- |
| Python 3.10+ | Run all `.py` scripts | `brew install python` |
| ffmpeg / ffprobe | Cut, concatenate, transcode, and burn subtitles | `brew install ffmpeg-full` |
| Node.js | Run the Web UI | `brew install node` |
| faster-whisper | Local SRT generation | `pip install -r requirements.txt` |
| OpenAI API key | Optional, for OpenAI transcription models | `export OPENAI_API_KEY="..."` |

`generate_srt_openai.py` calls the OpenAI API directly with the Python standard library, so the `openai` Python package is not required.

### Agent Skills

If you use Codex or another local coding agent that supports custom skills, you can install an `npocut` skill so the agent remembers the project workflow.

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

After installing the skill, restart the agent session or ask the agent to reload skills. The skill does not install Python, Node.js, or ffmpeg; install those dependencies separately with the Quick Start above.

### Web UI

```bash
cd npocut
npm run dev
```

The Web UI saves plan files directly into the same directory as the Python scripts.

| UI mode | Purpose | Output/saved file |
| --- | --- | --- |
| `Cut` | Mark IN/OUT ranges manually and export a keep plan | `clip_plan.csv` |
| `Submod` | Edit SRT start/end timestamps and subtitle text. Changing a start syncs the previous end; changing an end syncs the next start. `Time Nav` turns timestamp clicks into video seeking. Edits also auto-save a backup SRT | loaded `.srt` / `<source>.submod-backup.srt` |
| `Shorts` | Click `Add` on subtitle rows to keep them for one Short. Export writes selected ranges row by row with one output name | `shorts_plan.csv` |
| `Adv Cut` | Click `Del` on subtitle rows to mark deletion ranges, then export the reversed keep plan | `cut_plan_new.csv` |
| `SRT` | Generate a `python3 generate_srt.py ...` command | no plan |
| `Burn SRT` | Generate a `python3 burn_existing_srt.py ...` command | no plan |
| `Burn 9:16` | Generate a `python3 burn_vertical_srt.py ...` command for vertical subtitle burn-in | no plan |

Bottom command buttons:

| Button | Action |
| --- | --- |
| `Copy` | Copy the current command |
| `Terminal` | Save the current plan, open macOS Terminal in the current directory, and run the command |

Submod auto-backups are written next to the Python scripts and do not overwrite the original SRT. Example: loading `meeting_01.srt` creates `meeting_01.submod-backup.srt` while editing.

### Timestamp Format

These formats are supported:

```text
75.5
01:15.500
00:01:15.500
00:01:15,500
```

### Common Workflows

#### Long YouTube Video

```bash
python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"
npm run dev
# Export a plan from Cut or Adv Cut in the UI
python3 cut_plan.py "long.mp4" clip_plan.csv -o "long.cut.mp4" --srt "long.srt"
python3 burn_existing_srt.py "long.cut.mp4" "long.cut.srt" -o "long.final.mp4"
```

#### Create One YouTube Short

The `Shorts` UI mode is designed to create one Short at a time. Click `Add/Keep` on multiple subtitle rows, export `shorts_plan.csv`, and all selected ranges will be written with the same output name. Unselected time is skipped when the Short is generated.

```bash
python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"
npm run dev
# Switch to Shorts, click Add on subtitle rows, then export shorts_plan.csv
python3 make_shorts.py "long.mp4" shorts_plan.csv \
  --srt "long.srt" \
  --burn-srt \
  --out-dir shorts_out \
  --vertical blur
```

Example `shorts_plan.csv`:

```csv
output,start,end,title
short_01.mp4,00:01:10.000,00:01:58.000,hook
short_01.mp4,00:03:20.000,00:03:42.000,follow up
```

Rows with the same `output` are concatenated into one Short.

### Command Overview

| Script | Purpose | Common command |
| --- | --- | --- |
| `generate_srt.py` | Generate local SRT with faster-whisper | `python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"` |
| `generate_srt_openai.py` | Generate SRT with OpenAI transcription API | `python3 generate_srt_openai.py "long.mp4" -l zh -o "long.srt"` |
| `burn_subs.py` | Generate/check SRT, then burn subtitles | `python3 burn_subs.py "long.mp4"` |
| `burn_existing_srt.py` | Burn an existing SRT into a video | `python3 burn_existing_srt.py "long.mp4" "long.srt" -o "long.subbed.mp4"` |
| `burn_vertical_srt.py` | Burn an existing SRT into a 9:16 vertical video | `python3 burn_vertical_srt.py "long.mp4" "long.srt" -o "long.vertical.subbed.mp4"` |
| `srt_find.py` | Search SRT text to find edit points | `python3 srt_find.py "long.srt" -q "keyword" -c 2` |
| `cut_plan.py` | Cut/reorder keep ranges and retime SRT | `python3 cut_plan.py "long.mp4" clip_plan.csv -o "long.cut.mp4" --srt "long.srt"` |
| `remove_ranges.py` | Remove ranges and concatenate the remaining video | `python3 remove_ranges.py "long.mp4" --plan remove_ranges.txt -o "long.clean.mp4" --srt "long.srt"` |
| `srt_slice.py` | Retiming-only SRT generation from a keep plan | `python3 srt_slice.py "long.srt" clip_plan.csv -o "long.cut.srt"` |
| `make_shorts.py` | Generate one subtitle-aware vertical Short | `python3 make_shorts.py "long.mp4" shorts_plan.csv --srt "long.srt" --burn-srt --vertical blur` |
| `ffprobe_info.py` | Show video duration, codec, resolution, and streams | `python3 ffprobe_info.py "long.mp4"` |

### Command Parameter Reference

#### `generate_srt.py`

```bash
python3 generate_srt.py VIDEO [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source video file | required |
| `-o, --output` | Output SRT path | `<video>.srt` |
| `-m, --model` | faster-whisper model: `tiny`, `base`, `small`, `medium`, `large-v3` | `small` |
| `-l, --language` | Force input language, e.g. `zh`, `ja`, `en` | auto-detect |

#### `generate_srt_openai.py`

```bash
export OPENAI_API_KEY="your OpenAI API key"
python3 generate_srt_openai.py VIDEO [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source video/audio file | required |
| `-o, --output` | Output SRT path | `<video>.srt` |
| `-m, --model` | OpenAI transcription model; old local Whisper sizes are accepted for compatibility | `gpt-4o-transcribe-diarize` |
| `-l, --language` | Input language code, e.g. `zh`, `ja`, `en` | auto-detect |
| `--prompt` | Optional transcription prompt/context | none |
| `--chunk-seconds` | Audio chunk length in seconds | `300` |
| `--audio-bitrate` | Temporary audio bitrate | `48k` |
| `--timeout` | API request timeout in seconds | `600` |
| `--keep-temp` | Keep temporary audio chunks | off |

#### `burn_subs.py`

```bash
python3 burn_subs.py INPUT [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `INPUT` | Source MP4 file | required |
| `-o, --output` | Output MP4 | `<input>.subbed.mp4` |
| `-s, --srt` | SRT path | `<input>.srt` |
| `-m, --model` | faster-whisper model | `small` |
| `-l, --language` | Force language code | auto-detect |
| `--keep-srt` | Keep generated SRT after burning | kept |
| `-y, --yes` | Skip manual confirmation after SRT generation | off |

#### `burn_existing_srt.py`

```bash
python3 burn_existing_srt.py VIDEO SRT [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source MP4 file | required |
| `SRT` | Existing SRT subtitle file | required |
| `-o, --output` | Output MP4 | `<video>.subbed.mp4` |

#### `burn_vertical_srt.py`

```bash
python3 burn_vertical_srt.py VIDEO SRT [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source video | required |
| `SRT` | Existing SRT subtitle file | required |
| `-o, --output` | Output MP4 | `<video>.vertical.subbed.mp4` |
| `--vertical` | 9:16 mode: `crop`, `blur`, `pad` | `crop` |
| `--target` | Output dimensions | `1080x1920` |
| `--crf` | x264 CRF, lower is larger/better | `19` |
| `--preset` | x264 preset | `veryfast` |
| `--font-size` | Burned subtitle font size | auto |
| `--margin-v` | Burned subtitle bottom margin | auto |
| `--subtitle-line-chars` | Approximate characters per subtitle line | auto |
| `--font-name` | Burned subtitle font | `Helvetica` |
| `--dry-run` | Print ffmpeg command only | off |

#### `cut_plan.py`

```bash
python3 cut_plan.py VIDEO PLAN [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source video | required |
| `PLAN` | Keep-plan CSV/TXT with `start,end` rows | required |
| `-o, --output` | Output MP4 | `<video>.cut.mp4` |
| `--srt` | Source SRT to retime | none |
| `--out-srt` | Retimed SRT path | `<output>.srt` when `--srt` is set |
| `--copy` | Stream copy for speed; less frame-accurate around cuts | off |
| `--crf` | x264 CRF when re-encoding | `18` |
| `--preset` | x264 preset when re-encoding | `veryfast` |
| `--dry-run` | Print ffmpeg commands only | off |
| `--keep-temp` | Keep temporary segment files | off |

#### `remove_ranges.py`

```bash
python3 remove_ranges.py VIDEO [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source video | required |
| `-p, --plan` | Text/CSV file with ranges to remove | none |
| `-r, --remove` | Range to remove; repeatable, e.g. `-r 00:01:00-00:01:20` | none |
| `-o, --output` | Output MP4 | `<video>.clean.mp4` |
| `--srt` | Source SRT to retime | none |
| `--out-srt` | Retimed SRT path | `<output>.srt` when `--srt` is set |
| `--write-keep-plan` | Write computed keep ranges as CSV | none |
| `--copy` | Stream copy for speed; less frame-accurate around cuts | off |
| `--crf` | x264 CRF when re-encoding | `18` |
| `--preset` | x264 preset when re-encoding | `veryfast` |
| `--dry-run` | Print ffmpeg commands only | off |
| `--keep-temp` | Keep temporary segment files | off |

#### `make_shorts.py`

```bash
python3 make_shorts.py VIDEO PLAN [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source long video | required |
| `PLAN` | `output,start,end,title` Shorts plan | required |
| `--out-dir` | Directory for generated shorts | `shorts_out` |
| `--srt` | Source SRT to retime per short | none |
| `--burn-srt` | Burn the retimed SRT into each short; requires `--srt` | off |
| `--no-srt-output` | Do not write sidecar SRT files | off |
| `--vertical` | `crop`, `blur`, `pad`, or `none` | `crop` |
| `--target` | Output dimensions for vertical modes | `1080x1920` |
| `--max-seconds` | Warn when a short exceeds this duration; `0` disables | `60` |
| `--strict-duration` | Fail instead of warning when `--max-seconds` is exceeded | off |
| `--crf` | x264 CRF for final shorts | `19` |
| `--preset` | x264 preset | `veryfast` |
| `--font-size` | Burned subtitle font size | auto |
| `--margin-v` | Burned subtitle bottom margin | auto |
| `--subtitle-line-chars` | Approximate characters per burned subtitle line | auto |
| `--font-name` | Burned subtitle font | `Helvetica` |
| `--dry-run` | Print ffmpeg commands only | off |
| `--keep-temp` | Keep temporary timeline files | off |

#### `srt_find.py`

```bash
python3 srt_find.py SRT [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `SRT` | Source SRT | required |
| `-q, --query` | Text or regex to search | none |
| `-c, --context` | Neighbor cues to show around matches | `0` |
| `--all` | List all cues | default when `--query` is omitted |
| `--ignore-case` | Case-insensitive search | on |

#### `srt_slice.py`

```bash
python3 srt_slice.py SRT PLAN [OPTIONS]
```

| Argument | Description | Default |
| --- | --- | --- |
| `SRT` | Source SRT | required |
| `PLAN` | Keep-plan CSV/TXT with `start,end` rows | required |
| `-o, --output` | Output SRT | `<source>.cut.srt` |

#### `ffprobe_info.py`

```bash
python3 ffprobe_info.py VIDEO
```

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Video file to inspect | required |

#### `make_srt_only.py`

Legacy local SRT-only wrapper. Prefer `generate_srt.py`.

| Argument | Description | Default |
| --- | --- | --- |
| `VIDEO` | Source video | required |
| `-o, --output` | Output SRT | `<video>.srt` |
| `-m, --model` | faster-whisper model | `small` |
| `-l, --language` | Force language code | auto-detect |

### Sample Files

- `examples/clip_plan.csv`
- `examples/remove_ranges.txt`
- `examples/shorts_plan.csv`

---

## 日本語版

`npocut` は、コマンドラインと timestamp を中心にした動画編集ツールセットです。YouTube 長尺動画、単一 Shorts、字幕生成、字幕微修正、字幕焼き込み、SRT からの編集点検索に使えます。Web UI はローカルブラウザで動作し、動画はアップロードされません。

### macOS Quick Start

macOS に必ず Python が入っているとは限りません。まず確認します。

```bash
python3 --version
```

`python3` がない場合は、Homebrew で Python、Node.js、ffmpeg をまとめて入れるのが簡単です。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python ffmpeg-full node
```

Python がすでにある場合は、Node.js と ffmpeg だけで十分です。

```bash
brew install ffmpeg-full node
```

Node.js だけ不足している場合:

```bash
brew install node
node --version
npm --version
```

Homebrew を使わない場合は、Node.js 公式サイト `https://nodejs.org/` から macOS 用インストーラを入れてください。インストール後に確認します。

```bash
node --version
npm --version
```

リポジトリを取得し、Python 依存関係を入れます。

```bash
git clone https://github.com/roclive/npocut.git
cd npocut
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

Web UI を起動します。

```bash
npm run dev
```

ターミナルに表示された URL、通常は `http://localhost:5173/` を開きます。ページ上で動画と SRT を読み込むと、`Cut`、`Submod`、`Shorts`、`Adv Cut`、`SRT`、`Burn SRT` を使えます。

### 依存関係

| 依存関係 | 用途 | インストール |
| --- | --- | --- |
| Python 3.10+ | すべての `.py` スクリプトの実行 | `brew install python` |
| ffmpeg / ffprobe | 動画の切り出し、結合、変換、字幕焼き込み | `brew install ffmpeg-full` |
| Node.js | Web UI の実行 | `brew install node` |
| faster-whisper | ローカル SRT 生成 | `pip install -r requirements.txt` |
| OpenAI API key | 任意。OpenAI の転写モデルで SRT を生成 | `export OPENAI_API_KEY="..."` |

`generate_srt_openai.py` は Python 標準ライブラリで OpenAI API を直接呼び出すため、`openai` Python パッケージは不要です。

### Agent Skills

Codex など、カスタム skill に対応したローカル coding agent を使う場合は、`npocut` 用 skill を追加しておくと、agent が動画編集フローを思い出しやすくなります。

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

インストール後は、agent のセッションを再起動するか、skill を再読み込みしてください。この skill は Python、Node.js、ffmpeg をインストールしません。依存関係は上の Quick Start に従って別途インストールします。

### Web UI

```bash
cd npocut
npm run dev
```

Web UI は plan ファイルを Python スクリプトがあるディレクトリへ直接保存します。

| UI モード | 機能 | 出力/保存ファイル |
| --- | --- | --- |
| `Cut` | 手動で IN/OUT を打ち、残す範囲の plan を作成 | `clip_plan.csv` |
| `Submod` | SRT の start/end と本文を直接編集。start を変更すると前の字幕の end、end を変更すると次の字幕の start が同期されます。`Time Nav` で timestamp クリックによる動画ジャンプに切り替え。編集後は自動でバックアップ SRT も保存されます | 読み込んだ `.srt` / `<元ファイル名>.submod-backup.srt` |
| `Shorts` | 字幕行左の `Add` で、単一 short に残す範囲へ追加。export 時は選択した timestamp を行ごとに出力し、自動結合しません | `shorts_plan.csv` |
| `Adv Cut` | 字幕行左の `Del` で削除対象をマークし、反転した keep plan を出力 | `cut_plan_new.csv` |
| `SRT` | `python3 generate_srt.py ...` コマンドを生成 | plan なし |
| `Burn SRT` | `python3 burn_existing_srt.py ...` コマンドを生成 | plan なし |
| `Burn 9:16` | `python3 burn_vertical_srt.py ...` コマンドを生成し、既存 SRT を 9:16 縦動画へ焼き込み | plan なし |

下部コマンド欄のボタン:

| ボタン | 作用 |
| --- | --- |
| `Copy` | 現在のコマンドをコピー |
| `Terminal` | 現在の plan を保存してから、macOS Terminal を現在のディレクトリで開き、コマンドを実行 |

Submod の自動バックアップは Python スクリプトと同じディレクトリに保存され、元の SRT は上書きしません。例: `meeting_01.srt` を読み込むと、編集中に `meeting_01.submod-backup.srt` が作られます。

### Timestamp 形式

以下の形式に対応しています。

```text
75.5
01:15.500
00:01:15.500
00:01:15,500
```

### よく使う流れ

#### YouTube 長尺動画

```bash
python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"
npm run dev
# UI で Cut または Adv Cut を使って plan を export
python3 cut_plan.py "long.mp4" clip_plan.csv -o "long.cut.mp4" --srt "long.srt"
python3 burn_existing_srt.py "long.cut.mp4" "long.cut.srt" -o "long.final.mp4"
```

#### YouTube Short を 1 本作る

Web UI の `Shorts` モードは「一度に 1 本の short を作る」設計です。複数の字幕行で `Add/Keep` を押すと、export 時は選択した timestamp を行ごとに `shorts_plan.csv` へ書き出し、すべて同じ `output` にします。同じ `output` の複数行は short 生成時に順番に結合され、選択していない時間は飛ばされます。

```bash
python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"
npm run dev
# UI で Shorts に切り替え、字幕左の Add を押し、shorts_plan.csv を export
python3 make_shorts.py "long.mp4" shorts_plan.csv \
  --srt "long.srt" \
  --burn-srt \
  --out-dir shorts_out \
  --vertical blur
```

`shorts_plan.csv` の例:

```csv
output,start,end,title
short_01.mp4,00:01:10.000,00:01:58.000,hook
short_01.mp4,00:03:20.000,00:03:42.000,follow up
```

この例では `short_01.mp4` だけが生成され、同じ `output` の複数行が順番に結合されます。

### コマンド一覧

| スクリプト | 役割 | よく使うコマンド |
| --- | --- | --- |
| `generate_srt.py` | faster-whisper でローカル SRT を生成 | `python3 generate_srt.py "long.mp4" -m medium -l zh -o "long.srt"` |
| `generate_srt_openai.py` | OpenAI transcription API で SRT を生成 | `python3 generate_srt_openai.py "long.mp4" -l zh -o "long.srt"` |
| `burn_subs.py` | SRT 生成後に確認し、字幕を焼き込み | `python3 burn_subs.py "long.mp4"` |
| `burn_existing_srt.py` | 既存 SRT を動画へ焼き込み | `python3 burn_existing_srt.py "long.mp4" "long.srt" -o "long.subbed.mp4"` |
| `srt_find.py` | SRT を検索して編集点を探す | `python3 srt_find.py "long.srt" -q "keyword" -c 2` |
| `cut_plan.py` | keep plan に従って切り出し、並べ替え、新 SRT を生成 | `python3 cut_plan.py "long.mp4" clip_plan.csv -o "long.cut.mp4" --srt "long.srt"` |
| `remove_ranges.py` | 削除範囲 plan に従って削除し、残りを結合 | `python3 remove_ranges.py "long.mp4" --plan remove_ranges.txt -o "long.clean.mp4" --srt "long.srt"` |
| `srt_slice.py` | keep plan だけを使って SRT を再生成 | `python3 srt_slice.py "long.srt" clip_plan.csv -o "long.cut.srt"` |
| `make_shorts.py` | 字幕付き縦型 short を 1 本生成 | `python3 make_shorts.py "long.mp4" shorts_plan.csv --srt "long.srt" --burn-srt --vertical blur` |
| `ffprobe_info.py` | 動画の長さ、コーデック、解像度などを表示 | `python3 ffprobe_info.py "long.mp4"` |

### コマンド引数リファレンス

#### `generate_srt.py`

```bash
python3 generate_srt.py VIDEO [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `VIDEO` | 入力動画 | 必須 |
| `-o, --output` | 出力 SRT パス | `<video>.srt` |
| `-m, --model` | faster-whisper モデル。例: `tiny`、`base`、`small`、`medium`、`large-v3` | `small` |
| `-l, --language` | 入力言語。例: `zh`、`ja`、`en` | 自動検出 |

#### `generate_srt_openai.py`

```bash
export OPENAI_API_KEY="your OpenAI API key"
python3 generate_srt_openai.py VIDEO [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `VIDEO` | 入力動画または音声 | 必須 |
| `-o, --output` | 出力 SRT パス | `<video>.srt` |
| `-m, --model` | OpenAI 転写モデル。古い `medium` などのローカルモデル名は互換扱いで無視 | `gpt-4o-transcribe-diarize` |
| `-l, --language` | 入力言語。例: `zh`、`ja`、`en` | 自動検出 |
| `--prompt` | 転写モデルへ渡す文脈プロンプト | なし |
| `--chunk-seconds` | 長尺動画を一時音声に切る秒数 | `300` |
| `--audio-bitrate` | 一時音声のビットレート | `48k` |
| `--timeout` | API リクエストのタイムアウト秒数 | `600` |
| `--keep-temp` | 一時音声チャンクを残す | オフ |

#### `burn_subs.py`

```bash
python3 burn_subs.py INPUT [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `INPUT` | 入力 MP4 | 必須 |
| `-o, --output` | 出力動画 | `<input>.subbed.mp4` |
| `-s, --srt` | SRT パス | `<input>.srt` |
| `-m, --model` | faster-whisper モデル | `small` |
| `-l, --language` | 入力言語 | 自動検出 |
| `--keep-srt` | SRT ファイルを残す | デフォルトで保持 |
| `-y, --yes` | SRT 生成後の手動確認をスキップ | オフ |

#### `burn_existing_srt.py`

```bash
python3 burn_existing_srt.py VIDEO SRT [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `VIDEO` | 入力 MP4 | 必須 |
| `SRT` | 既存字幕ファイル | 必須 |
| `-o, --output` | 出力動画 | `<video>.subbed.mp4` |

#### `cut_plan.py`

```bash
python3 cut_plan.py VIDEO PLAN [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `VIDEO` | 入力動画 | 必須 |
| `PLAN` | `start,end,title` 形式の keep plan | 必須 |
| `-o, --output` | 出力 MP4 | `<video>.cut.mp4` |
| `--srt` | 元 SRT。指定すると retime 済み SRT も生成 | なし |
| `--out-srt` | 出力 SRT パス | `<output>.srt` |
| `--copy` | stream copy で高速化。切り口付近の精度は再エンコードより低い | オフ |
| `--crf` | x264 CRF | `18` |
| `--preset` | x264 preset | `veryfast` |
| `--dry-run` | ffmpeg コマンドだけ表示 | オフ |
| `--keep-temp` | 一時ファイルを残す | オフ |

#### `remove_ranges.py`

```bash
python3 remove_ranges.py VIDEO [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `VIDEO` | 入力動画 | 必須 |
| `-p, --plan` | 削除範囲ファイル。CSV、`start-end`、`start --> end` に対応 | なし |
| `-r, --remove` | 削除範囲を直接指定。複数回指定可 | なし |
| `-o, --output` | 出力 MP4 | `<video>.clean.mp4` |
| `--srt` | 元 SRT。指定すると retime 済み SRT も生成 | なし |
| `--out-srt` | 出力 SRT パス | `<output>.srt` |
| `--write-keep-plan` | 自動計算した keep plan を書き出す | なし |
| `--copy` | stream copy で高速化 | オフ |
| `--crf` | x264 CRF | `18` |
| `--preset` | x264 preset | `veryfast` |
| `--dry-run` | ffmpeg コマンドだけ表示 | オフ |
| `--keep-temp` | 一時ファイルを残す | オフ |

#### `make_shorts.py`

```bash
python3 make_shorts.py VIDEO PLAN [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `VIDEO` | 入力長尺動画 | 必須 |
| `PLAN` | `output,start,end,title` 形式の Shorts plan | 必須 |
| `--out-dir` | 出力ディレクトリ | `shorts_out` |
| `--srt` | 元 SRT。指定すると short 用に retime した SRT も生成 | なし |
| `--burn-srt` | retime 済み SRT を short に焼き込む | オフ |
| `--no-srt-output` | サイドカー SRT を出力しない | オフ |
| `--vertical` | 縦型変換モード: `crop`、`blur`、`pad`、`none` | `crop` |
| `--target` | 出力サイズ | `1080x1920` |
| `--max-seconds` | 長さ警告の閾値。`0` で無効 | `180` |
| `--strict-duration` | `--max-seconds` 超過時に失敗扱い | オフ |
| `--crf` | x264 CRF | `19` |
| `--preset` | x264 preset | `veryfast` |
| `--font-size` | 焼き込み字幕のフォントサイズ | `52` |
| `--margin-v` | 焼き込み字幕の下マージン | `220` |
| `--font-name` | 焼き込み字幕のフォント名 | `Helvetica` |
| `--dry-run` | ffmpeg コマンドだけ表示 | オフ |
| `--keep-temp` | 一時タイムラインを残す | オフ |

縦型モード:

| モード | 説明 |
| --- | --- |
| `crop` | 中央を 9:16 にクロップ。人物が中央にいる動画向き |
| `blur` | 背景をぼかし、元動画を中央配置。横動画を切りたくない場合向き |
| `pad` | 黒帯で余白を埋める |
| `none` | アスペクト比を変更しない |

#### `srt_find.py`

```bash
python3 srt_find.py SRT [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `SRT` | 入力字幕 | 必須 |
| `-q, --query` | 検索テキストまたは正規表現 | なし |
| `-c, --context` | ヒット前後に表示する字幕数 | `1` |
| `--all` | すべての字幕を表示 | `--query` なしの場合はデフォルト |
| `--ignore-case` | 大文字小文字を無視 | オン |

#### `srt_slice.py`

```bash
python3 srt_slice.py SRT PLAN [OPTIONS]
```

| 引数 | 説明 | デフォルト |
| --- | --- | --- |
| `SRT` | 元字幕 | 必須 |
| `PLAN` | `start,end,title` 形式の keep plan | 必須 |
| `-o, --output` | 出力 SRT | `<srt>.slice.srt` |

#### `ffprobe_info.py`

```bash
python3 ffprobe_info.py VIDEO
```

| 引数 | 説明 |
| --- | --- |
| `VIDEO` | 情報を確認する動画 |

### Plan ファイル形式

#### `clip_plan.csv` / `cut_plan_new.csv`

```csv
start,end,title
00:01:10.000,00:02:04.000,opening hook
00:08:30.000,00:09:12.000,best explanation
```

CSV の行順が出力動画の順番になります。

#### `remove_ranges.txt`

```text
00:03:12.000,00:03:28.000,dead air
00:10:00.000-00:10:20.000
00:24:15.000 --> 00:24:40.000 long pause
```

#### `shorts_plan.csv`

```csv
output,start,end,title
short_01.mp4,00:01:10.000,00:01:58.000,hook
short_01.mp4,00:03:20.000,00:03:42.000,follow up
```

同じ `output` の複数行は、1 本の short として結合されます。

### サンプルファイル

- `examples/clip_plan.csv`
- `examples/remove_ranges.txt`
- `examples/shorts_plan.csv`

---

## 中文版

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
