---
name: "npocut-video-workflows"
description: "Use for npocut video editing tasks: Web UI usage, generating SRT files, burning subtitles, cutting by timestamp plans, removing ranges, making one Short, merging two independent animation/video files, retiming SRTs, searching SRT cues, vertical 9:16 subtitle burns, and choosing/running the project's Python video tools without committing local media artifacts."
---

# npocut Video Workflows

Use this skill when the task mentions npocut, SRT generation, subtitle burning,
timestamp cuts, Submod, Shorts, cut plans, merging animations, or the ytsubone
video scripts.

## Project Paths

- Main tool directory: `/Users/zhangdapeng/Desktop/ytsubone/npocut`
- Legacy parent directory: `/Users/zhangdapeng/Desktop/ytsubone`
- Prefer the main tool directory unless the user explicitly refers to legacy
  root scripts or media files stored in the parent directory.

Start commands from the main tool directory:

```bash
cd /Users/zhangdapeng/Desktop/ytsubone/npocut
```

Quote filenames because local video files often contain spaces, Chinese, or
Japanese text. Use explicit `-o` output paths. Do not overwrite source video or
source SRT files unless the user asks for that exact overwrite.

## Intermediate Files Are Important

npocut is intentionally plan-file driven. The intermediate CSV/TXT files are
not throwaway details; they are the edit decision list and make the workflow
reviewable, repeatable, and recoverable.

- `clip_plan.csv`: keep-plan from the Cut tab. Rows are kept and exported in
  file order. Reorder rows to reorder the final video.
- `cut_plan_new.csv`: keep-plan exported from Adv Cut after marking subtitle
  rows with `Del`. This is the inverse of marked deletion ranges.
- `cut_plan.csv`: common manual keep-plan filename. Use it when the user asks
  for a plan based on SRT content.
- `remove_ranges.txt`: delete-plan for `remove_ranges.py`; the script computes
  the remaining keep ranges.
- `keep_plan.csv`: optional output from `remove_ranges.py --write-keep-plan`;
  useful for audit and for rerunning the same keep timeline through `cut_plan.py`.
- `shorts_plan.csv`: Shorts plan. Use `output,start,end,title`; rows with the
  same `output` are concatenated into one Short in row order.
- `*.cut.srt`, `*.clean.srt`, `*.submod-backup.srt`: retimed or backup SRTs.
  Keep them next to the matching output video so later burn-in or review uses
  the correct timeline.

Generated media, generated SRTs, local plans, and temp folders are normally
ignored by git. Do not `git add -A` for video projects. Stage explicit source
or documentation files only unless the user explicitly asks to version an
artifact.

Plan formats:

```csv
start,end,title
00:01:10.000,00:02:04.000,opening hook
00:08:30.000,00:09:12.000,best explanation
```

```text
00:03:12.000,00:03:28.000,dead air
00:10:00.000-00:10:20.000
00:24:15.000 --> 00:24:40.000 off-topic aside
```

```csv
output,start,end,title
short_01.mp4,00:01:10.000,00:01:58.000,hook
short_01.mp4,00:03:20.000,00:03:42.000,follow up
```

Supported timestamps include seconds, `MM:SS.mmm`, `HH:MM:SS.mmm`, and SRT
comma milliseconds such as `00:01:15,500`.

## Common Workflows

Run the Web UI:

```bash
npm run dev
```

Generate an SRT with local faster-whisper:

```bash
python3 generate_srt.py "input.mp4" -o "input.srt" -m small -l ja
```

If system `python3` is too old for `str | None` type hints, use the Conda base
Python:

```bash
/opt/homebrew/Caskroom/miniconda/base/bin/python generate_srt.py "input.mp4" -m large-v3 -o "input.srt"
```

Generate an SRT with OpenAI transcription:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" python3 generate_srt_openai.py "input.mp4" -o "input.srt" -l zh
```

Burn an existing SRT into a normal horizontal video:

```bash
python3 burn_existing_srt.py "input.mp4" "input.srt" -o "input.subbed.mp4"
```

Burn an existing SRT into a vertical 9:16 video:

```bash
python3 burn_vertical_srt.py "input.mp4" "input.srt" -o "input.vertical.subbed.mp4" --vertical crop --target 1080x1920
```

Generate SRT, pause for manual review, then burn:

```bash
python3 burn_subs.py "input.mp4" -o "input.subbed.mp4" -m small -l ja
```

Cut/reorder keep ranges from a plan and retime SRT:

```bash
python3 cut_plan.py "input.mp4" cut_plan.csv -o "input.cut.mp4" --srt "input.srt"
```

Remove unwanted ranges and stitch the remaining timeline:

```bash
python3 remove_ranges.py "input.mp4" -p remove_ranges.txt -o "input.clean.mp4" --srt "input.srt" --write-keep-plan keep_plan.csv
```

Make one Short from `shorts_plan.csv`:

```bash
python3 make_shorts.py "input.mp4" shorts_plan.csv --out-dir shorts_out --srt "input.srt" --burn-srt --vertical blur
```

Merge two independent animation/video files into one longer animation:

```bash
python3 merge_animations.py "first.mp4" "second.mp4" -o "combined.mp4"
python3 merge_animations.py "first.gif" "second.gif" -o "combined.gif" --fps 24
```

Search/list SRT cues for cut points:

```bash
python3 srt_find.py "input.srt" -q "keyword" -c 2
python3 srt_find.py "input.srt" --all
```

Retiming only: create an SRT from the same cut plan without cutting video:

```bash
python3 srt_slice.py "input.srt" cut_plan.csv -o "input.cut.srt"
```

Inspect media properties:

```bash
python3 ffprobe_info.py "input.mp4"
```

## Web UI Notes

- `Cut`: manual IN/OUT keep ranges; exports `clip_plan.csv`.
- `Submod`: edit SRT timestamps/text. Changing a cue start syncs the previous
  cue end; changing a cue end syncs the next cue start. Edits auto-save
  `<source>.submod-backup.srt` without overwriting the original SRT.
- `Shorts`: click `Add` on subtitle rows to keep them for one Short; exports
  `shorts_plan.csv`.
- `Adv Cut`: click `Del` on subtitle rows to mark deletion ranges; exports
  inverse keep ranges to `cut_plan_new.csv`.
- `SRT`, `Burn SRT`, `Burn 9:16`: generate runnable commands.
- Bottom `Terminal` button saves the current plan, opens macOS Terminal in the
  script directory, and runs the command.

## Tool Parameters

### `generate_srt.py`

`python3 generate_srt.py VIDEO [OPTIONS]`

- `VIDEO`: source video file.
- `-o, --output`: output SRT path; default `<video>.srt`.
- `-m, --model`: faster-whisper model, e.g. `tiny`, `base`, `small`, `medium`,
  `large-v3`; default `small`.
- `-l, --language`: force input language such as `zh`, `ja`, `en`; default is
  auto-detect.

### `generate_srt_openai.py`

`python3 generate_srt_openai.py VIDEO [OPTIONS]`

- `VIDEO`: source video/audio file.
- `-o, --output`: output SRT path; default `<video>.srt`.
- `-m, --model`: OpenAI transcription model; default
  `gpt-4o-transcribe-diarize`. Old local model names like `medium` are accepted
  for compatibility.
- `-l, --language`: input language code such as `zh`, `ja`, `en`.
- `--prompt`: optional transcription context prompt.
- `--chunk-seconds`: audio chunk length in seconds; default `300`.
- `--audio-bitrate`: temporary audio bitrate; default `48k`.
- `--timeout`: API request timeout in seconds; default `600`.
- `--keep-temp`: keep temporary audio chunks.

### `burn_subs.py`

`python3 burn_subs.py INPUT [OPTIONS]`

- `INPUT`: source MP4 file.
- `-o, --output`: output MP4; default `<input>.subbed.mp4`.
- `-s, --srt`: SRT path; default `<input>.srt`.
- `-m, --model`: faster-whisper model; default `small`.
- `-l, --language`: force language code; default auto-detect.
- `--keep-srt`: keep generated SRT; current behavior keeps it by default.
- `-y, --yes`: skip the manual confirmation step after SRT generation.

### `burn_existing_srt.py`

`python3 burn_existing_srt.py VIDEO SRT [OPTIONS]`

- `VIDEO`: source MP4 file.
- `SRT`: existing SRT subtitle file.
- `-o, --output`: output MP4; default `<video>.subbed.mp4`.

### `burn_vertical_srt.py`

`python3 burn_vertical_srt.py VIDEO SRT [OPTIONS]`

- `VIDEO`: source video.
- `SRT`: existing SRT subtitle file.
- `-o, --output`: output MP4; default `<video>.vertical.subbed.mp4`.
- `--vertical`: 9:16 conversion mode: `crop`, `blur`, or `pad`.
- `--target`: output dimensions, e.g. `1080x1920`.
- `--crf`: x264 quality value; lower is larger/better; default `19`.
- `--preset`: x264 preset; default `veryfast`.
- `--font-size`: burned subtitle font size.
- `--margin-v`: burned subtitle bottom margin.
- `--subtitle-line-chars`: approximate characters per subtitle line.
- `--font-name`: burned subtitle font; default `Helvetica`.
- `--dry-run`: print ffmpeg command only.

### `cut_plan.py`

`python3 cut_plan.py VIDEO PLAN [OPTIONS]`

- `VIDEO`: source video.
- `PLAN`: keep-plan CSV/TXT with `start,end` rows.
- `-o, --output`: output MP4; default `<video>.cut.mp4`.
- `--srt`: source SRT to retime alongside the video.
- `--out-srt`: retimed SRT path; default `<output>.srt` when `--srt` is set.
- `--copy`: use stream copy for speed; less frame-accurate around cuts.
- `--crf`: x264 CRF when re-encoding; default `18`.
- `--preset`: x264 preset when re-encoding; default `veryfast`.
- `--dry-run`: print ffmpeg commands only.
- `--keep-temp`: keep temporary segment files.

### `remove_ranges.py`

`python3 remove_ranges.py VIDEO [OPTIONS]`

- `VIDEO`: source video.
- `-p, --plan`: text/CSV file with ranges to remove.
- `-r, --remove`: one range to remove; repeatable, e.g.
  `-r 00:01:00-00:01:20`.
- `-o, --output`: output MP4; default `<video>.clean.mp4`.
- `--srt`: source SRT to retime.
- `--out-srt`: retimed SRT path; default `<output>.srt` when `--srt` is set.
- `--write-keep-plan`: write computed keep ranges as CSV.
- `--copy`: use stream copy for speed; less frame-accurate around cuts.
- `--crf`: x264 CRF when re-encoding; default `18`.
- `--preset`: x264 preset when re-encoding; default `veryfast`.
- `--dry-run`: print ffmpeg commands only.
- `--keep-temp`: keep temporary segment files.

### `make_shorts.py`

`python3 make_shorts.py VIDEO PLAN [OPTIONS]`

- `VIDEO`: source long video.
- `PLAN`: `output,start,end,title` CSV plan.
- `--out-dir`: directory for generated shorts.
- `--srt`: source SRT to retime per short.
- `--burn-srt`: burn each retimed SRT into the short; requires `--srt`.
- `--no-srt-output`: do not write sidecar SRT files.
- `--vertical`: conversion mode: `crop`, `blur`, `pad`, or `none`.
- `--target`: output dimensions for vertical modes, e.g. `1080x1920`.
- `--max-seconds`: warn when a short exceeds this duration; set `0` to disable.
- `--strict-duration`: fail instead of warning when `--max-seconds` is exceeded.
- `--crf`: x264 CRF for final shorts; default `19`.
- `--preset`: x264 preset; default `veryfast`.
- `--font-size`: burned subtitle font size.
- `--margin-v`: burned subtitle bottom margin.
- `--subtitle-line-chars`: approximate characters per burned subtitle line.
- `--font-name`: burned subtitle font; default `Helvetica`.
- `--dry-run`: print ffmpeg commands only.
- `--keep-temp`: keep temporary timeline files.

### `merge_animations.py`

`python3 merge_animations.py FIRST SECOND [OPTIONS]`

- `FIRST`: first independent animation/video file.
- `SECOND`: second independent animation/video file appended after the first.
- `-o, --output`: output file; default `<first>.merged.mp4`.
- `--target`: output dimensions such as `1920x1080`; default uses the first
  input's dimensions.
- `--fps`: output frame rate; default uses the first input's frame rate.
- `--fit`: how to fit mismatched aspect ratios: `contain`, `crop`, or
  `stretch`; default `contain`.
- `--background`: pad color for `--fit contain`; default `black`.
- `--crf`: x264 CRF for MP4/MOV output; default `18`.
- `--preset`: x264 preset for MP4/MOV output; default `veryfast`.
- `--gif-loop`: GIF loop count; `0` means loop forever.
- `--dry-run`: print ffmpeg command only.

### `srt_find.py`

`python3 srt_find.py SRT [OPTIONS]`

- `SRT`: source SRT.
- `-q, --query`: text or regex to search.
- `-c, --context`: neighboring cues to show around matches.
- `--all`: list all cues; default when `--query` is omitted.
- `--ignore-case`: case-insensitive search; default behavior.

### `srt_slice.py`

`python3 srt_slice.py SRT PLAN [OPTIONS]`

- `SRT`: source SRT.
- `PLAN`: keep-plan CSV/TXT with `start,end` rows.
- `-o, --output`: output SRT; default `<source>.cut.srt`.

### `ffprobe_info.py`

`python3 ffprobe_info.py VIDEO`

- `VIDEO`: video file to inspect.

### `make_srt_only.py`

Legacy local SRT-only wrapper. Prefer `generate_srt.py`.

- `VIDEO`: source video.
- `-o, --output`: output SRT; default `<video>.srt`.
- `-m, --model`: faster-whisper model.
- `-l, --language`: force language code.

## Operating Rules

- Check that input files exist before launching long ffmpeg or Whisper jobs.
- For uncertain edit plans, inspect SRT cues with `srt_find.py`, write a plan
  file, then run `cut_plan.py --dry-run` or `remove_ranges.py --dry-run`.
- Prefer `ffmpeg-full` on macOS when subtitle rendering needs libass; scripts
  already prefer `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` when available.
- If a user asks to commit/push, stage explicit source/doc files. Do not stage
  ignored generated media, local SRTs, `shorts_out/`, or local plan files unless
  explicitly requested.
- When generating a new cut based on subtitles, always produce or update the
  relevant plan file first, then run the video/SRT command from that plan.
